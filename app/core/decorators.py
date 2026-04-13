from functools import wraps

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils import timezone

from .constants import ResponseMessage, ResponseStatus
from .tools import ajax_response, create_response, missing_params
from app.users.models import UserSession


def check_maintenance(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        if getattr(settings, "IS_MAINTENANCE", False):
            return ajax_response(
                create_response(
                    status=ResponseStatus.FAIL,
                    message=settings.MAINTENANCE_MESSAGE or ResponseMessage.MAINTENANCE_MODE,
                )
            )
        return func(request, *args, **kwargs)

    return wrapper


def api_auth(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        maintenance_response = None
        if getattr(settings, "IS_MAINTENANCE", False):
            maintenance_response = ajax_response(
                create_response(
                    status=ResponseStatus.FAIL,
                    message=settings.MAINTENANCE_MESSAGE or ResponseMessage.MAINTENANCE_MODE,
                )
            )

        if maintenance_response:
            return maintenance_response

        if (
            not hasattr(request, "user")
            or isinstance(request.user, AnonymousUser)
            or not request.user.is_authenticated
        ):
            return ajax_response(
                create_response(
                    status=ResponseStatus.FAIL,
                    message=ResponseMessage.NOT_AUTHENTICATED,
                )
            )

        if not request.user.is_active:
            return ajax_response(create_response(status=ResponseStatus.FAIL, message=ResponseMessage.USER_INACTIVE))

        # KYC gate is intentionally disabled for now.
        # if not getattr(request.user, "kyc_verified", False):
        #     return ajax_response(
        #         create_response(status=ResponseStatus.FAIL, message=ResponseMessage.KYC_REQUIRED)
        #     )

        session_id = getattr(request, "auth_session_id", None)
        if not session_id:
            return ajax_response(
                create_response(
                    status=ResponseStatus.FAIL,
                    message="Session is missing",
                )
            )

        user_session = UserSession.objects.filter(public_id=session_id, user=request.user, is_active=True).first()
        if not user_session:
            return ajax_response(
                create_response(
                    status=ResponseStatus.FAIL,
                    message="Session is revoked or inactive",
                )
            )

        if user_session.state == "LOCKED":
            return ajax_response(
                create_response(
                    status=ResponseStatus.FAIL,
                    message="Session is locked. Re-enter passcode.",
                    payload={
                        "session_state": "LOCKED",
                        "session_id": str(user_session.public_id),
                    },
                )
            )

        now = timezone.now()
        idle_window = getattr(settings, "APP_IDLE_TIME", None)
        last_seen = user_session.last_seen_at or user_session.updated_dt
        if idle_window is not None and last_seen and now - last_seen > idle_window:
            user_session.state = "LOCKED"
            user_session.last_seen_at = now
            user_session.save(update_fields=["state", "last_seen_at"])
            return ajax_response(
                create_response(
                    status=ResponseStatus.FAIL,
                    message="Session is locked. Re-enter passcode.",
                    payload={
                        "session_state": "LOCKED",
                        "session_id": str(user_session.public_id),
                    },
                )
            )

        user_session.last_seen_at = now
        user_session.save(update_fields=["last_seen_at"])

        return func(request, *args, **kwargs)

    return wrapper


def api_return(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        try:
            result = func(request, *args, **kwargs)
            if isinstance(result, HttpResponse):
                return result
            return result
        except ValidationError as exc:
            message = exc.message if hasattr(exc, "message") else ResponseMessage.UNKNOWN_ERROR
            if isinstance(message, (list, tuple)):
                message = message[0]
            return ajax_response(create_response(status=ResponseStatus.FAIL, message=str(message)))
        except Exception as exc:
            try:
                import sentry_sdk

                sentry_sdk.capture_exception(exc)
            except Exception:
                pass
            return ajax_response(
                create_response(
                    status=ResponseStatus.FAIL,
                    message=str(exc) or ResponseMessage.UNKNOWN_ERROR,
                )
            )

    return wrapper


def params_required(GET_LIST=None, POST_LIST=None, FILES_LIST=None, HTTP_LIST=None):
    GET_LIST = GET_LIST or []
    POST_LIST = POST_LIST or []
    FILES_LIST = FILES_LIST or []
    HTTP_LIST = HTTP_LIST or []

    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            missing = []
            missing.extend(missing_params(request.GET, GET_LIST))
            missing.extend(missing_params(request.POST, POST_LIST))
            missing.extend(missing_params(request.FILES, FILES_LIST))
            for header_name in HTTP_LIST:
                header_key = f"HTTP_{header_name.upper().replace('-', '_')}"
                if not request.META.get(header_key):
                    missing.append(header_name)

            if missing:
                return ajax_response(
                    create_response(
                        status=ResponseStatus.FAIL,
                        message=ResponseMessage.NOT_ENOUGH_INFO,
                        payload={"missing_params": missing},
                    )
                )
            return func(request, *args, **kwargs)

        return wrapper

    return decorator
