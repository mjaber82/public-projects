import json
import secrets
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

from app.users.models import User, UserAccount
from app.wallets.models import Wallet

from .models import LedgerEntry, Transaction


def _is_fake_stripe_checkout_enabled() -> bool:
    return bool(getattr(settings, "FAKE_STRIPE_CHECKOUT", False))


def _create_fake_stripe_session_id() -> str:
    return f"fake_cs_{secrets.token_urlsafe(16)}"


def _get_topup_transaction_for_session(session_id: str):
    return (
        Transaction.objects.select_related("to_wallet", "to_wallet__user_account")
        .filter(stripe_session_id=session_id, transaction_type="TOP_UP")
        .first()
    )


def _complete_topup_transaction(
    session_id: str,
    payment_method_id: str | None = None,
    card_brand: str | None = None,
    card_last4: str | None = None,
) -> tuple[bool, str | None]:
    with transaction.atomic():
        tx = (
            Transaction.objects.select_for_update()
            .select_related("to_wallet", "to_wallet__user_account")
            .filter(stripe_session_id=session_id, transaction_type="TOP_UP")
            .first()
        )
        if not tx:
            return False, "Checkout session not found"
        if tx.status != "PENDING":
            return False, f"Checkout session is already {tx.status.lower()}"
        if not tx.to_wallet:
            return False, "Top-up wallet not found"

        wallet = Wallet.objects.select_for_update().get(pk=tx.to_wallet.pk)
        wallet.balance += tx.amount
        wallet.save(update_fields=["balance"])

        tx.status = "COMPLETED"
        tx.completed_dt = timezone.now()
        tx.payment_method_id = (payment_method_id or f"pm_{session_id[-12:]}")[:255]
        tx.card_brand = (card_brand or "visa")[:20]
        tx.card_last4 = (card_last4 or "4242")[-4:]
        tx.save(
            update_fields=[
                "status",
                "completed_dt",
                "payment_method_id",
                "card_brand",
                "card_last4",
            ]
        )
        tx.ledgers.update(status="POSTED")

        _sync_account_totals(wallet.user_account)
        return True, None


def _cancel_topup_transaction(session_id: str, expired: bool = False) -> tuple[bool, str | None]:
    with transaction.atomic():
        tx = (
            Transaction.objects.select_for_update()
            .filter(stripe_session_id=session_id, transaction_type="TOP_UP")
            .first()
        )
        if not tx:
            return False, "Checkout session not found"
        if tx.status != "PENDING":
            return False, f"Checkout session is already {tx.status.lower()}"

        now = timezone.now()
        tx.status = "EXPIRED" if expired else "CANCELLED"
        if expired:
            tx.rejected_dt = now
            tx.save(update_fields=["status", "rejected_dt"])
        else:
            tx.revoked_dt = now
            tx.save(update_fields=["status", "revoked_dt"])
        tx.ledgers.update(status="VOIDED")
        return True, None


def get_fake_checkout_session(session_id: str) -> tuple[dict | None, str | None]:
    tx = _get_topup_transaction_for_session(session_id)
    if not tx:
        return None, "Checkout session not found"

    return {
        "session_id": session_id,
        "transaction_id": str(tx.public_id),
        "status": tx.status,
        "amount": str(tx.amount),
        "currency": tx.currency,
        "wallet_id": str(tx.to_wallet.public_id) if tx.to_wallet else None,
        "test_mode": True,
    }, None


def process_fake_checkout_action(
    session_id: str,
    action: str,
    payment_method_id: str | None = None,
    card_brand: str | None = None,
    card_last4: str | None = None,
) -> tuple[bool, str | None]:
    normalized_action = (action or "complete").strip().lower()
    if normalized_action == "complete":
        return _complete_topup_transaction(session_id, payment_method_id, card_brand, card_last4)
    if normalized_action == "cancel":
        return _cancel_topup_transaction(session_id, expired=False)
    if normalized_action == "expire":
        return _cancel_topup_transaction(session_id, expired=True)
    return False, "Unsupported fake checkout action"


def _sync_account_totals(account: UserAccount) -> None:
    totals = account.wallets.aggregate(total_balance=Sum("balance"), total_in_transfer=Sum("in_transfer"))
    account.balance = totals["total_balance"] or Decimal("0")
    account.in_transfer = totals["total_in_transfer"] or Decimal("0")
    account.save(update_fields=["balance", "in_transfer"])


def _get_main_wallet(user: User) -> Wallet | None:
    return Wallet.objects.filter(user_account__user=user, is_main=True, is_active=True).first()


def _create_transfer_ledgers(transaction_obj: Transaction) -> None:
    from_account = transaction_obj.from_wallet.user_account if transaction_obj.from_wallet else None
    to_account = transaction_obj.to_wallet.user_account if transaction_obj.to_wallet else None

    if from_account:
        LedgerEntry.objects.create(
            user_account=from_account,
            transaction=transaction_obj,
            type="DEBIT",
            amount=-abs(transaction_obj.amount),
            status="PENDING",
        )

    if to_account:
        LedgerEntry.objects.create(
            user_account=to_account,
            transaction=transaction_obj,
            type="CREDIT",
            amount=abs(transaction_obj.amount),
            status="PENDING",
        )


def _create_topup_ledger(transaction_obj: Transaction) -> None:
    if transaction_obj.to_wallet:
        LedgerEntry.objects.create(
            user_account=transaction_obj.to_wallet.user_account,
            transaction=transaction_obj,
            type="CREDIT",
            amount=abs(transaction_obj.amount),
            status="PENDING",
        )


def _sum_transfer_amount(queryset) -> Decimal:
    total = queryset.aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0")


def initiate_transfer(
    sender_user: User,
    sender_wallet_id: str,
    amount: Decimal,
    receiver_msisdn: str | None = None,
    receiver_wallet_id: str | None = None,
) -> tuple[Transaction | None, str | None]:
    if amount <= 0:
        return None, "Amount must be greater than zero"

    min_transfer_amount = Decimal(settings.MIN_TRANSFER_AMOUNT_USD)
    if amount < min_transfer_amount:
        return None, f"Amount must be at least {min_transfer_amount} USD"

    try:
        sender_wallet = Wallet.objects.get(public_id=sender_wallet_id, user_account__user=sender_user, is_active=True)
    except Wallet.DoesNotExist:
        return None, "Sender wallet not found"

    if sender_wallet.balance < amount:
        return None, "Insufficient balance"

    with transaction.atomic():
        sender_wallet = Wallet.objects.select_for_update().get(pk=sender_wallet.pk)
        if sender_wallet.balance < amount:
            return None, "Insufficient balance"

        if receiver_wallet_id:
            try:
                receiver_wallet = Wallet.objects.get(
                    public_id=receiver_wallet_id,
                    user_account=sender_wallet.user_account,
                    is_active=True,
                )
            except Wallet.DoesNotExist:
                return None, "Receiver wallet not found"

            sender_wallet.balance -= amount
            receiver_wallet.balance += amount
            sender_wallet.save(update_fields=["balance"])
            receiver_wallet.save(update_fields=["balance"])

            tx = Transaction.objects.create(
                from_wallet=sender_wallet,
                to_wallet=receiver_wallet,
                amount=amount,
                transaction_type="TRANSFER",
                status="COMPLETED",
                completed_dt=timezone.now(),
            )
            _create_transfer_ledgers(tx)
            tx.ledgers.update(status="POSTED")
            _sync_account_totals(sender_wallet.user_account)
            return tx, None

        if not receiver_msisdn:
            return None, "Receiver phone number is required"

        receiver_user = User.objects.filter(msisdn=receiver_msisdn).first()
        if not receiver_user or not receiver_user.is_active:
            return None, "Receiver not found"

        is_cross_user_transfer = receiver_user.public_id != sender_user.public_id

        if not is_cross_user_transfer:
            return None, "Use receiver_wallet_id for transfers between your own wallets"

        if is_cross_user_transfer:
            today = timezone.now().date()
            month_start = today.replace(day=1)
            counted_statuses = ["PENDING", "COMPLETED"]

            sender_cross_user_transfers = Transaction.objects.filter(
                transaction_type="TRANSFER",
                status__in=counted_statuses,
                from_wallet__user_account__user=sender_user,
            ).exclude(to_wallet__user_account__user=sender_user)

            daily_sent_total = _sum_transfer_amount(sender_cross_user_transfers.filter(created_dt__date=today))
            monthly_sent_total = _sum_transfer_amount(
                sender_cross_user_transfers.filter(created_dt__date__gte=month_start)
            )

            receiver_cross_user_transfers = Transaction.objects.filter(
                transaction_type="TRANSFER",
                status__in=counted_statuses,
                to_wallet__user_account__user=receiver_user,
            ).exclude(from_wallet__user_account__user=receiver_user)
            daily_receive_total = _sum_transfer_amount(receiver_cross_user_transfers.filter(created_dt__date=today))

            daily_send_limit = Decimal(settings.DAILY_SEND_LIMIT_USD)
            monthly_send_limit = Decimal(settings.MONTHLY_SEND_LIMIT_USD)
            daily_receive_limit = Decimal(settings.DAILY_RECEIVE_LIMIT_USD)

            if daily_sent_total + amount > daily_send_limit:
                return None, f"Daily send limit exceeded ({daily_send_limit} USD)"
            if monthly_sent_total + amount > monthly_send_limit:
                return None, f"Monthly send limit exceeded ({monthly_send_limit} USD)"
            if daily_receive_total + amount > daily_receive_limit:
                return (
                    None,
                    f"Receiver daily receive limit exceeded ({daily_receive_limit} USD)",
                )

        receiver_main_wallet = _get_main_wallet(receiver_user)
        if not receiver_main_wallet:
            return None, "Receiver main wallet not found"

        sender_wallet.balance -= amount
        sender_wallet.in_transfer += amount
        sender_wallet.save(update_fields=["balance", "in_transfer"])

        tx = Transaction.objects.create(
            from_wallet=sender_wallet,
            to_wallet=receiver_main_wallet,
            amount=amount,
            transaction_type="TRANSFER",
            status="PENDING",
        )
        _create_transfer_ledgers(tx)
        _sync_account_totals(sender_wallet.user_account)
        _sync_account_totals(receiver_main_wallet.user_account)
        return tx, None


def accept_transfer(receiver_user: User, transaction_id: str) -> tuple[bool, str | None]:
    with transaction.atomic():
        tx = (
            Transaction.objects.select_for_update()
            .select_related(
                "from_wallet",
                "to_wallet",
                "from_wallet__user_account",
                "to_wallet__user_account",
            )
            .filter(public_id=transaction_id, status="PENDING")
            .first()
        )
        if not tx or not tx.to_wallet or tx.to_wallet.user_account.user_id != receiver_user.public_id:
            return False, "Transaction not found or not pending"

        if not receiver_user.is_active:
            return False, "Account is deactivated"

        sender_wallet = tx.from_wallet
        receiver_wallet = tx.to_wallet

        sender_wallet.in_transfer -= tx.amount
        receiver_wallet.balance += tx.amount
        sender_wallet.save(update_fields=["in_transfer"])
        receiver_wallet.save(update_fields=["balance"])

        tx.status = "COMPLETED"
        tx.completed_dt = timezone.now()
        tx.save(update_fields=["status", "completed_dt"])
        tx.ledgers.update(status="POSTED")

        _sync_account_totals(sender_wallet.user_account)
        _sync_account_totals(receiver_wallet.user_account)
        return True, None


def reject_transfer(receiver_user: User, transaction_id: str, reason: str) -> tuple[bool, str | None]:
    with transaction.atomic():
        tx = (
            Transaction.objects.select_for_update()
            .select_related(
                "from_wallet",
                "to_wallet",
                "from_wallet__user_account",
                "to_wallet__user_account",
            )
            .filter(public_id=transaction_id, status="PENDING")
            .first()
        )
        if not tx or not tx.to_wallet or tx.to_wallet.user_account.user_id != receiver_user.public_id:
            return False, "Transaction not found or not pending"

        sender_wallet = tx.from_wallet
        sender_wallet.balance += tx.amount
        sender_wallet.in_transfer -= tx.amount
        sender_wallet.save(update_fields=["balance", "in_transfer"])

        tx.status = "REJECTED"
        tx.reject_reason = reason
        tx.rejected_dt = timezone.now()
        tx.save(update_fields=["status", "reject_reason", "rejected_dt"])
        tx.ledgers.update(status="VOIDED")

        _sync_account_totals(sender_wallet.user_account)
        if tx.to_wallet:
            _sync_account_totals(tx.to_wallet.user_account)
        return True, None


def cancel_transfer(sender_user: User, transaction_id: str, reason: str) -> tuple[bool, str | None]:
    with transaction.atomic():
        tx = (
            Transaction.objects.select_for_update()
            .select_related(
                "from_wallet",
                "to_wallet",
                "from_wallet__user_account",
                "to_wallet__user_account",
            )
            .filter(
                public_id=transaction_id,
                status="PENDING",
                from_wallet__user_account__user=sender_user,
            )
            .first()
        )
        if not tx:
            return False, "Transaction not found or not pending"

        sender_wallet = tx.from_wallet
        sender_wallet.balance += tx.amount
        sender_wallet.in_transfer -= tx.amount
        sender_wallet.save(update_fields=["balance", "in_transfer"])

        tx.status = "CANCELLED"
        tx.reject_reason = reason
        tx.revoked_dt = timezone.now()
        tx.save(update_fields=["status", "reject_reason", "revoked_dt"])
        tx.ledgers.update(status="VOIDED")

        _sync_account_totals(sender_wallet.user_account)
        if tx.to_wallet:
            _sync_account_totals(tx.to_wallet.user_account)
        return True, None


def get_transaction_detail(user: User, transaction_id: str) -> tuple[Transaction | None, str | None]:
    tx = Transaction.objects.filter(
        Q(public_id=transaction_id) & (Q(from_wallet__user_account__user=user) | Q(to_wallet__user_account__user=user))
    ).first()
    if not tx:
        return None, "Transaction not found"
    return tx, None


def create_stripe_session(user: User, wallet_id: str, amount: Decimal) -> tuple[str | None, str | None]:
    if amount <= 0:
        return None, "Amount must be greater than zero"

    max_topup = Decimal(settings.MAX_TOPUP_AMOUNT_USD)
    if amount > max_topup:
        return None, f"Top-up amount cannot exceed {max_topup} USD"

    wallet = Wallet.objects.filter(public_id=wallet_id, user_account__user=user, is_active=True, is_main=True).first()
    if not wallet:
        return None, "Main wallet not found"

    if not _is_fake_stripe_checkout_enabled():
        return None, "Live Stripe checkout is not implemented"

    fake_session_id = _create_fake_stripe_session_id()

    tx = Transaction.objects.create(
        to_wallet=wallet,
        amount=amount,
        currency="USD",
        transaction_type="TOP_UP",
        status="PENDING",
        stripe_session_id=fake_session_id,
    )
    _create_topup_ledger(tx)
    return reverse("transactions-topup-fake-checkout", kwargs={"session_id": fake_session_id}), None


def handle_stripe_webhook(payload: bytes, sig_header: str) -> tuple[bool, str | None]:
    if not _is_fake_stripe_checkout_enabled():
        return False, "Live Stripe webhook is not implemented"

    try:
        event = json.loads((payload or b"{}").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, "Invalid webhook payload"

    event_type = event.get("type")
    event_object = (event.get("data") or {}).get("object") or {}
    session_id = str(event_object.get("id") or "").strip()
    if not session_id:
        return False, "Missing checkout session id"

    if event_type == "checkout.session.completed":
        payment_method_details = event_object.get("payment_method_details") or {}
        card_details = payment_method_details.get("card") or {}
        return _complete_topup_transaction(
            session_id,
            event_object.get("payment_method") or event_object.get("payment_method_id"),
            card_details.get("brand") or event_object.get("card_brand"),
            card_details.get("last4") or event_object.get("card_last4"),
        )
    if event_type == "checkout.session.expired":
        return _cancel_topup_transaction(session_id, expired=True)

    return True, None


def export_transactions_csv(user: User, filters: dict) -> tuple[str | None, str | None]:
    import csv
    from io import StringIO

    query = Q(from_wallet__user_account__user=user) | Q(to_wallet__user_account__user=user)

    if filters.get("status"):
        query &= Q(status=filters.get("status"))
    if filters.get("transaction_type"):
        query &= Q(transaction_type=filters.get("transaction_type"))

    transactions = Transaction.objects.filter(query).order_by("-created_dt")

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Transaction ID",
            "Type",
            "Status",
            "Amount",
            "Currency",
            "Sender",
            "Receiver",
            "Created Date",
            "Completed Date",
        ]
    )

    for tx in transactions:
        sender_msisdn = tx.from_wallet.user_account.user.msisdn if tx.from_wallet else "N/A"
        receiver_msisdn = tx.to_wallet.user_account.user.msisdn if tx.to_wallet else "N/A"
        writer.writerow(
            [
                tx.transaction_id,
                tx.transaction_type,
                tx.status,
                tx.amount,
                tx.currency,
                sender_msisdn,
                receiver_msisdn,
                tx.created_dt.isoformat(),
                tx.completed_dt.isoformat() if tx.completed_dt else "N/A",
            ]
        )

    return output.getvalue(), None
