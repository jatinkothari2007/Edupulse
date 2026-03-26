"""
EduPulse Teacher Routes — attendance, assignments, marks, notes, classes.
"""
from flask import Blueprint, jsonify, request, g
from firebase_config import db
from firebase_admin import firestore
from routes.auth_middleware import require_role
from utils.id_generator import assignment_id
from utils.notifier import notify_assignment_created, notify_message_received
from risk_engine import recalculate_and_save
import datetime

teacher_bp = Blueprint('teacher', __name__, url_prefix='/api/teacher')


# ── Classes ──────────────────────────────────────────────────────────────────

@teacher_bp.route('/classes', methods=['GET'])
@require_role('subject_teacher')
def get_classes():
    uid = g.uid
    subject = g.user_data.get('subject', '')
    # Support both old assignedClasses and new classId/classIds from seed
    class_ids = []
    assigned = g.user_data.get('assignedClasses', [])
    if assigned:
        class_ids = [e.get('classId', '') for e in assigned if e.get('classId')]
    else:
        # Seed stores classId (single) or classIds (list)
        cids = g.user_data.get('classIds', [])
        if not cids:
            cid = g.user_data.get('classId', '')
            if cid:
                cids = [cid]
        class_ids = cids

    classes = []
    for cid in class_ids:
        doc = db.collection('classes').document(cid).get()
        if doc.exists:
            c = doc.to_dict()
            c['id'] = cid
            c['mySubject'] = subject
            classes.append(c)
    return jsonify({'classes': classes})


@teacher_bp.route('/classes/<cid>/students', methods=['GET'])
@require_role('subject_teacher')
def class_students(cid):
    cls_doc = db.collection('classes').document(cid).get()
    if not cls_doc.exists:
        return jsonify({'error': 'Class not found'}), 404
    student_uids = cls_doc.to_dict().get('students', [])
    students = []
    for uid in student_uids:
        doc = db.collection('users').document(uid).get()
        if doc.exists:
            u = doc.to_dict()
            students.append({'uid': uid, 'name': u.get('name'), 'customId': u.get('customId')})
    return jsonify({'students': students})


# ── Attendance ───────────────────────────────────────────────────────────────

@teacher_bp.route('/attendance-summary', methods=['GET'])
@require_role('subject_teacher')
def attendance_summary():
    uid = g.uid
    subject = g.user_data.get('subject', '')
    class_ids = g.user_data.get('classIds', [])
    if not class_ids:
        cid = g.user_data.get('classId', '')
        if cid:
            class_ids = [cid]

    # Attendance for this teacher's subject
    # NOTE: mark_attendance stores as 'teacherUid'; older seed data may use 'teacherId'
    records = []
    seen_ids = set()
    for field in ('teacherUid', 'teacherId'):
        try:
            for d in db.collection('attendance').where(field, '==', uid).stream():
                if d.id not in seen_ids:
                    records.append(d.to_dict())
                    seen_ids.add(d.id)
        except Exception:
            pass

    # Group by date to build trend
    by_date = {}
    for r in records:
        date = r.get('date', '')
        if date not in by_date:
            by_date[date] = {'total': 0, 'present': 0}
        by_date[date]['total'] += 1
        if r.get('status') == 'present':
            by_date[date]['present'] += 1

    trend = sorted([
        {'date': d, 'pct': round(v['present']/v['total']*100, 1) if v['total'] else 0}
        for d, v in by_date.items()
    ], key=lambda x: x['date'])[-14:]  # last 14 days

    avg = round(sum(t['pct'] for t in trend) / len(trend), 1) if trend else 0

    # Per-class attendance percentage
    class_att = {}
    for r in records:
        cid = r.get('classId', '')
        if cid not in class_att:
            class_att[cid] = {'total': 0, 'present': 0}
        class_att[cid]['total'] += 1
        if r.get('status') == 'present':
            class_att[cid]['present'] += 1

    # Student count
    student_count = 0
    for cid in class_ids:
        doc = db.collection('classes').document(cid).get()
        if doc.exists:
            student_count += len(doc.to_dict().get('students', []))

    # Assignment count
    asgn_docs = db.collection('assignments').where('teacherId', '==', uid).stream()
    asgn_count = sum(1 for _ in asgn_docs)

    return jsonify({'trend': trend, 'avg': avg,
                    'studentCount': student_count, 'assignmentCount': asgn_count,
                    'classAttendance': class_att})


@teacher_bp.route('/attendance', methods=['GET'])
@require_role('subject_teacher')
def get_attendance_sessions():
    """Returns all attendance records marked by this teacher."""
    uid = g.uid
    docs = db.collection('attendance').where('teacherId', '==', uid).stream()
    records = [{**d.to_dict(), 'id': d.id} for d in docs]
    return jsonify({'records': records})


@teacher_bp.route('/attendance', methods=['POST'])
@require_role('subject_teacher')
def mark_attendance():
    data = request.json or {}
    class_id_val = data.get('classId', '')
    subject_id   = data.get('subjectId', '')
    date_str     = data.get('date', datetime.date.today().isoformat())
    records      = data.get('records', [])  # [{studentUid, status}]

    today = datetime.date.today().isoformat()
    if date_str > today:
        return jsonify({'error': 'Cannot mark attendance for future dates'}), 400

    for rec in records:
        student_uid = rec.get('studentUid', '')
        status      = rec.get('status', 'absent')
        doc_id      = f"{class_id_val}_{subject_id}_{date_str}_{student_uid}"
        db.collection('attendance').document(doc_id).set({
            'studentId': student_uid,
            'classId'  : class_id_val,
            'subjectId': subject_id,
            'teacherUid': g.uid,
            'date'     : date_str,
            'status'   : status,
            'markedAt' : firestore.SERVER_TIMESTAMP,
        })
        # Recalculate risk
        try:
            recalculate_and_save(student_uid)
        except Exception:
            pass

    return jsonify({'success': True, 'marked': len(records)})


@teacher_bp.route('/attendance/<class_id_val>/<subject_id>/<date_str>', methods=['GET'])
@require_role('subject_teacher')
def get_day_attendance(class_id_val, subject_id, date_str):
    docs = db.collection('attendance') \
             .where('classId', '==', class_id_val) \
             .where('subjectId', '==', subject_id) \
             .where('date', '==', date_str).stream()
    records = [{**d.to_dict(), 'id': d.id} for d in docs]
    return jsonify({'records': records})


# ── Assignments ──────────────────────────────────────────────────────────────

@teacher_bp.route('/assignments', methods=['GET'])
@require_role('subject_teacher')
def list_assignments():
    docs = db.collection('assignments').where('teacherUid', '==', g.uid).stream()
    assignments = [{**d.to_dict(), 'id': d.id} for d in docs]
    return jsonify({'assignments': assignments})


@teacher_bp.route('/assignments', methods=['POST'])
@require_role('subject_teacher')
def create_assignment():
    data = request.json or {}
    required = ['title', 'classId', 'subjectId', 'dueDate']
    for f_name in required:
        if not data.get(f_name):
            return jsonify({'error': f'Missing: {f_name}'}), 400

    aid = assignment_id()
    doc = {
        'assignmentId': aid,
        'title'       : data['title'],
        'description' : data.get('description', ''),
        'classId'     : data['classId'],
        'subjectId'   : data['subjectId'],
        'teacherUid'  : g.uid,
        'teacherName' : g.user_data.get('name', ''),
        'dueDate'     : data['dueDate'],
        'maxMarks'    : data.get('maxMarks', 100),
        'createdAt'   : firestore.SERVER_TIMESTAMP,
    }
    db.collection('assignments').document(aid).set(doc)

    # Notify all students in the class
    cls_doc = db.collection('classes').document(data['classId']).get()
    if cls_doc.exists:
        students = cls_doc.to_dict().get('students', [])
        for s_uid in students:
            notify_assignment_created(s_uid, data['title'], data['dueDate'])

    return jsonify({'success': True, 'assignmentId': aid}), 201


@teacher_bp.route('/assignments/<aid>/submissions', methods=['GET'])
@require_role('subject_teacher')
def get_submissions(aid):
    docs = db.collection('submissions').where('assignmentId', '==', aid).stream()
    submissions = [{**d.to_dict(), 'id': d.id} for d in docs]
    return jsonify({'submissions': submissions})


@teacher_bp.route('/assignments/<aid>/submissions/<sub_id>/grade', methods=['POST'])
@require_role('subject_teacher')
def grade_submission(aid, sub_id):
    data    = request.json or {}
    marks   = data.get('marks')
    feedback = data.get('feedback', '')
    if marks is None:
        return jsonify({'error': 'marks required'}), 400

    sub_doc = db.collection('submissions').document(sub_id).get()
    if not sub_doc.exists:
        return jsonify({'error': 'Submission not found'}), 404
    sub = sub_doc.to_dict()

    db.collection('submissions').document(sub_id).update({
        'marks'   : marks,
        'feedback': feedback,
        'gradedAt': firestore.SERVER_TIMESTAMP,
        'status'  : 'graded',
    })

    # Save mark record for risk engine
    asgn_doc = db.collection('assignments').document(aid).get()
    if asgn_doc.exists:
        asgn = asgn_doc.to_dict()
        db.collection('marks').add({
            'studentId' : sub.get('studentId'),
            'assignmentId': aid,
            'subjectId' : asgn.get('subjectId', ''),
            'classId'   : asgn.get('classId', ''),
            'marks'     : marks,
            'maxMarks'  : asgn.get('maxMarks', 100),
            'component' : 'assignment',
            'teacherUid': g.uid,
            'gradedAt'  : firestore.SERVER_TIMESTAMP,
        })

    # Recalculate risk
    try:
        recalculate_and_save(sub.get('studentId', ''))
    except Exception:
        pass

    return jsonify({'success': True})


# ── Marks ─────────────────────────────────────────────────────────────────────

@teacher_bp.route('/marks', methods=['GET'])
@require_role('subject_teacher')
def list_marks():
    docs = db.collection('marks').where('teacherUid', '==', g.uid).stream()
    marks = [{**d.to_dict(), 'id': d.id} for d in docs]
    return jsonify({'marks': marks})


@teacher_bp.route('/marks', methods=['POST'])
@require_role('subject_teacher')
def save_mark():
    data = request.json or {}
    required = ['studentId', 'subjectId', 'marks', 'maxMarks', 'component']
    for f_name in required:
        if data.get(f_name) is None:
            return jsonify({'error': f'Missing: {f_name}'}), 400

    doc_id = f"{data['studentId']}_{data['subjectId']}_{data['component']}"
    db.collection('marks').document(doc_id).set({
        'studentId' : data['studentId'],
        'subjectId' : data['subjectId'],
        'classId'   : data.get('classId', ''),
        'marks'     : float(data['marks']),
        'maxMarks'  : float(data['maxMarks']),
        'component' : data['component'],
        'teacherUid': g.uid,
        'updatedAt' : firestore.SERVER_TIMESTAMP,
    }, merge=True)

    try:
        recalculate_and_save(data['studentId'])
    except Exception:
        pass

    return jsonify({'success': True})


# ── Notes ─────────────────────────────────────────────────────────────────────

@teacher_bp.route('/notes', methods=['GET'])
@require_role('subject_teacher')
def list_notes():
    docs = db.collection('notes').where('teacherUid', '==', g.uid).stream()
    notes = [{**d.to_dict(), 'id': d.id} for d in docs]
    return jsonify({'notes': notes})


@teacher_bp.route('/notes', methods=['POST'])
@require_role('subject_teacher')
def create_note():
    data = request.json or {}
    required = ['title', 'classId', 'subjectId']
    for f_name in required:
        if not data.get(f_name):
            return jsonify({'error': f'Missing: {f_name}'}), 400

    ref = db.collection('notes').add({
        'title'      : data['title'],
        'description': data.get('description', ''),
        'classId'    : data['classId'],
        'subjectId'  : data['subjectId'],
        'teacherUid' : g.uid,
        'teacherName': g.user_data.get('name', ''),
        'fileUrl'    : data.get('fileUrl', ''),
        'fileName'   : data.get('fileName', ''),
        'date'       : data.get('date', datetime.date.today().isoformat()),
        'createdAt'  : firestore.SERVER_TIMESTAMP,
    })
    return jsonify({'success': True, 'noteId': ref[1].id}), 201


@teacher_bp.route('/notes/<note_id>', methods=['DELETE'])
@require_role('subject_teacher')
def delete_note(note_id):
    doc = db.collection('notes').document(note_id).get()
    if not doc.exists or doc.to_dict().get('teacherUid') != g.uid:
        return jsonify({'error': 'Not found or not authorised'}), 404
    db.collection('notes').document(note_id).delete()
    return jsonify({'success': True})
