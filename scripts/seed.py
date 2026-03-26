"""
EduPulse seed.py — Full database reset + seed.

USAGE:
    python seed.py

WHAT IT DOES:
  1. Deletes ALL existing Firebase Auth users
  2. Deletes ALL documents in key Firestore collections
  3. Creates 5 role-based users (Admin, Faculty, Teacher, Counsellor, Student x3)
  4. Seeds classes, marks, attendance, risk scores, mood logs
  5. Prints a credentials table at the end

REQUIRES: FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_API_KEY, FIREBASE_AUTH_DOMAIN in .env
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import os, json, time, random, string, datetime
import firebase_admin
from firebase_admin import credentials, auth as fb_auth, firestore as fb_firestore

# ── Initialize Firebase Admin ────────────────────────────────────────────────
sa_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
if not sa_json:
    raise RuntimeError('FIREBASE_SERVICE_ACCOUNT_JSON not set in .env')

cred = credentials.Certificate(json.loads(sa_json))
firebase_admin.initialize_app(cred)
db = fb_firestore.client()

print('\n══════════════════════════════════════════')
print('  EduPulse Database Reset & Seed Tool')
print('══════════════════════════════════════════\n')

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Delete all existing Firebase Auth users
# ══════════════════════════════════════════════════════════════════════════════
print('[1/4] Deleting all existing Firebase Auth users...')
page = fb_auth.list_users()
deleted = 0
while page:
    uids = [u.uid for u in page.users]
    if uids:
        fb_auth.delete_users(uids)
        deleted += len(uids)
    page = page.get_next_page()
print(f'      Deleted {deleted} auth user(s).')

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Delete all Firestore collections
# ══════════════════════════════════════════════════════════════════════════════
COLLECTIONS = [
    'users', 'classes', 'marks', 'attendance', 'assignments',
    'notes', 'quizzes', 'riskScores', 'moodLogs', 'sessions',
    'notifications', 'messages', 'conversations', 'counters',
    'auditLogs', 'announcements', 'polls', 'engagementLogs',
]

def delete_collection(col_ref, batch_size=100):
    docs = list(col_ref.limit(batch_size).stream())
    while docs:
        batch = db.batch()
        for d in docs:
            batch.delete(d.reference)
        batch.commit()
        docs = list(col_ref.limit(batch_size).stream())

print('[2/4] Clearing Firestore collections...')
for col in COLLECTIONS:
    delete_collection(db.collection(col))
    print(f'      Cleared: {col}')

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Create users
# ══════════════════════════════════════════════════════════════════════════════
print('\n[3/4] Creating users and seeding data...')

SERVER_TS = fb_firestore.SERVER_TIMESTAMP

def make_user(email, password, name, role, extra=None):
    """Create Firebase Auth user + Firestore profile."""
    fb_user = fb_auth.create_user(
        email=email,
        password=password,
        display_name=name,
    )
    profile = {
        'email':     email,
        'name':      name,
        'role':      role,
        'active':    True,
        'createdAt': SERVER_TS,
        **(extra or {}),
    }
    db.collection('users').document(fb_user.uid).set(profile)
    return fb_user.uid

# ── User definitions ─────────────────────────────────────────────────────────
USERS = [
    # email, password, name, role, extra
    ('admin@edupulse.com',           'Admin1', 'Super Admin',       'admin',           {'customId': 'ADP000001'}),
    ('faculty@edupulse.com',         'Admin1', 'Dr. Priya Sharma',  'faculty_advisor', {'customId': 'FAP000001', 'department': 'Computer Science'}),
    ('teacher.maths@edupulse.com',   'Admin1', 'Mr. Rohan Mehta',   'subject_teacher', {'customId': 'TEP000001', 'subject': 'Mathematics', 'department': 'Science'}),
    ('teacher.physics@edupulse.com', 'Admin1', 'Ms. Anita Verma',   'subject_teacher', {'customId': 'TEP000002', 'subject': 'Physics',     'department': 'Science'}),
    ('teacher.chem@edupulse.com',    'Admin1', 'Mr. Suresh Nair',   'subject_teacher', {'customId': 'TEP000003', 'subject': 'Chemistry',   'department': 'Science'}),
    ('teacher.english@edupulse.com', 'Admin1', 'Ms. Preethi Iyer',  'subject_teacher', {'customId': 'TEP000004', 'subject': 'English',     'department': 'Humanities'}),
    ('teacher.oodp@edupulse.com',    'Admin1', 'Mr. Vikram Bose',   'subject_teacher', {'customId': 'TEP000005', 'subject': 'OODP',        'department': 'Computer Science'}),
    ('counsellor@edupulse.com',      'Admin1', 'Ms. Kavita Joshi',  'counsellor',      {'customId': 'CNP000001', 'specialization': 'Academic & Mental Health'}),
    ('arjun@edupulse.com',        'Admin1', 'Arjun Patel',       'student',         {'customId': 'SEP000001', 'rollNumber': '001', 'classId': 'CLS0001', 'gender': 'Male',   'dob': '2005-03-12'}),
    ('sneha@edupulse.com',        'Admin1', 'Sneha Reddy',       'student',         {'customId': 'SEP000002', 'rollNumber': '002', 'classId': 'CLS0001', 'gender': 'Female', 'dob': '2005-07-22'}),
    ('karan@edupulse.com',        'Admin1', 'Karan Singh',       'student',         {'customId': 'SEP000003', 'rollNumber': '003', 'classId': 'CLS0001', 'gender': 'Male',   'dob': '2006-01-05'}),
]

created_uids = {}
for (email, pwd, name, role, extra) in USERS:
    uid = make_user(email, pwd, name, role, extra)
    created_uids[email] = uid
    print(f'      ✓ {role:<18} {name:<22} {email}')

# Convenience references
admin_uid      = created_uids['admin@edupulse.com']
faculty_uid    = created_uids['faculty@edupulse.com']
t_maths_uid    = created_uids['teacher.maths@edupulse.com']
t_physics_uid  = created_uids['teacher.physics@edupulse.com']
t_chem_uid     = created_uids['teacher.chem@edupulse.com']
t_english_uid  = created_uids['teacher.english@edupulse.com']
t_oodp_uid     = created_uids['teacher.oodp@edupulse.com']
counsellor_uid = created_uids['counsellor@edupulse.com']
s1_uid         = created_uids['arjun@edupulse.com']
s2_uid         = created_uids['sneha@edupulse.com']
s3_uid         = created_uids['karan@edupulse.com']
student_uids   = [s1_uid, s2_uid, s3_uid]
student_names  = {s1_uid: 'Arjun Patel', s2_uid: 'Sneha Reddy', s3_uid: 'Karan Singh'}
student_ids    = {s1_uid: 'SEP000001', s2_uid: 'SEP000002', s3_uid: 'SEP000003'}

teacher_uids_all = [t_maths_uid, t_physics_uid, t_chem_uid, t_english_uid, t_oodp_uid]
subject_teacher_map = {
    'Mathematics': t_maths_uid,
    'Physics':     t_physics_uid,
    'Chemistry':   t_chem_uid,
    'English':     t_english_uid,
    'OODP':        t_oodp_uid,
}

# Set counters
db.collection('counters').document('ADP').set({'count': 1})
db.collection('counters').document('FAP').set({'count': 1})
db.collection('counters').document('TEP').set({'count': 5})
db.collection('counters').document('CNP').set({'count': 1})
db.collection('counters').document('SEP').set({'count': 3})
db.collection('counters').document('CLS').set({'count': 1})

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Seed data
# ══════════════════════════════════════════════════════════════════════════════

# ── Class ────────────────────────────────────────────────────────────────────
class_ref = db.collection('classes').document('CLS0001')
class_ref.set({
    'classId':         'CLS0001',
    'name':            'Class 11 - A',
    'description':     'Senior secondary class A',
    'facultyAdvisorId': faculty_uid,
    'advisorId':        faculty_uid,
    'counsellorId':     counsellor_uid,
    'teacherIds':       teacher_uids_all,
    'students':         student_uids,
    'studentCount':     len(student_uids),
    'subjects':         ['Mathematics', 'Physics', 'Chemistry', 'English', 'OODP'],
    'createdAt':        SERVER_TS,
})

# Update each teacher doc with classId
for tuid in teacher_uids_all:
    db.collection('users').document(tuid).update({'classId': 'CLS0001', 'classIds': ['CLS0001']})
db.collection('users').document(counsellor_uid).update({'assignedStudents': student_uids, 'classIds': ['CLS0001']})

SUBJECTS = ['Mathematics', 'Physics', 'Chemistry', 'English', 'OODP']

# ── Marks ────────────────────────────────────────────────────────────────────
marks_data = {
    s1_uid: [82, 74, 88, 91, 76],   # Arjun — good
    s2_uid: [95, 90, 88, 97, 93],   # Sneha — excellent
    s3_uid: [45, 52, 38, 60, 44],   # Karan — at risk
}
for uid, scores in marks_data.items():
    for i, subject in enumerate(SUBJECTS):
        db.collection('marks').add({
            'studentId':   uid,
            'customId':    student_ids[uid],
            'studentName': student_names[uid],
            'classId':     'CLS0001',
            'subject':     subject,
            'teacherId':   subject_teacher_map[subject],
            'score':       scores[i],
            'maxScore':    100,
            'type':        'Unit Test 1',
            'term':        'Term 1',
            'createdAt':   SERVER_TS,
        })

# ── Attendance ───────────────────────────────────────────────────────────────
# 30 days of attendance
base_date = datetime.date.today() - datetime.timedelta(days=29)
attendance_pct = {s1_uid: 0.85, s2_uid: 0.97, s3_uid: 0.55}

for uid in student_uids:
    for day_offset in range(30):
        date = base_date + datetime.timedelta(days=day_offset)
        if date.weekday() >= 5:
            continue
        pct = attendance_pct[uid]
        for subject in SUBJECTS:
            present = random.random() < pct
            db.collection('attendance').add({
                'studentId':   uid,
                'customId':    student_ids[uid],
                'studentName': student_names[uid],
                'classId':     'CLS0001',
                'teacherId':   subject_teacher_map[subject],
                'date':        date.isoformat(),
                'status':      'present' if present else 'absent',
                'subject':     subject,
                'createdAt':   SERVER_TS,
            })

# ── Risk Scores ──────────────────────────────────────────────────────────────
risk_data = {
    s1_uid: {'riskScore': 35, 'riskLevel': 'LOW',    'factors': {'attendance': 85, 'marks': 82, 'mood': 7}},
    s2_uid: {'riskScore': 10, 'riskLevel': 'LOW',    'factors': {'attendance': 97, 'marks': 93, 'mood': 9}},
    s3_uid: {'riskScore': 78, 'riskLevel': 'HIGH',   'factors': {'attendance': 55, 'marks': 46, 'mood': 3}},
}
for uid, data in risk_data.items():
    db.collection('riskScores').document(uid).set({
        'studentId':   uid,
        'customId':    student_ids[uid],
        'studentName': student_names[uid],
        'classId':     'CLS0001',
        'riskScore':   data['riskScore'],
        'riskLevel':   data['riskLevel'],
        'factors':     data['factors'],
        'calculatedAt': SERVER_TS,
    })
    # Also patch user doc
    db.collection('users').document(uid).update({
        'riskScore': data['riskScore'],
        'riskLevel': data['riskLevel'],
        'counsellorId': counsellor_uid,
    })

# ── Mood Logs ─────────────────────────────────────────────────────────────────
mood_map = {s1_uid: [6,7,7,8,6], s2_uid: [9,9,8,9,10], s3_uid: [3,2,4,3,2]}
for uid, moods in mood_map.items():
    for i, score in enumerate(moods):
        date = (base_date + datetime.timedelta(days=i*5)).isoformat()
        db.collection('moodLogs').add({
            'studentId': uid, 'moodScore': score, 'date': date,
            'customId': student_ids[uid], 'createdAt': SERVER_TS,
        })

# ── Assignments ───────────────────────────────────────────────────────────────
for subject in SUBJECTS:
    db.collection('assignments').add({
        'title':     f'{subject} Assignment 1',
        'subject':   subject,
        'classId':   'CLS0001',
        'teacherId': subject_teacher_map[subject],
        'dueDate':   (datetime.date.today() + datetime.timedelta(days=7)).isoformat(),
        'maxMarks':  20,
        'createdAt': SERVER_TS,
    })

# ── Notes ─────────────────────────────────────────────────────────────────────
for subject in SUBJECTS:
    db.collection('notes').add({
        'title':     f'{subject} -- Chapter 1 Notes',
        'subject':   subject,
        'classId':   'CLS0001',
        'teacherId': subject_teacher_map[subject],
        'fileUrl':   '',
        'createdAt': SERVER_TS,
    })

# ── Counsellor Sessions ──────────────────────────────────────────────────────
db.collection('sessions').add({
    'counsellorId':  counsellor_uid,
    'studentId':     s3_uid,
    'studentName':   'Karan Singh',
    'customId':      'SEP000003',
    'date':          (datetime.date.today() + datetime.timedelta(days=2)).isoformat(),
    'scheduledAt':   (datetime.date.today() + datetime.timedelta(days=2)).isoformat(),
    'status':        'scheduled',
    'notes':         'First session — discuss academic performance',
    'createdAt':     SERVER_TS,
})

# ── Admin Analytics (aggregate pre-computed) ─────────────────────────────────
db.collection('analytics').document('overview').set({
    'userCounts':  {'admin': 1, 'faculty_advisor': 1, 'subject_teacher': 1, 'counsellor': 1, 'student': 3},
    'riskDist':    {'LOW': 2, 'MEDIUM': 0, 'HIGH': 1},
    'recentActivity': [
        {'userName': 'Super Admin',    'role': 'admin',           'action': 'seed_database',  'timestamp': None},
        {'userName': 'Arjun Patel',    'role': 'student',         'action': 'account_created', 'timestamp': None},
        {'userName': 'Sneha Reddy',    'role': 'student',         'action': 'account_created', 'timestamp': None},
        {'userName': 'Karan Singh',    'role': 'student',         'action': 'account_created', 'timestamp': None},
        {'userName': 'Mr. Rohan Mehta','role': 'subject_teacher', 'action': 'class_assigned',  'timestamp': None},
    ],
    'updatedAt': SERVER_TS,
})

# ══════════════════════════════════════════════════════════════════════════════
# DONE — Print credentials table
# ══════════════════════════════════════════════════════════════════════════════
print('\n[4/4] Done! ✅\n')
print('══════════════════════════════════════════════════════════════════════')
print('  CREDENTIALS — use these to log in')
print('══════════════════════════════════════════════════════════════════════')
creds = [
    ('Admin',           'ADP000001', 'admin@edupulse.com',          'Admin'),
    ('Faculty',         'FAP000001', 'faculty@edupulse.com',        'Admin'),
    ('Teacher-Maths',   'TEP000001', 'teacher.maths@edupulse.com',  'Admin'),
    ('Teacher-Physics', 'TEP000002', 'teacher.physics@edupulse.com','Admin'),
    ('Teacher-Chem',    'TEP000003', 'teacher.chem@edupulse.com',   'Admin'),
    ('Teacher-English', 'TEP000004', 'teacher.english@edupulse.com','Admin'),
    ('Teacher-OODP',    'TEP000005', 'teacher.oodp@edupulse.com',   'Admin'),
    ('Counsellor',      'CNP000001', 'counsellor@edupulse.com',     'Admin'),
    ('Student 1',       'SEP000001', 'student1@edupulse.com',       'Admin'),
    ('Student 2',       'SEP000002', 'student2@edupulse.com',       'Admin'),
    ('Student 3',       'SEP000003', 'student3@edupulse.com',       'Admin'),
]
print(f"  {'Role':<14} {'ID':<12} {'Email':<30} {'Password'}")
print(f"  {'-'*14} {'-'*12} {'-'*30} {'-'*14}")
for role, cid, email, pwd in creds:
    print(f'  {role:<14} {cid:<12} {email:<30} {pwd}')
print('══════════════════════════════════════════════════════════════════════')
print('\n  Seeded data summary:')
print('  • 1 class  (CLS0001 — Class 11-A)')
print('  • 5 subjects × 3 students = 15 marks records')
print('  • ~22 working days × 3 students = ~66 attendance records')
print('  • 3 risk scores (LOW, LOW, HIGH)')
print('  • 3 assignments, 2 notes, 1 counselling session')
print('  • Mood logs for all 3 students')
print('\n  Start the app:  python app.py\n')
