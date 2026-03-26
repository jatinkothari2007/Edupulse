"""
EduPulse Video Call Routes — session signaling metadata via Firestore.
WebRTC signaling happens directly client-side via Firestore SDK.
"""
from flask import Blueprint, jsonify, request, g
from firebase_config import db
from firebase_admin import firestore
from routes.auth_middleware import require_auth

videocall_bp = Blueprint('videocall', __name__, url_prefix='/api/videocall')


@videocall_bp.route('/session/<session_id>', methods=['GET'])
@require_auth
def get_session(session_id):
    doc = db.collection('sessions').document(session_id).get()
    if not doc.exists:
        return jsonify({'error': 'Session not found'}), 404
    s = doc.to_dict()
    s['id'] = session_id
    # Normalise sessionId so JS always has it
    if not s.get('sessionId'):
        s['sessionId'] = session_id

    # Verify participant — check both Uid and Id field variants (seed vs new sessions)
    uid = g.uid
    student_match   = (uid == s.get('studentUid') or uid == s.get('studentId'))
    counsellor_match = (uid == s.get('counsellorUid') or uid == s.get('counsellorId'))
    if not student_match and not counsellor_match:
        return jsonify({'error': 'Not a participant'}), 403

    return jsonify(s)


@videocall_bp.route('/session/<session_id>/complete', methods=['PUT'])
@require_auth
def complete_session(session_id):
    data     = request.json or {}
    duration = data.get('duration', 0)
    try:
        db.collection('sessions').document(session_id).update({
            'status'     : 'completed',
            'duration'   : duration,
            'completedAt': firestore.SERVER_TIMESTAMP,
        })
    except Exception:
        pass
    return jsonify({'success': True})


@videocall_bp.route('/student/sessions', methods=['GET'])
@require_auth
def student_sessions():
    uid = g.uid
    sessions = []
    seen_ids = set()
    # Try both field names — new sessions use studentUid, seed data uses studentId
    for field in ('studentUid', 'studentId'):
        try:
            docs = db.collection('sessions').where(field, '==', uid).stream()
            for d in docs:
                if d.id not in seen_ids:
                    sd = {**d.to_dict(), 'id': d.id}
                    # Normalise sessionId
                    if not sd.get('sessionId'):
                        sd['sessionId'] = d.id
                    sessions.append(sd)
                    seen_ids.add(d.id)
        except Exception:
            pass
    # Sort newest first in Python (no composite index needed)
    sessions.sort(key=lambda s: s.get('scheduledAt', ''), reverse=True)
    return jsonify({'sessions': sessions})
