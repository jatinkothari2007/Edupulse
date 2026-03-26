"""
EduPulse Auth Routes — login verification, user profile, sign-out.
"""
from flask import Blueprint, jsonify, request, g
from firebase_admin import auth as fb_auth
from firebase_config import db
from routes.auth_middleware import require_auth

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/me')
@require_auth
def get_me():
    """Returns current user's Firestore profile."""
    return jsonify(g.user_data)


@auth_bp.route('/verify-role', methods=['POST'])
@require_auth
def verify_role():
    """Verify that the user's role matches the selected role from portal."""
    data = request.json or {}
    selected_role = data.get('role', '').lower()
    actual_role   = g.user_data.get('role', '').lower()

    role_map = {
        'admin'          : 'admin',
        'faculty_advisor': 'faculty_advisor',
        'faculty advisor': 'faculty_advisor',
        'subject_teacher': 'subject_teacher',
        'subject teacher': 'subject_teacher',
        'counsellor'     : 'counsellor',
        'student'        : 'student',
    }
    norm_selected = role_map.get(selected_role, selected_role)
    norm_actual   = role_map.get(actual_role, actual_role)

    if norm_selected != norm_actual:
        return jsonify({'match': False, 'role': actual_role,
                        'error': f'This account is a {actual_role}, not a {selected_role}.'}), 403
    return jsonify({'match': True, 'role': actual_role, 'user': g.user_data})
