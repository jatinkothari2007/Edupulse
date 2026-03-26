"""
EduPulse Student Routes — marks, attendance, assignments, mood, engagement, notes.
"""
from flask import Blueprint, jsonify, request, g
from firebase_config import db
from firebase_admin import firestore
from routes.auth_middleware import require_role
from risk_engine import recalculate_and_save
import datetime, uuid

student_bp = Blueprint('student', __name__, url_prefix='/api/student')


# ── Dashboard Summary (single-call aggregation) ───────────────────────────────

@student_bp.route('/dashboard', methods=['GET'])
@require_role('student')
def dashboard():
    uid      = g.uid
    class_id = g.user_data.get('classId', '')

    # Marks
    m_docs = list(db.collection('marks').where('studentId', '==', uid).stream())
    marks_list = [d.to_dict() for d in m_docs]
    avg_marks = 0
    if marks_list:
        scores = [m.get('score', 0) for m in marks_list]
        max_scores = [m.get('maxScore', 100) for m in marks_list]
        avg_marks = round(sum(s / mx * 100 for s, mx in zip(scores, max_scores)) / len(marks_list), 1)

    # Marks trend per subject — store as percentage, sorted A→Z
    subject_scores = {}
    for m in marks_list:
        subj = m.get('subject', '') or ''
        if not subj or subj.strip().lower() in ('unknown', 'n/a', '-', ''):
            continue
        if subj not in subject_scores:
            subject_scores[subj] = []
        raw = m.get('score', 0) or 0
        mx  = m.get('maxScore', 100) or 100
        subject_scores[subj].append(raw / mx * 100)   # store as %
    trend = [
        {'subject': s, 'score': round(sum(v)/len(v), 1)}
        for s, v in sorted(subject_scores.items())   # alphabetical order
    ]

    # Attendance
    a_docs = list(db.collection('attendance').where('studentId', '==', uid).stream())
    att_records = [d.to_dict() for d in a_docs]
    att_pct = 0
    if att_records:
        present = sum(1 for r in att_records if r.get('status') == 'present')
        att_pct = round(present / len(att_records) * 100, 1)

    # Attendance per subject
    subj_att = {}
    for r in att_records:
        s = r.get('subject', '') or ''
        if not s or s.strip().lower() in ('unknown', 'n/a', '-', ''):
            continue   # skip records with no subject name
        if s not in subj_att:
            subj_att[s] = {'total': 0, 'present': 0}
        subj_att[s]['total'] += 1
        if r.get('status') == 'present':
            subj_att[s]['present'] += 1
    subjects = [{'subject': s, 'pct': round(v['present']/v['total']*100, 1) if v['total'] else 0}
                for s, v in subj_att.items()]

    # Risk
    risk_doc = db.collection('riskScores').document(uid).get()
    risk_score = 0
    risk_level = 'LOW'
    if risk_doc.exists:
        rd = risk_doc.to_dict()
        risk_score = rd.get('riskScore', 0)
        risk_level = rd.get('riskLevel', 'LOW')

    # Upcoming tasks (assignments due)
    today = datetime.date.today().isoformat()
    tasks = []
    if class_id:
        task_docs = db.collection('assignments').where('classId', '==', class_id).stream()
        for td in task_docs:
            t = {**td.to_dict(), 'id': td.id, 'type': 'assignment'}
            due = t.get('dueDate', '')
            if due >= today:
                t['urgent'] = due <= (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
                tasks.append(t)
    tasks.sort(key=lambda x: x.get('dueDate', ''))

    return jsonify({
        'attendancePct' : att_pct,
        'avgMarks'      : avg_marks,
        'riskScore'     : risk_score,
        'riskLevel'     : risk_level,
        'pendingTasks'  : len(tasks),
        'upcomingTasks' : tasks[:8],
        'trend'         : trend,
        'subjects'      : subjects,
    })


# ── Marks ─────────────────────────────────────────────────────────────────────

@student_bp.route('/marks', methods=['GET'])
@require_role('student')
def get_marks():
    uid     = g.uid
    class_id = g.user_data.get('classId', '')
    docs    = db.collection('marks').where('studentId', '==', uid).stream()
    marks   = [{**d.to_dict(), 'id': d.id} for d in docs]
    return jsonify({'marks': marks})


# ── Attendance ────────────────────────────────────────────────────────────────

@student_bp.route('/attendance', methods=['GET'])
@require_role('student')
def get_attendance():
    uid  = g.uid
    docs = db.collection('attendance').where('studentId', '==', uid).stream()
    records = [{**d.to_dict(), 'id': d.id} for d in docs]
    return jsonify({'records': records})


# ── Assignments ───────────────────────────────────────────────────────────────

@student_bp.route('/assignments', methods=['GET'])
@require_role('student')
def get_assignments():
    class_id = g.user_data.get('classId', '')
    if not class_id:
        return jsonify({'assignments': []})
    docs = db.collection('assignments').where('classId', '==', class_id).stream()
    assignments = []
    for d in docs:
        asgn = {**d.to_dict(), 'id': d.id}
        # Check submission
        sub_q = db.collection('submissions') \
                  .where('assignmentId', '==', d.id) \
                  .where('studentId', '==', g.uid).limit(1).get()
        if sub_q:
            sub = sub_q[0].to_dict()
            asgn['submissionStatus'] = 'submitted'
            asgn['submissionId']     = sub_q[0].id
            asgn['marks']            = sub.get('marks')
            asgn['feedback']         = sub.get('feedback', '')
            asgn['submittedAt']      = sub.get('submittedAt')
            asgn['submissionUrl']    = sub.get('driveLink') or sub.get('fileUrl', '')

        else:
            asgn['submissionStatus'] = 'pending'
        assignments.append(asgn)
    return jsonify({'assignments': assignments})


@student_bp.route('/assignments/<aid>/submit', methods=['POST'])
@require_role('student')
def submit_assignment(aid):
    data = request.json or {}
    # Check not already submitted
    sub_q = db.collection('submissions') \
               .where('assignmentId', '==', aid) \
               .where('studentId', '==', g.uid).limit(1).get()
    if sub_q:
        # Update existing submission
        sub_q[0].reference.update({
            'fileUrl'    : data.get('fileUrl', ''),
            'driveLink'  : data.get('driveLink', data.get('fileUrl', '')),
            'fileName'   : data.get('fileName', ''),
            'submittedAt': firestore.SERVER_TIMESTAMP,
            'status'     : 'submitted',
        })
        return jsonify({'success': True, 'updated': True})

    asgn_doc = db.collection('assignments').document(aid).get()
    if not asgn_doc.exists:
        return jsonify({'error': 'Assignment not found'}), 404

    ref = db.collection('submissions').add({
        'assignmentId': aid,
        'studentId'   : g.uid,
        'studentName' : g.user_data.get('name', ''),
        'fileUrl'     : data.get('fileUrl', ''),
        'driveLink'   : data.get('driveLink', data.get('fileUrl', '')),
        'fileName'    : data.get('fileName', ''),
        'submittedAt' : firestore.SERVER_TIMESTAMP,
        'status'      : 'submitted',
    })
    try:
        recalculate_and_save(g.uid)
    except Exception:
        pass
    return jsonify({'success': True, 'submissionId': ref[1].id}), 201


# ── Mood Check-In ─────────────────────────────────────────────────────────────

@student_bp.route('/mood', methods=['GET'])
@require_role('student')
def get_mood():
    uid = g.uid
    merged = {}  # date → entry (dedup; moodCheckins wins over moodLogs)

    # Read moodLogs (seeded data)
    try:
        for d in db.collection('moodLogs').where('studentId', '==', uid).stream():
            entry = {**d.to_dict(), 'id': d.id, '_src': 'moodLogs'}
            date  = entry.get('date', '')
            if date and date not in merged:
                merged[date] = entry
    except Exception:
        pass

    # Read moodCheckins (live check-ins; overrides moodLogs for same date)
    try:
        for d in db.collection('moodCheckins').where('studentId', '==', uid).stream():
            entry = {**d.to_dict(), 'id': d.id, '_src': 'moodCheckins'}
            date  = entry.get('date', '')
            if date:
                merged[date] = entry   # always overwrite with real check-in
    except Exception:
        pass

    checkins = sorted(merged.values(), key=lambda x: x.get('date', ''), reverse=True)[:30]
    return jsonify({'checkins': checkins})


@student_bp.route('/mood', methods=['POST'])
@require_role('student')
def submit_mood():
    data     = request.json or {}
    mood     = data.get('mood', '')
    note     = data.get('note', '')
    today    = datetime.date.today().isoformat()

    VALID_MOODS = ['great', 'good', 'okay', 'low', 'struggling']
    if mood not in VALID_MOODS:
        return jsonify({'error': f'mood must be one of {VALID_MOODS}'}), 400

    # Check already submitted today
    existing = db.collection('moodCheckins') \
                 .where('studentId', '==', g.uid) \
                 .where('date', '==', today).limit(1).get()
    if existing:
        return jsonify({'error': 'Already submitted mood today'}), 409

    db.collection('moodCheckins').add({
        'studentId': g.uid,
        'mood'     : mood,
        'note'     : note,
        'date'     : today,
        'timestamp': firestore.SERVER_TIMESTAMP,
    })

    # Check for consecutive low mood (3 days)
    try:
        _check_low_mood_streak(g.uid, g.user_data.get('name', ''))
    except Exception:
        pass

    try:
        recalculate_and_save(g.uid)
    except Exception:
        pass

    return jsonify({'success': True})


def _check_low_mood_streak(uid, name):
    from utils.ai_messenger import send_low_mood_message
    LOW_MOODS = ('low', 'struggling')
    today = datetime.date.today()
    streak = 0
    for i in range(3):
        day = (today - datetime.timedelta(days=i)).isoformat()
        docs = db.collection('moodCheckins') \
                 .where('studentId', '==', uid) \
                 .where('date', '==', day).limit(1).get()
        if docs and docs[0].to_dict().get('mood') in LOW_MOODS:
            streak += 1
        else:
            break
    if streak >= 3:
        send_low_mood_message(uid, name, streak)


# ── Risk Score ────────────────────────────────────────────────────────────────

@student_bp.route('/risk', methods=['GET'])
@require_role('student')
def get_risk():
    uid = g.uid
    doc = db.collection('riskScores').document(uid).get()

    # Check if stored doc has a useful breakdown (not all zeros / missing)
    stale = True
    if doc.exists:
        r = doc.to_dict()
        breakdown = r.get('breakdown', {})
        if breakdown and any(v for v in breakdown.values() if v):
            stale = False

    if stale:
        # Recalculate live from Firestore data
        try:
            result = recalculate_and_save(uid)
            return jsonify({
                'score'          : result.get('score', 0),
                'level'          : result.get('level', 'LOW'),
                'trend'          : result.get('trend', 'stable'),
                'breakdown'      : result.get('breakdown', {}),
                'recommendations': result.get('recommendations', []),
            })
        except Exception as e:
            # Fall back to stored if recalculation fails
            if doc.exists:
                r = doc.to_dict()
            else:
                return jsonify({'score': 0, 'level': 'LOW', 'breakdown': {}, 'recommendations': []})

    r = doc.to_dict()
    return jsonify({
        'score'          : r.get('riskScore', r.get('score', 0)),
        'level'          : r.get('riskLevel', r.get('level', 'LOW')),
        'trend'          : r.get('trend', 'stable'),
        'breakdown'      : r.get('breakdown', {}),
        'recommendations': r.get('recommendations', []),
    })


@student_bp.route('/recalculate', methods=['POST'])
@require_role('student')
def recalculate_risk_self():
    try:
        r = recalculate_and_save(g.uid)
        return jsonify({'success': True, 'score': r.get('score', r.get('riskScore', 0))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Notes ─────────────────────────────────────────────────────────────────────

@student_bp.route('/notes', methods=['GET'])
@require_role('student')
def get_notes():
    class_id = g.user_data.get('classId', '')
    if not class_id:
        return jsonify({'notes': []})
    docs = db.collection('notes').where('classId', '==', class_id).stream()
    notes = [{**d.to_dict(), 'id': d.id} for d in docs]
    return jsonify({'notes': notes})


@student_bp.route('/notes/<note_id>/open', methods=['POST'])
@require_role('student')
def track_note_open(note_id):
    """Track when student opens a note — feeds engagement score."""
    data = request.json or {}
    now  = datetime.datetime.now(datetime.timezone.utc)
    db.collection('noteEngagement').document(g.uid).collection(note_id).add({
        'action'     : 'note_open',
        'openedAt'   : firestore.SERVER_TIMESTAMP,
        'duration'   : data.get('duration', 0),
        'timeOfDay'  : now.hour,
    })
    # Also add to engagement log
    db.collection('engagementLogs').document(g.uid).collection('logs').add({
        'action'          : 'note_open',
        'noteId'          : note_id,
        'timestamp'       : firestore.SERVER_TIMESTAMP,
        'duration_seconds': data.get('duration', 0),
        'dayOfWeek'       : now.weekday(),
        'hourOfDay'       : now.hour,
    })
    return jsonify({'success': True})


# ── Engagement Logging ────────────────────────────────────────────────────────

@student_bp.route('/engagement/login', methods=['POST'])
@require_role('student')
def log_login():
    now = datetime.datetime.now(datetime.timezone.utc)
    db.collection('engagementLogs').document(g.uid).collection('logs').add({
        'action'   : 'login',
        'timestamp': firestore.SERVER_TIMESTAMP,
        'dayOfWeek': now.weekday(),
        'hourOfDay': now.hour,
    })
    return jsonify({'success': True})


@student_bp.route('/engagement/heatmap', methods=['GET'])
@require_role('student')
def get_heatmap():
    now    = datetime.datetime.now(datetime.timezone.utc)
    week_ago = now - datetime.timedelta(days=7)
    docs = db.collection('engagementLogs').document(g.uid).collection('logs').stream()
    grid = [[0]*24 for _ in range(7)]  # [dayOfWeek][hour]
    for d in docs:
        e = d.to_dict()
        ts = e.get('timestamp')
        try:
            if hasattr(ts, 'timestamp'):
                log_dt = ts.replace(tzinfo=datetime.timezone.utc) if hasattr(ts, 'replace') else ts
                if log_dt >= week_ago:
                    dow  = e.get('dayOfWeek', log_dt.weekday())
                    hour = e.get('hourOfDay', log_dt.hour)
                    if 0 <= dow <= 6 and 0 <= hour <= 23:
                        grid[dow][hour] += 1
        except Exception:
            pass
    return jsonify({'grid': grid})


# ── Quiz ──────────────────────────────────────────────────────────────────────

@student_bp.route('/quizzes', methods=['GET'])
@require_role('student')
def get_quizzes():
    class_id = g.user_data.get('classId', '')
    if not class_id:
        return jsonify({'quizzes': []})
    docs = db.collection('quizzes').where('classId', '==', class_id).stream()
    quizzes = []
    for d in docs:
        q = {**d.to_dict(), 'id': d.id}
        q.pop('questions', None)  # strip questions for list view
        # Check result
        result_q = db.collection('quizResults') \
                     .where('quizId', '==', d.id) \
                     .where('studentId', '==', g.uid).limit(1).get()
        q['attempted'] = len(result_q) > 0
        quizzes.append(q)
    return jsonify({'quizzes': quizzes})


@student_bp.route('/quizzes/<qid>', methods=['GET'])
@require_role('student')
def get_quiz(qid):
    doc = db.collection('quizzes').document(qid).get()
    if not doc.exists:
        return jsonify({'error': 'Quiz not found'}), 404
    q = doc.to_dict()
    q['id'] = qid
    return jsonify(q)


@student_bp.route('/quizzes/<qid>/submit', methods=['POST'])
@require_role('student')
def submit_quiz(qid):
    data = request.json or {}
    answers     = data.get('answers', {})       # {questionIndex: optionKey}
    proctor_data = data.get('proctorData', {})

    quiz_doc = db.collection('quizzes').document(qid).get()
    if not quiz_doc.exists:
        return jsonify({'error': 'Quiz not found'}), 404
    quiz = quiz_doc.to_dict()
    questions = quiz.get('questions', [])

    # Score
    correct = 0
    total   = len(questions)
    for i, q in enumerate(questions):
        if str(answers.get(str(i))) == q.get('correct', ''):
            correct += 1

    score_pct = round(correct / total * 100, 1) if total > 0 else 0

    # Distraction score from proctor data
    dist_count = proctor_data.get('distractionCount', 0)
    eng_score  = proctor_data.get('engagementScore', 100)

    db.collection('quizResults').add({
        'quizId'         : qid,
        'studentId'      : g.uid,
        'studentName'    : g.user_data.get('name', ''),
        'score'          : correct,
        'totalQuestions' : total,
        'scorePercent'   : score_pct,
        'distractionCount': dist_count,
        'tabSwitchCount' : proctor_data.get('tabSwitchCount', 0),
        'faceAbsenceSeconds': proctor_data.get('faceAbsenceSeconds', 0),
        'engagementScore': eng_score,
        'submittedAt'    : firestore.SERVER_TIMESTAMP,
    })

    # Update quiz status
    db.collection('quizzes').document(qid).update({'status': 'completed'})

    try:
        recalculate_and_save(g.uid)
    except Exception:
        pass

    return jsonify({
        'success'     : True,
        'score'       : correct,
        'total'       : total,
        'percent'     : score_pct,
        'engagement'  : eng_score,
    })



# ── Student Profile (for  counsellor / FA view) ───────────────────────────────

@student_bp.route('/profile', methods=['GET'])
@require_role('student')
def my_profile():
    u = g.user_data.copy()
    u.pop('passwordHash', None)
    return jsonify(u)


# ── Proctor Report (save after Pulse Quiz) ────────────────────────────────────

@student_bp.route('/quizzes/<qid>/proctor-report', methods=['POST'])
@require_role('student')
def save_proctor_report(qid):
    """
    Store the client-side proctorSession into Firestore and notify
    the student's Faculty Advisor that a new report is ready.
    """
    data = request.json or {}
    sess = data.get('proctorSession', {})
    if not sess:
        return jsonify({'error': 'proctorSession required'}), 400

    uid       = g.uid
    user_data = g.user_data
    class_id  = user_data.get('classId', '')

    # Resolve Faculty Advisor UID from the class document
    fa_uid = user_data.get('facultyAdvisorId', '')
    if not fa_uid and class_id:
        cls_doc = db.collection('classes').document(class_id).get()
        if cls_doc.exists:
            cd = cls_doc.to_dict()
            fa_uid = cd.get('facultyAdvisorId') or cd.get('advisorId') or cd.get('faUid', '')

    report_doc = {
        'quizId'         : qid,
        'studentId'      : uid,
        'studentName'    : user_data.get('name', ''),
        'studentCustomId': user_data.get('customId', ''),
        'classId'        : class_id,
        'facultyAdvisorId': fa_uid,
        'subject'        : sess.get('subject', 'Pulse Quiz'),
        'startTime'      : sess.get('startTime'),
        'endTime'        : sess.get('endTime'),
        'verdict'        : sess.get('verdict', 'clean'),
        'riskScore'      : sess.get('riskScore', 100),
        'focusScore'     : sess.get('focusScore', 100),
        'totalAlerts'    : sess.get('totalAlerts', 0),
        'suspiciousCount': sess.get('suspiciousCount', 0),
        'tabSwitchCount' : sess.get('tabSwitchCount', 0),
        'faceMissingEvents': sess.get('faceMissingEvents', 0),
        'anxiousCount'   : sess.get('anxiousCount', 0),
        'emotionLog'     : sess.get('emotionLog', []),
        'behaviorLog'    : sess.get('behaviorLog', []),
        'focusHistory'   : sess.get('focusHistory', []),
        'submittedAt'    : firestore.SERVER_TIMESTAMP,
    }
    ref = db.collection('proctorReports').add(report_doc)
    report_id = ref[1].id

    # Notify FA
    if fa_uid:
        sname    = user_data.get('name', 'A student')
        verdict  = sess.get('verdict', 'clean')
        icon     = {'clean': '✅', 'suspicious': '⚠️', 'malpractice': '🚨'}.get(verdict, 'ℹ️')
        db.collection('notifications').add({
            'userId'    : fa_uid,
            'type'      : 'proctor_report',
            'title'     : f'{icon} Proctor Report: {sname}',
            'message'   : f'{sname} completed the Pulse Quiz. Verdict: {verdict.upper()}. Risk Score: {sess.get("riskScore", 100)}',
            'reportId'  : report_id,
            'studentId' : uid,
            'read'      : False,
            'createdAt' : firestore.SERVER_TIMESTAMP,
        })

    return jsonify({'success': True, 'reportId': report_id})
