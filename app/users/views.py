import json

from app.core.constants import ResponseMessage, ResponseStatus
from app.core.decorators import api_auth, api_return
from app.core.tools import create_response, get_ip

from .serializers import (
    ChangeEmailSerializer,
    ChangePasscodeSerializer,
    ChangePhoneSerializer,
    CompleteRegistrationSerializer,
    ForgotPasscodeCompleteSerializer,
    ForgotPasscodeEmailVerifySerializer,
    ForgotPasscodeStartSerializer,
    LoginPasscodeSerializer,
    OtpRequestSerializer,
    OtpVerifySerializer,
    NoSimRecoveryCompleteSerializer,
    NoSimRecoveryEmailVerifySerializer,
    NoSimRecoveryStartSerializer,
    RefreshTokenSerializer,
    RegistrationEmailRequestSerializer,
    RegistrationEmailVerifySerializer,
    StepUpRequestSerializer,
    UnlockSessionSerializer,
    UpdateProfileSerializer,
    UserSerializer,
    VerifyAccountSerializer,
)
from .services import (
    send_change_email_otp,
    verify_change_email_otp,
    change_msisdn_with_step_up,
    change_passcode_with_step_up,
    complete_registration,
    deactivate_account,
    forgot_passcode_complete,
    forgot_passcode_start,
    forgot_passcode_verify_email,
    issue_step_up_token,
    login_with_passcode,
    no_sim_recovery_complete,
    no_sim_recovery_start,
    no_sim_recovery_verify_email,
    logout_user,
    refresh_access_token,
    request_phone_otp,
    send_registration_email_otp,
    unlock_session,
    update_profile,
    verify_account,
    verify_phone_otp,
    verify_registration_email_otp,
)


def _get_request_data(request):
    if request.method == "GET":
        return request.GET.dict()

    if request.POST:
        return request.POST.dict()

    if request.body:
        try:
            return json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    return {}


@api_return
def verify_account_view(request):
    serializer = VerifyAccountSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    payload, error = verify_account(serializer.validated_data["msisdn"])
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message=ResponseMessage.SUCCESS, payload=payload)


@api_return
def request_otp_view(request):
    serializer = OtpRequestSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    payload, error = request_phone_otp(
        serializer.validated_data["msisdn"],
        serializer.validated_data["purpose"],
        serializer.validated_data.get("recaptcha_token"),
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="OTP requested", payload=payload)


@api_return
def verify_otp_view(request):
    serializer = OtpVerifySerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    payload, error = verify_phone_otp(
        serializer.validated_data["msisdn"],
        serializer.validated_data["verification_code"],
        serializer.validated_data["purpose"],
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="OTP verified", payload=payload)


@api_return
def registration_email_request_view(request):
    serializer = RegistrationEmailRequestSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    success, error = send_registration_email_otp(
        serializer.validated_data["registration_token"],
        serializer.validated_data["email"],
    )
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Email OTP sent")


@api_return
def registration_email_verify_view(request):
    serializer = RegistrationEmailVerifySerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    success, error = verify_registration_email_otp(
        serializer.validated_data["registration_token"],
        serializer.validated_data["verification_code"],
    )
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Email verified")


@api_return
def complete_registration_view(request):
    serializer = CompleteRegistrationSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    payload, error = complete_registration(
        serializer.validated_data["registration_token"],
        serializer.validated_data["passcode"],
        serializer.validated_data.get("device_id") or request.META.get("HTTP_X_DEVICE_ID") or "unknown_device",
        get_ip(request),
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(status=ResponseStatus.SUCCESS, message="Registration completed", payload=payload)


@api_return
def login_passcode_view(request):
    serializer = LoginPasscodeSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    payload, error = login_with_passcode(
        serializer.validated_data["login_token"],
        serializer.validated_data["passcode"],
        get_ip(request),
        serializer.validated_data.get("device_id") or request.META.get("HTTP_X_DEVICE_ID") or "unknown_device",
        request.META.get("HTTP_USER_AGENT"),
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message=ResponseMessage.SUCCESS, payload=payload)


@api_return
def refresh_token_view(request):
    serializer = RefreshTokenSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    payload, error = refresh_access_token(serializer.validated_data["refresh_token"])
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message=ResponseMessage.SUCCESS, payload=payload)


@api_return
@api_auth
def unlock_session_view(request):
    serializer = UnlockSessionSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    payload, error = unlock_session(
        request.user,
        str(serializer.validated_data["session_id"]),
        serializer.validated_data["passcode"],
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Session unlocked", payload=payload)


@api_return
@api_auth
def logout_view(request):
    success, error = logout_user(request.user, str(getattr(request, "auth_session_id", "") or ""))
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Logged out")


@api_return
@api_auth
def get_info(request):
    return create_response(
        status=ResponseStatus.SUCCESS,
        message=ResponseMessage.SUCCESS,
        payload={"user": UserSerializer(request.user).data},
    )


@api_return
@api_auth
def update_profile_view(request):
    serializer = UpdateProfileSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    user, error = update_profile(request.user, serializer.validated_data)
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(
        status=ResponseStatus.SUCCESS,
        message=ResponseMessage.SUCCESS,
        payload={"user": UserSerializer(user).data},
    )


@api_return
@api_auth
def deactivate_account_view(request):
    success, error = deactivate_account(request.user)
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Account deactivated")


@api_return
@api_auth
def request_step_up_token_view(request):
    serializer = StepUpRequestSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    payload, error = issue_step_up_token(
        request.user,
        serializer.validated_data["current_passcode"],
        serializer.validated_data["purpose"],
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Step-up token issued", payload=payload)


@api_return
@api_auth
def change_passcode_view(request):
    serializer = ChangePasscodeSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    success, error = change_passcode_with_step_up(
        request.user,
        serializer.validated_data["step_up_token"],
        serializer.validated_data["new_passcode"],
    )
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Passcode changed")


@api_return
@api_auth
def change_phone_view(request):
    serializer = ChangePhoneSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    success, error = change_msisdn_with_step_up(
        request.user,
        serializer.validated_data["step_up_token"],
        serializer.validated_data["new_msisdn"],
        serializer.validated_data["verification_code"],
    )
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Phone changed")


@api_return
@api_auth
def change_email_view(request):
    serializer = ChangeEmailSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    verification_code = (serializer.validated_data.get("verification_code") or "").strip()
    if not verification_code:
        success, error = send_change_email_otp(
            request.user,
            serializer.validated_data["step_up_token"],
            serializer.validated_data["new_email"],
        )
        if not success:
            return create_response(status=ResponseStatus.FAIL, message=error)
        return create_response(status=ResponseStatus.SUCCESS, message="Email OTP sent")

    success, error = verify_change_email_otp(
        request.user,
        serializer.validated_data["step_up_token"],
        serializer.validated_data["new_email"],
        verification_code,
    )
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Email changed")


@api_return
def forgot_passcode_start_view(request):
    serializer = ForgotPasscodeStartSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    payload, error = forgot_passcode_start(
        serializer.validated_data["msisdn"],
        serializer.validated_data["verification_code"],
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Phone OTP verified", payload=payload)


@api_return
def forgot_passcode_email_verify_view(request):
    serializer = ForgotPasscodeEmailVerifySerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    payload, error = forgot_passcode_verify_email(
        serializer.validated_data["msisdn"],
        serializer.validated_data["email"],
        serializer.validated_data["step_up_token_1"],
        serializer.validated_data["verification_code"],
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Email OTP verified", payload=payload)


@api_return
def forgot_passcode_complete_view(request):
    serializer = ForgotPasscodeCompleteSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    success, error = forgot_passcode_complete(
        serializer.validated_data["msisdn"],
        serializer.validated_data["step_up_token_2"],
        serializer.validated_data["new_passcode"],
    )
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Passcode reset completed")


@api_return
def no_sim_recovery_start_view(request):
    serializer = NoSimRecoveryStartSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    payload, error = no_sim_recovery_start(
        serializer.validated_data["msisdn"],
        serializer.validated_data["passcode"],
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Passcode verified", payload=payload)


@api_return
def no_sim_recovery_email_verify_view(request):
    serializer = NoSimRecoveryEmailVerifySerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    payload, error = no_sim_recovery_verify_email(
        serializer.validated_data["msisdn"],
        serializer.validated_data["step_up_token_1"],
        serializer.validated_data["verification_code"],
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Email OTP verified", payload=payload)


@api_return
def no_sim_recovery_complete_view(request):
    serializer = NoSimRecoveryCompleteSerializer(data=_get_request_data(request))
    serializer.is_valid(raise_exception=True)

    success, error = no_sim_recovery_complete(
        serializer.validated_data["msisdn"],
        serializer.validated_data["step_up_token_2"],
        serializer.validated_data["new_msisdn"],
        serializer.validated_data["verification_code"],
    )
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)
    return create_response(status=ResponseStatus.SUCCESS, message="Phone recovery completed")
