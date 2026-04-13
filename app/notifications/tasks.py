import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from app.notifications.models import Notification

logger = logging.getLogger(__name__)


def _send_email_to_user(user, subject: str, message: str) -> None:
    if not user.email:
        return

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@digitalwallet.local")
    try:
        send_mail(subject, message, from_email, [user.email], fail_silently=True)
    except Exception:
        logger.exception("Failed to send notification email to user %s", user)


@shared_task(queue="notifications")
def cleanup_expired_notifications() -> int:
    expired = Notification.objects.filter(expires_at__lt=timezone.now())
    deleted_count, _ = expired.delete()
    return deleted_count
