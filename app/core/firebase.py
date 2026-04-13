import logging
import os

import firebase_admin
from firebase_admin import credentials


logger = logging.getLogger(__name__)


def initialize_firebase():
    if firebase_admin._apps:
        return

    cred_path = (os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or "").strip()
    if not cred_path:
        logger.info("Firebase Admin initialization skipped: FIREBASE_SERVICE_ACCOUNT_JSON is not configured")
        return

    if not os.path.exists(cred_path):
        logger.warning(
            "Firebase Admin initialization skipped: credential file not found at %s",
            cred_path,
        )
        return

    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
