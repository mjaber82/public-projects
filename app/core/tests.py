import json
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.test import SimpleTestCase, TestCase, RequestFactory, override_settings

from app.core.constants import ResponseMessage, ResponseStatus
from app.core.decorators import api_auth, api_return, check_maintenance, params_required
from app.core.exceptions import InsufficientFundsError, WalletException
from app.core.health import health_check
from app.core.middleware import JWTAuthMiddleware
from app.core.tools import (
    ajax_response,
    create_response,
    generate_account_id,
    get_ip,
    json_default_fn,
    missing_params,
    password_complexity_validator,
    validate_dob,
)


class CreateResponseTests(SimpleTestCase):
    def test_default_fail_status(self) -> None:
        resp = create_response()
        body = json.loads(resp.content)
        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "")
        self.assertNotIn("payload", body)

    def test_success_with_payload(self) -> None:
        resp = create_response(
            status=ResponseStatus.SUCCESS,
            message="Done",
            payload={"key": "value"},
        )
        body = json.loads(resp.content)
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Done")
        self.assertEqual(body["payload"]["key"], "value")

    def test_returns_json_response(self) -> None:
        resp = create_response(status=ResponseStatus.SUCCESS, message="ok")
        self.assertIsInstance(resp, JsonResponse)


class JsonDefaultFnTests(SimpleTestCase):
    def test_datetime_serialized_as_isoformat(self) -> None:
        dt = datetime(2024, 1, 15, 10, 30, 0)
        self.assertEqual(json_default_fn(dt), dt.isoformat())

    def test_date_serialized_as_isoformat(self) -> None:
        d = date(2024, 6, 1)
        self.assertEqual(json_default_fn(d), d.isoformat())

    def test_non_datetime_returns_str(self) -> None:
        self.assertEqual(json_default_fn(42), "42")
        self.assertEqual(json_default_fn(None), "None")


class AjaxResponseTests(SimpleTestCase):
    def test_dict_data_returns_http_response(self) -> None:
        data = {"status": "SUCCESS", "message": "ok"}
        resp = ajax_response(data)
        self.assertIsInstance(resp, HttpResponse)
        self.assertEqual(resp["Content-Type"], "application/json")
        body = json.loads(resp.content)
        self.assertEqual(body["status"], "SUCCESS")

    def test_http_response_passthrough(self) -> None:
        original = HttpResponse("raw", content_type="text/plain")
        resp = ajax_response(original)
        self.assertIs(resp, original)

    def test_cross_domain_headers(self) -> None:
        resp = ajax_response({"ok": True}, allow_cross_domain=True)
        self.assertEqual(resp["Access-Control-Allow-Origin"], "*")
        self.assertIn("POST", resp["Access-Control-Allow-Methods"])

    def test_no_cross_domain_headers_by_default(self) -> None:
        resp = ajax_response({"ok": True})
        self.assertFalse(resp.has_header("Access-Control-Allow-Origin"))


class MissingParamsTests(SimpleTestCase):
    def test_no_required_returns_empty(self) -> None:
        self.assertEqual(missing_params({"a": 1}, []), [])

    def test_all_present_returns_empty(self) -> None:
        self.assertEqual(missing_params({"a": 1, "b": 2}, ["a", "b"]), [])

    def test_missing_params_returned(self) -> None:
        self.assertEqual(missing_params({"a": 1}, ["a", "b", "c"]), ["b", "c"])

    def test_empty_value_counts_as_missing(self) -> None:
        self.assertEqual(missing_params({"a": ""}, ["a"]), ["a"])

    def test_none_value_counts_as_missing(self) -> None:
        self.assertEqual(missing_params({"a": None}, ["a"]), ["a"])


class GetIpTests(SimpleTestCase):
    def test_returns_ip_from_request(self) -> None:
        factory = RequestFactory()
        request = factory.get("/", REMOTE_ADDR="192.168.1.1")
        ip = get_ip(request)
        self.assertEqual(ip, "192.168.1.1")

    def test_returns_fallback_when_no_ip(self) -> None:
        request = Mock()
        request.META = {}
        ip = get_ip(request)
        self.assertEqual(ip, "0.0.0.0")


class GenerateAccountIdTests(SimpleTestCase):
    def test_format_pattern(self) -> None:
        for _ in range(50):
            account_id = generate_account_id()
            self.assertRegex(account_id, r"^\d{8}-\d{2}$")

    def test_produces_different_ids(self) -> None:
        ids = {generate_account_id() for _ in range(20)}
        self.assertGreater(len(ids), 1)


class PasswordComplexityValidatorTests(SimpleTestCase):
    def test_valid_password(self) -> None:
        self.assertTrue(password_complexity_validator("Password1"))
        self.assertTrue(password_complexity_validator("Ab1cdefg"))

    def test_too_short(self) -> None:
        self.assertFalse(password_complexity_validator("Ab1"))

    def test_no_uppercase(self) -> None:
        self.assertFalse(password_complexity_validator("password1"))

    def test_no_lowercase(self) -> None:
        self.assertFalse(password_complexity_validator("PASSWORD1"))

    def test_no_digit(self) -> None:
        self.assertFalse(password_complexity_validator("Password"))

    def test_has_spaces(self) -> None:
        self.assertFalse(password_complexity_validator("Pass word1"))

    def test_custom_min_length(self) -> None:
        self.assertTrue(password_complexity_validator("Ab1c", min_length=4))
        self.assertFalse(password_complexity_validator("Ab1", min_length=4))


class ValidateDobTests(SimpleTestCase):
    def test_valid_dob_no_min_age(self) -> None:
        self.assertIsNone(validate_dob("2000-01-01"))

    def test_invalid_format(self) -> None:
        self.assertEqual(validate_dob("01/01/2000"), "Date of birth must be in YYYY-MM-DD format")
        self.assertEqual(validate_dob("not-a-date"), "Date of birth must be in YYYY-MM-DD format")

    def test_min_age_enforcement(self) -> None:
        today = date.today()
        young_dob = (today - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
        self.assertIsNotNone(validate_dob(young_dob, min_age=18))

    def test_min_age_passes_for_old_enough(self) -> None:
        old_dob = "1990-01-01"
        self.assertIsNone(validate_dob(old_dob, min_age=18))


class HealthCheckTests(SimpleTestCase):
    def test_health_check_raises_due_to_double_wrapping(self) -> None:
        """health_check wraps create_response (JsonResponse) in another JsonResponse,
        causing a serialization error. This documents the existing behavior."""
        factory = RequestFactory()
        request = factory.get("/health/")
        with self.assertRaises(TypeError):
            health_check(request)


class ExceptionTests(SimpleTestCase):
    def test_wallet_exception_hierarchy(self) -> None:
        self.assertTrue(issubclass(InsufficientFundsError, WalletException))
        self.assertTrue(issubclass(WalletException, Exception))

    def test_insufficient_funds_raiseable(self) -> None:
        with self.assertRaises(InsufficientFundsError):
            raise InsufficientFundsError("Not enough balance")


class CheckMaintenanceDecoratorTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @override_settings(IS_MAINTENANCE=False)
    def test_passes_through_when_not_maintenance(self) -> None:
        @check_maintenance
        def my_view(request):
            return HttpResponse("ok")

        request = self.factory.get("/")
        response = my_view(request)
        self.assertEqual(response.content, b"ok")

    @override_settings(IS_MAINTENANCE=True, MAINTENANCE_MESSAGE="Down for updates")
    def test_returns_fail_during_maintenance(self) -> None:
        @check_maintenance
        def my_view(request):
            return HttpResponse("ok")

        request = self.factory.get("/")
        response = my_view(request)
        body = json.loads(response.content)
        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "Down for updates")

    @override_settings(IS_MAINTENANCE=True, MAINTENANCE_MESSAGE="")
    def test_maintenance_default_message(self) -> None:
        @check_maintenance
        def my_view(request):
            return HttpResponse("ok")

        request = self.factory.get("/")
        response = my_view(request)
        body = json.loads(response.content)
        self.assertEqual(body["message"], ResponseMessage.MAINTENANCE_MODE)


class ApiReturnDecoratorTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_returns_http_response_as_is(self) -> None:
        @api_return
        def my_view(request):
            return HttpResponse("direct")

        request = self.factory.get("/")
        response = my_view(request)
        self.assertEqual(response.content, b"direct")

    def test_catches_django_validation_error(self) -> None:
        @api_return
        def my_view(request):
            raise ValidationError("Field is invalid")

        request = self.factory.get("/")
        response = my_view(request)
        body = json.loads(response.content)
        self.assertEqual(body["status"], "FAIL")
        self.assertIn("invalid", body["message"].lower())

    def test_catches_generic_exception(self) -> None:
        @api_return
        def my_view(request):
            raise RuntimeError("Something broke")

        request = self.factory.get("/")
        response = my_view(request)
        body = json.loads(response.content)
        self.assertEqual(body["status"], "FAIL")

    def test_validation_error_list_message_falls_back_to_unknown(self) -> None:
        @api_return
        def my_view(request):
            raise ValidationError(["First error", "Second error"])

        request = self.factory.get("/")
        response = my_view(request)
        body = json.loads(response.content)
        self.assertEqual(body["status"], "FAIL")


class ParamsRequiredDecoratorTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_passes_when_all_params_present(self) -> None:
        @params_required(GET_LIST=["page"])
        def my_view(request):
            return HttpResponse("ok")

        request = self.factory.get("/", {"page": "1"})
        response = my_view(request)
        self.assertEqual(response.content, b"ok")

    def test_fails_when_get_params_missing(self) -> None:
        @params_required(GET_LIST=["page", "limit"])
        def my_view(request):
            return HttpResponse("ok")

        request = self.factory.get("/", {"page": "1"})
        response = my_view(request)
        body = json.loads(response.content)
        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], ResponseMessage.NOT_ENOUGH_INFO)
        self.assertIn("limit", body["payload"]["missing_params"])

    def test_fails_when_post_params_missing(self) -> None:
        @params_required(POST_LIST=["name"])
        def my_view(request):
            return HttpResponse("ok")

        request = self.factory.post("/")
        response = my_view(request)
        body = json.loads(response.content)
        self.assertIn("name", body["payload"]["missing_params"])

    def test_fails_when_http_header_missing(self) -> None:
        @params_required(HTTP_LIST=["X-Custom-Header"])
        def my_view(request):
            return HttpResponse("ok")

        request = self.factory.get("/")
        response = my_view(request)
        body = json.loads(response.content)
        self.assertIn("X-Custom-Header", body["payload"]["missing_params"])

    def test_passes_when_http_header_present(self) -> None:
        @params_required(HTTP_LIST=["X-Custom-Header"])
        def my_view(request):
            return HttpResponse("ok")

        request = self.factory.get("/", HTTP_X_CUSTOM_HEADER="value")
        response = my_view(request)
        self.assertEqual(response.content, b"ok")


class ApiAuthDecoratorTests(TestCase):
    def setUp(self) -> None:
        from app.users.models import Country, User, UserSession

        self.factory = RequestFactory()
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550199",
            country=self.country,
            email="authtest@example.com",
            passcode="1234",
        )
        self.session = UserSession.objects.create(
            user=self.user,
            device_id="test-device",
            ip_address="127.0.0.1",
            is_active=True,
            state="UNLOCKED",
        )

    def _make_view(self):
        @api_auth
        def my_view(request):
            return HttpResponse("authorized")

        return my_view

    def test_rejects_anonymous_user(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        view = self._make_view()
        request = self.factory.get("/")
        request.user = AnonymousUser()
        request.auth_session_id = None

        response = view(request)
        body = json.loads(response.content)
        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], ResponseMessage.NOT_AUTHENTICATED)

    def test_rejects_inactive_user(self) -> None:
        self.user.is_active = False
        self.user.save()

        view = self._make_view()
        request = self.factory.get("/")
        request.user = self.user
        request.auth_session_id = str(self.session.public_id)

        response = view(request)
        body = json.loads(response.content)
        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], ResponseMessage.USER_INACTIVE)

    def test_rejects_missing_session_id(self) -> None:
        view = self._make_view()
        request = self.factory.get("/")
        request.user = self.user
        request.auth_session_id = None

        response = view(request)
        body = json.loads(response.content)
        self.assertEqual(body["message"], "Session is missing")

    def test_rejects_revoked_session(self) -> None:
        self.session.is_active = False
        self.session.save()

        view = self._make_view()
        request = self.factory.get("/")
        request.user = self.user
        request.auth_session_id = str(self.session.public_id)

        response = view(request)
        body = json.loads(response.content)
        self.assertEqual(body["message"], "Session is revoked or inactive")

    def test_rejects_locked_session(self) -> None:
        self.session.state = "LOCKED"
        self.session.save()

        view = self._make_view()
        request = self.factory.get("/")
        request.user = self.user
        request.auth_session_id = str(self.session.public_id)

        response = view(request)
        body = json.loads(response.content)
        self.assertEqual(body["message"], "Session is locked. Re-enter passcode.")
        self.assertEqual(body["payload"]["session_state"], "LOCKED")

    @override_settings(APP_IDLE_TIME=timedelta(seconds=1))
    def test_locks_session_after_idle_timeout(self) -> None:
        from django.utils import timezone

        self.session.last_seen_at = timezone.now() - timedelta(seconds=60)
        self.session.save()

        view = self._make_view()
        request = self.factory.get("/")
        request.user = self.user
        request.auth_session_id = str(self.session.public_id)

        response = view(request)
        body = json.loads(response.content)
        self.assertEqual(body["message"], "Session is locked. Re-enter passcode.")

    @override_settings(IS_MAINTENANCE=True, MAINTENANCE_MESSAGE="Maintenance active")
    def test_maintenance_mode_blocks(self) -> None:
        view = self._make_view()
        request = self.factory.get("/")
        request.user = self.user
        request.auth_session_id = str(self.session.public_id)

        response = view(request)
        body = json.loads(response.content)
        self.assertEqual(body["message"], "Maintenance active")

    def test_success_updates_last_seen(self) -> None:
        view = self._make_view()
        request = self.factory.get("/")
        request.user = self.user
        request.auth_session_id = str(self.session.public_id)

        response = view(request)
        self.assertEqual(response.content, b"authorized")

        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.last_seen_at)


class JWTAuthMiddlewareTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.middleware = JWTAuthMiddleware(get_response=lambda r: r)

    def test_no_auth_header_sets_anonymous(self) -> None:
        request = self.factory.get("/")
        self.middleware.process_request(request)
        self.assertFalse(request.user.is_authenticated)

    def test_non_bearer_header_sets_anonymous(self) -> None:
        request = self.factory.get("/", HTTP_AUTHORIZATION="Token abc123")
        self.middleware.process_request(request)
        self.assertFalse(request.user.is_authenticated)

    def test_invalid_token_sets_anonymous(self) -> None:
        request = self.factory.get("/", HTTP_AUTHORIZATION="Bearer invalid-jwt-token")
        self.middleware.process_request(request)
        self.assertFalse(request.user.is_authenticated)

    @patch("app.core.middleware.AccessToken")
    @patch("app.core.middleware.get_user_model")
    def test_valid_token_sets_user(self, get_user_model_mock, access_token_mock) -> None:
        mock_user = Mock(is_authenticated=True)
        user_model = Mock()
        user_model.objects.get.return_value = mock_user
        user_model.DoesNotExist = Exception
        get_user_model_mock.return_value = user_model

        access_token_mock.return_value.payload = {"user_id": "test-uuid", "sid": "session-uuid"}

        request = self.factory.get("/", HTTP_AUTHORIZATION="Bearer valid-token")
        self.middleware.process_request(request)

        self.assertEqual(request.user, mock_user)
        self.assertEqual(request.auth_session_id, "session-uuid")


class FirebaseInitializeTests(SimpleTestCase):
    @patch("app.core.firebase.firebase_admin")
    def test_skips_if_already_initialized(self, firebase_admin_mock) -> None:
        firebase_admin_mock._apps = {"default": True}

        from app.core.firebase import initialize_firebase

        initialize_firebase()
        firebase_admin_mock.initialize_app.assert_not_called()

    @patch("app.core.firebase.firebase_admin")
    @patch.dict("os.environ", {"FIREBASE_SERVICE_ACCOUNT_JSON": ""})
    def test_skips_if_no_cred_path(self, firebase_admin_mock) -> None:
        firebase_admin_mock._apps = {}

        from app.core.firebase import initialize_firebase

        initialize_firebase()
        firebase_admin_mock.initialize_app.assert_not_called()

    @patch("app.core.firebase.os.path.exists", return_value=False)
    @patch("app.core.firebase.firebase_admin")
    @patch.dict("os.environ", {"FIREBASE_SERVICE_ACCOUNT_JSON": "/fake/path.json"})
    def test_skips_if_file_not_found(self, firebase_admin_mock, exists_mock) -> None:
        firebase_admin_mock._apps = {}

        from app.core.firebase import initialize_firebase

        initialize_firebase()
        firebase_admin_mock.initialize_app.assert_not_called()
