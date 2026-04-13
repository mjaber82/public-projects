from django.urls import path

from . import views

urlpatterns = [
    path("auth/verify-account/", views.verify_account_view, name="auth-verify-account"),
    path("auth/otp/request/", views.request_otp_view, name="auth-otp-request"),
    path("auth/otp/verify/", views.verify_otp_view, name="auth-otp-verify"),
    path(
        "auth/register/email/request/",
        views.registration_email_request_view,
        name="auth-register-email-request",
    ),
    path(
        "auth/register/email/verify/",
        views.registration_email_verify_view,
        name="auth-register-email-verify",
    ),
    path(
        "auth/register/complete/",
        views.complete_registration_view,
        name="auth-register-complete",
    ),
    path("auth/login/passcode/", views.login_passcode_view, name="auth-login-passcode"),
    path("auth/token/refresh/", views.refresh_token_view, name="auth-token-refresh"),
    path("auth/session/unlock/", views.unlock_session_view, name="auth-session-unlock"),
    path("auth/logout/", views.logout_view, name="auth-logout"),
    path("users/get_info/", views.get_info, name="users-get-info"),
    path("users/update/", views.update_profile_view, name="users-update-profile"),
    path("users/deactivate/", views.deactivate_account_view, name="users-deactivate"),
    path(
        "users/step-up/request/",
        views.request_step_up_token_view,
        name="users-step-up-request",
    ),
    path(
        "users/passcode/change/",
        views.change_passcode_view,
        name="users-passcode-change",
    ),
    path("users/phone/change/", views.change_phone_view, name="users-phone-change"),
    path("users/email/change/", views.change_email_view, name="users-email-change"),
    path(
        "auth/passcode/forgot/start/",
        views.forgot_passcode_start_view,
        name="auth-passcode-forgot-start",
    ),
    path(
        "auth/passcode/forgot/email-verify/",
        views.forgot_passcode_email_verify_view,
        name="auth-passcode-forgot-email-verify",
    ),
    path(
        "auth/passcode/forgot/complete/",
        views.forgot_passcode_complete_view,
        name="auth-passcode-forgot-complete",
    ),
    path(
        "auth/recovery/no-sim/start/",
        views.no_sim_recovery_start_view,
        name="auth-recovery-no-sim-start",
    ),
    path(
        "auth/recovery/no-sim/email-verify/",
        views.no_sim_recovery_email_verify_view,
        name="auth-recovery-no-sim-email-verify",
    ),
    path(
        "auth/recovery/no-sim/complete/",
        views.no_sim_recovery_complete_view,
        name="auth-recovery-no-sim-complete",
    ),
]
