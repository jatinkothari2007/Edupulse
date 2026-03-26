"""
EduPulse Messaging Routes — AES-encrypted real-time messaging via Firestore.
"""
from flask import Blueprint, jsonify, request, g
from firebase_config import db
from firebase_admin import firestore
from routes.auth_middleware import require_auth
from utils.notifier import notify_message_received
import datetime, uuid

messaging_bp = Blueprint('messaging', __name__, url_prefix='/api/messaging')

# Who can message whom
ALLOWED_TARGETS = {
    'admin'          : ['admin', 'faculty_advisor', 'subject_teacher', 'counsellor', 'student'],
    'faculty_advisor': ['admin', 'student', 'subject_teacher', 'counsellor'],
    'subject_teacher': ['admin', 'faculty_advisor', 'student'],
    'counsellor'     : ['faculty_advisor', 'student'],
    'student'        : ['admin', 'counsellor', 'faculty_advisor', 'subject_teacher'],
}


@messaging_bp.route('/conversations', methods=['GET'])
@require_auth
def list_conversations():
    uid  = g.uid
    role = g.user_data.get('role', '')
    # Single-field query only — order_by would require a composite index
    docs = db.collection('conversations') \
             .where('participants', 'array_contains', uid) \
             .limit(50).stream()
    convs = []
    for d in docs:
        conv = d.to_dict()
        conv['id'] = d.id
        # Convert SERVER_TIMESTAMP to a sortable string
        ts = conv.get('lastTimestamp')
        conv['_ts'] = ts.timestamp() if hasattr(ts, 'timestamp') else 0
        convs.append(conv)
    # Sort in Python
    convs.sort(key=lambda c: c['_ts'], reverse=True)
    return jsonify({'conversations': convs})


@messaging_bp.route('/conversations/<conv_id>/messages', methods=['GET'])
@require_auth
def get_messages(conv_id):
    # Verify participant
    conv_doc = db.collection('conversations').document(conv_id).get()
    if not conv_doc.exists:
        return jsonify({'error': 'Conversation not found'}), 404
    if g.uid not in conv_doc.to_dict().get('participants', []):
        return jsonify({'error': 'Not a participant'}), 403

    # No order_by — sort in Python to avoid composite index requirement
    raw = db.collection('conversations').document(conv_id) \
             .collection('messages').limit(200).stream()
    messages = []
    for d in raw:
        m = {**d.to_dict(), 'id': d.id}
        ts = m.get('timestamp')
        m['_ts'] = ts.timestamp() if hasattr(ts, 'timestamp') else 0
        messages.append(m)
    messages.sort(key=lambda x: x['_ts'])
    return jsonify({'messages': messages})


@messaging_bp.route('/conversations', methods=['POST'])
@require_auth
def start_conversation():
    data       = request.json or {}
    target_uid = data.get('targetUid', '')
    if not target_uid:
        return jsonify({'error': 'targetUid required'}), 400
    if target_uid == g.uid:
        return jsonify({'error': 'Cannot message yourself'}), 400

    # Role check
    my_role = g.user_data.get('role', '')
    target_doc = db.collection('users').document(target_uid).get()
    if not target_doc.exists:
        return jsonify({'error': 'Target user not found'}), 404
    target_role = target_doc.to_dict().get('role', '')
    allowed = ALLOWED_TARGETS.get(my_role, [])
    if target_role not in allowed:
        return jsonify({'error': f'{my_role} cannot message {target_role}'}), 403

    # Check if conv already exists
    existing = db.collection('conversations') \
                 .where('participants', 'array_contains', g.uid).stream()
    for d in existing:
        conv = d.to_dict()
        parts = conv.get('participants', [])
        if target_uid in parts and len(parts) == 2 and not conv.get('isAI'):
            return jsonify({'conversationId': d.id})

    # Create new conversation
    conv_id = str(uuid.uuid4())
    db.collection('conversations').document(conv_id).set({
        'participants'    : [g.uid, target_uid],
        'participantNames': {
            g.uid     : g.user_data.get('name', ''),
            target_uid: target_doc.to_dict().get('name', ''),
        },
        'lastMessage' : '',
        'lastTimestamp': firestore.SERVER_TIMESTAMP,
        'isAI'        : False,
    })
    return jsonify({'conversationId': conv_id}), 201


@messaging_bp.route('/conversations/<conv_id>/messages', methods=['POST'])
@require_auth
def send_message(conv_id):
    data = request.json or {}
    encrypted_text = data.get('text', '')
    if not encrypted_text:
        return jsonify({'error': 'text required'}), 400

    conv_doc = db.collection('conversations').document(conv_id).get()
    if not conv_doc.exists:
        return jsonify({'error': 'Conversation not found'}), 404
    conv = conv_doc.to_dict()
    if g.uid not in conv.get('participants', []):
        return jsonify({'error': 'Not a participant'}), 403

    msg_id = str(uuid.uuid4())
    db.collection('conversations').document(conv_id) \
      .collection('messages').document(msg_id).set({
          'id'        : msg_id,
          'senderId'  : g.uid,
          'senderName': g.user_data.get('name', ''),
          'text'      : encrypted_text,
          'encrypted' : True,
          'timestamp' : firestore.SERVER_TIMESTAMP,
          'isRead'    : False,
      })

    # Update conversation last message
    preview = '🔒 Encrypted message'
    db.collection('conversations').document(conv_id).update({
        'lastMessage'  : preview,
        'lastTimestamp': firestore.SERVER_TIMESTAMP,
        'lastSenderId' : g.uid,
    })

    # Notify the other participant
    participants = conv.get('participants', [])
    for p in participants:
        if p != g.uid:
            notify_message_received(p, g.user_data.get('name', 'Someone'), 'You have a new message.')
    
    return jsonify({'success': True, 'messageId': msg_id})


@messaging_bp.route('/conversations/<conv_id>/messages/<msg_id>/read', methods=['PUT'])
@require_auth
def mark_read(conv_id, msg_id):
    db.collection('conversations').document(conv_id) \
      .collection('messages').document(msg_id).update({'isRead': True})
    return jsonify({'success': True})


@messaging_bp.route('/contacts', methods=['GET'])
@require_auth
def get_contacts():
    """Return messageable contacts based on role."""
    my_role = g.user_data.get('role', '')
    allowed_roles = ALLOWED_TARGETS.get(my_role, [])

    contacts = []
    for role in allowed_roles:
        if role == 'student' and my_role == 'student':
            continue  # students can't message other students
        query = db.collection('users').where('role', '==', role)
        # For student: only their FA and counsellor
        # For student: scope to their class contacts only
        if my_role == 'student':
            class_id = g.user_data.get('classId', '')
            cls_data = {}
            if class_id:
                cls_doc = db.collection('classes').document(class_id).get()
                cls_data = cls_doc.to_dict() if cls_doc.exists else {}

            if role == 'faculty_advisor':
                # Try faUid on user doc first, then class doc
                fa_uid = g.user_data.get('faUid') or cls_data.get('facultyAdvisorId') or cls_data.get('advisorId', '')
                if fa_uid:
                    doc = db.collection('users').document(fa_uid).get()
                    if doc.exists:
                        u = doc.to_dict()
                        contacts.append({'uid': fa_uid, 'name': u.get('name'), 'role': role, 'customId': u.get('customId')})
                continue

            elif role == 'counsellor':
                # Try counsellorUid on user doc first, then class doc
                c_uid = g.user_data.get('counsellorUid') or cls_data.get('counsellorId', '')
                if c_uid:
                    doc = db.collection('users').document(c_uid).get()
                    if doc.exists:
                        u = doc.to_dict()
                        contacts.append({'uid': c_uid, 'name': u.get('name'), 'role': role, 'customId': u.get('customId')})
                continue

            elif role == 'subject_teacher':
                # Fetch only teachers assigned to the student's class
                teacher_ids = cls_data.get('teacherIds', [])
                for t_uid in teacher_ids:
                    if t_uid == g.uid:
                        continue
                    doc = db.collection('users').document(t_uid).get()
                    if doc.exists:
                        u = doc.to_dict()
                        if u.get('role') == 'subject_teacher':
                            contacts.append({'uid': t_uid, 'name': u.get('name'), 'role': role,
                                             'customId': u.get('customId'), 'subject': u.get('subject', '')})
                continue

        # Generic: fetch all users with this role
        docs = query.stream()
        for d in docs:
            if d.id == g.uid:
                continue
            u = d.to_dict()
            contacts.append({'uid': d.id, 'name': u.get('name'), 'role': role, 'customId': u.get('customId')})

    return jsonify({'contacts': contacts})
