"""
EduPulse full_seed.py — Optimised batch seeder for a fresh Firebase project.

Improvements over seed.py:
  • All Firestore writes use db.batch() → ~10 API calls instead of 400+
  • Marks use field names 'marks'/'maxMarks'/'component' (matches risk_engine)
  • Mood logs use string 'mood' field (matches moodCheckins schema)
  • Attendance is 1 record per student per day (not 5×subject)
  • Includes 2 high-risk students in one pass (no separate script needed)

USAGE:
    python full_seed.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import os, json, random, datetime
import firebase_admin
from firebase_admin import credentials, auth as fb_auth, firestore as fb_firestore

# ── Firebase init ────────────────────────────────────────────────────────────
sa_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
if not sa_json:
    raise RuntimeError('FIREBASE_SERVICE_ACCOUNT_JSON not set in .env')

cred = credentials.Certificate(json.loads(sa_json))
try:
    firebase_admin.initialize_app(cred)
except ValueError:
    pass   # already initialised

db        = fb_firestore.client()
SERVER_TS = fb_firestore.SERVER_TIMESTAMP

print('\n══════════════════════════════════════════════')
print('  EduPulse Optimised Batch Seed (full_seed.py)')
print('══════════════════════════════════════════════\n')

# ════════════════════════════════════════════════════════════════════════════
# Batch-write helper  (Firestore max = 500 ops per batch)
# ════════════════════════════════════════════════════════════════════════════
class BatchWriter:
    """Accumulates Firestore set/add ops and flushes every 490 writes."""
    MAX = 490

    def __init__(self):
        self._batch = db.batch()
        self._count = 0
        self._total = 0

    def set(self, ref, data, merge=False):
        self._batch.set(ref, data, merge=merge)
        self._flush_if_full()

    def add(self, col_ref, data):
        ref = col_ref.document()          # auto-id
        self._batch.set(ref, data)
        self._flush_if_full()
        return ref

    def delete(self, ref):
        self._batch.delete(ref)
        self._flush_if_full()

    def _flush_if_full(self):
        self._count += 1
        self._total += 1
        if self._count >= self.MAX:
            self._batch.commit()
            self._batch = db.batch()
            self._count = 0

    def commit(self):
        if self._count > 0:
            self._batch.commit()
            self._count = 0
        print(f'      ✓ Committed {self._total} Firestore ops')

bw = BatchWriter()

# ════════════════════════════════════════════════════════════════════════════
# STEP 1 — Delete all existing Auth users
# ════════════════════════════════════════════════════════════════════════════
print('[1/5] Deleting existing Firebase Auth users…')
page = fb_auth.list_users()
deleted = 0
while page:
    uids = [u.uid for u in page.users]
    if uids:
        fb_auth.delete_users(uids)
        deleted += len(uids)
    page = page.get_next_page()
print(f'      Deleted {deleted} auth user(s).')

# ════════════════════════════════════════════════════════════════════════════
# STEP 2 — Delete all Firestore collections (batch deletes)
# ════════════════════════════════════════════════════════════════════════════
COLLECTIONS = [
    'users','classes','marks','attendance','assignments','notes','quizzes',
    'riskScores','moodLogs','moodCheckins','sessions','notifications',
    'messages','conversations','counters','analytics','submissions',
    'quizResults','engagementLogs','announcements',
]

print('[2/5] Clearing Firestore collections…')
del_bw = BatchWriter()
for col in COLLECTIONS:
    docs = list(db.collection(col).limit(500).stream())
    while docs:
        for d in docs:
            del_bw.delete(d.reference)
        del_bw.commit()
        del_bw = BatchWriter()
        docs = list(db.collection(col).limit(500).stream())
    print(f'      Cleared: {col}')

# ════════════════════════════════════════════════════════════════════════════
# STEP 3 — Create Firebase Auth users + Firestore profiles
# ════════════════════════════════════════════════════════════════════════════
print('\n[3/5] Creating auth users…')

def make_user(email, password, name, role, extra=None):
    fb_user = fb_auth.create_user(email=email, password=password, display_name=name)
    profile = {'email': email, 'name': name, 'role': role,
               'active': True, 'createdAt': SERVER_TS, **(extra or {})}
    bw.set(db.collection('users').document(fb_user.uid), profile)
    return fb_user.uid

USERS = [
    ('admin@edupulse.com',           'Admin1', 'Super Admin',       'admin',           {'customId': 'ADP000001'}),
    ('faculty@edupulse.com',         'Admin1', 'Dr. Priya Sharma',  'faculty_advisor', {'customId': 'FAP000001', 'department': 'Computer Science'}),
    ('teacher.maths@edupulse.com',   'Admin1', 'Mr. Rohan Mehta',   'subject_teacher', {'customId': 'TEP000001', 'subject': 'Mathematics'}),
    ('teacher.physics@edupulse.com', 'Admin1', 'Ms. Anita Verma',   'subject_teacher', {'customId': 'TEP000002', 'subject': 'Physics'}),
    ('teacher.chem@edupulse.com',    'Admin1', 'Mr. Suresh Nair',   'subject_teacher', {'customId': 'TEP000003', 'subject': 'Chemistry'}),
    ('teacher.english@edupulse.com', 'Admin1', 'Ms. Preethi Iyer',  'subject_teacher', {'customId': 'TEP000004', 'subject': 'English'}),
    ('teacher.oodp@edupulse.com',    'Admin1', 'Mr. Vikram Bose',   'subject_teacher', {'customId': 'TEP000005', 'subject': 'OODP'}),
    ('counsellor@edupulse.com',      'Admin1', 'Ms. Kavita Joshi',  'counsellor',      {'customId': 'CNP000001'}),
    # Regular students
    ('arjun@edupulse.com',       'Admin1', 'Arjun Patel',   'student', {'customId': 'SEP000001', 'rollNumber': '001', 'classId': 'CLS0001', 'gender': 'Male',   'dob': '2005-03-12'}),
    ('sneha@edupulse.com',       'Admin1', 'Sneha Reddy',   'student', {'customId': 'SEP000002', 'rollNumber': '002', 'classId': 'CLS0001', 'gender': 'Female', 'dob': '2005-07-22'}),
    ('karan@edupulse.com',       'Admin1', 'Karan Singh',   'student', {'customId': 'SEP000003', 'rollNumber': '003', 'classId': 'CLS0001', 'gender': 'Male',   'dob': '2006-01-05'}),
    # High-risk students
    ('riya.sharma@edupulse.com', 'Admin1', 'Riya Sharma',   'student', {'customId': 'SEP000006', 'rollNumber': '006', 'classId': 'CLS0001', 'gender': 'Female', 'dob': '2006-02-20'}),
    ('dev.patel@edupulse.com',   'Admin1', 'Dev Patel',     'student', {'customId': 'SEP000007', 'rollNumber': '007', 'classId': 'CLS0001', 'gender': 'Male',   'dob': '2005-11-10'}),
]

created_uids = {}
for (email, pwd, name, role, extra) in USERS:
    uid = make_user(email, pwd, name, role, extra)
    created_uids[email] = uid
    print(f'      ✓ {role:<18} {name:<22} {email}')

bw.commit()
bw = BatchWriter()

# Convenience aliases
admin_uid      = created_uids['admin@edupulse.com']
faculty_uid    = created_uids['faculty@edupulse.com']
t_maths_uid    = created_uids['teacher.maths@edupulse.com']
t_physics_uid  = created_uids['teacher.physics@edupulse.com']
t_chem_uid     = created_uids['teacher.chem@edupulse.com']
t_english_uid  = created_uids['teacher.english@edupulse.com']
t_oodp_uid     = created_uids['teacher.oodp@edupulse.com']
counsellor_uid = created_uids['counsellor@edupulse.com']
s1_uid  = created_uids['arjun@edupulse.com']
s2_uid  = created_uids['sneha@edupulse.com']
s3_uid  = created_uids['karan@edupulse.com']
s4_uid  = created_uids['riya.sharma@edupulse.com']
s5_uid  = created_uids['dev.patel@edupulse.com']

regular_student_uids  = [s1_uid, s2_uid, s3_uid]
highrisk_student_uids = [s4_uid, s5_uid]
all_student_uids      = regular_student_uids + highrisk_student_uids

student_names = {
    s1_uid: 'Arjun Patel', s2_uid: 'Sneha Reddy', s3_uid: 'Karan Singh',
    s4_uid: 'Riya Sharma',  s5_uid: 'Dev Patel',
}
student_ids = {
    s1_uid: 'SEP000001', s2_uid: 'SEP000002', s3_uid: 'SEP000003',
    s4_uid: 'SEP000006', s5_uid: 'SEP000007',
}
teacher_uids_all = [t_maths_uid, t_physics_uid, t_chem_uid, t_english_uid, t_oodp_uid]
subject_teacher_map = {
    'Mathematics': t_maths_uid, 'Physics': t_physics_uid,
    'Chemistry':   t_chem_uid,  'English': t_english_uid, 'OODP': t_oodp_uid,
}
SUBJECTS = ['Mathematics', 'Physics', 'Chemistry', 'English', 'OODP']

# ════════════════════════════════════════════════════════════════════════════
# STEP 4 — Seed data (all batched)
# ════════════════════════════════════════════════════════════════════════════
print('\n[4/5] Seeding data (batched)…')

# ── Counters ──────────────────────────────────────────────────────────────
for code, count in [('ADP',1),('FAP',1),('TEP',5),('CNP',1),('SEP',7),('CLS',1)]:
    bw.set(db.collection('counters').document(code), {'count': count})

# ── Class ─────────────────────────────────────────────────────────────────
bw.set(db.collection('classes').document('CLS0001'), {
    'classId':          'CLS0001',
    'name':             'Class 11 - A',
    'description':      'Senior secondary class A',
    'facultyAdvisorId': faculty_uid,
    'advisorId':        faculty_uid,
    'counsellorId':     counsellor_uid,
    'teacherIds':       teacher_uids_all,
    'students':         all_student_uids,
    'studentCount':     len(all_student_uids),
    'subjects':         SUBJECTS,
    'createdAt':        SERVER_TS,
})

# Update teacher/counsellor docs with classId
for tuid in teacher_uids_all:
    bw.set(db.collection('users').document(tuid),
           {'classId': 'CLS0001', 'classIds': ['CLS0001']}, merge=True)
bw.set(db.collection('users').document(counsellor_uid),
       {'assignedStudents': all_student_uids, 'classIds': ['CLS0001']}, merge=True)

# ── Marks (correct field names for risk_engine) ───────────────────────────
# LOW risk students: high scores / HIGH risk: very low scores
marks_data = {
    s1_uid: [82, 74, 88, 91, 76],   # Arjun — LOW risk
    s2_uid: [95, 90, 88, 97, 93],   # Sneha — LOW risk
    s3_uid: [45, 52, 38, 60, 44],   # Karan — MEDIUM risk
    s4_uid: [ 6,  9,  5,  8,  7],   # Riya  — HIGH risk
    s5_uid: [ 7,  8,  4,  9,  6],   # Dev   — HIGH risk
}
for uid, scores in marks_data.items():
    for i, subject in enumerate(SUBJECTS):
        bw.add(db.collection('marks'), {
            'studentId'  : uid,
            'customId'   : student_ids[uid],
            'studentName': student_names[uid],
            'classId'    : 'CLS0001',
            'subject'    : subject,
            'teacherId'  : subject_teacher_map[subject],
            'marks'      : scores[i],    # ← risk_engine reads 'marks'
            'maxMarks'   : 100,          # ← risk_engine reads 'maxMarks'
            'component'  : 'end-term',   # ← counted in exam_score (weight 30%)
            'type'       : 'Unit Test 1',
            'term'       : 'Term 1',
            'createdAt'  : SERVER_TS,
        })
print('      ✓ Marks seeded (25 records)')

# ── Attendance (1 record/student/day — no per-subject duplication) ────────
today    = datetime.date.today()
base_day = today - datetime.timedelta(days=29)
att_pct  = {
    s1_uid: 0.85, s2_uid: 0.97, s3_uid: 0.55,
    s4_uid: 0.10, s5_uid: 0.10,   # high-risk: nearly always absent
}
att_count = 0
for uid in all_student_uids:
    for offset in range(30):
        d = base_day + datetime.timedelta(days=offset)
        if d.weekday() >= 5:    # skip weekends
            continue
        status = 'present' if random.random() < att_pct[uid] else 'absent'
        bw.add(db.collection('attendance'), {
            'studentId'  : uid,
            'customId'   : student_ids[uid],
            'studentName': student_names[uid],
            'classId'    : 'CLS0001',
            'date'       : d.isoformat(),
            'status'     : status,
            'createdAt'  : SERVER_TS,
        })
        att_count += 1
print(f'      ✓ Attendance seeded ({att_count} records, ~22 days × 5 students)')

# ── Mood logs (string 'mood' field so mood page shows emojis) ────────────
MOOD_MAP = {
    s1_uid: ['good','great','okay','good','great','okay','good'],
    s2_uid: ['great','great','good','great','great','great','good'],
    s3_uid: ['okay','low','okay','low','okay','low','low'],
    s4_uid: ['struggling']*14,   # high-risk
    s5_uid: ['struggling']*14,   # high-risk
}
for uid, moods in MOOD_MAP.items():
    for i, mood in enumerate(moods):
        d = (today - datetime.timedelta(days=i)).isoformat()
        bw.add(db.collection('moodLogs'), {
            'studentId'  : uid,
            'customId'   : student_ids[uid],
            'studentName': student_names[uid],
            'mood'       : mood,   # ← string key, matches moodCheckins schema
            'date'       : d,
            'createdAt'  : SERVER_TS,
        })
print('      ✓ Mood logs seeded')

# ── Risk Scores ───────────────────────────────────────────────────────────
risk_data = {
    s1_uid: (35,  'LOW',    'Arjun Patel'),
    s2_uid: (10,  'LOW',    'Sneha Reddy'),
    s3_uid: (68,  'HIGH',   'Karan Singh'),
    s4_uid: (82,  'HIGH',   'Riya Sharma'),
    s5_uid: (80,  'HIGH',   'Dev Patel'),
}
for uid, (score, level, name) in risk_data.items():
    bw.set(db.collection('riskScores').document(uid), {
        'studentId'  : uid,
        'customId'   : student_ids[uid],
        'studentName': name,
        'classId'    : 'CLS0001',
        'riskScore'  : score,
        'riskLevel'  : level,
        'score'      : score,
        'level'      : level,
        'calculatedAt': SERVER_TS,
        'lastUpdated' : SERVER_TS,
    })
    bw.set(db.collection('users').document(uid),
           {'riskScore': score, 'riskLevel': level, 'counsellorId': counsellor_uid},
           merge=True)
print('      ✓ Risk scores seeded (5 students)')

# ── Assignments (5 subjects) ──────────────────────────────────────────────
from utils.id_generator import assignment_id
for subject in SUBJECTS:
    aid = assignment_id()
    bw.set(db.collection('assignments').document(aid), {
        'assignmentId': aid,
        'title'       : f'{subject} Assignment 1',
        'subject'     : subject,
        'subjectId'   : subject,
        'classId'     : 'CLS0001',
        'teacherUid'  : subject_teacher_map[subject],
        'teacherId'   : subject_teacher_map[subject],
        'dueDate'     : (today + datetime.timedelta(days=7)).isoformat(),
        'maxMarks'    : 20,
        'createdAt'   : SERVER_TS,
    })
print('      ✓ Assignments seeded (5)')

# ── Notes ─────────────────────────────────────────────────────────────────
for subject in SUBJECTS:
    bw.add(db.collection('notes'), {
        'title'    : f'{subject} — Chapter 1 Notes',
        'subject'  : subject,
        'classId'  : 'CLS0001',
        'teacherId': subject_teacher_map[subject],
        'fileUrl'  : '',
        'createdAt': SERVER_TS,
    })
print('      ✓ Notes seeded (5)')

# ── Quiz (one Pulse Quiz for all students) ────────────────────────────────
quiz_id = 'QZ0001'
bw.set(db.collection('quizzes').document(quiz_id), {
    'id'         : quiz_id,
    'title'      : 'Pulse Quiz',
    'classId'    : 'CLS0001',
    'scheduledAt': today.isoformat(),
    'duration'   : 10,
    'questions'  : [
        {'question': 'What is 2 + 2?',                       'options': {'a':'3','b':'4','c':'5','d':'6'},                                         'correct': 'b'},
        {'question': 'Which planet is closest to the sun?',  'options': {'a':'Earth','b':'Mars','c':'Mercury','d':'Venus'},                         'correct': 'c'},
        {'question': 'H2O is the chemical formula for?',     'options': {'a':'Hydrogen','b':'Water','c':'Oxygen','d':'Salt'},                       'correct': 'b'},
        {'question': 'How many sides does a triangle have?', 'options': {'a':'2','b':'3','c':'4','d':'5'},                                          'correct': 'b'},
        {'question': 'What is the capital of France?',       'options': {'a':'Berlin','b':'Madrid','c':'Paris','d':'Rome'},                         'correct': 'c'},
        {'question': 'Which gas do plants absorb from air?', 'options': {'a':'Oxygen','b':'Nitrogen','c':'Carbon Dioxide','d':'Hydrogen'},           'correct': 'c'},
        {'question': 'Speed of light is approximately?',     'options': {'a':'3x10^8 m/s','b':'3x10^6 m/s','c':'3x10^10 m/s','d':'3x10^4 m/s'},   'correct': 'a'},
        {'question': 'Powerhouse of the cell?',              'options': {'a':'Nucleus','b':'Ribosome','c':'Mitochondria','d':'Vacuole'},             'correct': 'c'},
        {'question': 'Which element has symbol Na?',         'options': {'a':'Nitrogen','b':'Sodium','c':'Nickel','d':'Neon'},                      'correct': 'b'},
        {'question': 'Newton is the unit of?',               'options': {'a':'Energy','b':'Power','c':'Force','d':'Mass'},                          'correct': 'c'},
    ],
    'createdAt': SERVER_TS,
})
print('      ✓ Quiz seeded (1)')

# ── Counsellor session ────────────────────────────────────────────────────
bw.add(db.collection('sessions'), {
    'counsellorId': counsellor_uid,
    'studentId'   : s3_uid,
    'studentName' : 'Karan Singh',
    'customId'    : 'SEP000003',
    'date'        : (today + datetime.timedelta(days=2)).isoformat(),
    'scheduledAt' : (today + datetime.timedelta(days=2)).isoformat(),
    'status'      : 'scheduled',
    'notes'       : 'First session — discuss academic performance',
    'createdAt'   : SERVER_TS,
})
print('      ✓ Counsellor session seeded (1)')

# ── Analytics overview ────────────────────────────────────────────────────
bw.set(db.collection('analytics').document('overview'), {
    'userCounts': {'admin':1,'faculty_advisor':1,'subject_teacher':5,'counsellor':1,'student':5},
    'riskDist'  : {'LOW':2,'MEDIUM':1,'HIGH':2},
    'updatedAt' : SERVER_TS,
})

# ── Flush remaining batch ─────────────────────────────────────────────────
bw.commit()

# ════════════════════════════════════════════════════════════════════════════
# STEP 5 — Print credentials
# ════════════════════════════════════════════════════════════════════════════
print('\n[5/5] Done! ✅\n')
print('═'*70)
print('  CREDENTIALS — use these to log in')
print('═'*70)
for role, cid, email, pwd in [
    ('Admin',           'ADP000001', 'admin@edupulse.com',           'Admin1'),
    ('Faculty Advisor', 'FAP000001', 'faculty@edupulse.com',         'Admin1'),
    ('Teacher-Maths',   'TEP000001', 'teacher.maths@edupulse.com',   'Admin1'),
    ('Teacher-Physics', 'TEP000002', 'teacher.physics@edupulse.com', 'Admin1'),
    ('Teacher-Chem',    'TEP000003', 'teacher.chem@edupulse.com',    'Admin1'),
    ('Teacher-English', 'TEP000004', 'teacher.english@edupulse.com', 'Admin1'),
    ('Teacher-OODP',    'TEP000005', 'teacher.oodp@edupulse.com',    'Admin1'),
    ('Counsellor',      'CNP000001', 'counsellor@edupulse.com',      'Admin1'),
    ('Student 1 (LOW)', 'SEP000001', 'arjun@edupulse.com',           'Admin1'),
    ('Student 2 (LOW)', 'SEP000002', 'sneha@edupulse.com',           'Admin1'),
    ('Student 3 (MED)', 'SEP000003', 'karan@edupulse.com',           'Admin1'),
    ('Student 4 (HIGH)','SEP000006', 'riya.sharma@edupulse.com',     'Admin1'),
    ('Student 5 (HIGH)','SEP000007', 'dev.patel@edupulse.com',       'Admin1'),
]:
    print(f"  {role:<18} {cid:<12} {email:<34} {pwd}")
print('═'*70)
print('\n  Summary:')
print('  • 5 students (2 HIGH risk pre-seeded)')
print('  • 25 marks records   (marks/maxMarks/component=end-term)')
print('  • ~110 attendance records (1/student/day, not 5/subject/day)')
print('  • 5+14 mood logs per student (mood=struggling for high-risk)')
print('  • 5 assignments, 5 notes, 1 quiz, 1 session')
print('\n  Start the app:  python app.py\n')
