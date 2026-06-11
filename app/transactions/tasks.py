import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from app.core.constants import TransactionStatus
from app.notifications.services import create_notification
from app.transactions.models import Transaction

logger = logging.getLogger(__name__)


def _send_transaction_email_to_user(user, subject: str, message: str) -> None:
    if not user.email or not user.email_notifications:
        return

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@digitalwallet.local")
    try:
        send_mail(subject, message, from_email, [user.email], fail_silently=False)
    except Exception:
        logger.exception("Failed to send notification email to user %s", user)


@shared_task(queue="notifications")
def notify_transfer_initiated(transaction_public_id: str) -> bool:
    try:
        tx = Transaction.objects.select_related(
            "from_wallet__user_account__user", "to_wallet__user_account__user"
        ).get(public_id=transaction_public_id)
    except Transaction.DoesNotExist:
        logger.warning("notify_transfer_initiated: transaction not found %s", transaction_public_id)
        return False

    sender = tx.from_wallet.user_account.user if tx.from_wallet else None
    receiver = tx.to_wallet.user_account.user if tx.to_wallet else None
    if not sender:
        return False

    sender_title = "Transfer initiated"
    sender_body = (
        f"Your transfer of {tx.amount} {tx.currency} is pending. The recipient will accept or reject it soon."
    )
    create_notification(sender, sender_title, sender_body, "TRANSFER_INITIATED", related_tx=tx)

    if receiver:
        receiver_title = "Transfer received"
        receiver_body = f"You have a pending transfer of {tx.amount} {tx.currency} from {sender.username}."
        create_notification(receiver, receiver_title, receiver_body, "TRANSFER_RECEIVED", related_tx=tx)
        _send_transaction_email_to_user(
            receiver,
            receiver_title,
            f"A transfer of {tx.amount} {tx.currency} from {sender.username} is waiting for your acceptance.",
        )

    return True


@shared_task(queue="notifications")
def notify_transfer_completed(transaction_public_id: str) -> bool:
    try:
        tx = Transaction.objects.select_related(
            "from_wallet__user_account__user", "to_wallet__user_account__user"
        ).get(public_id=transaction_public_id)
    except Transaction.DoesNotExist:
        logger.warning("notify_transfer_completed: transaction not found %s", transaction_public_id)
        return False

    sender = tx.from_wallet.user_account.user if tx.from_wallet else None
    receiver = tx.to_wallet.user_account.user if tx.to_wallet else None
    if not sender:
        return False

    sender_title = "Transfer completed"
    sender_body = f"Your transfer of {tx.amount} {tx.currency} to {receiver.username if receiver else 'the recipient'} has been completed."
    create_notification(sender, sender_title, sender_body, "TRANSFER_COMPLETED", related_tx=tx)
    _send_transaction_email_to_user(
        sender,
        sender_title,
        sender_body,
    )

    if receiver:
        receiver_title = "Transfer received"
        receiver_body = f"You have received {tx.amount} {tx.currency} from {sender.username}."
        create_notification(receiver, receiver_title, receiver_body, "TRANSFER_COMPLETED", related_tx=tx)
        _send_transaction_email_to_user(
            receiver,
            receiver_title,
            receiver_body,
        )

    return True


@shared_task(queue="notifications")
def notify_transfer_rejected(transaction_public_id: str) -> bool:
    try:
        tx = Transaction.objects.select_related(
            "from_wallet__user_account__user", "to_wallet__user_account__user"
        ).get(public_id=transaction_public_id)
    except Transaction.DoesNotExist:
        logger.warning("notify_transfer_rejected: transaction not found %s", transaction_public_id)
        return False

    sender = tx.from_wallet.user_account.user if tx.from_wallet else None
    if not sender:
        return False
    reject_reason = tx.reject_reason or "No reason was provided."
    title = "Transfer rejected"
    body = f"Your transfer of {tx.amount} {tx.currency} was rejected. Reason: {reject_reason}"
    create_notification(sender, title, body, "TRANSFER_REJECTED", related_tx=tx)
    _send_transaction_email_to_user(sender, title, body)

    return True


@shared_task(queue="notifications")
def notify_topup_completed(transaction_public_id: str) -> bool:
    try:
        tx = Transaction.objects.select_related("to_wallet__user_account__user").get(public_id=transaction_public_id)
    except Transaction.DoesNotExist:
        logger.warning("notify_topup_completed: transaction not found %s", transaction_public_id)
        return False

    user = tx.to_wallet.user_account.user if tx.to_wallet else None
    if not user:
        return False
    title = "Top-up completed"
    body = f"Your wallet has been credited with {tx.amount} {tx.currency}."
    create_notification(user, title, body, "TOP_UP_COMPLETED", related_tx=tx)
    _send_transaction_email_to_user(user, title, body)

    return True


@shared_task(queue="default")
def expire_pending_tx() -> int:
    from django.db import transaction as db_transaction
    from app.wallets.models import Wallet

    expiration_days = getattr(settings, "TRANSACTION_TIMEOUT_DAYS", 30)
    cutoff = timezone.now() - timedelta(days=expiration_days)
    expired_transactions = Transaction.objects.filter(status=TransactionStatus.PENDING, created_dt__lt=cutoff)

    count = 0
    for tx in expired_transactions.select_related("from_wallet__user_account__user", "to_wallet__user_account"):
        sender_user = tx.from_wallet.user_account.user if tx.from_wallet else None
        if not sender_user:
            logger.warning("expire_pending_tx: skipping transaction %s with no sender wallet", tx.public_id)
            continue

        try:
            with db_transaction.atomic():
                locked_tx = Transaction.objects.select_for_update().get(pk=tx.pk, status=TransactionStatus.PENDING)
                locked_tx.status = TransactionStatus.EXPIRED
                locked_tx.rejected_dt = timezone.now()
                locked_tx.save(update_fields=["status", "rejected_dt"])
                locked_tx.ledgers.update(status="VOIDED")

                sender_wallet = Wallet.objects.select_for_update().get(pk=tx.from_wallet.pk)
                sender_wallet.balance += tx.amount
                sender_wallet.in_transfer -= tx.amount
                sender_wallet.save(update_fields=["balance", "in_transfer"])

            create_notification(
                sender_user,
                "Pending transfer expired",
                f"Your pending transfer of {tx.amount} {tx.currency} has expired after {expiration_days} days.",
                "TRANSFER_EXPIRED",
                related_tx=tx,
            )
            count += 1
        except Transaction.DoesNotExist:
            logger.info("expire_pending_tx: transaction %s already processed", tx.public_id)
        except Exception:
            logger.exception("expire_pending_tx: failed to expire transaction %s", tx.public_id)

    return count
