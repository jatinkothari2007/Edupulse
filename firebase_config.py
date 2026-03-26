import firebase_admin
from firebase_admin import credentials, firestore, auth
import os
import json
from dotenv import load_dotenv

load_dotenv()

# Support both inline JSON and file path for credentials
_cred_path = os.environ.get('FIREBASE_ADMIN_CREDENTIALS_PATH')
_cred_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON')

if _cred_path and os.path.exists(_cred_path):
    cred = credentials.Certificate(_cred_path)
elif _cred_json:
    cred = credentials.Certificate(json.loads(_cred_json))
else:
    raise RuntimeError(
        "No Firebase credentials found. Set FIREBASE_ADMIN_CREDENTIALS_PATH "
        "or FIREBASE_SERVICE_ACCOUNT_JSON in your .env file."
    )

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'databaseURL': os.environ.get('FIREBASE_DATABASE_URL', '')
    })

db = firestore.client()
