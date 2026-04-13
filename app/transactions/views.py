import json

from django.db.models import Q
from app.core.constants import ResponseMessage, ResponseStatus
from app.core.decorators import api_return, api_auth, params_required
from app.core.tools import create_response
from .serializers import (
    RejectTransactionSerializer,
    TransactionActionSerializer,
    TransactionSerializer,
    TopUpSessionSerializer,
    TransferCreateSerializer,
)
from .services import (
    accept_transfer,
    cancel_transfer,
    create_stripe_session,
    export_transactions_csv,
    get_fake_checkout_session,
    get_transaction_detail,
    initiate_transfer,
    process_fake_checkout_action,
    reject_transfer,
    handle_stripe_webhook,
)
from .models import Transaction


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
def transactions_root(request):
    if request.method == "GET":
        filters = Q(from_wallet__user_account__user=request.user) | Q(to_wallet__user_account__user=request.user)
        params = request.GET
        wallet_id = params.get("wallet_id")
        if params.get("status"):
            filters &= Q(status=params.get("status"))
        if params.get("transaction_type"):
            filters &= Q(transaction_type=params.get("transaction_type"))

        transactions = Transaction.objects.filter(filters).order_by("-created_dt")
        return create_response(
            status=ResponseStatus.SUCCESS,
            message=ResponseMessage.SUCCESS,
            payload={
                "transactions": TransactionSerializer(transactions, many=True, context={"wallet_id": wallet_id}).data
            },
        )

    if request.method == "POST":
        data = _get_request_data(request)
        key = data.get("key")
        if not key:
            return create_response(status=ResponseStatus.FAIL, message="Transaction key is required")

        transaction_obj, error = get_transaction_detail(request.user, key)
        if error:
            return create_response(status=ResponseStatus.FAIL, message=error)

        return create_response(
            status=ResponseStatus.SUCCESS,
            message=ResponseMessage.SUCCESS,
            payload={"transaction": TransactionSerializer(transaction_obj).data},
        )

    return create_response(status=ResponseStatus.FAIL, message="Method not allowed")


@api_return
@api_auth
def transfer(request):
    data = _get_request_data(request)
    serializer = TransferCreateSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    transaction_obj, error = initiate_transfer(
        request.user,
        serializer.validated_data["sender_wallet_id"],
        serializer.validated_data["amount"],
        serializer.validated_data.get("receiver_msisdn"),
        serializer.validated_data.get("receiver_wallet_id"),
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(
        status=ResponseStatus.SUCCESS,
        message="Transfer initiated",
        payload={
            "transaction": TransactionSerializer(
                transaction_obj,
                context={
                    "wallet_id": str(transaction_obj.from_wallet.wallet_id) if transaction_obj.from_wallet else None
                },
            ).data
        },
    )


@api_return
@api_auth
def accept(request):
    data = _get_request_data(request)
    serializer = TransactionActionSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    success, error = accept_transfer(request.user, serializer.validated_data["key"])
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(status=ResponseStatus.SUCCESS, message="Transaction accepted")


@api_return
@api_auth
def reject(request):
    data = _get_request_data(request)
    serializer = RejectTransactionSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    success, error = reject_transfer(
        request.user,
        serializer.validated_data["key"],
        serializer.validated_data.get("reason", ""),
    )
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(status=ResponseStatus.SUCCESS, message="Transaction rejected")


@api_return
@api_auth
def cancel(request):
    data = _get_request_data(request)
    serializer = RejectTransactionSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    success, error = cancel_transfer(
        request.user,
        serializer.validated_data["key"],
        serializer.validated_data.get("reason", ""),
    )
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(status=ResponseStatus.SUCCESS, message="Transaction cancelled")


@api_return
@api_auth
def create_topup_session(request):
    data = _get_request_data(request)
    serializer = TopUpSessionSerializer(data=data)
    serializer.is_valid(raise_exception=True)

    session_url, error = create_stripe_session(
        request.user,
        serializer.validated_data["wallet_id"],
        serializer.validated_data["amount"],
    )
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(
        status=ResponseStatus.SUCCESS,
        message="Top-up session created",
        payload={"session_url": session_url},
    )


@api_return
def fake_topup_checkout(request, session_id: str):
    if request.method == "GET":
        payload, error = get_fake_checkout_session(session_id)
        if error:
            return create_response(status=ResponseStatus.FAIL, message=error)
        return create_response(
            status=ResponseStatus.SUCCESS,
            message="Fake checkout session",
            payload=payload,
        )

    data = _get_request_data(request)
    success, error = process_fake_checkout_action(
        session_id,
        data.get("action", "complete"),
        data.get("payment_method_id"),
        data.get("card_brand"),
        data.get("card_last4"),
    )
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(status=ResponseStatus.SUCCESS, message="Fake checkout processed")


@api_return
@params_required(HTTP_LIST=["Stripe-Signature"])
def stripe_webhook(request):
    signature = request.META.get("HTTP_STRIPE_SIGNATURE")
    success, error = handle_stripe_webhook(request.body or b"", signature)
    if not success:
        return create_response(status=ResponseStatus.FAIL, message=error)

    return create_response(status=ResponseStatus.SUCCESS, message="Webhook processed")


@api_return
@api_auth
def export_transactions(request):
    filters = {
        "status": request.GET.get("status"),
        "transaction_type": request.GET.get("transaction_type"),
    }
    csv_content, error = export_transactions_csv(request.user, filters)
    if error:
        return create_response(status=ResponseStatus.FAIL, message=error)

    from django.http import HttpResponse

    response = HttpResponse(csv_content, content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="transactions.csv"'
    return response
