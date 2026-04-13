from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser
from django.db import models, transaction

from app.core.models import BaseModel
from app.core.constants import RegistrationSessionStatus, UserSessionState


def generate_unique_account_id():
    from app.core.tools import generate_account_id

    max_attempts = 10

    for _ in range(max_attempts):
        account_id = generate_account_id()

        if not UserAccount.objects.filter(account_id=account_id).exists():
            return account_id

    raise Exception("Failed to generate unique account_id")


class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)
    iso_2 = models.CharField(max_length=2, unique=True, db_index=True)
    iso_phone_code = models.CharField(max_length=10)

    class Meta:
        db_table = "countries"
        ordering = ["name"]
        verbose_name_plural = "countries"

    def __str__(self):
        return f"{self.name} ({self.iso_2})"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, msisdn, country, email, passcode, **extra_fields):
        if not msisdn:
            raise ValueError("The msisdn must be set")
        if country is None:
            raise ValueError("The country must be set")
        if not email:
            raise ValueError("The email must be set")
        if not passcode:
            raise ValueError("The passcode must be set")

        with transaction.atomic():
            user = self.model(
                msisdn=msisdn,
                country=country,
                email=email,
                **extra_fields,
            )
            # Passcode is stored in Django's hashed password field.
            user.set_password(passcode)
            user.save(using=self._db)

            account = UserAccount.objects.create(user=user)

            # Import lazily to avoid circular imports.
            from app.wallets.models import Wallet

            Wallet.objects.create(
                user_account=account,
                name="Main",
                is_main=True,
            )

            return user

    def create_user(self, msisdn, country, email, passcode, **extra_fields):
        return self._create_user(
            msisdn=msisdn,
            country=country,
            email=email,
            passcode=passcode,
            **extra_fields,
        )


class User(AbstractBaseUser, BaseModel):
    username = models.CharField(max_length=50, unique=True, db_index=True, null=True, blank=True)
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=100, blank=True, default="")
    last_name = models.CharField(max_length=100, blank=True, default="")
    msisdn = models.CharField(max_length=20, unique=True, db_index=True)
    dob = models.DateField(null=True, blank=True)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    consent = models.BooleanField(default=False)
    kyc_verified = models.BooleanField(default=False)
    kyc_verified_dt = models.DateTimeField(blank=True, null=True)
    email_notifications = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "msisdn"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return self.msisdn


class UserAccount(BaseModel):
    account_id = models.CharField(
        max_length=11,
        unique=True,
        editable=False,
        default=generate_unique_account_id,
        db_index=True,
    )
    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="account", db_index=True)
    currency = models.CharField(max_length=3, default="USD")
    balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    in_transfer = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    class Meta:
        db_table = "user_accounts"

    def __str__(self):
        return f"Account({self.account_id}) for {self.user.username}"


class UserSession(BaseModel):
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    device_id = models.CharField(max_length=128, db_index=True)
    ip_address = models.GenericIPAddressField()
    refresh_token_hash = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(blank=True, null=True)
    state = models.CharField(
        max_length=20,
        choices=UserSessionState.choices,
        default=UserSessionState.UNLOCKED,
    )

    class Meta:
        db_table = "user_sessions"
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]
        constraints = [models.UniqueConstraint(fields=["user", "device_id"], name="unique_user_session")]

    def __str__(self):
        return f"Device({self.device_id}) for {self.user.username}"


class FailedLoginAudit(BaseModel):
    msisdn = models.CharField(max_length=20, db_index=True)
    device_id = models.CharField(max_length=100)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    failure_reason = models.CharField(max_length=50)

    class Meta:
        db_table = "failed_login_audit"
        indexes = [
            models.Index(fields=["msisdn", "created_dt"]),
        ]

    def __str__(self):
        return f"FailedLoginAudit({self.msisdn}, {self.device_id}, {self.failure_reason})"


class RegistrationSession(BaseModel):
    msisdn = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(blank=True, null=True)
    registration_token = models.CharField(max_length=255, unique=True, db_index=True)
    phone_verified = models.BooleanField(default=True)
    email_verified = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=RegistrationSessionStatus.choices,
        default=RegistrationSessionStatus.EMAIL_PENDING,
    )
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "registration_sessions"
        indexes = [models.Index(fields=["msisdn", "status"])]

    def __str__(self):
        return f"RegistrationSession({self.msisdn}, {self.status})"
