from django.db import models

from app.core.models import BaseModel


def generate_unique_wallet_id():
    from app.core.tools import generate_account_id

    max_attempts = 10

    for _ in range(max_attempts):
        wallet_id = generate_account_id()

        if not Wallet.objects.filter(wallet_id=wallet_id).exists():
            return wallet_id

    raise Exception("Failed to generate unique wallet_id")


class Wallet(BaseModel):
    wallet_id = models.CharField(
        max_length=11,
        unique=True,
        editable=False,
        default=generate_unique_wallet_id,
        db_index=True,
    )
    name = models.CharField(max_length=100)
    user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT, related_name="wallets")
    balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    in_transfer = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    is_main = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "wallets"
        indexes = [
            models.Index(fields=["user_account", "is_active"]),
            models.Index(fields=["user_account", "is_main"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["user_account", "name"], name="unique_wallet_name_per_account"),
            models.UniqueConstraint(
                fields=["user_account", "is_main"],
                condition=models.Q(is_main=True),
                name="unique_main_wallet_per_account",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.wallet_id})"
