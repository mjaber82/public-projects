import json

from app.core.constants import ResponseMessage, ResponseStatus
from app.core.decorators import api_return, api_auth
from app.core.tools import create_response
from .serializers import NotificationActionSerializer, NotificationSerializer
from .services import (
    clear_notification,
    clear_notifications,
    get_notifications,
    mark_read,
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
@api_auth
def notification_list(request):
    notifications = get_notifications(request.user)
    return create_response(
        status=ResponseStatus.SUCCESS,
        message=ResponseMessage.SUCCESS,
        payload={"notifications": NotificationSerializer(notifications, many=True).data},
    )


@api_return
@api_auth
def mark_notification_read(request):
    data = _get_request_data(request)
    serializer = NotificationActionSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    success, error = mark_read(request.user, serializer.validated_data["key"])
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(status=ResponseStatus.SUCCESS, message="Notification marked as read")


@api_return
@api_auth
def mark_all_read(request):
    updated_count = clear_notifications(request.user)
    return create_response(
        status=ResponseStatus.SUCCESS,
        message="Notifications marked as read",
        payload={"updated_count": updated_count},
    )


@api_return
@api_auth
def clear_notification_view(request):
    data = _get_request_data(request)
    serializer = NotificationActionSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    success, error = clear_notification(request.user, serializer.validated_data["key"])
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(status=ResponseStatus.SUCCESS, message="Notification deleted")


@api_return
@api_auth
def clear_all_notifications(request):
    deleted_count, _ = request.user.notifications.all().delete()
    return create_response(
        status=ResponseStatus.SUCCESS,
        message="Notifications cleared",
        payload={"deleted_count": deleted_count},
    )
