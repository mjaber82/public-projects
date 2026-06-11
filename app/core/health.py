from .constants import ResponseMessage, ResponseStatus
from .tools import create_response


def health_check(request):
    return create_response(
        status=ResponseStatus.SUCCESS,
        message=ResponseMessage.SUCCESS,
        payload={"status": "ok"},
    )
