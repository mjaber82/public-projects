from django.db import models
from django.utils.translation import gettext_lazy as _


class ResponseStatus:
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"


class ResponseMessage:
    SUCCESS = "Success"
    DB_ERROR = "Database error"
    SERVER_ERROR = "Server error"
    UNKNOWN_ERROR = "Unknown error"
    INVALID_CREDENTIALS = "Invalid credentials"
    NOT_AUTHENTICATED = "Authentication required"
    USER_INACTIVE = "User account is inactive"
    KYC_REQUIRED = "KYC verification is required"
    PROFILE_COMPLETION_REQUIRED = "Complete your profile to access this feature"
    MAINTENANCE_MODE = "System is under maintenance"
    NOT_ENOUGH_INFO = "Missing required parameters"


class TransactionType(models.TextChoices):
    TRANSFER = "TRANSFER", _("Transfer")
    TOP_UP = "TOP_UP", _("Top-Up")


class TransactionStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    COMPLETED = "COMPLETED", _("Completed")
    REJECTED = "REJECTED", _("Rejected")
    EXPIRED = "EXPIRED", _("Expired")
    CANCELLED = "CANCELLED", _("Cancelled")


class UserSessionState(models.TextChoices):
    LOCKED = "LOCKED", _("Locked")
    UNLOCKED = "UNLOCKED", _("Unlocked")


class LedgerEntryType(models.TextChoices):
    DEBIT = "DEBIT", _("Debit")
    CREDIT = "CREDIT", _("Credit")


class LedgerEntryStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    POSTED = "POSTED", _("Posted")
    VOIDED = "VOIDED", _("Voided")


class NotificationStatus(models.TextChoices):
    UNREAD = "UNREAD", _("Unread")
    READ = "READ", _("Read")


class RegistrationSessionStatus(models.TextChoices):
    EMAIL_PENDING = "EMAIL_PENDING", _("Email Pending")
    EMAIL_OTP_SENT = "EMAIL_OTP_SENT", _("Email OTP Sent")
    EMAIL_VERIFIED = "EMAIL_VERIFIED", _("Email Verified")
