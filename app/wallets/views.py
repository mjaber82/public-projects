import json

from app.core.constants import ResponseMessage, ResponseStatus
from app.core.decorators import api_return, api_auth
from app.core.tools import create_response
from .serializers import (
    CreateWalletSerializer,
    UpdateWalletSerializer,
    WalletActionSerializer,
    WalletSerializer,
)
from .services import (
    create_wallet as create_wallet_service,
    deactivate_wallet,
    get_wallet_detail,
    get_wallet_list,
    update_wallet_name,
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
def wallet_list(request):
    wallets = get_wallet_list(request.user)
    return create_response(
        status=ResponseStatus.SUCCESS,
        message=ResponseMessage.SUCCESS,
        payload={"wallets": WalletSerializer(wallets, many=True).data},
    )


@api_return
@api_auth
def wallet_detail(request):
    data = _get_request_data(request)
    serializer = WalletActionSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    wallet, error = get_wallet_detail(request.user, serializer.validated_data["key"])
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(
        status=ResponseStatus.SUCCESS,
        message=ResponseMessage.SUCCESS,
        payload={"wallet": WalletSerializer(wallet).data},
    )


@api_return
@api_auth
def create_wallet(request):
    data = _get_request_data(request)
    serializer = CreateWalletSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    wallet, error = create_wallet_service(request.user, serializer.validated_data["name"])
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(
        status=ResponseStatus.SUCCESS,
        message="Wallet created",
        payload={"wallet": WalletSerializer(wallet).data},
    )


@api_return
@api_auth
def update_wallet(request):
    data = _get_request_data(request)
    serializer = UpdateWalletSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    wallet, error = update_wallet_name(
        request.user,
        serializer.validated_data["key"],
        serializer.validated_data["name"],
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(
        status=ResponseStatus.SUCCESS,
        message="Wallet updated",
        payload={"wallet": WalletSerializer(wallet).data},
    )


@api_return
@api_auth
def deactivate_wallet_view(request):
    data = _get_request_data(request)
    serializer = WalletActionSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    success, error = deactivate_wallet(request.user, serializer.validated_data["key"])
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(status=ResponseStatus.SUCCESS, message="Wallet deactivated")
