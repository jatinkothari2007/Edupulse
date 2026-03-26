"""
EduPulse Faculty Advisor Routes — classes, Pulse Quiz, risk scores, counsellor assignment.
"""
from flask import Blueprint, jsonify, request, g
from firebase_config import db
from firebase_admin import firestore
from routes.auth_middleware import require_role
from utils.id_generator import class_id, quiz_id
from utils.notifier import notify_quiz_scheduled, notify_risk_alert
from utils.ai_messenger import generate_quiz_questions
import datetime

faculty_bp = Blueprint('faculty', __name__, url_prefix='/api/faculty')


# ── Classes ──────────────────────────────────────────────────────────────────

@faculty_bp.route('/classes', methods=['GET'])
@require_role('faculty_advisor')
def get_classes():
    # Try both field names (seed uses 'facultyAdvisorId', FA-created classes use 'faUid')
    classes = []
    seen_ids = set()
    for field in ('faUid', 'facultyAdvisorId', 'advisorId'):
        docs = db.collection('classes').where(field, '==', g.uid).stream()
        for d in docs:
            if d.id not in seen_ids:
                c = d.to_dict()
                c['id'] = d.id
                classes.append(c)
                seen_ids.add(d.id)
    return jsonify({'classes': classes})


@faculty_bp.route('/classes', methods=['POST'])
@require_role('faculty_advisor')
def create_class():
    data = request.json or {}
    name = data.get('name', '')
    if not name:
        return jsonify({'error': 'Class name required'}), 400

    cid = class_id()
    fa_doc = db.collection('users').document(g.uid).get()
    fa_data = fa_doc.to_dict() if fa_doc.exists else {}

    class_doc = {
        'classId'   : cid,
        'name'      : name,
        'faUid'     : g.uid,
        'faName'    : fa_data.get('name', ''),
        'faCustomId': fa_data.get('customId', ''),
        'students'  : [],
        'teachers'  : [],
        'subjects'  : data.get('subjects', []),
        'schedule'  : {},
        'createdAt' : firestore.SERVER_TIMESTAMP,
    }
    ref = db.collection('classes').document(cid)
    ref.set(class_doc)
    return jsonify({'success': True, 'classId': cid}), 201


@faculty_bp.route('/classes/<cid>/students', methods=['POST'])
@require_role('faculty_advisor')
def add_student_to_class(cid):
    data     = request.json or {}
    student_uid = data.get('studentUid', '')
    if not student_uid:
        return jsonify({'error': 'studentUid required'}), 400

    student_doc = db.collection('users').document(student_uid).get()
    if not student_doc.exists:
        return jsonify({'error': 'Student not found'}), 404

    db.collection('classes').document(cid).update({
        'students': firestore.ArrayUnion([student_uid])
    })
    # Update student's classId
    db.collection('users').document(student_uid).update({
        'classId': cid,
        'faUid'  : g.uid,
    })
    return jsonify({'success': True})


@faculty_bp.route('/classes/<cid>/students/<uid>', methods=['DELETE'])
@require_role('faculty_advisor')
def remove_student_from_class(cid, uid):
    """Remove a student from a class and clear their classId."""
    db.collection('classes').document(cid).update({
        'students': firestore.ArrayRemove([uid])
    })
    # Clear student's classId if it matches this class
    student_doc = db.collection('users').document(uid).get()
    if student_doc.exists and student_doc.to_dict().get('classId') == cid:
        db.collection('users').document(uid).update({'classId': ''})
    return jsonify({'success': True})


@faculty_bp.route('/classes/<cid>/teachers', methods=['POST'])
@require_role('faculty_advisor')
def assign_teacher(cid):
    data = request.json or {}
    teacher_uid = data.get('teacherUid', '')
    subject_id  = data.get('subjectId', '')
    if not teacher_uid:
        return jsonify({'error': 'teacherUid required'}), 400

    db.collection('classes').document(cid).update({
        'teachers': firestore.ArrayUnion([{'uid': teacher_uid, 'subjectId': subject_id}])
    })
    # Update teacher's assigned classes
    db.collection('users').document(teacher_uid).update({
        'assignedClasses': firestore.ArrayUnion([{'classId': cid, 'subjectId': subject_id}])
    })
    return jsonify({'success': True})


@faculty_bp.route('/classes/<cid>/teachers/<uid>', methods=['DELETE'])
@require_role('faculty_advisor')
def remove_teacher_from_class(cid, uid):
    """Remove a teacher from a class (handles both dict and raw-uid storage formats)."""
    cls_doc = db.collection('classes').document(cid).get()
    if not cls_doc.exists:
        return jsonify({'error': 'Class not found'}), 404

    teachers = cls_doc.to_dict().get('teachers', [])
    # teachers may be stored as [{uid, subjectId}] or plain uid strings
    updated = [t for t in teachers if (t.get('uid') if isinstance(t, dict) else t) != uid]
    db.collection('classes').document(cid).update({'teachers': updated})

    # Remove class from teacher's assignedClasses list
    t_doc = db.collection('users').document(uid).get()
    if t_doc.exists:
        assigned = t_doc.to_dict().get('assignedClasses', [])
        new_assigned = [a for a in assigned if (a.get('classId') if isinstance(a, dict) else a) != cid]
        db.collection('users').document(uid).update({'assignedClasses': new_assigned})

    return jsonify({'success': True})


@faculty_bp.route('/classes/<cid>/schedule', methods=['POST'])
@require_role('faculty_advisor')
def set_schedule(cid):
    data = request.json or {}
    schedule = data.get('schedule', {})  # {subjectId: {day, time, duration}}
    db.collection('classes').document(cid).update({'schedule': schedule})
    return jsonify({'success': True})


@faculty_bp.route('/classes/<cid>', methods=['GET'])
@require_role('faculty_advisor')
def get_class(cid):
    doc = db.collection('classes').document(cid).get()
    if not doc.exists:
        return jsonify({'error': 'Not found'}), 404
    c = doc.to_dict()
    c['id'] = cid
    return jsonify(c)


# ── Counsellor Assignment ─────────────────────────────────────────────────

@faculty_bp.route('/counsellor-assign', methods=['POST'])
@require_role('faculty_advisor')
def assign_counsellor():
    data = request.json or {}
    student_uids  = data.get('studentUids', [])
    counsellor_uid = data.get('counsellorUid', '')
    if not student_uids or not counsellor_uid:
        return jsonify({'error': 'studentUids and counsellorUid required'}), 400

    counsellor_doc = db.collection('users').document(counsellor_uid).get()
    if not counsellor_doc.exists:
        return jsonify({'error': 'Counsellor not found'}), 404
    counsellor_data = counsellor_doc.to_dict()

    for sud in student_uids:
        db.collection('users').document(sud).update({
            'counsellorUid'  : counsellor_uid,
            'counsellorName' : counsellor_data.get('name', ''),
            'caseStatus'     : 'active',
        })
        db.collection('users').document(counsellor_uid).update({
            'assignedStudents': firestore.ArrayUnion([sud])
        })

    return jsonify({'success': True, 'assigned': len(student_uids)})


@faculty_bp.route('/counsellors', methods=['GET'])
@require_role('faculty_advisor')
def list_counsellors():
    docs = db.collection('users').where('role', '==', 'counsellor').stream()
    counsellors = []
    for d in docs:
        c = d.to_dict()
        c['uid'] = d.id
        counsellors.append({'uid': d.id, 'name': c.get('name'), 'customId': c.get('customId')})
    return jsonify({'counsellors': counsellors})


@faculty_bp.route('/teachers', methods=['GET'])
@require_role('faculty_advisor')
def list_teachers():
    """Return all subject teachers for the Assign Teacher modal."""
    docs = db.collection('users').where('role', '==', 'subject_teacher').stream()
    teachers = []
    for d in docs:
        t = d.to_dict()
        teachers.append({
            'uid'     : d.id,
            'name'    : t.get('name', ''),
            'customId': t.get('customId', ''),
            'subject' : t.get('subject', ''),
        })
    teachers.sort(key=lambda t: t.get('name', ''))
    return jsonify({'teachers': teachers})


# ── Risk Scores ───────────────────────────────────────────────────────────

@faculty_bp.route('/risk-scores', methods=['GET'])
@require_role('faculty_advisor')
def risk_scores():
    # Get all students in FA's classes (try both field names)
    seen_ids = set()
    student_uids = []
    for field in ('faUid', 'facultyAdvisorId', 'advisorId'):
        classes_docs = db.collection('classes').where(field, '==', g.uid).stream()
        for cls in classes_docs:
            if cls.id not in seen_ids:
                student_uids.extend(cls.to_dict().get('students', []))
                seen_ids.add(cls.id)

    # Fallback: if still empty, get all students who have faUid == g.uid
    if not student_uids:
        s_docs = db.collection('users').where('role', '==', 'student').stream()
        student_uids = [d.id for d in s_docs]

    student_uids = list(set(student_uids))
    results = []
    for uid in student_uids:
        user_doc  = db.collection('users').document(uid).get()
        risk_doc  = db.collection('riskScores').document(uid).get()
        if user_doc.exists:
            u = user_doc.to_dict()
            r = risk_doc.to_dict() if risk_doc.exists else {}
            # Support both field name conventions
            score = r.get('riskScore', r.get('score', 0))
            level = r.get('riskLevel', r.get('level', 'LOW'))
            results.append({
                'uid'            : uid,
                'name'           : u.get('name', ''),
                'customId'       : u.get('customId', ''),
                'classId'        : u.get('classId', ''),
                'score'          : score,
                'level'          : level,
                'trend'          : r.get('trend', 'stable'),
                'breakdown'      : r.get('breakdown', {}),
                'recommendations': r.get('recommendations', []),
                'counsellorUid'  : u.get('counsellorUid', ''),
                'counsellorName' : u.get('counsellorName', ''),
            })
    return jsonify({'students': results})


# ── Pulse Quiz Management ─────────────────────────────────────────────────

@faculty_bp.route('/quizzes', methods=['GET'])
@require_role('faculty_advisor')
def list_quizzes():
    # Get class IDs for this FA — try all field name variants
    seen_class_ids = set()
    class_ids = []
    for field in ('faUid', 'facultyAdvisorId', 'advisorId'):
        docs = db.collection('classes').where(field, '==', g.uid).stream()
        for d in docs:
            if d.id not in seen_class_ids:
                class_ids.append(d.id)
                seen_class_ids.add(d.id)

    quizzes = []
    seen_quiz_ids = set()

    # Fetch quizzes by classId
    for cid in class_ids:
        qdocs = db.collection('quizzes').where('classId', '==', cid).stream()
        for q in qdocs:
            if q.id not in seen_quiz_ids:
                qd = q.to_dict()
                qd['id'] = q.id
                quizzes.append(qd)
                seen_quiz_ids.add(q.id)

    # Fallback: also fetch quizzes created by this FA directly
    if not quizzes:
        qdocs = db.collection('quizzes').where('faUid', '==', g.uid).stream()
        for q in qdocs:
            if q.id not in seen_quiz_ids:
                qd = q.to_dict()
                qd['id'] = q.id
                quizzes.append(qd)
                seen_quiz_ids.add(q.id)

    quizzes.sort(key=lambda q: q.get('scheduledAt', ''), reverse=True)
    return jsonify({'quizzes': quizzes, 'total': len(quizzes)})


@faculty_bp.route('/quizzes', methods=['POST'])
@require_role('faculty_advisor')
def create_quiz():
    data = request.json or {}
    class_id_val = data.get('classId', '')
    if not class_id_val:
        return jsonify({'error': 'classId required'}), 400

    qid = quiz_id()
    scheduled_at = data.get('scheduledAt', '')
    title = data.get('title', 'Pulse Quiz')

    # Generate questions via AI
    questions = generate_quiz_questions()

    quiz_doc = {
        'quizId'     : qid,
        'classId'    : class_id_val,
        'title'      : title,
        'faUid'      : g.uid,
        'scheduledAt': scheduled_at,
        'timeLimitMin': 10,
        'status'     : 'scheduled',
        'questions'  : questions,
        'createdAt'  : firestore.SERVER_TIMESTAMP,
    }
    db.collection('quizzes').document(qid).set(quiz_doc)

    # Notify all students in the class
    cls_doc = db.collection('classes').document(class_id_val).get()
    if cls_doc.exists:
        students = cls_doc.to_dict().get('students', [])
        for s_uid in students:
            notify_quiz_scheduled(s_uid, title, scheduled_at)

    return jsonify({'success': True, 'quizId': qid}), 201


@faculty_bp.route('/quizzes/<qid>/results', methods=['GET'])
@require_role('faculty_advisor')
def quiz_results(qid):
    docs = db.collection('quizResults').where('quizId', '==', qid).stream()
    results = []
    for d in docs:
        r = d.to_dict()
        # Get student name
        s_doc = db.collection('users').document(r.get('studentId', '')).get()
        if s_doc.exists:
            r['studentName'] = s_doc.to_dict().get('name', '')
            r['studentCustomId'] = s_doc.to_dict().get('customId', '')
        results.append(r)
    return jsonify({'results': results})


# ── Students list for FA ──────────────────────────────────────────────────

@faculty_bp.route('/students', methods=['GET'])
@require_role('faculty_advisor')
def fa_students():
    classes_docs = db.collection('classes').where('faUid', '==', g.uid).stream()
    student_uids = []
    for cls in classes_docs:
        student_uids.extend(cls.to_dict().get('students', []))
    student_uids = list(set(student_uids))
    students = []
    for uid in student_uids:
        doc = db.collection('users').document(uid).get()
        if doc.exists:
            u = doc.to_dict()
            u['uid'] = uid
            students.append(u)
    return jsonify({'students': students})


@faculty_bp.route('/students/all', methods=['GET'])
@require_role('faculty_advisor')
def all_students():
    """Return all users with role=student so FA can search & enroll them."""
    docs = db.collection('users').where('role', '==', 'student').stream()
    students = []
    for d in docs:
        u = d.to_dict()
        students.append({
            'uid'     : d.id,
            'name'    : u.get('name', ''),
            'customId': u.get('customId', ''),
            'classId' : u.get('classId', ''),
        })
    students.sort(key=lambda s: s.get('name', ''))
    return jsonify({'students': students})


# ── Proctor Reports ───────────────────────────────────────────────────────────

@faculty_bp.route('/proctor-reports', methods=['GET'])
@require_role('faculty_advisor')
def get_proctor_reports():
    """Return all quiz proctor reports for students in this FA's classes."""
    docs = db.collection('proctorReports') \
              .where('facultyAdvisorId', '==', g.uid) \
              .order_by('submittedAt', direction=firestore.Query.DESCENDING) \
              .limit(50).stream()
    reports = []
    for d in docs:
        r = {**d.to_dict(), 'id': d.id}
        # Drop large log arrays for the list view
        r.pop('emotionLog',   None)
        r.pop('behaviorLog',  None)
        r.pop('focusHistory', None)
        reports.append(r)
    return jsonify({'reports': reports})


@faculty_bp.route('/proctor-reports/<rid>', methods=['GET'])
@require_role('faculty_advisor')
def get_proctor_report_detail(rid):
    """Return a single proctor report in full (including logs)."""
    doc = db.collection('proctorReports').document(rid).get()
    if not doc.exists:
        return jsonify({'error': 'Report not found'}), 404
    r = {**doc.to_dict(), 'id': doc.id}
    if r.get('facultyAdvisorId') != g.uid:
        return jsonify({'error': 'Forbidden'}), 403
    return jsonify({'report': r})

