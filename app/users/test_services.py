from django.test import SimpleTestCase, TestCase, override_settings

from app.users.models import Country, User
from app.users.services import (
    _firebase_auth_emulator_host,
    _firebase_identity_base_url,
    _firebase_web_api_key,
    _generate_numeric_otp,
    _is_firebase_auth_emulator_enabled,
    _is_valid_passcode,
    _login_attempts_key,
    _login_block_key,
    _login_penalty_level_key,
    _login_token_key,
    _normalize_key_part,
    _phone_otp_session_key,
    _registration_email_otp_key,
    _step_up_token_key,
    verify_account,
)


class NormalizeKeyPartTests(SimpleTestCase):
    def test_strips_and_lowercases(self) -> None:
        self.assertEqual(_normalize_key_part("  Hello World  "), "hello_world")

    def test_none_returns_unknown(self) -> None:
        self.assertEqual(_normalize_key_part(None), "unknown")

    def test_empty_returns_unknown(self) -> None:
        self.assertEqual(_normalize_key_part(""), "unknown")

    def test_spaces_replaced_with_underscore(self) -> None:
        self.assertEqual(_normalize_key_part("a b"), "a_b")


class IsValidPasscodeTests(SimpleTestCase):
    def test_valid_4_digit(self) -> None:
        self.assertTrue(_is_valid_passcode("1234"))
        self.assertTrue(_is_valid_passcode("0000"))
        self.assertTrue(_is_valid_passcode("9999"))

    def test_invalid_non_numeric(self) -> None:
        self.assertFalse(_is_valid_passcode("abcd"))

    def test_invalid_too_short(self) -> None:
        self.assertFalse(_is_valid_passcode("123"))

    def test_invalid_too_long(self) -> None:
        self.assertFalse(_is_valid_passcode("12345"))

    def test_invalid_empty(self) -> None:
        self.assertFalse(_is_valid_passcode(""))

    def test_invalid_none(self) -> None:
        self.assertFalse(_is_valid_passcode(None))

    def test_strips_whitespace(self) -> None:
        self.assertTrue(_is_valid_passcode(" 1234 "))


class GenerateNumericOtpTests(SimpleTestCase):
    def test_default_length_6(self) -> None:
        otp = _generate_numeric_otp()
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())

    def test_custom_length(self) -> None:
        otp = _generate_numeric_otp(4)
        self.assertEqual(len(otp), 4)

    def test_zero_length_defaults_to_6(self) -> None:
        otp = _generate_numeric_otp(0)
        self.assertEqual(len(otp), 6)

    def test_negative_length_defaults_to_6(self) -> None:
        otp = _generate_numeric_otp(-1)
        self.assertEqual(len(otp), 6)


class CacheKeyTests(SimpleTestCase):
    def test_phone_otp_session_key(self) -> None:
        key = _phone_otp_session_key("+12025550123", "REGISTER")
        self.assertIn("register", key)
        self.assertIn("+12025550123", key)

    def test_registration_email_otp_key(self) -> None:
        key = _registration_email_otp_key("token-abc")
        self.assertEqual(key, "auth:registration-email-otp:token-abc")

    def test_login_attempts_key(self) -> None:
        key = _login_attempts_key("+12025550123", "device-1")
        self.assertIn("login:attempts", key)

    def test_login_penalty_level_key(self) -> None:
        key = _login_penalty_level_key("+12025550123", "device-1")
        self.assertIn("login:penalty", key)

    def test_login_block_key(self) -> None:
        key = _login_block_key("+12025550123", "device-1")
        self.assertIn("login:block", key)

    def test_login_token_key(self) -> None:
        key = _login_token_key("my-token")
        self.assertEqual(key, "auth:login-token:my-token")

    def test_step_up_token_key(self) -> None:
        key = _step_up_token_key("step-token")
        self.assertEqual(key, "auth:step-up-token:step-token")


class FirebaseConfigTests(SimpleTestCase):
    @override_settings(FIREBASE_WEB_API_KEY="test-key-123")
    def test_firebase_web_api_key(self) -> None:
        self.assertEqual(_firebase_web_api_key(), "test-key-123")

    @override_settings(FIREBASE_WEB_API_KEY="")
    def test_firebase_web_api_key_empty(self) -> None:
        self.assertIsNone(_firebase_web_api_key())

    @override_settings(FIREBASE_AUTH_EMULATOR_HOST="localhost:9099")
    def test_firebase_auth_emulator_host(self) -> None:
        self.assertEqual(_firebase_auth_emulator_host(), "localhost:9099")

    @override_settings(FIREBASE_AUTH_EMULATOR_HOST="")
    def test_firebase_auth_emulator_host_empty(self) -> None:
        self.assertIsNone(_firebase_auth_emulator_host())

    @override_settings(FIREBASE_AUTH_EMULATOR_HOST="http://localhost:9099")
    def test_firebase_auth_emulator_host_strips_prefix(self) -> None:
        self.assertEqual(_firebase_auth_emulator_host(), "localhost:9099")

    @override_settings(FIREBASE_AUTH_EMULATOR_HOST="localhost:9099")
    def test_is_firebase_auth_emulator_enabled_true(self) -> None:
        self.assertTrue(_is_firebase_auth_emulator_enabled())

    @override_settings(FIREBASE_AUTH_EMULATOR_HOST="")
    def test_is_firebase_auth_emulator_enabled_false(self) -> None:
        self.assertFalse(_is_firebase_auth_emulator_enabled())

    @override_settings(FIREBASE_AUTH_EMULATOR_HOST="my-emulator:9099")
    def test_firebase_identity_base_url_emulator(self) -> None:
        url = _firebase_identity_base_url()
        self.assertIn("my-emulator:9099", url)
        self.assertIn("identitytoolkit.googleapis.com", url)

    @override_settings(FIREBASE_AUTH_EMULATOR_HOST="")
    def test_firebase_identity_base_url_production(self) -> None:
        url = _firebase_identity_base_url()
        self.assertEqual(url, "https://identitytoolkit.googleapis.com/v1")


class VerifyAccountTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="GB")
        self.user = User.objects.create_user(
            msisdn="+447911123456",
            country=self.country,
            email="verify_account@example.com",
            passcode="1234",
        )

    def test_existing_active_account(self) -> None:
        result, error = verify_account("+447911123456")
        self.assertIsNone(error)
        self.assertTrue(result["account_exists"])
        self.assertTrue(result["account_active"])

    def test_existing_inactive_account(self) -> None:
        self.user.is_active = False
        self.user.save()

        result, error = verify_account("+447911123456")
        self.assertIsNone(error)
        self.assertTrue(result["account_exists"])
        self.assertFalse(result["account_active"])

    def test_nonexistent_account(self) -> None:
        result, error = verify_account("+447911199999")
        self.assertIsNone(error)
        self.assertFalse(result["account_exists"])
        self.assertFalse(result["account_active"])

    def test_invalid_msisdn(self) -> None:
        result, error = verify_account("invalid")
        self.assertIsNone(result)
        self.assertIsNotNone(error)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class LoginRateLimitingTests(TestCase):
    """Tests for the login rate limiting utility functions."""

    def setUp(self) -> None:
        from django.core.cache import cache

        cache.clear()

    def tearDown(self) -> None:
        from django.core.cache import cache

        cache.clear()

    def test_current_block_seconds_returns_zero_when_not_blocked(self) -> None:
        from app.users.services import _current_block_seconds

        result = _current_block_seconds("+12025550123", "device-1")
        self.assertEqual(result, 0)

    def test_register_failed_attempt_no_block_under_5(self) -> None:
        from app.users.services import _register_failed_attempt

        for _ in range(4):
            blocked, seconds = _register_failed_attempt("+12025550123", "device-1")
            self.assertFalse(blocked)
            self.assertEqual(seconds, 0)

    @override_settings(PENALTY_RULES={0: 60}, MAX_PENALTY_LEVEL=1)
    def test_register_failed_attempt_blocks_at_5(self) -> None:
        from app.users.services import _register_failed_attempt

        # First 4 attempts - no block
        for _ in range(4):
            _register_failed_attempt("+12025550123", "device-1")

        # 5th attempt triggers block
        blocked, seconds = _register_failed_attempt("+12025550123", "device-1")
        self.assertTrue(blocked)
        self.assertEqual(seconds, 60)

    def test_reset_login_limit_state(self) -> None:
        from app.users.services import _register_failed_attempt, _reset_login_limit_state, _current_block_seconds

        # Create some state
        for _ in range(4):
            _register_failed_attempt("+12025550123", "device-1")

        _reset_login_limit_state("+12025550123", "device-1")

        # After reset, no block
        self.assertEqual(_current_block_seconds("+12025550123", "device-1"), 0)
