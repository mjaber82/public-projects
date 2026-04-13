from django.http import JsonResponse

from .constants import ResponseMessage, ResponseStatus
from .tools import create_response


def health_check(request):
    return JsonResponse(
        create_response(
            status=ResponseStatus.SUCCESS,
            message=ResponseMessage.SUCCESS,
            payload={"status": "ok"},
        ),
        safe=False,
    )
