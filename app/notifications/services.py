from datetime import timedelta

from django.utils import timezone

from .models import Notification


def create_notification(user, title: str, body: str, event_type: str, related_tx=None) -> Notification:
    """Creates a web notification record. Called from Celery tasks."""
    return Notification.objects.create(user=user, title=title, body=body, event_type=event_type, related_tx=related_tx)


def mark_read(user, notification_id: str) -> tuple[bool, str | None]:
    """Marks notification as READ, sets read_dt = now(), expires_at = now() + 7 days."""
    try:
        notification = Notification.objects.get(public_id=notification_id, user=user)
        notification.status = "READ"
        notification.read_dt = timezone.now()
        notification.expires_at = notification.read_dt + timedelta(days=7)
        notification.save()
        return True, None
    except Notification.DoesNotExist:
        return False, "Notification not found"


def clear_notifications(user) -> int:
    """Marks all user UNREAD notifications as READ. Returns count updated."""
    return Notification.objects.filter(user=user, status="UNREAD").update(
        status="READ",
        read_dt=timezone.now(),
        expires_at=timezone.now() + timedelta(days=7),
    )


def get_notifications(user):
    return Notification.objects.filter(user=user).order_by("status", "-created_dt")


def clear_notification(user, notification_id: str) -> tuple[bool, str | None]:
    try:
        notification = Notification.objects.get(public_id=notification_id, user=user)
        notification.delete()
        return True, None
    except Notification.DoesNotExist:
        return False, "Notification not found"
