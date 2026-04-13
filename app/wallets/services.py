from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from app.transactions.models import Transaction
from app.users.models import UserAccount

from .models import Wallet


def _get_or_create_user_account(user):
    account = UserAccount.objects.filter(user=user).first()
    if account:
        return account
    return UserAccount.objects.create(user=user, currency="USD", balance=0, in_transfer=0)


def _get_main_wallet(account: UserAccount) -> Wallet | None:
    return Wallet.objects.filter(user_account=account, is_main=True).first()


def ensure_main_wallet(user) -> Wallet:
    account = _get_or_create_user_account(user)
    main_wallet = _get_main_wallet(account)
    if main_wallet:
        return main_wallet
    return Wallet.objects.create(user_account=account, name="Main", is_main=True)


def create_wallet(user, name: str) -> tuple[Wallet | None, str | None]:
    name = (name or "").strip()
    if not name:
        return None, "Wallet name cannot be empty"

    account = _get_or_create_user_account(user)
    ensure_main_wallet(user)

    if name.lower() == "main":
        return None, "Main wallet already exists"

    if Wallet.objects.filter(user_account=account, name=name).exists():
        return None, "Wallet name already exists for this user"

    wallet = Wallet.objects.create(user_account=account, name=name, is_main=False)
    return wallet, None


def deactivate_wallet(user, wallet_id: str) -> tuple[bool, str | None]:
    try:
        wallet = Wallet.objects.get(public_id=wallet_id, user_account__user=user, is_active=True)
    except Wallet.DoesNotExist:
        return False, "Wallet not found or already inactive"

    if wallet.is_main:
        return False, "Main wallet cannot be deactivated"

    if wallet.in_transfer > Decimal("0"):
        return False, "Wallet has booked balance in transfer"

    if (
        Transaction.objects.filter(from_wallet=wallet, status="PENDING").exists()
        or Transaction.objects.filter(
            to_wallet=wallet,
            status="PENDING",
        ).exists()
    ):
        return False, "Wallet has pending transactions"

    with transaction.atomic():
        wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
        account = wallet.user_account
        main_wallet = _get_main_wallet(account)
        if not main_wallet or not main_wallet.is_active:
            return False, "Main wallet is not available"

        if wallet.balance > Decimal("0"):
            main_wallet.balance += wallet.balance
            main_wallet.save(update_fields=["balance"])
            wallet.balance = Decimal("0")

        wallet.is_active = False
        wallet.deactivated_at = timezone.now()
        wallet.save(update_fields=["balance", "is_active", "deactivated_at"])

    return True, None


def get_wallet_list(user) -> list[Wallet]:
    ensure_main_wallet(user)
    return list(Wallet.objects.filter(user_account__user=user, is_active=True).order_by("-is_main", "name"))


def get_wallet_detail(user, wallet_id: str) -> tuple[Wallet | None, str | None]:
    try:
        wallet = Wallet.objects.get(public_id=wallet_id, user_account__user=user)
        return wallet, None
    except Wallet.DoesNotExist:
        return None, "Wallet not found"


def update_wallet_name(user, wallet_id: str, name: str) -> tuple[Wallet | None, str | None]:
    name = (name or "").strip()
    if not name:
        return None, "Wallet name cannot be empty"

    try:
        wallet = Wallet.objects.get(public_id=wallet_id, user_account__user=user, is_active=True)
    except Wallet.DoesNotExist:
        return None, "Wallet not found"

    if wallet.is_main:
        return None, "Main wallet name cannot be changed"

    if Wallet.objects.filter(user_account=wallet.user_account, name=name).exclude(public_id=wallet_id).exists():
        return None, "Wallet name already exists for this user"

    wallet.name = name
    wallet.save(update_fields=["name"])
    return wallet, None
