import json
import logging
import re
import secrets
import random
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from rest_framework_simplejwt.exceptions import TokenError

from app.core.tools import normalize_msisdn, validate_email_address, validate_username
from app.core.constants import RegistrationSessionStatus

from .models import FailedLoginAudit, RegistrationSession, User, UserSession
from .tokens import RefreshToken
from .email_utils import (
    render_welcome_email,
    render_deactivation_email,
    render_email_change_email,
)

logger = logging.getLogger(__name__)


UNKNOWN_DEVICE_ID = "unknown_device"
LOGIN_ATTEMPTS_WINDOW_SECONDS = 10 * 60
LOGIN_TOKEN_TTL_SECONDS = 10 * 60
REGISTRATION_TOKEN_TTL_SECONDS = 15 * 60
STEP_UP_TOKEN_TTL_SECONDS = 10 * 60
EMAIL_OTP_TTL_SECONDS = 10 * 60
EMULATOR_EMAIL_OTP_CODE = "123456"


def _phone_otp_session_key(msisdn: str, purpose: str) -> str:
    return f"auth:phone-otp-session:{_normalize_key_part(purpose)}:{_normalize_key_part(msisdn)}"


def _registration_email_otp_key(registration_token: str) -> str:
    return f"auth:registration-email-otp:{registration_token}"


def _change_email_otp_key(user: User, new_email: str) -> str:
    return f"auth:change-email-otp:{user.public_id}:{_normalize_key_part(new_email)}"


def _firebase_web_api_key() -> str | None:
    return (getattr(settings, "FIREBASE_WEB_API_KEY", "") or "").strip() or None


def _firebase_auth_emulator_host() -> str | None:
    host = (getattr(settings, "FIREBASE_AUTH_EMULATOR_HOST", "") or "").strip()
    if not host:
        return None
    return host.removeprefix("http://").removeprefix("https://")


def _is_firebase_auth_emulator_enabled() -> bool:
    return _firebase_auth_emulator_host() is not None


def _firebase_identity_base_url() -> str:
    emulator_host = _firebase_auth_emulator_host()
    if emulator_host:
        return f"http://{emulator_host}/identitytoolkit.googleapis.com/v1"
    return "https://identitytoolkit.googleapis.com/v1"


def _firebase_post(endpoint: str, payload: dict) -> tuple[dict | None, str | None]:
    api_key = _firebase_web_api_key()
    if not api_key and not _is_firebase_auth_emulator_enabled():
        return None, "Firebase Web API key is not configured"
    if not api_key:
        api_key = "fake-api-key"

    url = f"{_firebase_identity_base_url()}/{endpoint}?key={api_key}"
    request_payload = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=request_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8") or "{}"
            return json.loads(body), None
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8") if exc.fp else ""
        try:
            error_payload = json.loads(response_body or "{}")
            error_message = error_payload.get("error", {}).get("message")
        except json.JSONDecodeError:
            error_message = None
        return None, f"Firebase OTP request failed: {error_message or 'unknown error'}"
    except URLError:
        return None, "Firebase OTP request failed: network error"


def _request_firebase_phone_otp(msisdn: str, recaptcha_token: str | None) -> tuple[str | None, str | None]:
    payload = {"phoneNumber": msisdn}
    if not _is_firebase_auth_emulator_enabled():
        payload["recaptchaToken"] = recaptcha_token

    result, error = _firebase_post("accounts:sendVerificationCode", payload)
    if error:
        return None, error

    session_info = (result or {}).get("sessionInfo")
    if not session_info:
        return None, "Firebase OTP request failed: missing session info"
    return session_info, None


def _verify_firebase_phone_otp(session_info: str, otp_code: str) -> tuple[dict | None, str | None]:
    payload = {
        "sessionInfo": session_info,
        "code": otp_code,
    }
    result, error = _firebase_post("accounts:signInWithPhoneNumber", payload)
    if error:
        return None, error

    if not (result or {}).get("phoneNumber"):
        return None, "Invalid OTP"
    return result, None


def _generate_numeric_otp(length: int = 6) -> str:
    if length <= 0:
        length = 6
    return "".join(str(random.randint(0, 9)) for _ in range(length))


def _normalize_key_part(value: str | None) -> str:
    return (value or "").strip().lower().replace(" ", "_") or "unknown"


def _login_attempts_key(msisdn: str, device_id: str) -> str:
    return f"login:attempts:{_normalize_key_part(msisdn)}:{_normalize_key_part(device_id)}"


def _login_penalty_level_key(msisdn: str, device_id: str) -> str:
    return f"login:penalty:{_normalize_key_part(msisdn)}:{_normalize_key_part(device_id)}"


def _login_block_key(msisdn: str, device_id: str) -> str:
    return f"login:block:{_normalize_key_part(msisdn)}:{_normalize_key_part(device_id)}"


def _login_token_key(token: str) -> str:
    return f"auth:login-token:{token}"


def _step_up_token_key(token: str) -> str:
    return f"auth:step-up-token:{token}"


def _is_valid_passcode(passcode: str) -> bool:
    return bool(re.fullmatch(r"\d{4}", (passcode or "").strip()))


def _record_failed_login(
    msisdn: str,
    device_id: str,
    ip: str,
    user_agent: str | None,
    failure_reason: str,
) -> None:
    FailedLoginAudit.objects.create(
        msisdn=msisdn,
        device_id=device_id or UNKNOWN_DEVICE_ID,
        ip_address=ip or "0.0.0.0",
        user_agent=user_agent,
        failure_reason=failure_reason,
    )


def _current_block_seconds(msisdn: str, device_id: str) -> int:
    return int(cache.get(_login_block_key(msisdn, device_id)) or 0)


def _register_failed_attempt(msisdn: str, device_id: str) -> tuple[bool, int]:
    attempts_key = _login_attempts_key(msisdn, device_id)
    penalty_key = _login_penalty_level_key(msisdn, device_id)
    block_key = _login_block_key(msisdn, device_id)

    attempts = int(cache.get(attempts_key) or 0) + 1
    cache.set(attempts_key, attempts, timeout=LOGIN_ATTEMPTS_WINDOW_SECONDS)

    if attempts < 5:
        return False, 0

    current_penalty_level = int(cache.get(penalty_key) or 0)
    max_penalty_level = int(getattr(settings, "MAX_PENALTY_LEVEL", 4))
    next_penalty_level = min(current_penalty_level + 1, max_penalty_level)
    cache.set(penalty_key, next_penalty_level, timeout=7 * 24 * 60 * 60)

    rules = getattr(settings, "PENALTY_RULES", {})
    rule_index = max(0, min(next_penalty_level - 1, len(rules) - 1))
    block_seconds = int(rules.get(rule_index, 15 * 60))
    cache.set(block_key, block_seconds, timeout=block_seconds)
    cache.delete(attempts_key)
    return True, block_seconds


def _reset_login_limit_state(msisdn: str, device_id: str) -> None:
    cache.delete_many(
        [
            _login_attempts_key(msisdn, device_id),
            _login_penalty_level_key(msisdn, device_id),
            _login_block_key(msisdn, device_id),
        ]
    )


def _issue_auth_tokens(user: User, user_session: UserSession) -> dict[str, str]:
    refresh = RefreshToken.for_user_session(user, user_session)
    user_session.refresh_token_hash = make_password(str(refresh))
    user_session.last_seen_at = timezone.now()
    user_session.state = "UNLOCKED"
    user_session.is_active = True
    user_session.save(update_fields=["refresh_token_hash", "last_seen_at", "state", "is_active"])

    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
        "session_id": str(user_session.public_id),
        "session_state": user_session.state,
    }


def _get_or_create_device_session(user: User, device_id: str, ip: str) -> UserSession:
    user_session, _ = UserSession.objects.get_or_create(
        user=user,
        device_id=device_id,
        defaults={
            "ip_address": ip or "0.0.0.0",
            "is_active": True,
            "last_seen_at": timezone.now(),
            "state": "UNLOCKED",
        },
    )
    user_session.ip_address = ip or "0.0.0.0"
    user_session.save(update_fields=["ip_address"])
    return user_session


def verify_account(msisdn: str) -> tuple[dict | None, str | None]:
    normalized_msisdn, _, msisdn_error = normalize_msisdn(msisdn)
    if msisdn_error:
        return None, msisdn_error
    user = User.objects.filter(msisdn=normalized_msisdn).first()
    return {
        "account_exists": user is not None,
        "account_active": bool(user and user.is_active),
    }, None


def request_phone_otp(msisdn: str, purpose: str, recaptcha_token: str | None = None) -> tuple[dict | None, str | None]:
    normalized_msisdn, _, msisdn_error = normalize_msisdn(msisdn)
    if msisdn_error:
        return None, msisdn_error

    user_exists = User.objects.filter(msisdn=normalized_msisdn).exists()

    if purpose == "REGISTER" and user_exists:
        return None, "Account already exists"
    if purpose == "LOGIN" and not user_exists:
        return None, "Account not found"
    if not recaptcha_token and not _is_firebase_auth_emulator_enabled():
        return None, "recaptcha_token is required"

    session_info, otp_error = _request_firebase_phone_otp(normalized_msisdn, recaptcha_token)
    if otp_error:
        return None, otp_error

    otp_window_seconds = int(getattr(settings, "OTP_WINDOW_SECONDS", 3600))
    cache.set(
        _phone_otp_session_key(normalized_msisdn, purpose),
        session_info,
        timeout=otp_window_seconds,
    )
    return {
        "otp_required": True,
        "purpose": purpose,
        "msisdn": normalized_msisdn,
        "expires_in_seconds": otp_window_seconds,
    }, None


def verify_phone_otp(msisdn: str, otp_code: str, purpose: str) -> tuple[dict | None, str | None]:
    normalized_msisdn, _, msisdn_error = normalize_msisdn(msisdn)
    if msisdn_error:
        return None, msisdn_error

    if not otp_code:
        return None, "Invalid OTP"

    session_key = _phone_otp_session_key(normalized_msisdn, purpose)
    session_info = cache.get(session_key)
    if not session_info:
        return None, "OTP session expired. Request OTP again"

    verification_result, verification_error = _verify_firebase_phone_otp(str(session_info), otp_code)
    if verification_error:
        return None, verification_error

    verified_phone = (verification_result or {}).get("phoneNumber")
    if verified_phone and verified_phone != normalized_msisdn:
        return None, "OTP does not match the provided phone number"

    cache.delete(session_key)

    if purpose == "REGISTER":
        if User.objects.filter(msisdn=normalized_msisdn).exists():
            return None, "Account already exists"

        registration_token = secrets.token_urlsafe(32)
        RegistrationSession.objects.filter(msisdn=normalized_msisdn).delete()
        RegistrationSession.objects.create(
            msisdn=normalized_msisdn,
            registration_token=registration_token,
            phone_verified=True,
            email_verified=False,
            status=RegistrationSessionStatus.EMAIL_PENDING,
            expires_at=timezone.now() + timedelta(seconds=REGISTRATION_TOKEN_TTL_SECONDS),
        )
        return {
            "registration_token": registration_token,
            "expires_in_seconds": REGISTRATION_TOKEN_TTL_SECONDS,
        }, None

    if purpose == "LOGIN":
        user = User.objects.filter(msisdn=normalized_msisdn).first()
        if not user:
            return None, "Account not found"

        login_token = secrets.token_urlsafe(32)
        cache.set(
            _login_token_key(login_token),
            {"msisdn": normalized_msisdn},
            timeout=LOGIN_TOKEN_TTL_SECONDS,
        )
        return {
            "login_token": login_token,
            "expires_in_seconds": LOGIN_TOKEN_TTL_SECONDS,
        }, None

    return None, "Invalid purpose"


def send_registration_email_otp(registration_token: str, email: str) -> tuple[bool, str | None]:
    registration = RegistrationSession.objects.filter(registration_token=registration_token).first()
    if not registration or registration.expires_at < timezone.now():
        return False, "Registration token expired"

    normalized_email, email_error = validate_email_address(email)
    if email_error:
        return False, email_error

    registration.email = normalized_email
    registration.status = RegistrationSessionStatus.EMAIL_OTP_SENT
    registration.save(update_fields=["email", "status"])

    otp_ttl = int(getattr(settings, "EMAIL_OTP_TTL_SECONDS", EMAIL_OTP_TTL_SECONDS))
    if _is_firebase_auth_emulator_enabled():
        otp_code = EMULATOR_EMAIL_OTP_CODE
    else:
        otp_code = _generate_numeric_otp(6)

    cache.set(
        _registration_email_otp_key(registration_token),
        {"otp": otp_code, "email": normalized_email},
        timeout=otp_ttl,
    )

    if _is_firebase_auth_emulator_enabled():
        return True, None

    subject = "Your Digital Wallet email verification code"
    body = f"Your verification code is {otp_code}. It expires in {otp_ttl // 60} minutes."
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@digitalwallet.local")
    try:
        send_mail(subject, body, from_email, [normalized_email], fail_silently=False)
    except Exception:
        cache.delete(_registration_email_otp_key(registration_token))
        return False, "Unable to send verification email"

    return True, None


def verify_registration_email_otp(registration_token: str, otp_code: str) -> tuple[bool, str | None]:
    registration = RegistrationSession.objects.filter(registration_token=registration_token).first()
    if not registration or registration.expires_at < timezone.now():
        return False, "Registration token expired"
    if not registration.email:
        return False, "Email is not set"
    if not otp_code:
        return False, "Invalid OTP"

    verification_data = cache.get(_registration_email_otp_key(registration_token)) or {}
    stored_otp = str(verification_data.get("otp") or "")
    stored_email = str(verification_data.get("email") or "")
    if not stored_otp:
        return False, "Email OTP expired. Request a new code"
    if stored_email != registration.email:
        return False, "Email verification context mismatch"
    if stored_otp != str(otp_code).strip():
        return False, "Invalid OTP"

    cache.delete(_registration_email_otp_key(registration_token))

    registration.email_verified = True
    registration.status = RegistrationSessionStatus.EMAIL_VERIFIED
    registration.save(update_fields=["email_verified", "status"])
    return True, None


def complete_registration(
    registration_token: str,
    passcode: str,
    device_id: str,
    ip: str,
) -> tuple[dict | None, str | None]:
    if not _is_valid_passcode(passcode):
        return None, "Passcode must be exactly 4 digits"

    registration = RegistrationSession.objects.filter(registration_token=registration_token).first()
    if not registration or registration.expires_at < timezone.now():
        return None, "Registration token expired"
    if not registration.phone_verified or not registration.email_verified or not registration.email:
        return None, "Registration is not completed"

    if User.objects.filter(msisdn=registration.msisdn).exists():
        return None, "Account already exists"

    _, country, msisdn_error = normalize_msisdn(registration.msisdn)
    if msisdn_error:
        return None, msisdn_error

    with transaction.atomic():
        msisdn = registration.msisdn  # Capture before deletion
        user = User.objects.create_user(
            msisdn=registration.msisdn,
            country=country,
            email=registration.email,
            passcode=passcode,
        )
        user_session = _get_or_create_device_session(user, (device_id or "").strip() or UNKNOWN_DEVICE_ID, ip)
        tokens = _issue_auth_tokens(user, user_session)
        registration.delete()

        # Send welcome email
        _send_welcome_email(user, msisdn)

        return tokens, None


def login_with_passcode(
    login_token: str,
    passcode: str,
    ip: str,
    device_id: str,
    user_agent: str | None,
) -> tuple[dict | None, str | None]:
    if not _is_valid_passcode(passcode):
        return None, "Passcode must be exactly 4 digits"

    token_payload = cache.get(_login_token_key(login_token)) or {}
    msisdn = token_payload.get("msisdn")
    if not msisdn:
        return None, "Invalid login token"

    normalized_device_id = (device_id or "").strip() or UNKNOWN_DEVICE_ID
    blocked_for = _current_block_seconds(msisdn, normalized_device_id)
    if blocked_for > 0:
        _record_failed_login(msisdn, normalized_device_id, ip, user_agent, "blocked")
        return None, f"Too many failed attempts. Try again in {blocked_for} seconds."

    user = User.objects.filter(msisdn=msisdn).first()
    if not user:
        return None, "Account not found"

    if not user.check_password(passcode):
        _record_failed_login(msisdn, normalized_device_id, ip, user_agent, "wrong_passcode")
        blocked_now, block_seconds = _register_failed_attempt(msisdn, normalized_device_id)
        if blocked_now:
            return (
                None,
                f"Too many failed attempts. Try again in {block_seconds} seconds.",
            )
        return None, "Invalid passcode"

    _reset_login_limit_state(msisdn, normalized_device_id)

    if not user.is_active:
        user.is_active = True
        user.deactivated_at = None
        user.save(update_fields=["is_active", "deactivated_at"])

    user_session = _get_or_create_device_session(user, normalized_device_id, ip)
    token_data = _issue_auth_tokens(user, user_session)
    cache.delete(_login_token_key(login_token))
    return token_data, None


def refresh_access_token(refresh_token: str) -> tuple[dict | None, str | None]:
    try:
        refresh = RefreshToken(refresh_token)
        user = User.objects.get(public_id=refresh["user_id"])
        session_id = refresh.get("sid")
        if not session_id:
            return None, "Invalid refresh token"

        user_session = UserSession.objects.filter(public_id=session_id, user=user, is_active=True).first()
        if not user_session or not user_session.refresh_token_hash:
            return None, "Session revoked"
        if not check_password(refresh_token, user_session.refresh_token_hash):
            return None, "Invalid refresh token"

        token_data = _issue_auth_tokens(user, user_session)
        return token_data, None
    except (TokenError, KeyError, User.DoesNotExist):
        return None, "Invalid refresh token"


def logout_user(user: User, session_id: str | None) -> tuple[bool, str | None]:
    if not session_id:
        return False, "Session id is required"

    user_session = UserSession.objects.filter(public_id=session_id, user=user, is_active=True).first()
    if not user_session:
        return False, "Session not found"

    user_session.is_active = False
    user_session.last_seen_at = timezone.now()
    user_session.refresh_token_hash = None
    user_session.state = "LOCKED"
    user_session.save(update_fields=["is_active", "last_seen_at", "refresh_token_hash", "state"])
    return True, None


def unlock_session(user: User, session_id: str, passcode: str) -> tuple[dict | None, str | None]:
    if not _is_valid_passcode(passcode):
        return None, "Passcode must be exactly 4 digits"

    user_session = UserSession.objects.filter(public_id=session_id, user=user, is_active=True).first()
    if not user_session:
        return None, "Session not found"

    if user_session.state != "LOCKED":
        return None, "Session is not locked"

    if not user.check_password(passcode):
        return None, "Invalid passcode"

    return _issue_auth_tokens(user, user_session), None


def deactivate_account(user: User) -> tuple[bool, str | None]:
    if not user.is_active:
        return False, "Account is already deactivated"

    with transaction.atomic():
        user.is_active = False
        user.deactivated_at = timezone.now()
        user.save(update_fields=["is_active", "deactivated_at"])
        UserSession.objects.filter(user=user, is_active=True).update(
            is_active=False,
            state="LOCKED",
            refresh_token_hash=None,
            last_seen_at=timezone.now(),
        )

        # Send deactivation confirmation email
        _send_deactivation_email(user)

    return True, None


def update_profile(user: User, data: dict[str, object]) -> tuple[User | None, str | None]:
    errors: dict[str, str] = {}

    first_name_input = data.get("first_name")
    last_name_input = data.get("last_name")
    if first_name_input is not None and len(str(first_name_input).strip()) < 2:
        errors["first_name"] = "First name must be at least 2 characters"
    if last_name_input is not None and len(str(last_name_input).strip()) < 2:
        errors["last_name"] = "Last name must be at least 2 characters"

    first_name = (data.get("first_name") or user.first_name or "").strip().lower()
    last_name = (data.get("last_name") or user.last_name or "").strip().lower()
    username_input = data.get("username")
    if username_input is None:
        username = user.username
    else:
        normalized_username, username_error = validate_username(str(username_input))
        current_username = (user.username or "").strip().lower()
        if username_error and normalized_username != current_username:
            errors["username"] = username_error
        username = normalized_username or None

    email_notifications = data.get("email_notifications")
    if email_notifications is None:
        email_notifications = user.email_notifications

    if errors:
        return None, json.dumps(errors)

    user.first_name = first_name
    user.last_name = last_name
    user.username = username
    user.email_notifications = bool(email_notifications)
    user.save(update_fields=["first_name", "last_name", "username", "email_notifications"])
    return user, None


def issue_step_up_token(user: User, current_passcode: str, purpose: str) -> tuple[dict | None, str | None]:
    if not _is_valid_passcode(current_passcode):
        return None, "Passcode must be exactly 4 digits"
    if not user.check_password(current_passcode):
        return None, "Current passcode is invalid"

    token = secrets.token_urlsafe(32)
    cache.set(
        _step_up_token_key(token),
        {"user_id": str(user.public_id), "purpose": purpose},
        timeout=STEP_UP_TOKEN_TTL_SECONDS,
    )
    return {
        "step_up_token": token,
        "expires_in_seconds": STEP_UP_TOKEN_TTL_SECONDS,
    }, None


def _consume_step_up_token(step_up_token: str, user: User, purpose: str) -> tuple[bool, str | None]:
    payload = cache.get(_step_up_token_key(step_up_token)) or {}
    if not payload:
        return False, "Invalid step-up token"
    if payload.get("user_id") != str(user.public_id):
        return False, "Invalid step-up token"
    if payload.get("purpose") != purpose:
        return False, "Invalid step-up token purpose"
    cache.delete(_step_up_token_key(step_up_token))
    return True, None


def _validate_step_up_token(step_up_token: str, user: User, purpose: str) -> tuple[bool, str | None]:
    payload = cache.get(_step_up_token_key(step_up_token)) or {}
    if not payload:
        return False, "Invalid step-up token"
    if payload.get("user_id") != str(user.public_id):
        return False, "Invalid step-up token"
    if payload.get("purpose") != purpose:
        return False, "Invalid step-up token purpose"
    return True, None


def _apply_email_change(user: User, email: str) -> None:
    with transaction.atomic():
        user.email = email
        user.save(update_fields=["email"])
        UserSession.objects.filter(user=user, is_active=True).update(
            is_active=False,
            state="LOCKED",
            refresh_token_hash=None,
            last_seen_at=timezone.now(),
        )

    # Send email change confirmation to the new email address
    _send_email_change_confirmation(email, user.first_name)


def change_passcode_with_step_up(user: User, step_up_token: str, new_passcode: str) -> tuple[bool, str | None]:
    ok, error = _consume_step_up_token(step_up_token, user, "CHANGE_PASSCODE")
    if not ok:
        return False, error
    if not _is_valid_passcode(new_passcode):
        return False, "Passcode must be exactly 4 digits"

    with transaction.atomic():
        user.set_password(new_passcode)
        user.save(update_fields=["password"])
        UserSession.objects.filter(user=user, is_active=True).update(
            is_active=False,
            state="LOCKED",
            refresh_token_hash=None,
            last_seen_at=timezone.now(),
        )
    return True, None


def change_email_with_step_up(
    user: User, step_up_token: str, new_email: str, otp_code: str
) -> tuple[bool, str | None]:
    ok, error = _consume_step_up_token(step_up_token, user, "CHANGE_EMAIL")
    if not ok:
        return False, error
    if not otp_code:
        return False, "Invalid OTP"

    email, email_error = validate_email_address(new_email)
    if email_error:
        return False, email_error
    if email == (user.email or "").strip().lower():
        return False, "New email must be different from current email"

    _apply_email_change(user, email)
    return True, None


def send_change_email_otp(user: User, step_up_token: str, new_email: str) -> tuple[bool, str | None]:
    ok, error = _validate_step_up_token(step_up_token, user, "CHANGE_EMAIL")
    if not ok:
        return False, error

    email, email_error = validate_email_address(new_email)
    if email_error:
        return False, email_error
    if email == (user.email or "").strip().lower():
        return False, "New email must be different from current email"

    otp_ttl = int(getattr(settings, "EMAIL_OTP_TTL_SECONDS", EMAIL_OTP_TTL_SECONDS))
    otp_code = EMULATOR_EMAIL_OTP_CODE if _is_firebase_auth_emulator_enabled() else _generate_numeric_otp(6)
    cache.set(
        _change_email_otp_key(user, email),
        {"otp": otp_code, "email": email},
        timeout=otp_ttl,
    )

    if _is_firebase_auth_emulator_enabled():
        return True, None

    subject = "Your Digital Wallet email change verification code"
    body = f"Your verification code is {otp_code}. It expires in {otp_ttl // 60} minutes."
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@digitalwallet.local")
    try:
        send_mail(subject, body, from_email, [email], fail_silently=False)
    except Exception:
        cache.delete(_change_email_otp_key(user, email))
        return False, "Unable to send verification email"

    return True, None


def verify_change_email_otp(user: User, step_up_token: str, new_email: str, otp_code: str) -> tuple[bool, str | None]:
    if not otp_code:
        return False, "Invalid OTP"

    email, email_error = validate_email_address(new_email)
    if email_error:
        return False, email_error
    if email == (user.email or "").strip().lower():
        return False, "New email must be different from current email"

    verification_data = cache.get(_change_email_otp_key(user, email)) or {}
    stored_otp = str(verification_data.get("otp") or "")
    stored_email = str(verification_data.get("email") or "")
    if not stored_otp:
        return False, "Email OTP expired. Request a new code"
    if stored_email != email:
        return False, "Email verification context mismatch"
    if stored_otp != str(otp_code).strip():
        return False, "Invalid OTP"

    ok, error = _consume_step_up_token(step_up_token, user, "CHANGE_EMAIL")
    if not ok:
        return False, error

    cache.delete(_change_email_otp_key(user, email))
    _apply_email_change(user, email)
    return True, None


def change_msisdn_with_step_up(
    user: User, step_up_token: str, new_msisdn: str, otp_code: str
) -> tuple[bool, str | None]:
    ok, error = _consume_step_up_token(step_up_token, user, "CHANGE_PHONE")
    if not ok:
        return False, error
    if not otp_code:
        return False, "Invalid OTP"

    normalized_msisdn, country, msisdn_error = normalize_msisdn(new_msisdn)
    if msisdn_error:
        return False, msisdn_error
    if User.objects.filter(msisdn=normalized_msisdn).exclude(public_id=user.public_id).exists():
        return False, "MSISDN already registered"

    with transaction.atomic():
        user.msisdn = normalized_msisdn
        user.country = country
        user.save(update_fields=["msisdn", "country"])
        UserSession.objects.filter(user=user, is_active=True).update(
            is_active=False,
            state="LOCKED",
            refresh_token_hash=None,
            last_seen_at=timezone.now(),
        )
    return True, None


def _send_welcome_email(user: User, msisdn: str) -> None:
    """Send welcome email after successful registration."""
    if not user.email:
        return

    try:
        html_content, plain_text = render_welcome_email(
            first_name=user.first_name or user.msisdn,
            msisdn=msisdn,
            email=user.email,
        )
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@digitalwallet.local")
        send_mail(
            subject="Welcome to Digital Wallet!",
            message=plain_text,
            from_email=from_email,
            recipient_list=[user.email],
            fail_silently=True,
            html_message=html_content,
        )
    except Exception:
        logger.exception("Failed to send welcome email to user %s", user.public_id)


def _send_deactivation_email(user: User) -> None:
    """Send deactivation confirmation email."""
    if not user.email or not user.deactivated_at:
        return

    try:
        localized_deactivated_at = timezone.localtime(user.deactivated_at)
        formatted_date = localized_deactivated_at.strftime("%Y-%m-%d %H:%M:%S %Z")

        html_content, plain_text = render_deactivation_email(
            first_name=user.first_name or user.msisdn,
            deactivated_at=formatted_date,
        )
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@digitalwallet.local")
        send_mail(
            subject="Account Deactivated",
            message=plain_text,
            from_email=from_email,
            recipient_list=[user.email],
            fail_silently=True,
            html_message=html_content,
        )
    except Exception:
        logger.exception("Failed to send deactivation email to user %s", user.public_id)


def _send_email_change_confirmation(new_email: str, first_name: str) -> None:
    """Send email change confirmation to the new email address."""
    if not new_email:
        return

    try:
        changed_at = timezone.now()
        localized_changed_at = timezone.localtime(changed_at)
        formatted_changed_at = localized_changed_at.strftime("%Y-%m-%d %H:%M:%S %Z")

        html_content, plain_text = render_email_change_email(
            first_name=first_name or "User",
            new_email=new_email,
            changed_at=formatted_changed_at,
        )
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@digitalwallet.local")
        send_mail(
            subject="Your Digital Wallet email was changed",
            message=plain_text,
            from_email=from_email,
            recipient_list=[new_email],
            fail_silently=True,
            html_message=html_content,
        )
    except Exception:
        logger.exception("Failed to send email change confirmation to %s", new_email)


def forgot_passcode_start(msisdn: str, otp_code: str) -> tuple[dict | None, str | None]:
    normalized_msisdn, _, msisdn_error = normalize_msisdn(msisdn)
    if msisdn_error:
        return None, msisdn_error
    if not otp_code:
        return None, "Invalid OTP"

    user = User.objects.filter(msisdn=normalized_msisdn).first()
    if not user:
        return None, "Account not found"

    token = secrets.token_urlsafe(32)
    cache.set(
        _step_up_token_key(token),
        {"user_id": str(user.public_id), "purpose": "FORGOT_PASSCODE_STEP1"},
        timeout=STEP_UP_TOKEN_TTL_SECONDS,
    )
    return {
        "step_up_token_1": token,
        "expires_in_seconds": STEP_UP_TOKEN_TTL_SECONDS,
    }, None


def forgot_passcode_verify_email(
    msisdn: str, email: str, step_up_token_1: str, otp_code: str
) -> tuple[dict | None, str | None]:
    normalized_msisdn, _, msisdn_error = normalize_msisdn(msisdn)
    if msisdn_error:
        return None, msisdn_error
    if not otp_code:
        return None, "Invalid OTP"

    user = User.objects.filter(msisdn=normalized_msisdn, email=email).first()
    if not user:
        return None, "User not found"

    payload = cache.get(_step_up_token_key(step_up_token_1)) or {}
    if payload.get("user_id") != str(user.public_id) or payload.get("purpose") != "FORGOT_PASSCODE_STEP1":
        return None, "Invalid step-up token"
    cache.delete(_step_up_token_key(step_up_token_1))

    token2 = secrets.token_urlsafe(32)
    cache.set(
        _step_up_token_key(token2),
        {"user_id": str(user.public_id), "purpose": "FORGOT_PASSCODE_STEP2"},
        timeout=STEP_UP_TOKEN_TTL_SECONDS,
    )
    return {
        "step_up_token_2": token2,
        "expires_in_seconds": STEP_UP_TOKEN_TTL_SECONDS,
    }, None


def forgot_passcode_complete(msisdn: str, step_up_token_2: str, new_passcode: str) -> tuple[bool, str | None]:
    normalized_msisdn, _, msisdn_error = normalize_msisdn(msisdn)
    if msisdn_error:
        return False, msisdn_error
    if not _is_valid_passcode(new_passcode):
        return False, "Passcode must be exactly 4 digits"

    user = User.objects.filter(msisdn=normalized_msisdn).first()
    if not user:
        return False, "Account not found"

    payload = cache.get(_step_up_token_key(step_up_token_2)) or {}
    if payload.get("user_id") != str(user.public_id) or payload.get("purpose") != "FORGOT_PASSCODE_STEP2":
        return False, "Invalid step-up token"
    cache.delete(_step_up_token_key(step_up_token_2))

    with transaction.atomic():
        user.set_password(new_passcode)
        user.save(update_fields=["password"])
        UserSession.objects.filter(user=user, is_active=True).update(
            is_active=False,
            state="LOCKED",
            refresh_token_hash=None,
            last_seen_at=timezone.now(),
        )
    return True, None


def no_sim_recovery_start(msisdn: str, passcode: str) -> tuple[dict | None, str | None]:
    normalized_msisdn, _, msisdn_error = normalize_msisdn(msisdn)
    if msisdn_error:
        return None, msisdn_error
    if not _is_valid_passcode(passcode):
        return None, "Passcode must be exactly 4 digits"

    user = User.objects.filter(msisdn=normalized_msisdn).first()
    if not user:
        return None, "Account not found"
    if not user.check_password(passcode):
        return None, "Invalid passcode"

    token = secrets.token_urlsafe(32)
    cache.set(
        _step_up_token_key(token),
        {"user_id": str(user.public_id), "purpose": "NO_SIM_STEP1"},
        timeout=STEP_UP_TOKEN_TTL_SECONDS,
    )
    return {
        "step_up_token_1": token,
        "expires_in_seconds": STEP_UP_TOKEN_TTL_SECONDS,
    }, None


def no_sim_recovery_verify_email(msisdn: str, step_up_token_1: str, otp_code: str) -> tuple[dict | None, str | None]:
    normalized_msisdn, _, msisdn_error = normalize_msisdn(msisdn)
    if msisdn_error:
        return None, msisdn_error
    if not otp_code:
        return None, "Invalid OTP"

    user = User.objects.filter(msisdn=normalized_msisdn).first()
    if not user:
        return None, "Account not found"

    payload = cache.get(_step_up_token_key(step_up_token_1)) or {}
    if payload.get("user_id") != str(user.public_id) or payload.get("purpose") != "NO_SIM_STEP1":
        return None, "Invalid step-up token"
    cache.delete(_step_up_token_key(step_up_token_1))

    token2 = secrets.token_urlsafe(32)
    cache.set(
        _step_up_token_key(token2),
        {"user_id": str(user.public_id), "purpose": "NO_SIM_STEP2"},
        timeout=STEP_UP_TOKEN_TTL_SECONDS,
    )
    return {
        "step_up_token_2": token2,
        "expires_in_seconds": STEP_UP_TOKEN_TTL_SECONDS,
    }, None


def no_sim_recovery_complete(
    msisdn: str, step_up_token_2: str, new_msisdn: str, otp_code: str
) -> tuple[bool, str | None]:
    normalized_msisdn, _, msisdn_error = normalize_msisdn(msisdn)
    if msisdn_error:
        return False, msisdn_error
    if not otp_code:
        return False, "Invalid OTP"

    user = User.objects.filter(msisdn=normalized_msisdn).first()
    if not user:
        return False, "Account not found"

    payload = cache.get(_step_up_token_key(step_up_token_2)) or {}
    if payload.get("user_id") != str(user.public_id) or payload.get("purpose") != "NO_SIM_STEP2":
        return False, "Invalid step-up token"
    cache.delete(_step_up_token_key(step_up_token_2))

    normalized_new_msisdn, country, new_msisdn_error = normalize_msisdn(new_msisdn)
    if new_msisdn_error:
        return False, new_msisdn_error
    if User.objects.filter(msisdn=normalized_new_msisdn).exclude(public_id=user.public_id).exists():
        return False, "MSISDN already registered"

    with transaction.atomic():
        user.msisdn = normalized_new_msisdn
        user.country = country
        user.save(update_fields=["msisdn", "country"])
        UserSession.objects.filter(user=user, is_active=True).update(
            is_active=False,
            state="LOCKED",
            refresh_token_hash=None,
            last_seen_at=timezone.now(),
        )

    return True, None
