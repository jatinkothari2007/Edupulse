from dotenv import load_dotenv
load_dotenv()

import os
from flask import Flask, jsonify, render_template, redirect, url_for, request
from flask_cors import CORS
from firebase_config import db, auth  # noqa: F401

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'edupulse_secret')
CORS(app)

# ── Debug endpoint — verify auth + Firestore chain ───────────────────────────
@app.route('/api/debug/ping')
def debug_ping():
    return jsonify({'status': 'ok', 'message': 'Flask is running'})

@app.route('/api/debug/firestore')
def debug_firestore():
    try:
        users = list(db.collection('users').limit(3).stream())
        return jsonify({'status': 'ok', 'userCount': len(users),
                        'sample': [u.to_dict().get('email','?') for u in users]})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

# ── Firebase client config (served to browser) ───────────────────────────────
@app.route('/firebase-config')
def firebase_config():
    project_id = os.environ.get('FIREBASE_PROJECT_ID', '')
    storage_bucket = (
        os.environ.get('FIREBASE_STORAGE_BUCKET')
        or (f'{project_id}.appspot.com' if project_id else '')
    )
    cfg = {
        'apiKey'           : os.environ.get('FIREBASE_API_KEY', ''),
        'authDomain'       : os.environ.get('FIREBASE_AUTH_DOMAIN', ''),
        'projectId'        : project_id,
        'storageBucket'    : storage_bucket,
        'messagingSenderId': os.environ.get('FIREBASE_MESSAGING_SENDER_ID', ''),
        'appId'            : os.environ.get('FIREBASE_APP_ID', ''),
    }
    if not cfg['apiKey']:
        app.logger.error('[EduPulse] FIREBASE_API_KEY is not set in .env')
    if not cfg['appId']:
        app.logger.warning('[EduPulse] FIREBASE_APP_ID is not set — Firebase init may fail on client')
    return jsonify(cfg)

# ── Portal (first page) ──────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('portal.html')

@app.route('/portal')
def portal():
    return render_template('portal.html')

# ── Login Page ───────────────────────────────────────────────────────────────
@app.route('/login')
def login_page():
    return render_template('login.html')

# ── Dashboards ───────────────────────────────────────────────────────────────
@app.route('/dashboard/admin')
def admin_dashboard():
    return render_template('dashboard/admin.html')

@app.route('/dashboard/faculty')
def faculty_dashboard():
    return render_template('dashboard/faculty.html')

@app.route('/dashboard/teacher')
def teacher_dashboard():
    return render_template('dashboard/teacher.html')

@app.route('/dashboard/counsellor')
def counsellor_dashboard():
    return render_template('dashboard/counsellor.html')

@app.route('/dashboard/student')
def student_dashboard():
    return render_template('dashboard/student.html')

# ── Admin Pages ──────────────────────────────────────────────────────────────
@app.route('/pages/admin/users')
def admin_users():
    return render_template('pages/admin/users.html')



@app.route('/pages/admin/login-activity')
def admin_login_activity():
    return render_template('pages/admin/login-activity.html')

# ── Faculty Pages ─────────────────────────────────────────────────────────────
@app.route('/pages/faculty/classes')
def faculty_classes():
    return render_template('pages/faculty/classes.html')

@app.route('/pages/faculty/risk-scores')
def faculty_risk():
    return render_template('pages/faculty/risk-scores.html')

@app.route('/pages/faculty/quiz-manage')
def faculty_quiz():
    return render_template('pages/faculty/quiz-manage.html')

@app.route('/pages/faculty/counsellor-assign')
def faculty_counsellor_assign():
    return render_template('pages/faculty/counsellor-assign.html')

# ── Teacher Pages ─────────────────────────────────────────────────────────────
@app.route('/pages/teacher/classes')
def teacher_classes():
    return render_template('pages/teacher/classes.html')

@app.route('/pages/teacher/attendance')
def teacher_attendance():
    return render_template('pages/teacher/attendance.html')

@app.route('/pages/teacher/assignments')
def teacher_assignments():
    return render_template('pages/teacher/assignments.html')

@app.route('/pages/teacher/marks')
def teacher_marks():
    return render_template('pages/teacher/marks.html')

@app.route('/pages/teacher/notes')
def teacher_notes():
    return render_template('pages/teacher/notes.html')

# ── Counsellor Pages ──────────────────────────────────────────────────────────
@app.route('/pages/counsellor/students')
def counsellor_students():
    return render_template('pages/counsellor/students.html')

@app.route('/pages/counsellor/sessions')
def counsellor_sessions():
    return render_template('pages/counsellor/sessions.html')

@app.route('/pages/counsellor/cases')
def counsellor_cases():
    return render_template('pages/counsellor/cases.html')

# ── Student Pages ─────────────────────────────────────────────────────────────
@app.route('/pages/student/marks')
def student_marks():
    return render_template('pages/student/marks.html')

@app.route('/pages/student/attendance')
def student_attendance():
    return render_template('pages/student/attendance.html')

@app.route('/pages/student/assignments')
def student_assignments():
    return render_template('pages/student/assignments.html')

@app.route('/pages/student/notes')
def student_notes():
    return render_template('pages/student/notes.html')

@app.route('/pages/student/quiz')
def student_quiz():
    return render_template('pages/student/quiz.html')

@app.route('/pages/student/risk')
def student_risk():
    return render_template('pages/student/risk.html')

@app.route('/pages/student/mood')
def student_mood():
    return render_template('pages/student/mood.html')

@app.route('/pages/student/videocall')
def student_videocall():
    return render_template('pages/student/videocall.html')

# ── Shared Pages ──────────────────────────────────────────────────────────────
@app.route('/pages/messaging')
def messaging_page():
    return render_template('pages/messaging.html')

@app.route('/pages/notifications')
def notifications_page():
    return render_template('pages/notifications.html')

@app.route('/pages/videocall')
def videocall_page():
    return render_template('pages/videocall.html')

# ── Blueprints ────────────────────────────────────────────────────────────────
from routes.auth          import auth_bp
from routes.admin         import admin_bp
from routes.advisor       import advisor_bp
from routes.faculty       import faculty_bp
from routes.teacher       import teacher_bp
from routes.counsellor    import counsellor_bp
from routes.student       import student_bp
from routes.messaging     import messaging_bp
from routes.notifications import notifications_bp
from routes.risk          import risk_bp
from routes.quiz          import quiz_bp
from routes.videocall     import videocall_bp
from routes.reports       import reports_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(advisor_bp)
app.register_blueprint(faculty_bp)
app.register_blueprint(teacher_bp)
app.register_blueprint(counsellor_bp)
app.register_blueprint(student_bp)
app.register_blueprint(messaging_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(risk_bp)
app.register_blueprint(quiz_bp)
app.register_blueprint(videocall_bp)
app.register_blueprint(reports_bp)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
