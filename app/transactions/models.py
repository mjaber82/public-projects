from django.db import models

from app.core.constants import (
    LedgerEntryStatus,
    LedgerEntryType,
    TransactionStatus,
    TransactionType,
)
from app.core.models import BaseModel


def generate_unique_tx_id():
    from app.core.tools import generate_account_id

    max_attempts = 10

    for _ in range(max_attempts):
        tx_id = generate_account_id()

        if not Transaction.objects.filter(transaction_id=tx_id).exists():
            return tx_id

    raise Exception("Failed to generate unique transaction_id")


class Transaction(BaseModel):
    transaction_id = models.CharField(
        max_length=11,
        unique=True,
        editable=False,
        default=generate_unique_tx_id,
        db_index=True,
    )
    from_wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.PROTECT,
        related_name="sent_transactions",
        null=True,
        blank=True,
    )
    to_wallet = models.ForeignKey(
        "wallets.Wallet",
        on_delete=models.PROTECT,
        related_name="received_transactions",
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
    )
    stripe_session_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    payment_method_id = models.CharField(max_length=255, null=True, blank=True)
    card_brand = models.CharField(max_length=20, null=True, blank=True)
    card_last4 = models.CharField(max_length=4, null=True, blank=True)
    reject_reason = models.TextField(null=True, blank=True)
    completed_dt = models.DateTimeField(null=True, blank=True)
    rejected_dt = models.DateTimeField(null=True, blank=True)
    revoked_dt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "transactions"
        indexes = [
            models.Index(fields=["from_wallet", "status"]),
            models.Index(fields=["to_wallet", "status"]),
            models.Index(fields=["status", "created_dt"]),
        ]

    def __str__(self):
        return f"Transaction {self.transaction_id} ({self.status})"


class LedgerEntry(models.Model):
    user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT)
    transaction = models.ForeignKey("transactions.Transaction", on_delete=models.PROTECT, related_name="ledgers")
    type = models.CharField(max_length=10, choices=LedgerEntryType.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(
        max_length=10,
        choices=LedgerEntryStatus.choices,
        default=LedgerEntryStatus.PENDING,
    )
    created_dt = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_dt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ledger_entries"
        indexes = [
            models.Index(fields=["user_account", "status"]),
            models.Index(fields=["transaction", "status"]),
        ]
