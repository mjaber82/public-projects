from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from app.notifications.models import Notification
from app.notifications.services import (
    clear_notification,
    clear_notifications,
    create_notification,
    get_notifications,
    mark_read,
)
from app.notifications.tasks import _send_email_to_user, cleanup_expired_notifications
from app.users.models import Country, User


class CreateNotificationTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550401",
            country=self.country,
            email="notif_test@example.com",
            passcode="1234",
        )

    def test_creates_notification(self) -> None:
        notification = create_notification(self.user, "Test Title", "Test Body", "TEST_EVENT")
        self.assertEqual(notification.title, "Test Title")
        self.assertEqual(notification.body, "Test Body")
        self.assertEqual(notification.event_type, "TEST_EVENT")
        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.status, "UNREAD")
        self.assertIsNone(notification.related_tx)


class MarkReadTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550402",
            country=self.country,
            email="notif_read@example.com",
            passcode="1234",
        )
        self.notification = create_notification(self.user, "Title", "Body", "EVENT")

    def test_mark_read_success(self) -> None:
        success, error = mark_read(self.user, str(self.notification.public_id))
        self.assertTrue(success)
        self.assertIsNone(error)

        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, "READ")
        self.assertIsNotNone(self.notification.read_dt)
        self.assertIsNotNone(self.notification.expires_at)

    def test_mark_read_not_found(self) -> None:
        success, error = mark_read(self.user, "00000000-0000-0000-0000-000000000000")
        self.assertFalse(success)
        self.assertEqual(error, "Notification not found")


class ClearNotificationsTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550403",
            country=self.country,
            email="notif_clear@example.com",
            passcode="1234",
        )

    def test_marks_all_unread_as_read(self) -> None:
        create_notification(self.user, "N1", "B1", "E1")
        create_notification(self.user, "N2", "B2", "E2")
        create_notification(self.user, "N3", "B3", "E3")

        count = clear_notifications(self.user)
        self.assertEqual(count, 3)
        self.assertEqual(Notification.objects.filter(user=self.user, status="READ").count(), 3)

    def test_does_not_affect_already_read(self) -> None:
        n = create_notification(self.user, "N1", "B1", "E1")
        n.status = "READ"
        n.save()

        count = clear_notifications(self.user)
        self.assertEqual(count, 0)


class GetNotificationsTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550404",
            country=self.country,
            email="notif_get@example.com",
            passcode="1234",
        )

    def test_returns_user_notifications_ordered(self) -> None:
        create_notification(self.user, "N1", "B1", "E1")
        create_notification(self.user, "N2", "B2", "E2")

        notifications = get_notifications(self.user)
        self.assertEqual(notifications.count(), 2)


class ClearNotificationTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550405",
            country=self.country,
            email="notif_del@example.com",
            passcode="1234",
        )

    def test_deletes_notification(self) -> None:
        n = create_notification(self.user, "Title", "Body", "EVENT")
        success, error = clear_notification(self.user, str(n.public_id))
        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertFalse(Notification.objects.filter(pk=n.pk).exists())

    def test_not_found(self) -> None:
        success, error = clear_notification(self.user, "00000000-0000-0000-0000-000000000000")
        self.assertFalse(success)
        self.assertEqual(error, "Notification not found")


class CleanupExpiredNotificationsTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550406",
            country=self.country,
            email="notif_cleanup@example.com",
            passcode="1234",
        )

    def test_deletes_expired_notifications(self) -> None:
        n1 = create_notification(self.user, "Expired", "Body", "EVENT")
        n1.expires_at = timezone.now() - timedelta(days=1)
        n1.save()

        n2 = create_notification(self.user, "Active", "Body", "EVENT")
        n2.expires_at = timezone.now() + timedelta(days=1)
        n2.save()

        deleted_count = cleanup_expired_notifications()
        self.assertEqual(deleted_count, 1)
        self.assertFalse(Notification.objects.filter(pk=n1.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=n2.pk).exists())


class SendEmailToUserTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550407",
            country=self.country,
            email="notif_email@example.com",
            passcode="1234",
        )

    @patch("app.notifications.tasks.send_mail")
    def test_sends_email_when_user_has_email(self, send_mail_mock) -> None:
        _send_email_to_user(self.user, "Subject", "Message")
        send_mail_mock.assert_called_once()

    @patch("app.notifications.tasks.send_mail")
    def test_skips_when_no_email(self, send_mail_mock) -> None:
        self.user.email = ""
        self.user.save()
        _send_email_to_user(self.user, "Subject", "Message")
        send_mail_mock.assert_not_called()

    @patch("app.notifications.tasks.send_mail", side_effect=Exception("SMTP error"))
    def test_handles_send_failure_gracefully(self, send_mail_mock) -> None:
        # Should not raise
        _send_email_to_user(self.user, "Subject", "Message")
