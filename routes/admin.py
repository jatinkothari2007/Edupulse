"""
EduPulse Admin Routes — full user management, analytics, audit logs.
"""
from flask import Blueprint, jsonify, request, g
from firebase_admin import auth as fb_auth
from firebase_config import db
from firebase_admin import firestore
from routes.auth_middleware import require_role
from utils.id_generator import (
    student_id, teacher_id, fa_id, counsellor_id, admin_id
)
from utils.notifier import send_notification
import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

ROLE_ID_MAP = {
    'student'        : student_id,
    'subject_teacher': teacher_id,
    'faculty_advisor': fa_id,
    'counsellor'     : counsellor_id,
    'admin'          : admin_id,
}


@admin_bp.route('/users', methods=['GET'])
@require_role('admin')
def list_users():
    role = request.args.get('role')
    query = db.collection('users')
    if role:
        query = query.where('role', '==', role)
    docs = query.stream()
    users = []
    for d in docs:
        u = d.to_dict()
        u['uid'] = d.id
        u.pop('passwordHash', None)
        users.append(u)
    return jsonify({'users': users})


@admin_bp.route('/users', methods=['POST'])
@require_role('admin')
def create_user():
    data = request.json or {}
    required = ['name', 'email', 'password', 'role']
    for f_name in required:
        if not data.get(f_name):
            return jsonify({'error': f'Missing field: {f_name}'}), 400

    role = data['role']
    if role not in ROLE_ID_MAP:
        return jsonify({'error': f'Invalid role: {role}'}), 400

    id_fn   = ROLE_ID_MAP[role]
    cust_id = id_fn()

    try:
        fb_user = fb_auth.create_user(
            email=data['email'],
            password=data['password'],
            display_name=data['name'],
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    user_record = {
        'uid'       : fb_user.uid,
        'customId'  : cust_id,
        'name'      : data['name'],
        'email'     : data['email'],
        'role'      : role,
        'postTitle' : data.get('postTitle', ''),
        'active'    : True,
        'createdAt' : firestore.SERVER_TIMESTAMP,
        'createdBy' : g.uid,
    }
    # Role-specific extras
    if role == 'subject_teacher':
        user_record['subject'] = data.get('subject', '')
        user_record['subjectId'] = data.get('subjectId', '')
    if role == 'student':
        user_record['classId']   = data.get('classId', '')
        user_record['className'] = data.get('className', '')

    db.collection('users').document(fb_user.uid).set(user_record)

    # Audit log
    db.collection('auditLogs').add({
        'action'    : 'user_created',
        'targetUid' : fb_user.uid,
        'targetRole': role,
        'customId'  : cust_id,
        'performedBy': g.uid,
        'timestamp' : firestore.SERVER_TIMESTAMP,
    })

    # Welcome notification
    send_notification(
        to_uid=fb_user.uid,
        notif_type='account_created',
        title='Welcome to EduPulse! 🎉',
        message=f'Your account has been created. Your ID is {cust_id}.',
        priority='low',
        play_sound=False,
    )

    return jsonify({'success': True, 'uid': fb_user.uid, 'customId': cust_id}), 201


@admin_bp.route('/users/<uid>', methods=['GET'])
@require_role('admin')
def get_user(uid):
    doc = db.collection('users').document(uid).get()
    if not doc.exists:
        return jsonify({'error': 'User not found'}), 404
    u = doc.to_dict()
    u['uid'] = uid
    u.pop('passwordHash', None)
    return jsonify(u)


@admin_bp.route('/users/<uid>/deactivate', methods=['PUT'])
@require_role('admin')
def deactivate_user(uid):
    db.collection('users').document(uid).update({'active': False})
    fb_auth.update_user(uid, disabled=True)
    db.collection('auditLogs').add({
        'action': 'user_deactivated', 'targetUid': uid,
        'performedBy': g.uid, 'timestamp': firestore.SERVER_TIMESTAMP,
    })
    return jsonify({'success': True})


@admin_bp.route('/users/<uid>/reactivate', methods=['PUT'])
@require_role('admin')
def reactivate_user(uid):
    db.collection('users').document(uid).update({'active': True})
    fb_auth.update_user(uid, disabled=False)
    return jsonify({'success': True})


@admin_bp.route('/users/<uid>/reset-password', methods=['POST'])
@require_role('admin')
def reset_password(uid):
    data = request.json or {}
    new_pass = data.get('password', '')
    if len(new_pass) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    fb_auth.update_user(uid, password=new_pass)
    return jsonify({'success': True})


@admin_bp.route('/analytics', methods=['GET'])
@require_role('admin')
def analytics():
    counts = {}
    for role in ['admin', 'faculty_advisor', 'subject_teacher', 'counsellor', 'student']:
        docs = db.collection('users').where('role', '==', role).stream()
        counts[role] = sum(1 for _ in docs)

    risk_docs = db.collection('riskScores').stream()
    risk_dist = {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0}
    for d in risk_docs:
        lvl = d.to_dict().get('riskLevel', 'LOW').upper()
        if lvl in risk_dist:
            risk_dist[lvl] += 1

    audit_docs = db.collection('auditLogs') \
                   .order_by('timestamp', direction=firestore.Query.DESCENDING) \
                   .limit(20).stream()
    recent_activity = [{**d.to_dict(), 'id': d.id} for d in audit_docs]

    return jsonify({
        'userCounts'    : counts,
        'riskDist'      : risk_dist,
        'recentActivity': recent_activity,
    })


@admin_bp.route('/audit-logs', methods=['GET'])
@require_role('admin')
def audit_logs():
    docs = db.collection('auditLogs') \
             .order_by('timestamp', direction=firestore.Query.DESCENDING) \
             .limit(100).stream()
    logs = [{**d.to_dict(), 'id': d.id} for d in docs]
    return jsonify({'logs': logs})


@admin_bp.route('/broadcast', methods=['POST'])
@require_role('admin')
def broadcast_message():
    data = request.json or {}
    title   = data.get('title', 'Message from Admin')
    message = data.get('message', '')
    roles   = data.get('roles', [])  # empty = all

    query = db.collection('users')
    if roles:
        query = query.where('role', 'in', roles)
    docs = query.stream()
    sent = 0
    for d in docs:
        uid = d.id
        if uid == g.uid:
            continue
        send_notification(
            to_uid=uid, notif_type='broadcast',
            title=title, message=message,
            from_uid=g.uid, from_role='admin',
            priority='medium', play_sound=True,
        )
        sent += 1
    return jsonify({'success': True, 'sent': sent})


@admin_bp.route('/login-activity', methods=['GET'])
@require_role('admin')
def login_activity():
    """Return per-user login count and last login time."""
    by_user = {}

    # Try loginLogs collection — may be missing or lack an index
    try:
        logs_snap = db.collection('loginLogs').order_by(
            'timestamp', direction=firestore.Query.DESCENDING
        ).limit(500).stream()
        for doc in logs_snap:
            d   = doc.to_dict()
            uid = d.get('uid', '')
            if not uid:
                continue
            if uid not in by_user:
                by_user[uid] = {
                    'uid'       : uid,
                    'name'      : d.get('name', ''),
                    'customId'  : d.get('customId', ''),
                    'role'      : d.get('role', ''),
                    'loginCount': 0,
                    'lastLogin' : None,
                }
            by_user[uid]['loginCount'] = by_user[uid]['loginCount'] + 1
            ts = d.get('timestamp')
            if ts and (by_user[uid]['lastLogin'] is None or ts > by_user[uid]['lastLogin']):
                by_user[uid]['lastLogin'] = ts
    except Exception:
        by_user = {}

    # Always fill from users collection (limited to 300 to prevent scan timeouts)
    try:
        users_snap = db.collection('users').limit(300).stream()
        for doc in users_snap:
            d   = doc.to_dict()
            uid = doc.id
            if uid not in by_user:
                by_user[uid] = {
                    'uid'       : uid,
                    'name'      : d.get('name', ''),
                    'customId'  : d.get('customId', ''),
                    'role'      : d.get('role', ''),
                    'loginCount': int(d.get('loginCount') or 0),
                    'lastLogin' : d.get('lastLogin'),
                }
            else:
                if not by_user[uid]['name']:     by_user[uid]['name']     = d.get('name', '')
                if not by_user[uid]['customId']: by_user[uid]['customId'] = d.get('customId', '')
                if not by_user[uid]['role']:     by_user[uid]['role']     = d.get('role', '')
    except Exception as e:
        if not by_user:
            return jsonify({'error': str(e), 'activity': []}), 200

    # Serialise timestamps to ISO strings
    result = []
    for u in by_user.values():
        ts = u.get('lastLogin')
        if ts is not None:
            try:
                u['lastLogin'] = ts.isoformat()
            except Exception:
                try:
                    u['lastLogin'] = str(ts)
                except Exception:
                    u['lastLogin'] = None
        result.append(u)

    result.sort(key=lambda x: x.get('lastLogin') or '', reverse=True)
    return jsonify({'activity': result})



