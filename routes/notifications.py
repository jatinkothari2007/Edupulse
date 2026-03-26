"""
EduPulse Notifications Routes — mark read, mark all read.
"""
from flask import Blueprint, jsonify, request, g
from google.cloud import firestore
from firebase_config import db
from routes.auth_middleware import require_auth

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')


@notifications_bp.route('/', methods=['GET'])
@require_auth
def list_notifications():
    docs = db.collection('notifications').document(g.uid) \
             .collection('items') \
             .order_by('createdAt', direction=firestore.Query.DESCENDING) \
             .limit(50).stream()
    notifs = [{**d.to_dict(), 'id': d.id} for d in docs]
    return jsonify({'notifications': notifs})


@notifications_bp.route('/<notif_id>/read', methods=['PUT'])
@require_auth
def mark_read(notif_id):
    db.collection('notifications').document(g.uid) \
      .collection('items').document(notif_id).update({'isRead': True})
    return jsonify({'success': True})


@notifications_bp.route('/read-all', methods=['PUT'])
@require_auth
def mark_all_read():
    docs = db.collection('notifications').document(g.uid) \
             .collection('items').where('isRead', '==', False).stream()
    batch = db.batch()
    for d in docs:
        batch.update(d.reference, {'isRead': True})
    batch.commit()
    return jsonify({'success': True})
