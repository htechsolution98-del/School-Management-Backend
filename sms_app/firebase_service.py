import os
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

_firebase_app = None


def get_firebase_app():
    """
    Initializes or retrieves the Firebase Admin app singleton.
    Reads credentials from .env:
      - FIREBASE_CREDENTIALS_PATH (JSON file path)
      - OR FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, FIREBASE_PRIVATE_KEY
    Returns the app instance, or None if credentials are not configured yet.
    """
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials

        # Check if already initialized by default
        if firebase_admin._apps:
            _firebase_app = firebase_admin.get_app()
            return _firebase_app

        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH") or os.getenv("FIREBASE_CREDENTIALS_JSON_PATH")
        if cred_path:
            full_path = cred_path if os.path.isabs(cred_path) else os.path.join(str(settings.BASE_DIR), cred_path)
            if os.path.exists(full_path):
                cred = credentials.Certificate(full_path)
                _firebase_app = firebase_admin.initialize_app(cred)
                logger.info("[FCM] Firebase initialized with credential file: %s", full_path)
                return _firebase_app

        # Direct credentials in environment
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        client_email = os.getenv("FIREBASE_CLIENT_EMAIL")
        private_key = os.getenv("FIREBASE_PRIVATE_KEY")

        if project_id and client_email and private_key:
            # Handle escaped newlines in private key string
            formatted_key = private_key.replace("\\n", "\n")
            cred_dict = {
                "type": "service_account",
                "project_id": project_id,
                "client_email": client_email,
                "private_key": formatted_key,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
            cred = credentials.Certificate(cred_dict)
            _firebase_app = firebase_admin.initialize_app(cred)
            logger.info("[FCM] Firebase initialized with environment service account for project: %s", project_id)
            return _firebase_app

        logger.warning(
            "[FCM] Firebase credentials not found in .env (FIREBASE_CREDENTIALS_PATH or project credentials). "
            "Push notifications are currently in standby."
        )
        return None

    except Exception as e:
        logger.error("[FCM] Error initializing Firebase Admin SDK: %s", e)
        return None


def register_user_fcm_token(user, token, device_type="web"):
    """
    Registers or updates an FCM device token for an authenticated user.
    """
    if not user or not user.is_authenticated or not token:
        return None

    from .models import FCMDeviceToken

    token_obj, _ = FCMDeviceToken.objects.update_or_create(
        token=token.strip(),
        defaults={
            "user": user,
            "device_type": device_type or "web",
        },
    )
    return token_obj


def send_student_absence_notification(student, attendance_date, reason=""):
    """
    Sends an FCM push notification to parents when their child is marked ABSENT.
    Sends to:
      1. Registered parent device tokens for this student.
      2. Topic `parent_student_{student.id}` for real-time mobile app topic subscribers.
    """
    if not student:
        return {"success": False, "reason": "Student not provided"}

    student_name = f"{student.name or ''} {student.surname or ''}".strip() or f"Student #{student.id}"
    date_str = str(attendance_date)

    title = f"Absent Alert: {student_name} is Absent"
    body = (
        f"Dear Parent, your child {student_name} was marked ABSENT today ({date_str}). "
        f"Please contact the school office if this was unexpected."
    )
    if reason:
        body += f" Reason noted: {reason}"

    data_payload = {
        "notification_type": "STUDENT_ABSENCE",
        "student_id": str(student.id),
        "student_name": student_name,
        "attendance_date": date_str,
        "status": "ABSENT",
    }

    # Fetch parent users
    from .models import Perents, FCMDeviceToken

    parent_records = Perents.objects.filter(perents_of=student).select_related("user")
    parent_users = [p.user for p in parent_records if p.user]

    tokens = []
    if parent_users:
        tokens = list(
            FCMDeviceToken.objects.filter(user__in=parent_users)
            .values_list("token", flat=True)
            .distinct()
        )

    app = get_firebase_app()
    if not app:
        logger.info(
            "[FCM Standby] Student %s marked absent. %d parent tokens found. "
            "Notification will deliver once Firebase credentials are set in .env.",
            student.id,
            len(tokens),
        )
        return {
            "success": False,
            "standby": True,
            "message": "Firebase credentials not configured yet in .env",
            "parent_count": len(parent_users),
            "tokens_found": len(tokens),
        }

    try:
        from firebase_admin import messaging

        results = {
            "token_messages_sent": 0,
            "topic_message_sent": False,
            "errors": [],
        }

        # 1. Send via Multicast to registered parent tokens
        if tokens:
            notification = messaging.Notification(
                title=title,
                body=body,
            )
            multicast_message = messaging.MulticastMessage(
                tokens=tokens,
                notification=notification,
                data=data_payload,
            )
            response = messaging.send_each_for_multicast(multicast_message)
            results["token_messages_sent"] = response.success_count
            logger.info(
                "[FCM] Absence push delivered to %d/%d parent devices for student %s",
                response.success_count,
                len(tokens),
                student.id,
            )

        # 2. Also broadcast to student's parent topic (fallback for apps subscribed to student topic)
        student_topic = f"parent_student_{student.id}"
        topic_message = messaging.Message(
            topic=student_topic,
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data_payload,
        )
        try:
            messaging.send(topic_message)
            results["topic_message_sent"] = True
            logger.info("[FCM] Absence push broadcast to topic '%s'", student_topic)
        except Exception as te:
            logger.warning("[FCM] Topic send note: %s", te)

        return {"success": True, **results}

    except Exception as e:
        logger.error("[FCM] Failed to dispatch absence notification for student %s: %s", student.id, e)
        return {"success": False, "error": str(e)}
