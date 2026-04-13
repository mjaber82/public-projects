from django.db import models

from app.core.constants import NotificationStatus
from app.core.models import BaseModel


class Notification(BaseModel):
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=NotificationStatus.choices,
        default=NotificationStatus.UNREAD,
    )
    read_dt = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    event_type = models.CharField(max_length=50)
    related_tx = models.ForeignKey("transactions.Transaction", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "notifications"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Notification {self.id} to {self.user.username}: {self.title}"
