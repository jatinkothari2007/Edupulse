"""
add_high_risk_students.py — Adds two HIGH-risk students to EduPulse DB.
Does NOT touch existing users. Run: python add_high_risk_students.py
"""
from dotenv import load_dotenv
load_dotenv()

import os, json, datetime
import firebase_admin
from firebase_admin import credentials, auth as fb_auth, firestore as fb_firestore

# Init Firebase Admin
sa_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
if not sa_json:
    raise RuntimeError('FIREBASE_SERVICE_ACCOUNT_JSON not set in .env')

cred = credentials.Certificate(json.loads(sa_json))
try:
    firebase_admin.initialize_app(cred)
except ValueError:
    pass  # already initialized

db = fb_firestore.client()
SERVER_TS = fb_firestore.SERVER_TIMESTAMP

# ── Increment SEP counter ─────────────────────────────────────────────────────
counter_ref = db.collection('counters').document('SEP')
counter_doc = counter_ref.get()
current_count = counter_doc.to_dict().get('count', 3) if counter_doc.exists else 3
new_id_4 = current_count + 1
new_id_5 = current_count + 2
customId_4 = f'SEP{str(new_id_4).zfill(6)}'
customId_5 = f'SEP{str(new_id_5).zfill(6)}'
counter_ref.set({'count': new_id_5})

# ── Student definitions ───────────────────────────────────────────────────────
STUDENTS = [
    {
        'email':      f'riya.sharma@edupulse.com',
        'password':   'Admin1',
        'name':       'Riya Sharma',
        'customId':   customId_4,
        'rollNumber': str(new_id_4).zfill(3),
        'gender':     'Female',
        'dob':        '2005-06-14',
    },
    {
        'email':      f'dev.patel@edupulse.com',
        'password':   'Admin1',
        'name':       'Dev Patel',
        'customId':   customId_5,
        'rollNumber': str(new_id_5).zfill(3),
        'gender':     'Male',
        'dob':        '2006-02-28',
    },
]

SUBJECTS = ['Mathematics', 'Physics', 'Chemistry', 'English', 'OODP']

created = []
for s in STUDENTS:
    print(f"\n→ Creating {s['name']} ({s['customId']})…")

    # Create Firebase Auth user
    fb_user = fb_auth.create_user(
        email=s['email'],
        password=s['password'],
        display_name=s['name'],
    )
    uid = fb_user.uid

    # Firestore user profile
    db.collection('users').document(uid).set({
        'email':      s['email'],
        'name':       s['name'],
        'role':       'student',
        'active':     True,
        'customId':   s['customId'],
        'rollNumber': s['rollNumber'],
        'classId':    'CLS0001',
        'gender':     s['gender'],
        'dob':        s['dob'],
        'createdAt':  SERVER_TS,
    })

    # Add to class student list
    db.collection('classes').document('CLS0001').update({
        'students': fb_firestore.ArrayUnion([uid]),
        'studentCount': fb_firestore.Increment(1),
    })

    # Marks — low scores to justify HIGH risk
    scores = [28, 34, 22, 41, 30]  # out of 100 — clearly failing
    score_map = dict(zip(SUBJECTS, scores))

    # Fetch teacher IDs from existing class
    cls_doc = db.collection('classes').document('CLS0001').get().to_dict() or {}

    for i, subject in enumerate(SUBJECTS):
        db.collection('marks').add({
            'studentId':   uid,
            'customId':    s['customId'],
            'studentName': s['name'],
            'classId':     'CLS0001',
            'subject':     subject,
            'score':       scores[i],
            'maxScore':    100,
            'type':        'Unit Test 1',
            'term':        'Term 1',
            'createdAt':   SERVER_TS,
        })

    # Attendance — poor (40% attendance)
    today = datetime.date.today()
    for day_offset in range(20):
        d = today - datetime.timedelta(days=day_offset)
        if d.weekday() >= 5:
            continue
        db.collection('attendance').add({
            'studentId':   uid,
            'customId':    s['customId'],
            'studentName': s['name'],
            'classId':     'CLS0001',
            'date':        d.isoformat(),
            'status':      'absent' if day_offset % 3 != 0 else 'present',  # ~33% present
            'createdAt':   SERVER_TS,
        })

    # Mood logs — consistently distressed
    moods = ['distressed', 'anxious', 'overwhelmed', 'sad', 'burned_out']
    for i in range(7):
        d = today - datetime.timedelta(days=i)
        db.collection('moodLogs').add({
            'studentId': uid,
            'customId':  s['customId'],
            'mood':      moods[i % len(moods)],
            'note':      'Feeling very behind on coursework',
            'date':      d.isoformat(),
            'createdAt': SERVER_TS,
        })

    # Risk score — HIGH
    db.collection('riskScores').document(uid).set({
        'studentId':   uid,
        'customId':    s['customId'],
        'studentName': s['name'],
        'classId':     'CLS0001',
        'riskLevel':   'HIGH',
        'riskScore':   88 + (2 * STUDENTS.index(s)),   # 88 / 90
        'factors': {
            'marks':       0.28,   # 28% avg marks
            'attendance':  0.33,   # 33% attendance
            'mood':        0.85,   # mostly distressed
        },
        'calculatedAt': SERVER_TS,
    })

    created.append({'uid': uid, 'name': s['name'], 'customId': s['customId'], 'email': s['email']})
    print(f"  ✓ Created | UID: {uid} | Risk: HIGH | Marks avg: ~31%")

print('\n══════════════════════════════════════════')
print('  Done! Two HIGH-risk students added.')
print('══════════════════════════════════════════')
for c in created:
    print(f"  {c['customId']}  {c['name']:<18}  {c['email']}  password: Admin1")
print()
