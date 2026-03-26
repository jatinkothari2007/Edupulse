"""
EduPulse Quiz Routes — faculty quiz management, student quiz taking.
(Most quiz logic is in faculty.py and student.py — this is for shared endpoints.)
"""
from flask import Blueprint, jsonify, request, g
from firebase_config import db
from routes.auth_middleware import require_auth

quiz_bp = Blueprint('quiz', __name__, url_prefix='/api/quiz')


@quiz_bp.route('/<qid>', methods=['GET'])
@require_auth
def get_quiz(qid):
    doc = db.collection('quizzes').document(qid).get()
    if not doc.exists:
        return jsonify({'error': 'Quiz not found'}), 404
    q = doc.to_dict()
    q['id'] = qid
    # Strip correct answers if student
    role = g.user_data.get('role', '')
    if role == 'student':
        for ques in q.get('questions', []):
            ques.pop('correct', None)
    return jsonify(q)
