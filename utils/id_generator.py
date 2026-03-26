"""
EduPulse ID Generator — Sequential custom IDs using Firestore transactions.
"""
from firebase_config import db
from google.cloud import firestore as gc_firestore


def generate_id(prefix: str, digits: int) -> str:
    """
    Generates next sequential custom ID.
    Reads current counter from Firestore counters collection.
    Increments atomically using Firestore transaction.
    Returns formatted ID string like 'SEP000001'.
    """
    counter_ref = db.collection('counters').document(prefix)

    @gc_firestore.transactional
    def update_counter(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        current  = snapshot.get('count') if snapshot.exists else 0
        next_val = current + 1
        transaction.set(ref, {'count': next_val})
        return next_val

    txn      = db.transaction()
    next_num = update_counter(txn, counter_ref)
    return f"{prefix}{str(next_num).zfill(digits)}"


# ── Convenience helpers ───────────────────────────────
def student_id()   -> str: return generate_id('SEP', 6)
def teacher_id()   -> str: return generate_id('TEP', 6)
def fa_id()        -> str: return generate_id('FAP', 6)
def counsellor_id()-> str: return generate_id('CNP', 6)
def admin_id()     -> str: return generate_id('ADP', 6)
def class_id()     -> str: return generate_id('CLS', 4)
def quiz_id()      -> str: return generate_id('QIZ', 6)
def assignment_id()-> str: return generate_id('ASN', 6)
def session_id()   -> str: return generate_id('SES', 6)

SUBJECT_IDS = {
    'maths'    : 'MAT0001',
    'oodp'     : 'OODP0001',
    'english'  : 'ENG0001',
    'chemistry': 'CHE0001',
    'physics'  : 'PHY0001',
}
