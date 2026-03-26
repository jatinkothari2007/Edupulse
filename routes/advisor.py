from flask import Blueprint, jsonify, request, g
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from routes.auth_middleware import require_auth, require_role, log_audit
from firebase_config import db

advisor_bp = Blueprint('advisor', __name__)


@advisor_bp.route('/api/advisor/classes', methods=['GET'])
@require_role('admin', 'faculty_advisor')
def get_classes():
    try:
        docs = db.collection('classes').stream()
        classes = []
        for d in docs:
            c = d.to_dict()
            c['id'] = d.id
            classes.append(c)
        return jsonify({'success': True, 'data': classes})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@advisor_bp.route('/api/advisor/classes', methods=['POST'])
@require_role('admin', 'faculty_advisor')
def create_class():
    try:
        data = request.get_json() or {}
        if not data.get('name'):
            return jsonify({'success': False, 'error': 'Class name is required'}), 400
        doc = {
            'name':              data['name'],
            'description':       data.get('description', ''),
            'facultyAdvisorId':  data.get('facultyAdvisorId', ''),
            'advisorId':         g.uid,
            'counsellorId':      data.get('counsellorId', ''),
            'students':          data.get('students', []),
            'createdAt':         SERVER_TIMESTAMP,
            'createdBy':         g.uid,
        }
        ref = db.collection('classes').add(doc)
        log_audit('create_class', f'Created class {data["name"]}', ref[1].id)
        return jsonify({'success': True, 'data': {'id': ref[1].id}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@advisor_bp.route('/api/advisor/classes/<class_id>', methods=['PUT'])
@require_role('admin', 'faculty_advisor')
def update_class(class_id):
    try:
        data = request.get_json() or {}
        allowed = ['name', 'description', 'facultyAdvisorId', 'counsellorId', 'students']
        updates = {k: v for k, v in data.items() if k in allowed}
        updates['updatedAt'] = SERVER_TIMESTAMP
        db.collection('classes').document(class_id).update(updates)
        log_audit('update_class', f'Updated class {class_id}', class_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@advisor_bp.route('/api/advisor/risk-overview', methods=['GET'])
@require_role('admin', 'faculty_advisor')
def risk_overview():
    try:
        risks = list(db.collection('riskScores').stream())
        data = []
        for r in risks:
            rd = r.to_dict()
            rd['id'] = r.id
            # Attach student name
            user_doc = db.collection('users').document(r.id).get()
            if user_doc.exists:
                ud = user_doc.to_dict()
                rd['studentName'] = ud.get('name', '')
                rd['studentEmail'] = ud.get('email', '')
                rd['classId'] = ud.get('classId', '')
            data.append(rd)
        data.sort(key=lambda x: x.get('riskScore', 0), reverse=True)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@advisor_bp.route('/api/advisor/polls', methods=['POST'])
@require_role('admin', 'faculty_advisor')
def create_poll():
    try:
        data = request.get_json() or {}
        if not data.get('question') or not data.get('options'):
            return jsonify({'success': False, 'error': 'Question and options required'}), 400
        doc = {
            'question':  data['question'],
            'options':   [{'text': o, 'votes': []} for o in data['options']],
            'classId':   data.get('classId', ''),
            'createdBy': g.uid,
            'isActive':  True,
            'createdAt': SERVER_TIMESTAMP,
        }
        ref = db.collection('polls').add(doc)
        log_audit('create_poll', f'Created poll: {data["question"]}', ref[1].id)
        return jsonify({'success': True, 'data': {'id': ref[1].id}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@advisor_bp.route('/api/advisor/polls', methods=['GET'])
@require_role('admin', 'faculty_advisor')
def get_polls():
    try:
        docs = db.collection('polls').stream()
        polls = []
        for d in docs:
            p = d.to_dict()
            p['id'] = d.id
            polls.append(p)
        return jsonify({'success': True, 'data': polls})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@advisor_bp.route('/api/advisor/announcements', methods=['POST'])
@require_role('admin', 'faculty_advisor')
def post_announcement():
    try:
        data = request.get_json() or {}
        if not data.get('title') or not data.get('message'):
            return jsonify({'success': False, 'error': 'Title and message required'}), 400
        doc = {
            'title':     data['title'],
            'message':   data['message'],
            'classId':   data.get('classId', ''),
            'createdBy': g.uid,
            'createdAt': SERVER_TIMESTAMP,
        }
        ref = db.collection('announcements').add(doc)
        log_audit('create_announcement', data['title'], ref[1].id)
        return jsonify({'success': True, 'data': {'id': ref[1].id}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
