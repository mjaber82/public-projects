from types import SimpleNamespace
from unittest.mock import Mock, patch
import json

from django.test import SimpleTestCase
from django.test.client import RequestFactory
from django.urls import resolve, reverse
from rest_framework.exceptions import ValidationError

from app.notifications import views
from app.notifications.tasks import _send_email_to_user


class NotificationsEndpointWiringTests(SimpleTestCase):
    ENDPOINTS = [
        ("notifications-list", "/api/v1/notifications/", views.notification_list),
        (
            "notifications-read",
            "/api/v1/notifications/read/",
            views.mark_notification_read,
        ),
        (
            "notifications-read-all",
            "/api/v1/notifications/read-all/",
            views.mark_all_read,
        ),
        (
            "notifications-clear",
            "/api/v1/notifications/clear/",
            views.clear_notification_view,
        ),
        (
            "notifications-clear-all",
            "/api/v1/notifications/clear-all/",
            views.clear_all_notifications,
        ),
    ]

    def test_endpoint_reverse_paths(self) -> None:
        for route_name, expected_path, _ in self.ENDPOINTS:
            with self.subTest(route_name=route_name):
                self.assertEqual(reverse(route_name), expected_path)

    def test_endpoint_resolve_targets(self) -> None:
        for _, endpoint_path, expected_view in self.ENDPOINTS:
            with self.subTest(endpoint_path=endpoint_path):
                match = resolve(endpoint_path)
                self.assertIs(match.func, expected_view)


class NotificationEmailTaskTests(SimpleTestCase):
    @patch("app.notifications.tasks.send_mail")
    def test_generic_notification_email_ignores_transaction_email_preference(self, send_mail_mock) -> None:
        user = SimpleNamespace(email="user@example.com", email_notifications=False)

        _send_email_to_user(user, "Security alert", "Body")

        send_mail_mock.assert_called_once()


class NotificationsViewTests(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.factory = RequestFactory()
        self.user = object()

    def _raw_get(self, path: str):
        request = self.factory.get(path)
        request.user = self.user
        return request

    def _raw_post(self, path: str, payload: dict):
        request = self.factory.post(
            path,
            data=payload,
        )
        request.user = self.user
        return request

    @patch("app.notifications.views.NotificationSerializer")
    @patch("app.notifications.views.get_notifications")
    def test_notification_list_success(self, get_notifications_mock, serializer_mock) -> None:
        request = self._raw_get(reverse("notifications-list"))
        notifications = [Mock()]
        get_notifications_mock.return_value = notifications
        serializer_mock.return_value.data = [{"title": "Transfer received"}]

        response = views.notification_list.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        get_notifications_mock.assert_called_once_with(self.user)
        serializer_mock.assert_called_once_with(notifications, many=True)
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Success")
        self.assertEqual(body["payload"]["notifications"], [{"title": "Transfer received"}])

    @patch("app.notifications.views.mark_read")
    def test_mark_notification_read_success(self, mark_read_mock) -> None:
        request = self._raw_post(
            reverse("notifications-read"),
            {"key": "11111111-1111-1111-1111-111111111111"},
        )
        mark_read_mock.return_value = (True, None)

        response = views.mark_notification_read.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        mark_read_mock.assert_called_once_with(self.user, mark_read_mock.call_args.args[1])
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Notification marked as read")

    @patch("app.notifications.views.mark_read")
    def test_mark_notification_read_fail(self, mark_read_mock) -> None:
        request = self._raw_post(
            reverse("notifications-read"),
            {"key": "11111111-1111-1111-1111-111111111111"},
        )
        mark_read_mock.return_value = (False, "Notification not found")

        response = views.mark_notification_read.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "Notification not found")

    def test_mark_notification_read_invalid_key(self) -> None:
        request = self._raw_post(reverse("notifications-read"), {"key": "not-a-uuid"})

        with self.assertRaises(ValidationError):
            views.mark_notification_read.__wrapped__.__wrapped__(request)

    @patch("app.notifications.views.clear_notifications")
    def test_mark_all_read_success(self, clear_notifications_mock) -> None:
        request = self._raw_post(reverse("notifications-read-all"), {})
        clear_notifications_mock.return_value = 3

        response = views.mark_all_read.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        clear_notifications_mock.assert_called_once_with(self.user)
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Notifications marked as read")
        self.assertEqual(body["payload"]["updated_count"], 3)

    @patch("app.notifications.views.clear_notification")
    def test_clear_notification_success(self, clear_notification_mock) -> None:
        request = self._raw_post(
            reverse("notifications-clear"),
            {"key": "11111111-1111-1111-1111-111111111111"},
        )
        clear_notification_mock.return_value = (True, None)

        response = views.clear_notification_view.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        clear_notification_mock.assert_called_once_with(self.user, clear_notification_mock.call_args.args[1])
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Notification deleted")

    @patch("app.notifications.views.clear_notification")
    def test_clear_notification_fail(self, clear_notification_mock) -> None:
        request = self._raw_post(
            reverse("notifications-clear"),
            {"key": "11111111-1111-1111-1111-111111111111"},
        )
        clear_notification_mock.return_value = (False, "Notification not found")

        response = views.clear_notification_view.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "Notification not found")

    def test_clear_notification_invalid_key(self) -> None:
        request = self._raw_post(reverse("notifications-clear"), {"key": "not-a-uuid"})

        with self.assertRaises(ValidationError):
            views.clear_notification_view.__wrapped__.__wrapped__(request)

    def test_clear_all_notifications_success(self) -> None:
        notifications_manager = Mock()
        notifications_manager.all.return_value.delete.return_value = (
            2,
            {"app.notifications.Notification": 2},
        )
        mock_user = Mock(notifications=notifications_manager)
        request = self.factory.post(reverse("notifications-clear-all"), data={})
        request.user = mock_user

        response = views.clear_all_notifications.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        notifications_manager.all.assert_called_once()
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Notifications cleared")
        self.assertEqual(body["payload"]["deleted_count"], 2)
