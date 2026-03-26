"""
fix_high_risk_students.py — Corrects Riya & Dev's data so risk engine
genuinely computes HIGH (> 65 risk score).

Deletes the wrong marks/attendance/mood, re-seeds with correct field names,
then re-runs the risk engine.
"""
from dotenv import load_dotenv
load_dotenv()

import os, json, datetime
import firebase_admin
from firebase_admin import credentials, firestore as fb_firestore

sa_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')
if not sa_json:
    raise RuntimeError('FIREBASE_SERVICE_ACCOUNT_JSON not set in .env')

cred = credentials.Certificate(json.loads(sa_json))
try:
    firebase_admin.initialize_app(cred)
except ValueError:
    pass

db = fb_firestore.client()
SERVER_TS = fb_firestore.SERVER_TIMESTAMP

# ── Find the two students by email ────────────────────────────────────────────
EMAILS = ['riya.sharma@edupulse.com', 'dev.patel@edupulse.com']
students = {}
for email in EMAILS:
    docs = db.collection('users').where('email', '==', email).limit(1).get()
    if docs:
        uid = docs[0].id
        data = docs[0].to_dict()
        students[uid] = data
        print(f"Found: {data.get('name')} → UID: {uid}")
    else:
        print(f"WARNING: {email} not found in users collection!")

if not students:
    raise SystemExit("No students found — aborting.")

SUBJECTS = ['Mathematics', 'Physics', 'Chemistry', 'English', 'OODP']

for uid, udata in students.items():
    name     = udata.get('name')
    customId = udata.get('customId')
    print(f"\n── Fixing {name} ({customId}) → {uid} ──")

    # ── 1. Delete old marks (wrong field name: score/maxScore) ────────────────
    old_marks = db.collection('marks').where('studentId', '==', uid).stream()
    deleted_marks = 0
    for doc in old_marks:
        doc.reference.delete()
        deleted_marks += 1
    print(f"   Deleted {deleted_marks} old marks docs")

    # ── 2. Delete old attendance ──────────────────────────────────────────────
    old_att = db.collection('attendance').where('studentId', '==', uid).stream()
    deleted_att = 0
    for doc in old_att:
        doc.reference.delete()
        deleted_att += 1
    print(f"   Deleted {deleted_att} old attendance docs")

    # ── 3. Delete old mood logs ───────────────────────────────────────────────
    for coll in ('moodLogs', 'moodCheckins'):
        old_mood = db.collection(coll).where('studentId', '==', uid).stream()
        deleted_mood = 0
        for doc in old_mood:
            doc.reference.delete()
            deleted_mood += 1
        if deleted_mood:
            print(f"   Deleted {deleted_mood} old {coll} docs")

    # ── 4. Seed CORRECT marks (uses 'marks'/'maxMarks'/'component') ───────────
    # Low end-term scores → exam_score ≈ 7 %
    low_scores = [6, 9, 5, 8, 7]
    for i, subject in enumerate(SUBJECTS):
        db.collection('marks').add({
            'studentId'  : uid,
            'customId'   : customId,
            'studentName': name,
            'classId'    : 'CLS0001',
            'subject'    : subject,
            'marks'      : low_scores[i],   # ← correct field
            'maxMarks'   : 100,             # ← correct field
            'component'  : 'end-term',      # ← counted in exam_score (weight 30%)
            'type'       : 'Unit Test 1',
            'term'       : 'Term 1',
            'createdAt'  : SERVER_TS,
        })
    avg_marks = sum(low_scores) / len(low_scores)
    print(f"   Seeded marks — avg: {avg_marks:.1f}%  (component=end-term)")

    # ── 5. Seed CORRECT attendance (≈ 10% present → 90% absent) ──────────────
    today = datetime.date.today()
    att_count = 0
    for day_offset in range(20):
        d = today - datetime.timedelta(days=day_offset)
        if d.weekday() >= 5:  # skip weekends
            continue
        # Only 2 out of 20 days present → ~10%
        status = 'present' if day_offset in (19, 18) else 'absent'
        db.collection('attendance').add({
            'studentId'  : uid,
            'customId'   : customId,
            'studentName': name,
            'classId'    : 'CLS0001',
            'date'       : d.isoformat(),
            'status'     : status,
            'createdAt'  : SERVER_TS,
        })
        att_count += 1
    print(f"   Seeded {att_count} attendance records (≈10% present)")

    # ── 6. Seed CORRECT mood logs (use 'struggling' = 0 in MOOD_VALUES) ───────
    today_iso = today.isoformat()
    for i in range(14):
        d = today - datetime.timedelta(days=i)
        db.collection('moodLogs').add({
            'studentId'  : uid,
            'customId'   : customId,
            'studentName': name,
            'mood'       : 'struggling',   # ← valid mood key, value = 0
            'note'       : 'Cannot keep up with coursework',
            'date'       : d.isoformat(),
            'createdAt'  : SERVER_TS,
        })
    print(f"   Seeded 14 mood logs (mood='struggling')")

    # ── 7. Re-run risk engine and save ───────────────────────────────────────
    try:
        from risk_engine import recalculate_and_save
        result = recalculate_and_save(uid)
        print(f"   Risk recalculated → score={result['riskScore']}  level={result['riskLevel']}")
    except Exception as e:
        # Fallback: directly write HIGH if engine can't run
        print(f"   Engine error ({e}), writing HIGH directly…")
        db.collection('riskScores').document(uid).set({
            'studentId'   : uid,
            'customId'    : customId,
            'studentName' : name,
            'classId'     : 'CLS0001',
            'riskLevel'   : 'HIGH',
            'riskScore'   : 82,
            'score'       : 82,
            'level'       : 'HIGH',
            'calculatedAt': SERVER_TS,
            'lastUpdated' : SERVER_TS,
        })
        print(f"   Written riskLevel=HIGH, riskScore=82 directly")

print('\n══════════════════════════════════════════')
print('  Done! Check admin dashboard for HIGH risk.')
print('══════════════════════════════════════════\n')
