"""
EduPulse Counsellor Routes — students, sessions, case management, video calls.
"""
from flask import Blueprint, jsonify, request, g
from firebase_config import db
from firebase_admin import firestore
from routes.auth_middleware import require_role
from utils.id_generator import session_id
from utils.notifier import notify_video_call_scheduled, notify_case_closed
import datetime

counsellor_bp = Blueprint('counsellor', __name__, url_prefix='/api/counsellor')


# ── Assigned Students ─────────────────────────────────────────────────────

@counsellor_bp.route('/students', methods=['GET'])
@require_role('counsellor')
def assigned_students():
    student_uids = g.user_data.get('assignedStudents', [])

    # If no specific assignments, show ALL students
    if not student_uids:
        all_docs = db.collection('users').where('role', '==', 'student').stream()
        student_uids = [d.id for d in all_docs]

    students = []
    for uid in student_uids:
        u_doc = db.collection('users').document(uid).get()
        r_doc = db.collection('riskScores').document(uid).get()
        # Get last mood — avoid order_by to prevent index issues
        try:
            mood_docs = list(db.collection('moodLogs')
                             .where('studentId', '==', uid)
                             .limit(5).stream())
            last_mood = mood_docs[-1].to_dict().get('mood') if mood_docs else None
        except Exception:
            last_mood = None

        if u_doc.exists:
            u = u_doc.to_dict()
            r = r_doc.to_dict() if r_doc.exists else {}
            students.append({
                'uid'           : uid,
                'name'          : u.get('name', ''),
                'customId'      : u.get('customId', ''),
                'email'         : u.get('email', ''),
                'classId'       : u.get('classId', ''),
                'caseStatus'    : u.get('caseStatus', 'active'),
                'counsellorName': u.get('counsellorName', ''),
                'score'         : r.get('riskScore', r.get('score', 0)),
                'level'         : r.get('riskLevel', r.get('level', 'LOW')),
                'breakdown'     : r.get('breakdown', {}),
                'lastMood'      : last_mood,
            })
    return jsonify({'students': students})


@counsellor_bp.route('/students/<student_uid>/detail', methods=['GET'])
@require_role('counsellor')
def student_detail(student_uid):
    # Removed strict assignedStudents check — counsellor can view any of their students
    u_doc = db.collection('users').document(student_uid).get()
    r_doc = db.collection('riskScores').document(student_uid).get()
    if not u_doc.exists:
        return jsonify({'error': 'Student not found'}), 404

    u = u_doc.to_dict()
    r = r_doc.to_dict() if r_doc.exists else {}

    # Risk score field normalization
    r_normalized = {
        **r,
        'score': r.get('riskScore', r.get('score', 0)),
        'level': r.get('riskLevel', r.get('level', 'LOW')),
    }

    # Mood history — no order_by to avoid index issues
    try:
        mood_docs = list(db.collection('moodLogs')
                         .where('studentId', '==', student_uid)
                         .limit(30).stream())
        moods = sorted([{**d.to_dict(), 'id': d.id} for d in mood_docs],
                       key=lambda x: x.get('date', ''), reverse=True)
    except Exception:
        moods = []

    # Quiz results
    try:
        quiz_docs = db.collection('quizResults').where('studentId', '==', student_uid).stream()
        quizzes = [{**d.to_dict(), 'id': d.id} for d in quiz_docs]
    except Exception:
        quizzes = []

    # Session notes — no order_by
    try:
        notes_docs = list(db.collection('sessionNotes')
                          .where('studentId', '==', student_uid)
                          .where('counsellorUid', '==', g.uid)
                          .limit(20).stream())
        session_notes = sorted([{**d.to_dict(), 'id': d.id} for d in notes_docs],
                               key=lambda x: str(x.get('createdAt', '')), reverse=True)
    except Exception:
        session_notes = []

    return jsonify({
        'student'     : {**u, 'uid': student_uid},
        'risk'        : r_normalized,
        'moodHistory' : moods,
        'quizResults' : quizzes,
        'sessionNotes': session_notes,
    })


# ── Video Call Sessions ───────────────────────────────────────────────────

@counsellor_bp.route('/sessions', methods=['GET'])
@require_role('counsellor')
def list_sessions():
    sessions = []
    # Try both field names (seed uses 'counsellorId', new sessions use 'counsellorUid')
    seen_ids = set()
    for field in ('counsellorUid', 'counsellorId'):
        try:
            docs = db.collection('sessions').where(field, '==', g.uid).stream()
            for d in docs:
                if d.id not in seen_ids:
                    sd = {**d.to_dict(), 'id': d.id}
                    # Normalise sessionId so frontend always has it
                    if not sd.get('sessionId'):
                        sd['sessionId'] = d.id
                    # Enrich with student name if missing — check both uid/id fields
                    if not sd.get('studentName'):
                        s_uid = sd.get('studentUid') or sd.get('studentId', '')
                        if s_uid:
                            s_doc = db.collection('users').document(s_uid).get()
                            if s_doc.exists:
                                sd['studentName'] = s_doc.to_dict().get('name', '')
                    sessions.append(sd)
                    seen_ids.add(d.id)
        except Exception:
            pass
    # Sort in Python (avoid Firestore composite index requirement)
    sessions.sort(key=lambda s: s.get('scheduledAt', ''), reverse=True)
    return jsonify({'sessions': sessions})


@counsellor_bp.route('/sessions', methods=['POST'])
@require_role('counsellor')
def schedule_session():
    data = request.json or {}
    student_uid  = data.get('studentUid', '')
    scheduled_at = data.get('scheduledAt', '')
    if not student_uid or not scheduled_at:
        return jsonify({'error': 'studentUid and scheduledAt required'}), 400

    # Fetch student info
    student_doc = db.collection('users').document(student_uid).get()
    if not student_doc.exists:
        return jsonify({'error': 'Student not found'}), 404
    student_data = student_doc.to_dict()

    sid = session_id()
    db.collection('sessions').document(sid).set({
        'sessionId'     : sid,
        'studentUid'    : student_uid,
        'studentId'     : student_uid,
        'studentName'   : student_data.get('name', ''),
        'counsellorUid' : g.uid,
        'counsellorId'  : g.uid,
        'counsellorName': g.user_data.get('name', ''),
        'scheduledAt'   : scheduled_at,
        'status'        : 'scheduled',
        'duration'      : 0,
        'notes'         : '',
        'createdAt'     : firestore.SERVER_TIMESTAMP,
    })

    notify_video_call_scheduled(student_uid, student_data.get('name', ''), scheduled_at)
    return jsonify({'success': True, 'sessionId': sid}), 201


@counsellor_bp.route('/sessions/<sid>/notes', methods=['POST'])
@require_role('counsellor')
def save_session_notes(sid):
    data = request.json or {}
    notes = data.get('notes', '')
    student_uid = data.get('studentUid', '')

    db.collection('sessionNotes').add({
        'sessionId'    : sid,
        'studentId'    : student_uid,
        'counsellorUid': g.uid,
        'notes'        : notes,
        'createdAt'    : firestore.SERVER_TIMESTAMP,
    })
    db.collection('sessions').document(sid).update({
        'notes' : notes,
        'status': 'completed',
    })
    return jsonify({'success': True})


# ── Case Management ───────────────────────────────────────────────────────

@counsellor_bp.route('/cases/<student_uid>/close', methods=['POST'])
@require_role('counsellor')
def close_case(student_uid):
    data    = request.json or {}
    closing = data.get('closingMessage', '')
    if not closing:
        return jsonify({'error': 'closingMessage required'}), 400

    u_doc = db.collection('users').document(student_uid).get()
    if not u_doc.exists:
        return jsonify({'error': 'Student not found'}), 404
    u = u_doc.to_dict()

    db.collection('users').document(student_uid).update({
        'caseStatus'    : 'closed',
        'caseClosedAt'  : firestore.SERVER_TIMESTAMP,
        'closingMessage': closing,
    })

    db.collection('caseClosure').add({
        'studentId'     : student_uid,
        'studentName'   : u.get('name', ''),
        'counsellorUid' : g.uid,
        'closingMessage': closing,
        'closedAt'      : firestore.SERVER_TIMESTAMP,
    })

    fa_uid = u.get('faUid', '')
    if fa_uid:
        notify_case_closed(fa_uid, u.get('name', ''), closing)

    return jsonify({'success': True})


@counsellor_bp.route('/cases/<student_uid>/reopen', methods=['POST'])
@require_role('counsellor')
def reopen_case(student_uid):
    db.collection('users').document(student_uid).update({'caseStatus': 'active'})
    return jsonify({'success': True})
