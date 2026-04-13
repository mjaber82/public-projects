from django.test import SimpleTestCase
from django.urls import resolve, reverse
from django.test.client import RequestFactory
from unittest.mock import patch
import json

from app.users import views
from app.users.serializers import ChangeEmailSerializer


class UsersEndpointWiringTests(SimpleTestCase):
    ENDPOINTS = [
        (
            "auth-verify-account",
            "/api/v1/auth/verify-account/",
            views.verify_account_view,
        ),
        ("auth-otp-request", "/api/v1/auth/otp/request/", views.request_otp_view),
        ("auth-otp-verify", "/api/v1/auth/otp/verify/", views.verify_otp_view),
        (
            "auth-register-email-request",
            "/api/v1/auth/register/email/request/",
            views.registration_email_request_view,
        ),
        (
            "auth-register-email-verify",
            "/api/v1/auth/register/email/verify/",
            views.registration_email_verify_view,
        ),
        (
            "auth-register-complete",
            "/api/v1/auth/register/complete/",
            views.complete_registration_view,
        ),
        (
            "auth-login-passcode",
            "/api/v1/auth/login/passcode/",
            views.login_passcode_view,
        ),
        ("auth-token-refresh", "/api/v1/auth/token/refresh/", views.refresh_token_view),
        (
            "auth-session-unlock",
            "/api/v1/auth/session/unlock/",
            views.unlock_session_view,
        ),
        ("auth-logout", "/api/v1/auth/logout/", views.logout_view),
        ("users-get-info", "/api/v1/users/get_info/", views.get_info),
        ("users-update-profile", "/api/v1/users/update/", views.update_profile_view),
        (
            "users-deactivate",
            "/api/v1/users/deactivate/",
            views.deactivate_account_view,
        ),
        (
            "users-step-up-request",
            "/api/v1/users/step-up/request/",
            views.request_step_up_token_view,
        ),
        (
            "users-passcode-change",
            "/api/v1/users/passcode/change/",
            views.change_passcode_view,
        ),
        ("users-phone-change", "/api/v1/users/phone/change/", views.change_phone_view),
        ("users-email-change", "/api/v1/users/email/change/", views.change_email_view),
        (
            "auth-passcode-forgot-start",
            "/api/v1/auth/passcode/forgot/start/",
            views.forgot_passcode_start_view,
        ),
        (
            "auth-passcode-forgot-email-verify",
            "/api/v1/auth/passcode/forgot/email-verify/",
            views.forgot_passcode_email_verify_view,
        ),
        (
            "auth-passcode-forgot-complete",
            "/api/v1/auth/passcode/forgot/complete/",
            views.forgot_passcode_complete_view,
        ),
        (
            "auth-recovery-no-sim-start",
            "/api/v1/auth/recovery/no-sim/start/",
            views.no_sim_recovery_start_view,
        ),
        (
            "auth-recovery-no-sim-email-verify",
            "/api/v1/auth/recovery/no-sim/email-verify/",
            views.no_sim_recovery_email_verify_view,
        ),
        (
            "auth-recovery-no-sim-complete",
            "/api/v1/auth/recovery/no-sim/complete/",
            views.no_sim_recovery_complete_view,
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


class UsersAuthFlowViewTests(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.factory = RequestFactory()

    def _post(self, route_name: str, payload: dict, **extra):
        return self.client.post(
            reverse(route_name),
            data=json.dumps(payload),
            content_type="application/json",
            **extra,
        )

    def _raw_post(self, path: str, payload: dict):
        return self.factory.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    @patch("app.users.views.verify_account")
    def test_verify_account_view_success(self, verify_account_mock) -> None:
        verify_account_mock.return_value = (
            {"account_exists": False, "account_active": False},
            None,
        )

        response = self._post("auth-verify-account", {"msisdn": "+12025550123"})
        body = response.json()

        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Success")
        self.assertIn("payload", body)

    @patch("app.users.views.verify_account")
    def test_verify_account_view_fail(self, verify_account_mock) -> None:
        verify_account_mock.return_value = (None, "Invalid phone number")

        response = self._post("auth-verify-account", {"msisdn": "bad"})
        body = response.json()

        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "Invalid phone number")

    @patch("app.users.views.request_phone_otp")
    def test_request_otp_view_success(self, request_phone_otp_mock) -> None:
        request_phone_otp_mock.return_value = ({"otp_required": True}, None)

        response = self._post(
            "auth-otp-request",
            {
                "msisdn": "+12025550123",
                "purpose": "REGISTER",
                "recaptcha_token": "token",
            },
        )
        body = response.json()

        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "OTP requested")

    @patch("app.users.views.request_phone_otp")
    def test_request_otp_view_fail(self, request_phone_otp_mock) -> None:
        request_phone_otp_mock.return_value = (None, "Account already exists")

        response = self._post(
            "auth-otp-request",
            {
                "msisdn": "+12025550123",
                "purpose": "REGISTER",
                "recaptcha_token": "token",
            },
        )
        body = response.json()

        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "Account already exists")

    @patch("app.users.views.verify_phone_otp")
    def test_verify_otp_view_success(self, verify_phone_otp_mock) -> None:
        verify_phone_otp_mock.return_value = ({"registration_token": "abc"}, None)

        response = self._post(
            "auth-otp-verify",
            {
                "msisdn": "+12025550123",
                "verification_code": "123456",
                "purpose": "REGISTER",
            },
        )
        body = response.json()

        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "OTP verified")

    @patch("app.users.views.verify_phone_otp")
    def test_verify_otp_view_fail(self, verify_phone_otp_mock) -> None:
        verify_phone_otp_mock.return_value = (None, "Invalid OTP")

        response = self._post(
            "auth-otp-verify",
            {
                "msisdn": "+12025550123",
                "verification_code": "000000",
                "purpose": "REGISTER",
            },
        )
        body = response.json()

        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "Invalid OTP")

    @patch("app.users.views.send_registration_email_otp")
    def test_registration_email_request_view_success(self, send_registration_email_otp_mock) -> None:
        send_registration_email_otp_mock.return_value = (True, None)

        response = self._post(
            "auth-register-email-request",
            {"registration_token": "reg-token", "email": "user@example.com"},
        )
        body = response.json()

        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Email OTP sent")

    @patch("app.users.views.verify_registration_email_otp")
    def test_registration_email_verify_view_success(self, verify_registration_email_otp_mock) -> None:
        verify_registration_email_otp_mock.return_value = (True, None)

        response = self._post(
            "auth-register-email-verify",
            {"registration_token": "reg-token", "verification_code": "123456"},
        )
        body = response.json()

        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Email verified")

    @patch("app.users.views.complete_registration")
    @patch("app.users.views.get_ip")
    def test_complete_registration_view_success(self, get_ip_mock, complete_registration_mock) -> None:
        get_ip_mock.return_value = "1.2.3.4"
        complete_registration_mock.return_value = (
            {"access_token": "a", "refresh_token": "b"},
            None,
        )

        response = self._post(
            "auth-register-complete",
            {
                "registration_token": "reg-token",
                "passcode": "1234",
                "device_id": "device-1",
            },
        )
        body = response.json()

        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Registration completed")
        complete_registration_mock.assert_called_once_with("reg-token", "1234", "device-1", "1.2.3.4")

    @patch("app.users.views.login_with_passcode")
    @patch("app.users.views.get_ip")
    def test_login_passcode_view_success(self, get_ip_mock, login_with_passcode_mock) -> None:
        get_ip_mock.return_value = "1.2.3.4"
        login_with_passcode_mock.return_value = (
            {"access_token": "a", "refresh_token": "b"},
            None,
        )

        response = self._post(
            "auth-login-passcode",
            {"login_token": "login-token", "passcode": "1234", "device_id": "device-1"},
            HTTP_USER_AGENT="pytest",
        )
        body = response.json()

        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Success")
        login_with_passcode_mock.assert_called_once_with("login-token", "1234", "1.2.3.4", "device-1", "pytest")

    @patch("app.users.views.login_with_passcode")
    def test_login_passcode_view_fail(self, login_with_passcode_mock) -> None:
        login_with_passcode_mock.return_value = (None, "Invalid passcode")

        response = self._post(
            "auth-login-passcode",
            {"login_token": "login-token", "passcode": "9999", "device_id": "device-1"},
        )
        body = response.json()

        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "Invalid passcode")

    @patch("app.users.views.refresh_access_token")
    def test_refresh_token_view_success(self, refresh_access_token_mock) -> None:
        refresh_access_token_mock.return_value = (
            {"access_token": "new-a", "refresh_token": "new-r"},
            None,
        )

        response = self._post("auth-token-refresh", {"refresh_token": "refresh-token"})
        body = response.json()

        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Success")

    @patch("app.users.views.refresh_access_token")
    def test_refresh_token_view_fail(self, refresh_access_token_mock) -> None:
        refresh_access_token_mock.return_value = (None, "Invalid refresh token")

        response = self._post("auth-token-refresh", {"refresh_token": "bad-token"})
        body = response.json()

        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "Invalid refresh token")

    @patch("app.users.views.verify_change_email_otp")
    @patch("app.users.views.send_change_email_otp")
    def test_change_email_view_sends_otp_when_verification_code_missing(
        self,
        send_change_email_otp_mock,
        verify_change_email_otp_mock,
    ) -> None:
        request = self._raw_post(
            reverse("users-email-change"),
            {"step_up_token": "step-1", "new_email": "new@example.com"},
        )
        request.user = object()
        send_change_email_otp_mock.return_value = (True, None)

        response = views.change_email_view.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        send_change_email_otp_mock.assert_called_once_with(request.user, "step-1", "new@example.com")
        verify_change_email_otp_mock.assert_not_called()
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Email OTP sent")

    @patch("app.users.views.verify_change_email_otp")
    @patch("app.users.views.send_change_email_otp")
    def test_change_email_view_verifies_otp_when_verification_code_present(
        self,
        send_change_email_otp_mock,
        verify_change_email_otp_mock,
    ) -> None:
        request = self._raw_post(
            reverse("users-email-change"),
            {
                "step_up_token": "step-1",
                "new_email": "new@example.com",
                "verification_code": "123456",
            },
        )
        request.user = object()
        verify_change_email_otp_mock.return_value = (True, None)

        response = views.change_email_view.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        send_change_email_otp_mock.assert_not_called()
        verify_change_email_otp_mock.assert_called_once_with(request.user, "step-1", "new@example.com", "123456")
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Email changed")

    def test_change_email_serializer_requires_new_email(self) -> None:
        serializer = ChangeEmailSerializer(data={"step_up_token": "step-1"})

        self.assertFalse(serializer.is_valid())
        self.assertIn("new_email", serializer.errors)

    def test_change_email_serializer_allows_missing_verification_code(self) -> None:
        serializer = ChangeEmailSerializer(data={"step_up_token": "step-1", "new_email": "new@example.com"})

        self.assertTrue(serializer.is_valid(), serializer.errors)
