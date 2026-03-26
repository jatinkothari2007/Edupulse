"""
EduPulse Risk Engine — 7-factor academic risk score calculation.
HIGH score (0-100) = HIGH risk (bad). LOW score = LOW risk (good).

All Firestore queries use only single-field filters to avoid composite index requirements.
Date/range filtering is done in Python after fetching.
"""
from firebase_config import db
from firebase_admin import firestore
from datetime import datetime, timedelta, timezone
from utils.cache import get as cache_get, set as cache_set, delete as cache_del

RISK_TTL = 300  # re-calculate at most once per 5 minutes per student


MOOD_VALUES = {
    'great'      : 100,
    'good'       : 80,
    'okay'       : 60,
    'low'        : 30,
    'struggling' : 0,
}


def _safe_avg(lst):
    return sum(lst) / len(lst) if lst else None


def calculate_risk(student_id: str) -> dict:
    """
    Calculate risk score for a student.
    Returns dict with score, level, breakdown, recommendations, trend.
    Cached for RISK_TTL seconds to avoid quota exhaustion.
    """
    _cache_key = f'risk:{student_id}'
    cached = cache_get(_cache_key)
    if cached is not None:
        return cached

    now   = datetime.now(timezone.utc)
    day14 = (now - timedelta(days=14)).strftime('%Y-%m-%d')
    day7  = (now - timedelta(days=7)).strftime('%Y-%m-%d')

    # ── 1. Exam Marks (30%) ───────────────────────────────────
    # Single where clause only — filter component in Python
    marks_docs = db.collection('marks').where('studentId', '==', student_id).stream()
    exam_scores = []
    other_scores = []
    for d in marks_docs:
        m = d.to_dict()
        if m.get('maxMarks', 0) > 0 and m.get('marks') is not None:
            pct = m['marks'] / m['maxMarks'] * 100
            if m.get('component') == 'end-term':
                exam_scores.append(pct)
            else:
                other_scores.append(pct)
    exam_score  = _safe_avg(exam_scores)  or 75.0
    grade_score = _safe_avg(other_scores) or 75.0  # reuse for factor 7

    # ── 2. Attendance (20%) ───────────────────────────────────
    att_docs = db.collection('attendance').where('studentId', '==', student_id).stream()
    total_classes = 0
    attended = 0.0
    for d in att_docs:
        a = d.to_dict()
        total_classes += 1
        status = a.get('status', 'absent')
        if status == 'present':
            attended += 1
        elif status == 'late':
            attended += 0.5
    attendance_score = (attended / total_classes * 100) if total_classes > 0 else 100.0

    # ── 3. Assignment Submission (15%) ───────────────────────
    user_doc  = db.collection('users').document(student_id).get()
    user_data = user_doc.to_dict() if user_doc.exists else {}
    class_id  = user_data.get('classId', '')

    total_asgn    = 0
    submitted_asgn = 0
    if class_id:
        asgn_docs = db.collection('assignments').where('classId', '==', class_id).stream()
        for d in asgn_docs:
            total_asgn += 1
            sub_query = db.collection('submissions') \
                          .where('assignmentId', '==', d.id) \
                          .where('studentId', '==', student_id) \
                          .limit(1).get()
            if len(sub_query) > 0:
                submitted_asgn += 1
    submission_score = (submitted_asgn / total_asgn * 100) if total_asgn > 0 else 100.0

    # ── 4. Pulse Quiz (15%) ────────────────────────────────
    quiz_results = db.collection('quizResults').where('studentId', '==', student_id).stream()
    quiz_pcts   = []
    dist_counts = []
    for d in quiz_results:
        q = d.to_dict()
        if q.get('totalQuestions', 0) > 0:
            quiz_pcts.append(q.get('score', 0) / q['totalQuestions'] * 100)
        dist_counts.append(q.get('distractionCount', 0))
    quiz_avg = _safe_avg(quiz_pcts) or 75.0
    avg_dist  = _safe_avg(dist_counts) or 0
    distraction_penalty = min(30, avg_dist * 2)
    quiz_score = max(0, quiz_avg - distraction_penalty)

    # ── 5. Mood Map (10%) ─────────────────────────────────
    # Single where only — filter date in Python
    mood_vals = []
    for collection in ('moodLogs', 'moodCheckins'):
        try:
            mood_docs = db.collection(collection).where('studentId', '==', student_id).stream()
            for d in mood_docs:
                m = d.to_dict()
                m_date = m.get('date', '')
                if m_date >= day14:   # filter last 14 days in Python
                    val = MOOD_VALUES.get(m.get('mood', 'okay'), 60)
                    mood_vals.append(val)
        except Exception:
            pass
    mood_score = _safe_avg(mood_vals) or 70.0

    # ── 6. App Engagement (7%) ────────────────────────────
    note_opens_last7 = 0
    login_days_last7 = set()
    session_minutes  = []
    try:
        eng_docs = db.collection('engagementLogs').document(student_id) \
                     .collection('logs').stream()
        for d in eng_docs:
            e = d.to_dict()
            ts = e.get('timestamp')
            if ts:
                try:
                    if hasattr(ts, 'date'):
                        log_dt = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
                    else:
                        log_dt = datetime.fromtimestamp(ts.timestamp(), tz=timezone.utc)
                    log_date = log_dt.strftime('%Y-%m-%d')
                    if log_date >= day7:
                        action = e.get('action', '')
                        if action in ('note_open', 'note_read'):
                            note_opens_last7 += 1
                        if action == 'login':
                            login_days_last7.add(log_date)
                        dur = e.get('duration_seconds', 0)
                        if dur:
                            session_minutes.append(dur / 60)
                except Exception:
                    pass
    except Exception:
        pass

    note_opens_score = min(100, note_opens_last7 * 10)
    login_score      = min(100, len(login_days_last7) / 7 * 100)
    time_score       = min(100, (_safe_avg(session_minutes) or 0) / 30 * 100)
    engagement_score = note_opens_score * 0.4 + login_score * 0.4 + time_score * 0.2

    # ── Performance & Risk ────────────────────────────────
    performance = (
        exam_score        * 0.30 +
        attendance_score  * 0.20 +
        submission_score  * 0.15 +
        quiz_score        * 0.15 +
        mood_score        * 0.10 +
        engagement_score  * 0.07 +
        grade_score       * 0.03
    )
    risk_score = round(100 - performance, 1)
    risk_score = max(0.0, min(100.0, risk_score))

    # ── Classification ────────────────────────────────────
    if risk_score <= 35:
        level = 'LOW'
    elif risk_score <= 65:
        level = 'MEDIUM'
    else:
        level = 'HIGH'

    # ── Recommendations ───────────────────────────────────
    recommendations = []
    if exam_score < 50:
        recommendations.append("Exam performance is critically low. Immediate academic support needed.")
    if attendance_score < 75:
        recommendations.append("Attendance is below the required threshold.")
    if submission_score < 60:
        recommendations.append("Multiple assignments not submitted.")
    if quiz_score < 50:
        recommendations.append("Pulse Quiz scores indicate low engagement.")
    if mood_score < 40:
        recommendations.append("Student wellbeing needs immediate attention.")
    if engagement_score < 40:
        recommendations.append("Student is not engaging with study materials.")
    if not recommendations:
        recommendations.append("Keep up the great work! Stay consistent.")

    breakdown = {
        'examScore'       : round(exam_score, 1),
        'attendanceScore' : round(attendance_score, 1),
        'submissionScore' : round(submission_score, 1),
        'quizScore'       : round(quiz_score, 1),
        'moodScore'       : round(mood_score, 1),
        'engagementScore' : round(engagement_score, 1),
        'gradeScore'      : round(grade_score, 1),
    }

    result = {
        'score'          : risk_score,
        'riskScore'      : risk_score,
        'level'          : level,
        'riskLevel'      : level,
        'breakdown'      : breakdown,
        'recommendations': recommendations,
        'lastUpdated'    : firestore.SERVER_TIMESTAMP,
    }
    cache_set(f'risk:{student_id}', result, RISK_TTL)
    return result


def save_risk_score(student_id: str, result: dict):
    """Save risk score to Firestore and trigger notifications."""
    cache_del(f'risk:{student_id}')   # bust cache so next read is fresh
    from utils.notifier import notify_risk_alert, notify_risk_declined
    from utils.ai_messenger import send_high_risk_message

    # Get previous score for trend detection
    prev_doc = db.collection('riskScores').document(student_id).get()
    prev_score = None
    if prev_doc.exists:
        pd = prev_doc.to_dict()
        prev_score = pd.get('score', pd.get('riskScore'))

    new_score = result['score']
    trend = 'stable'
    if prev_score is not None:
        diff = new_score - prev_score
        if diff > 5:
            trend = 'worsening'
        elif diff < -5:
            trend = 'improving'

    result['trend'] = trend
    db.collection('riskScores').document(student_id).set(result)

    # Get student data for notifications
    user_doc = db.collection('users').document(student_id).get()
    if not user_doc.exists:
        return
    user = user_doc.to_dict()
    student_name = user.get('name', 'A student')
    fa_uid       = user.get('faUid') or user.get('facultyAdvisorId')

    if fa_uid:
        if result['level'] in ('HIGH', 'MEDIUM'):
            notify_risk_alert(fa_uid, student_name, result['level'], new_score, student_id)
        if prev_score is not None and (new_score - prev_score) >= 10:
            notify_risk_declined(fa_uid, student_name, prev_score, new_score)

    if result['level'] == 'HIGH':
        try:
            send_high_risk_message(student_id, student_name, new_score)
        except Exception:
            pass


def recalculate_and_save(student_id: str):
    """Full pipeline: calculate + save + notify."""
    result = calculate_risk(student_id)
    save_risk_score(student_id, result)
    return result
