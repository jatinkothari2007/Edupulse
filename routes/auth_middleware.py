"""
EduPulse Auth Middleware — verifies Firebase ID token from Bearer header.
"""
from functools import wraps
from flask import request, jsonify, g
from firebase_admin import auth as fb_auth
from firebase_config import db
from google.cloud.firestore_v1 import SERVER_TIMESTAMP


def require_auth(f):
    """Decorator: verifies Firebase Bearer token, populates g.uid and g.user_data."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        token = None
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        if not token:
            token = request.args.get('token')
        if not token:
            return jsonify({'error': 'Unauthorized — no token'}), 401

        try:
            decoded = fb_auth.verify_id_token(token)
            g.uid = decoded['uid']
        except Exception as e:
            return jsonify({'error': 'Invalid token', 'details': str(e)}), 401

        # Load user data from Firestore
        user_doc = db.collection('users').document(g.uid).get()
        if not user_doc.exists:
            return jsonify({'error': 'User not found in database'}), 403
        g.user_data = user_doc.to_dict()
        g.user_data['uid'] = g.uid
        return f(*args, **kwargs)
    return decorated


def require_role(*allowed_roles):
    """Decorator: verifies token AND restricts endpoint to specific roles."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # ── 1. Auth check (inline — avoids double-wrapping) ─────────────
            auth_header = request.headers.get('Authorization', '')
            token = None
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
            if not token:
                token = request.args.get('token')
            if not token:
                return jsonify({'error': 'Unauthorized — no token'}), 401

            try:
                decoded = fb_auth.verify_id_token(token)
                g.uid = decoded['uid']
            except Exception as e:
                return jsonify({'error': 'Invalid token', 'details': str(e)}), 401

            user_doc = db.collection('users').document(g.uid).get()
            if not user_doc.exists:
                return jsonify({'error': 'User not found in database'}), 403
            g.user_data = user_doc.to_dict()
            g.user_data['uid'] = g.uid

            # ── 2. Role check ────────────────────────────────────────────────
            role = g.user_data.get('role', '')
            if role not in allowed_roles:
                return jsonify({
                    'error': f'Forbidden — requires role: {", ".join(allowed_roles)}',
                    'yourRole': role,
                }), 403

            return f(*args, **kwargs)
        return decorated
    return decorator


def log_audit(action: str, detail: str, resource_id: str = '') -> None:
    """Write an audit log entry to Firestore. Non-blocking — swallows errors."""
    try:
        uid = getattr(g, 'uid', 'system')
        db.collection('auditLogs').add({
            'uid':        uid,
            'action':     action,
            'detail':     detail,
            'resourceId': resource_id,
            'timestamp':  SERVER_TIMESTAMP,
        })
    except Exception:
        pass  # audit failure must never break a request
