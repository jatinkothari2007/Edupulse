"""
EduPulse Risk Routes — manual recalculation endpoint.
"""
from flask import Blueprint, jsonify, request, g
from routes.auth_middleware import require_auth, require_role
from risk_engine import recalculate_and_save

risk_bp = Blueprint('risk', __name__, url_prefix='/api/risk')


@risk_bp.route('/recalculate/<student_id>', methods=['POST'])
@require_auth
def recalculate(student_id):
    """Manually trigger risk recalculation for a student."""
    role = g.user_data.get('role', '')
    # Only admin, FA, counsellor or the student themselves
    if role == 'student' and g.uid != student_id:
        return jsonify({'error': 'Forbidden'}), 403
    result = recalculate_and_save(student_id)
    return jsonify(result)


@risk_bp.route('/all', methods=['POST'])
@require_role('admin')
def recalculate_all():
    """Admin: recalculate risk for ALL students."""
    from firebase_config import db
    docs = db.collection('users').where('role', '==', 'student').stream()
    count = 0
    for d in docs:
        try:
            recalculate_and_save(d.id)
            count += 1
        except Exception:
            pass
    return jsonify({'success': True, 'count': count})
