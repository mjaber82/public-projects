# Digital Wallet App — Low-Level Design (LLD)

**Stack:** Python 3.13 | Django 6.0.4 | DRF 3.17.1 | SQLite (local) | Celery | Redis | Docker
**Architecture:** Modular Monolith (Microservice-ready)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Project Structure](#2-project-structure)
3. [Data Models](#3-data-models)
4. [Decorator System](#4-decorator-system)
5. [Service Layer](#5-service-layer)
6. [Async Tasks (Celery)](#6-async-tasks-celery)
7. [API Endpoints](#7-api-endpoints)
8. [Critical Test Cases](#8-critical-test-cases)
9. [Security & Financial Integrity](#9-security--financial-integrity)
10. [Data Flow Diagrams](#10-data-flow-diagrams)
11. [Seed Data Migration](#11-seed-data-migration)
12. [CI/CD Pipeline](#12-cicd-pipeline)
13. [Config File Examples](#13-config-file-examples)

---

## 1. Project Overview

### 1.1 Scope

| Key        | Value                                                                 |
| ---------- | --------------------------------------------------------------------- |
| App Name   | Digital Wallet                                                        |
| Database   | SQLite (local dev)                                                    |
| Runtime    | Python 3.13 / Django 6.0.4 / DRF 3.17.1                               |
| Deployment | Docker + Docker Compose (local only)                                  |
| CI         | GitHub Actions (build + test)                                         |
| Auth       | JWT (djangorestframework-simplejwt) + Firebase OTP + 4-digit passcode |
| Payments   | Stripe webhook-confirmed top-ups (fake checkout mode in local dev)    |
| Async      | Celery worker + Redis broker (notifications + maintenance tasks)      |
| Tests      | pytest-django                                                         |

### 1.2 Architecture Philosophy

Modular Monolith — a single deployable unit organized into well-isolated Django apps. Each app (users, wallets, transactions, notifications) owns its own models, services, serializers, and URLs — easily extractable later as microservices.

### 1.3 Key Design Decisions

| Decision            | Choice                                                 | Rationale                                           |
| ------------------- | ------------------------------------------------------ | --------------------------------------------------- |
| Auth                | Firebase OTP + session JWT + passcode                  | Phone-verified identity; passcode replaces password |
| Session management  | UserSession with refresh_token_hash (bcrypt)           | Stateful session allows per-device revocation       |
| Session binding     | sid (session UUID) embedded in JWT                     | Ties every JWT to a specific session row            |
| Session locking     | LOCKED/UNLOCKED state + idle timeout                   | Protects unattended devices; re-auth with passcode  |
| DB Transactions     | @transaction.atomic + select_for_update                | Prevent double-spend, race conditions               |
| Async Jobs          | Celery + Redis broker                                  | Non-blocking notifications, deferred cleanup tasks  |
| Double-entry ledger | LedgerEntry per transaction participant                | Auditable financial trail; PENDING->POSTED/VOIDED   |
| Account indirection | UserAccount between User and Wallet                    | Separates identity from financial account ledger    |
| Rate Limiting       | Redis counters (TTL-based)                             | Sub-millisecond, TTL auto-expiry                    |
| Payments            | Stripe Checkout + Webhooks (FAKE_STRIPE_CHECKOUT flag) | Local dev without real Stripe keys                  |
| ORM Optimization    | select_related, prefetch_related, only()               | Minimize N+1, reduce payload size                   |
| DB Indexing         | Composite + partial indexes                            | Optimized for all filter/sort query patterns        |
| Soft Delete         | is_active / deactivated_at flags                       | Preserve audit trail, no CASCADE data loss          |
| Code Style          | Service layer pattern                                  | Fat service, thin view — testable business logic    |

---

## 2. Project Structure

```
digital-wallet/
├── .env                         # not committed to git
├── .env.local                   # committed to git, used only for local setup (dev)
├── .github/
│   └── workflows/
│       └── ci.yml               # GitHub Actions: build + pytest
├── .gitignore
├── .pre-commit-config.yaml      # pre-commit hook configuration
├── docker-compose.yml           # web + redis + celery services
├── Dockerfile
├── manage.py
├── pyproject.toml               # ruff + project metadata
├── README.md
├── requirements.txt
└── app/                         # Django project root
    ├── __init__.py
    ├── settings/
    │   ├── base.py              # shared settings (installed apps, middleware, JWT, etc.)
    │   ├── dev.py               # DEBUG=True, SQLite, console email backend
    │   └── prod.py              # DEBUG=False, strong security headers, SMTP email
    ├── urls.py                  # root URL dispatcher -> /api/v1/
    ├── wsgi.py
    ├── celery.py                # Celery app init
    │
    ├── core/                    # Cross-cutting utilities
    │   ├── models.py            # BaseModel abstract class
    │   ├── constants.py         # TextChoices enums: TransactionType, TransactionStatus,
    │   │                        #   UserSessionState, LedgerEntryType, LedgerEntryStatus,
    │   │                        #   NotificationStatus, RegistrationSessionStatus
    │   ├── decorators.py        # @api_auth, @api_return, @params_required, @check_maintenance
    │   ├── exceptions.py        # WalletException, InsufficientFundsError
    │   ├── firebase.py          # Firebase Admin SDK init (phone OTP verification)
    │   ├── health.py            # Minimal app/db health check endpoint
    │   ├── middleware.py        # JWTAuthMiddleware -> populates request.user + request.auth_session_id
    │   └── tools.py             # ajax_response, get_ip, generate_account_id, validate_*
    │
    ├── users/                   # Auth, registration, profile, session management
    │   ├── models.py            # User, UserAccount, UserSession, FailedLoginAudit,
    │   │                        # RegistrationSession, Country
    │   ├── serializers.py
    │   ├── services.py          # all business logic (no HTTP objects)
    │   ├── views.py             # thin: validate -> service -> respond
    │   ├── urls.py
    │   ├── tokens.py            # CustomRefreshToken — embeds user_id + sid claim
    │   ├── email_utils.py       # email send helpers (welcome, email change, deactivation)
    │   ├── apps.py
    │   ├── tests.py
    │   ├── email_templates/
    │   │   ├── welcome.html
    │   │   ├── email_change_confirmation.html
    │   │   └── deactivation_confirmation.html
    │   └── migrations/
    │
    ├── wallets/                 # Wallet CRUD + lifecycle management
    │   ├── models.py
    │   ├── serializers.py
    │   ├── services.py
    │   ├── views.py
    │   ├── urls.py
    │   ├── apps.py
    │   ├── tests.py
    │   └── migrations/
    │
    ├── transactions/            # Transfer, top-up, Stripe webhook, export
    │   ├── models.py
    │   ├── serializers.py
    │   ├── services.py
    │   ├── views.py
    │   ├── urls.py
    │   ├── apps.py
    │   ├── tasks.py             # Celery: notify_transfer_initiated/completed/rejected,
    │   │                        #   notify_topup_completed, expire_pending_tx
    │   ├── tests.py
    │   └── migrations/
    │
    └── notifications/           # Notification model + delivery logic
        ├── models.py
        ├── serializers.py
        ├── services.py
        ├── views.py
        ├── urls.py
        ├── apps.py
        ├── tasks.py             # Celery: cleanup_expired_notifications
        ├── tests.py
        └── migrations/
```

---

## 3. Data Models

All domain models inherit from `BaseModel` (abstract). UUID primary keys everywhere.

### 3.1 BaseModel (Abstract) — `core/models.py`

```python
class BaseModel(models.Model):
    public_id  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_dt = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_dt = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
```

### 3.2 Country Model — `users/models.py`

```python
class Country(models.Model):
    name           = models.CharField(max_length=100, unique=True)
    iso_2          = models.CharField(max_length=2, unique=True, db_index=True)  # e.g. "LB"
    iso_phone_code = models.CharField(max_length=10)                             # e.g. "+961"

    class Meta:
        db_table           = "countries"
        ordering           = ["name"]
        verbose_name_plural = "countries"
```

> **Seed note:** Countries are seeded via `users/migrations/0002_seed_initial_data.py` on first `docker compose up`. Immutable — no public API endpoint.

### 3.3 User & UserManager — `users/models.py`

Authentication uses a 4-digit **passcode** stored in Django's hashed `password` field via `user.set_password(passcode)`. `USERNAME_FIELD = "msisdn"`.

`UserManager._create_user()` runs atomically: creates `User` -> `UserAccount` -> main `Wallet` in one transaction.

```python
class UserManager(BaseUserManager):
    def _create_user(self, msisdn, country, email, passcode, **extra_fields):
        with transaction.atomic():
            user = self.model(msisdn=msisdn, country=country, email=email, **extra_fields)
            user.set_password(passcode)   # passcode stored as hashed password
            user.save(using=self._db)
            account = UserAccount.objects.create(user=user)
            Wallet.objects.create(user_account=account, name="Main", is_main=True)
            return user


class User(AbstractBaseUser, BaseModel):
    username        = models.CharField(max_length=50, unique=True, db_index=True, null=True, blank=True)
    email           = models.EmailField(unique=True, db_index=True)            # required
    first_name      = models.CharField(max_length=100, blank=True, default="")
    last_name       = models.CharField(max_length=100, blank=True, default="")
    msisdn          = models.CharField(max_length=20, unique=True, db_index=True)
    dob             = models.DateField(null=True, blank=True)
    country         = models.ForeignKey(Country, on_delete=models.PROTECT, db_index=True)
    is_active       = models.BooleanField(default=True, db_index=True)
    deactivated_at  = models.DateTimeField(null=True, blank=True)
    consent         = models.BooleanField(default=False)
    kyc_verified    = models.BooleanField(default=False)
    kyc_verified_dt = models.DateTimeField(blank=True, null=True)
    email_notifications = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "msisdn"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
```

**Design decisions:**

- No `role`, `token_version`, balance fields, `is_staff`, `is_phone_verified`, `is_profile_completed`, or `email_status` on `User`. These were removed in the current implementation.
- Balance data lives on `UserAccount`, not `User`.
- Session invalidation uses `UserSession.refresh_token_hash` (not `token_version`).
- KYC gate check in `@api_auth` is currently commented out.

### 3.4 UserAccount Model — `users/models.py`

Intermediate layer between identity (`User`) and wallets. Holds denormalized account-level balance aggregates.

```python
class UserAccount(BaseModel):
    account_id  = models.CharField(max_length=11, unique=True, editable=False,
                                   default=generate_unique_account_id, db_index=True)
                  # format: "XXXXXXXX-XX" (8 alphanum + dash + 2 alphanum)
    user        = models.OneToOneField(User, on_delete=models.PROTECT, related_name="account")
    currency    = models.CharField(max_length=3, default="USD")
    balance     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
                  # denormalized: sum of all active wallet balances
    in_transfer = models.DecimalField(max_digits=18, decimal_places=2, default=0)
                  # denormalized: sum of all active wallet in_transfer values

    class Meta:
        db_table = "user_accounts"
```

- `account_id` generated by `generate_account_id()` in `core/tools.py`. Uniqueness checked in a loop (up to 10 attempts).
- `_sync_account_totals(account)` in `transactions/services.py` recalculates both fields by aggregating wallet rows — called after any balance mutation.

### 3.5 UserSession Model — `users/models.py`

Replaces old `UserDevice`. One row per active login session per device. Supports per-device revocation and idle-timeout locking.

```python
class UserSession(BaseModel):
    user               = models.ForeignKey(User, on_delete=models.PROTECT)
    device_id          = models.CharField(max_length=128, db_index=True)
    ip_address         = models.GenericIPAddressField()
    refresh_token_hash = models.CharField(max_length=255, blank=True, null=True)
                         # bcrypt hash of the current refresh token; nulled on logout
    is_active          = models.BooleanField(default=True)
    last_seen_at       = models.DateTimeField(blank=True, null=True)
                         # updated on every authenticated request by @api_auth
    state              = models.CharField(max_length=20,
                                          choices=UserSessionState.choices,
                                          default=UserSessionState.UNLOCKED)
                         # LOCKED | UNLOCKED

    class Meta:
        db_table    = "user_sessions"
        indexes     = [models.Index(fields=["user", "is_active"])]
        constraints = [models.UniqueConstraint(fields=["user", "device_id"],
                                               name="unique_user_session")]
```

**Session lifecycle:**

| Event                     | Effect on UserSession                                    |
| ------------------------- | -------------------------------------------------------- |
| Login                     | Create/reuse row, set refresh_token_hash, state=UNLOCKED |
| Authenticated request     | @api_auth updates last_seen_at; checks idle timeout      |
| Idle timeout exceeded     | state=LOCKED; client must call /auth/session/unlock/     |
| Unlock (correct passcode) | state=UNLOCKED, new token pair issued                    |
| Logout                    | is_active=False, refresh_token_hash=None, state=LOCKED   |
| Token refresh             | refresh_token_hash verified via bcrypt; new hash stored  |

### 3.6 FailedLoginAudit Model — `users/models.py`

Persistent log of failed login attempts for abuse detection.

```python
class FailedLoginAudit(BaseModel):
    msisdn         = models.CharField(max_length=20, db_index=True)
    device_id      = models.CharField(max_length=100)
    ip_address     = models.GenericIPAddressField()
    user_agent     = models.TextField(blank=True, null=True)
    failure_reason = models.CharField(max_length=50)

    class Meta:
        db_table = "failed_login_audit"
        indexes  = [models.Index(fields=["msisdn", "created_dt"])]
```

### 3.7 RegistrationSession Model — `users/models.py`

Tracks multi-step registration state between phone OTP verification and final account creation.

```python
class RegistrationSession(BaseModel):
    msisdn             = models.CharField(max_length=20, db_index=True)
    email              = models.EmailField(blank=True, null=True)
    registration_token = models.CharField(max_length=255, unique=True, db_index=True)
                         # short-lived opaque token issued after phone OTP passes
    phone_verified     = models.BooleanField(default=True)
    email_verified     = models.BooleanField(default=False)
    status             = models.CharField(max_length=20,
                                          choices=RegistrationSessionStatus.choices,
                                          default=RegistrationSessionStatus.EMAIL_PENDING)
                         # EMAIL_PENDING | EMAIL_OTP_SENT | EMAIL_VERIFIED
    expires_at         = models.DateTimeField()

    class Meta:
        db_table = "registration_sessions"
        indexes  = [models.Index(fields=["msisdn", "status"])]
```

### 3.8 Wallet Model — `wallets/models.py`

```python
class Wallet(BaseModel):
    wallet_id    = models.CharField(max_length=11, unique=True, editable=False,
                                    default=generate_unique_wallet_id, db_index=True)
                   # format: "XXXXXXXX-XX" — same generator as account_id
    name         = models.CharField(max_length=100)
    user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT,
                                     related_name="wallets")
    balance      = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    in_transfer  = models.DecimalField(max_digits=18, decimal_places=2, default=0)
                   # funds locked in PENDING inter-user transfers
    is_active    = models.BooleanField(default=True, db_index=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    is_main      = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table    = "wallets"
        indexes     = [
            models.Index(fields=["user_account", "is_active"]),
            models.Index(fields=["user_account", "is_main"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["user_account", "name"],
                                    name="unique_wallet_name_per_account"),
            models.UniqueConstraint(fields=["user_account", "is_main"],
                                    condition=models.Q(is_main=True),
                                    name="unique_main_wallet_per_account"),
        ]
```

**Wallet design decisions:**

- MAIN wallet auto-created atomically with the user by `UserManager._create_user()`.
- FK is `user_account` (-> `UserAccount`), **not** a direct FK to `User`.
- `wallet_id` is a human-readable `XXXXXXXX-XX` string (not an integer).
- Sub-wallets may not be named "Main" (enforced in service layer).
- MAIN wallet cannot be renamed, deactivated, or deleted.
- Deactivating a sub-wallet transfers its remaining balance to the main wallet atomically.

### 3.9 Transaction Model — `transactions/models.py`

```python
class Transaction(BaseModel):
    transaction_id    = models.CharField(max_length=11, unique=True, editable=False,
                                         default=generate_unique_tx_id, db_index=True)
    from_wallet       = models.ForeignKey("wallets.Wallet", on_delete=models.PROTECT,
                                          related_name="sent_transactions",
                                          null=True, blank=True)
    to_wallet         = models.ForeignKey("wallets.Wallet", on_delete=models.PROTECT,
                                          related_name="received_transactions",
                                          null=True, blank=True)
    amount            = models.DecimalField(max_digits=18, decimal_places=2)
    currency          = models.CharField(max_length=10, default="USD")
    transaction_type  = models.CharField(max_length=20, choices=TransactionType.choices)
                        # TRANSFER | TOP_UP
    status            = models.CharField(max_length=20, choices=TransactionStatus.choices,
                                         default=TransactionStatus.PENDING)
                        # PENDING | COMPLETED | REJECTED | EXPIRED | CANCELLED
    stripe_session_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    payment_method_id = models.CharField(max_length=255, null=True, blank=True)
    card_brand        = models.CharField(max_length=20, null=True, blank=True)
    card_last4        = models.CharField(max_length=4, null=True, blank=True)
    reject_reason     = models.TextField(null=True, blank=True)
    completed_dt      = models.DateTimeField(null=True, blank=True)
    rejected_dt       = models.DateTimeField(null=True, blank=True)
    revoked_dt        = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "transactions"
        indexes  = [
            models.Index(fields=["from_wallet", "status"]),
            models.Index(fields=["to_wallet", "status"]),
            models.Index(fields=["status", "created_dt"]),
        ]
```

**Transaction design decisions:**

- No `sender_user`/`receiver_user` FK — user identity derived through wallet -> user_account -> user chain.
- `rejected_dt` set when status becomes REJECTED; `revoked_dt` set when status becomes CANCELLED.
- Transactions are immutable once COMPLETED or REJECTED — enforced at service layer.
- `stripe_session_id` indexed for fast webhook lookup.

### 3.10 LedgerEntry Model — `transactions/models.py`

Double-entry bookkeeping record. Every inter-user transfer creates two entries (DEBIT for sender, CREDIT for receiver).

```python
class LedgerEntry(models.Model):   # does NOT inherit BaseModel
    user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT)
    transaction  = models.ForeignKey("transactions.Transaction", on_delete=models.PROTECT,
                                     related_name="ledgers")
    type         = models.CharField(max_length=10, choices=LedgerEntryType.choices)
                   # DEBIT | CREDIT
    amount       = models.DecimalField(max_digits=18, decimal_places=2)
    status       = models.CharField(max_length=10, choices=LedgerEntryStatus.choices,
                                    default=LedgerEntryStatus.PENDING)
                   # PENDING -> POSTED (on complete) | VOIDED (on reject/cancel)
    created_dt   = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_dt   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ledger_entries"
        indexes  = [
            models.Index(fields=["user_account", "status"]),
            models.Index(fields=["transaction", "status"]),
        ]
```

### 3.11 Notification Model — `notifications/models.py`

```python
class Notification(BaseModel):
    user       = models.ForeignKey("users.User", on_delete=models.CASCADE,
                                   related_name="notifications")
    title      = models.CharField(max_length=200)
    body       = models.TextField()
    status     = models.CharField(max_length=20, choices=NotificationStatus.choices,
                                  default=NotificationStatus.UNREAD)
                 # UNREAD | READ
    read_dt    = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
                 # set to created_dt + expiry period; used by cleanup_expired_notifications
    event_type = models.CharField(max_length=50)
                 # TRANSFER_INITIATED | TRANSFER_RECEIVED | TRANSFER_COMPLETED |
                 # TRANSFER_REJECTED | TRANSFER_EXPIRED | TOP_UP_COMPLETED
    related_tx = models.ForeignKey("transactions.Transaction", on_delete=models.SET_NULL,
                                   null=True, blank=True)

    class Meta:
        db_table = "notifications"
        indexes  = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["expires_at"]),
        ]
```

---

## 4. Decorator System

All view-level cross-cutting concerns are handled via decorators in `core/decorators.py`. Standard stack (outermost executes first):

```python
@csrf_exempt
@params_required(POST_LIST=[...])
@api_auth
@api_return
def my_view(request): ...
```

### 4.1 `@check_maintenance`

Checks `settings.IS_MAINTENANCE`. Returns a maintenance payload if True. Called automatically by `@api_auth` — never applied independently.

### 4.2 `@api_auth`

Primary authentication + session validation gateway. **Execution order:**

1. Calls `@check_maintenance` — returns early if maintenance mode.
2. Checks `request.user` is not `None` / not `AnonymousUser`.
3. Checks `user.is_active`.
4. Checks `request.auth_session_id` is present (set by JWT middleware from `sid` claim).
5. Fetches `UserSession` by `user` + `public_id=auth_session_id` — returns error if not found or `is_active=False`.
6. If `session.state == LOCKED` -> returns session-locked error (includes `session_id` in payload).
7. Checks idle timeout: if `last_seen_at` older than `SESSION_IDLE_TIMEOUT_MINUTES` -> sets `state=LOCKED`, saves, returns locked error.
8. Updates `session.last_seen_at = now()`.

> KYC gate check is **commented out** in the current codebase.

### 4.3 `@params_required(GET_LIST, POST_LIST, FILES_LIST, HTTP_LIST)`

Validates presence of required parameters. Returns `NOT_ENOUGH_INFO` with a map of missing params. Fires **before** `@api_auth` so unauthenticated calls still receive descriptive validation errors.

### 4.4 `@api_return`

Wraps the view in try/except. On `ValidationError`, extracts the first message. On any other exception, calls `sentry_sdk.capture_exception`. Always formats the result via `tools.ajax_response` — returns a `JsonResponse` with the standard `{status, message, payload}` envelope.

### 4.5 `tools.py` — Response Utilities — `core/tools.py`

```python
def create_response(status=None, message=None, payload=None) -> dict:
    return {
        "status":  status  or ResponseStatus.FAIL,
        "message": message or ResponseMessage.UNKNOWN_ERROR,
        "payload": payload,
    }

def ajax_response(data_dict) -> JsonResponse:
    return JsonResponse(data_dict, safe=False)

def get_ip(request) -> str:
    from ipware import get_client_ip
    ip, _ = get_client_ip(request)
    return ip or "0.0.0.0"

def generate_account_id() -> str:
    """Returns a random string in format XXXXXXXX-XX (8 alphanum + dash + 2 alphanum)."""
```

---

## 5. Service Layer

Every Django app contains a `services.py`. Views are thin HTTP adapters — all business logic lives in services.

### 5.1 Service Layer Contract

```
Rule 1: Service functions NEVER receive request objects — only primitive types or model instances.
Rule 2: Service functions return (result, error_message) tuples — never raise HTTP exceptions.
Rule 3: Service functions that write to the DB must use atomic transactions.
Rule 4: Services may call other module services; they NEVER import another module's views.
```

### 5.2 `users/services.py` — Registration Flow

Multi-step flow: **Phone OTP -> registration_token -> Email OTP -> passcode completion**

```
Step 1: verify_account(msisdn)
    -> Checks if account already exists and is active. Returns status hint to client.

Step 2: request_phone_otp(msisdn, purpose, recaptcha_token)
    -> purpose: "REGISTER" | "LOGIN"
    -> Calls Firebase to send SMS OTP to the MSISDN.

Step 3: verify_phone_otp(msisdn, otp_code, purpose)
    -> REGISTER path:
       - Calls Firebase to verify OTP code
       - Creates RegistrationSession(msisdn=msisdn, status=EMAIL_PENDING)
       - Returns {registration_token} to client
    -> LOGIN path:
       - Calls Firebase to verify OTP code
       - Caches a short-lived login_token keyed by msisdn
       - Returns {login_token} to client

Step 4: send_registration_email_otp(registration_token, email)
    -> Validates registration_token -> RegistrationSession lookup
    -> Sends 6-digit OTP to email via send_mail
    -> Stores OTP in cache, sets status=EMAIL_OTP_SENT

Step 5: verify_registration_email_otp(registration_token, otp_code)
    -> Validates token, checks OTP from cache
    -> Sets session.email_verified=True, status=EMAIL_VERIFIED

Step 6: complete_registration(registration_token, passcode, device_id, ip)
    -> Validates token, checks email_verified=True
    -> @db_tx.atomic:
       - UserManager._create_user() -> User + UserAccount + main Wallet
       - UserSession.objects.create(user, device_id, ip, state=UNLOCKED)
       - CustomRefreshToken.for_user_session(user, session) -> embeds user_id + sid
    -> Sends welcome email
    -> Returns {access_token, refresh_token, user_data}
```

### 5.3 `users/services.py` — Login Flow

```
Step 1: verify_account(msisdn)
    -> Returns status of account (exists/active/inactive).

Step 2: request_phone_otp(msisdn, "LOGIN") -> Firebase SMS OTP

Step 3: verify_phone_otp(msisdn, otp_code, "LOGIN")
    -> Returns {login_token} (cached, short-lived)

Step 4: login_with_passcode(login_token, passcode, ip, device_id, user_agent)
    -> Validates login_token from cache
    -> Fetches User by msisdn
    -> Checks passcode via user.check_password(passcode)
    -> On failure: logs FailedLoginAudit; applies Redis rate-limiting (progressive backoff)
    -> On success:
       - Create or reuse UserSession(user, device_id); store new refresh_token_hash (bcrypt)
       - CustomRefreshToken.for_user_session(user, session)
       - Returns {access_token, refresh_token, user_data}
```

### 5.4 `users/services.py` — Session Management

```python
def refresh_access_token(refresh_token: str) -> tuple[dict | None, str | None]:
    """
    1. Decode refresh token -> extract user_id + sid
    2. Fetch UserSession by public_id=sid
    3. bcrypt.checkpw(refresh_token, session.refresh_token_hash) — reject if mismatch or None
    4. Issue new access token + new refresh token
    5. Update session.refresh_token_hash with new bcrypt hash
    6. Return {access_token, refresh_token}
    """

def logout_user(user: User, session_id: str) -> tuple[bool, str | None]:
    """
    Deactivates the specific session only:
    is_active=False, refresh_token_hash=None, state=LOCKED.
    Other sessions (other devices) remain unaffected.
    """

def unlock_session(user: User, session_id: str, passcode: str) -> tuple[dict | None, str | None]:
    """
    Validates passcode for a LOCKED session.
    On success: state=UNLOCKED, issues new token pair.
    """
```

### 5.5 `users/services.py` — Step-Up Token Pattern

Sensitive operations (change passcode, change phone, change email) use a two-stage step-up pattern.

```python
def issue_step_up_token(user: User, current_passcode: str, purpose: str) -> tuple[str | None, str | None]:
    """
    Verifies current passcode -> caches short-lived step_up_token (10 min TTL)
    keyed by (user_id, purpose).
    Returns {step_up_token}.
    """

def change_passcode_with_step_up(user, step_up_token, new_passcode)
def change_msisdn_with_step_up(user, step_up_token, new_msisdn)
def send_change_email_otp(user, step_up_token, new_email)       # step 1 of email change
def verify_change_email_otp(user, step_up_token, otp_code)      # step 2 of email change — applies new email
```

### 5.6 `users/services.py` — Account Recovery Flows

**Forgot Passcode** (user still has phone access):

```
forgot_passcode_start(msisdn, otp_code)
    -> Verifies Firebase phone OTP -> issues step_up_token_1 (purpose=FORGOT_PASSCODE_STEP1)

forgot_passcode_verify_email(msisdn, step_up_token_1, email_otp_code)
    -> Validates step_up_token_1 -> verifies email OTP from cache
    -> Issues step_up_token_2 (purpose=FORGOT_PASSCODE_STEP2)

forgot_passcode_complete(msisdn, step_up_token_2, new_passcode)
    -> Validates step_up_token_2 -> user.set_password(new_passcode) -> save
```

**No-SIM Recovery** (user locked out of phone number):

```
no_sim_recovery_start(user, passcode)
    -> Verifies passcode (re-auth) -> issues step_up_token_1 (purpose=NO_SIM_STEP1)

no_sim_recovery_verify_email(user, step_up_token_1, email_otp_code)
    -> Validates step_up_token_1 -> verifies email OTP
    -> Issues step_up_token_2 (purpose=NO_SIM_STEP2)

no_sim_recovery_complete(user, step_up_token_2, new_msisdn)
    -> Validates step_up_token_2 -> user.msisdn = new_msisdn -> save
```

### 5.7 `wallets/services.py`

```python
def create_wallet(user: User, name: str) -> tuple[Wallet | None, str | None]:
    """
    Validates name is not "Main" and is unique within the user's account.
    Creates Wallet(user_account=user.account, name=name, is_main=False).
    """

def deactivate_wallet(user: User, wallet_id: str) -> tuple[bool, str | None]:
    """
    Blocks if: wallet is MAIN | wallet has in_transfer > 0 |
               wallet has PENDING transactions | wallet already inactive.
    On success: @atomic — transfers remaining balance to main wallet, sets is_active=False.
    """

def get_wallet_list(user: User) -> QuerySet:
    """
    Ensures main wallet exists (creates if missing).
    Returns active wallets ordered by -is_main, name.
    """

def update_wallet_name(user: User, wallet_id: str, name: str) -> tuple[Wallet | None, str | None]:
    """Validates name uniqueness per account. Blocks renaming MAIN wallet."""
```

### 5.8 `transactions/services.py`

```python
def initiate_transfer(
    sender_user: User,
    sender_wallet_id: str,
    amount: Decimal,
    receiver_msisdn: str | None = None,
    receiver_wallet_id: str | None = None,
) -> tuple[Transaction | None, str | None]:
    """
    Intra-user (receiver_wallet_id, same UserAccount):
        @atomic: SELECT FOR UPDATE sender wallet -> check balance ->
        sender_wallet.balance -= amount -> receiver_wallet.balance += amount ->
        Transaction(status=COMPLETED) — no LedgerEntries created.

    Inter-user (receiver_msisdn):
        Validate receiver exists -> check daily/monthly send limits + daily receive limits ->
        @atomic: SELECT FOR UPDATE sender wallet -> check balance >= amount ->
        sender_wallet.balance -= amount -> sender_wallet.in_transfer += amount ->
        Transaction(status=PENDING) ->
        LedgerEntry(DEBIT, PENDING) for sender + LedgerEntry(CREDIT, PENDING) for receiver ->
        notify_transfer_initiated.delay(tx.public_id)
    """

def accept_transfer(receiver_user: User, transaction_id: str) -> tuple[bool, str | None]:
    """
    @atomic: SELECT FOR UPDATE tx -> validate status=PENDING, receiver owns to_wallet ->
    receiver_wallet.balance += amount -> sender_wallet.in_transfer -= amount ->
    tx.status=COMPLETED, completed_dt=now() ->
    ledger entries -> POSTED -> _sync_account_totals for both accounts ->
    notify_transfer_completed.delay(tx.public_id)
    """

def reject_transfer(receiver_user: User, transaction_id: str, reason: str) -> tuple[bool, str | None]:
    """
    @atomic: SELECT FOR UPDATE tx -> validate ->
    sender_wallet.balance += amount, sender_wallet.in_transfer -= amount ->
    tx.status=REJECTED, reject_reason, rejected_dt=now() ->
    ledger entries -> VOIDED -> _sync_account_totals for sender ->
    notify_transfer_rejected.delay(tx.public_id)
    """

def cancel_transfer(sender_user: User, transaction_id: str) -> tuple[bool, str | None]:
    """Same refund flow as reject. Sets status=CANCELLED, revoked_dt=now(). Ledgers -> VOIDED."""

def create_stripe_session(user: User, wallet_id: str, amount: Decimal) -> tuple[str | None, str | None]:
    """
    Only allowed for MAIN wallet top-ups.
    If FAKE_STRIPE_CHECKOUT=True: generates a fake session_id, returns a local fake-checkout URL.
    Creates Transaction(status=PENDING, type=TOP_UP, stripe_session_id=session_id).
    Returns (session_url, None) or (None, error).
    """

def handle_stripe_webhook(payload: bytes, sig_header: str) -> tuple[bool, str | None]:
    """
    If FAKE_STRIPE_CHECKOUT=True: parses JSON payload directly (no signature verification).
    On checkout.session.completed:
        @atomic: SELECT FOR UPDATE tx -> guard if status != PENDING (idempotent) ->
        to_wallet.balance += amount -> tx.status=COMPLETED, completed_dt=now() ->
        _sync_account_totals -> notify_topup_completed.delay(tx.public_id)
    """

def _sync_account_totals(account: UserAccount) -> None:
    """Recalculates account.balance and account.in_transfer by aggregating wallet rows."""

def export_transactions_csv(user: User, filters: dict) -> HttpResponse:
    """Returns CSV response with columns including sender/receiver msisdn."""
```

### 5.9 `notifications/services.py`

```python
def create_notification(user: User, title: str, body: str,
                        event_type: str, related_tx=None) -> Notification:
    """Creates a web notification record. Called from Celery tasks."""

def mark_read(user: User, notification_id: str) -> tuple[bool, str | None]:
    """Marks a single notification READ, sets read_dt=now()."""

def mark_all_read(user: User) -> int:
    """Marks all UNREAD notifications for the user as READ. Returns count updated."""

def clear_notification(user: User, notification_id: str) -> tuple[bool, str | None]:
    """Hard-deletes a single notification owned by the user."""

def clear_all_notifications(user: User) -> int:
    """Hard-deletes all notifications for the user. Returns count deleted."""
```

---

## 6. Async Tasks (Celery)

Notification tasks live in `transactions/tasks.py` and `notifications/tasks.py`. They queue on `"notifications"` except `expire_pending_tx` which uses `"default"`.

| Trigger                       | Celery Task                     | Queue         | Action                                                                                                         |
| ----------------------------- | ------------------------------- | ------------- | -------------------------------------------------------------------------------------------------------------- |
| Transfer initiated (PENDING)  | `notify_transfer_initiated`     | notifications | Web notification to sender (TRANSFER_INITIATED) + receiver (TRANSFER_RECEIVED). Email to receiver if opted-in. |
| Transfer accepted (COMPLETED) | `notify_transfer_completed`     | notifications | Web + email to both sender and receiver.                                                                       |
| Transfer rejected (REJECTED)  | `notify_transfer_rejected`      | notifications | Web + email to sender with reject_reason.                                                                      |
| Stripe webhook confirmed      | `notify_topup_completed`        | notifications | Web + email to user confirming top-up amount.                                                                  |
| Celery beat: daily cron       | `cleanup_expired_notifications` | notifications | Hard-deletes Notification rows where `expires_at < now()`.                                                     |
| Celery beat: daily cron       | `expire_pending_tx`             | default       | Expires PENDING transactions older than `TRANSACTION_TIMEOUT_DAYS`. Notifies sender (TRANSFER_EXPIRED).        |

**Email gating:** `_send_transaction_email_to_user(user, subject, message)` checks `user.email` and `user.email_notifications` before calling `send_mail`. Silently skips if not opted in.

---

## 7. API Endpoints

All endpoints prefixed with `/api/v1/`. Auth is JWT Bearer token unless noted.

**Standard response envelope:**

```json
{ "status": "SUCCESS" | "FAIL", "message": "...", "payload": { ... } }
```

> Always use `public_id` as the object primary key in request bodies.

### 7.1 Authentication & Registration Endpoints

| Method | URL                                    | Auth          | Description                                                                                                 |
| ------ | -------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------- |
| POST   | `/api/v1/auth/verify-account/`         | None          | Check if MSISDN is registered, active, or unknown. Returns status hint.                                     |
| POST   | `/api/v1/auth/otp/request/`            | None          | Request Firebase SMS OTP. Body: msisdn, purpose (REGISTER or LOGIN).                                        |
| POST   | `/api/v1/auth/otp/verify/`             | None          | Verify Firebase OTP. REGISTER -> {registration_token}. LOGIN -> {login_token}.                              |
| POST   | `/api/v1/auth/register/email/request/` | None          | Send email OTP during registration. Requires registration_token + email.                                    |
| POST   | `/api/v1/auth/register/email/verify/`  | None          | Verify email OTP. Marks RegistrationSession.email_verified=True.                                            |
| POST   | `/api/v1/auth/register/complete/`      | None          | Complete registration: passcode + device_id -> User + UserAccount + Wallet + UserSession. Returns JWT pair. |
| POST   | `/api/v1/auth/login/passcode/`         | None          | Login with login_token + 4-digit passcode. Returns JWT pair.                                                |
| POST   | `/api/v1/auth/token/refresh/`          | Refresh token | Refresh access token. Validates via UserSession.refresh_token_hash (bcrypt).                                |
| POST   | `/api/v1/auth/session/unlock/`         | JWT           | Re-enter passcode to unlock LOCKED session. Returns new JWT pair.                                           |
| POST   | `/api/v1/auth/logout/`                 | JWT           | Deactivates current session (is_active=False, refresh_token_hash=None).                                     |

**Registration sequence:**

```
1. POST /auth/verify-account/           -> confirms msisdn not taken
2. POST /auth/otp/request/              -> Firebase sends OTP (purpose=REGISTER)
3. POST /auth/otp/verify/               -> returns {registration_token}
4. POST /auth/register/email/request/   -> sends email OTP
5. POST /auth/register/email/verify/    -> marks email_verified
6. POST /auth/register/complete/        -> creates account, returns JWT pair
```

**Login sequence:**

```
1. POST /auth/verify-account/     -> confirms msisdn exists + active
2. POST /auth/otp/request/        -> Firebase sends OTP (purpose=LOGIN)
3. POST /auth/otp/verify/         -> returns {login_token}
4. POST /auth/login/passcode/     -> passcode check -> {access_token, refresh_token}
```

### 7.2 Forgot Passcode & No-SIM Recovery Endpoints

| Method | URL                                          | Auth | Description                                                      |
| ------ | -------------------------------------------- | ---- | ---------------------------------------------------------------- |
| POST   | `/api/v1/auth/passcode/forgot/start/`        | None | Verify phone OTP -> return step_up_token_1.                      |
| POST   | `/api/v1/auth/passcode/forgot/email-verify/` | None | Verify email OTP with step_up_token_1 -> return step_up_token_2. |
| POST   | `/api/v1/auth/passcode/forgot/complete/`     | None | Reset passcode with step_up_token_2.                             |
| POST   | `/api/v1/auth/recovery/no-sim/start/`        | JWT  | Re-enter current passcode -> return step_up_token_1.             |
| POST   | `/api/v1/auth/recovery/no-sim/email-verify/` | JWT  | Verify email OTP with step_up_token_1 -> return step_up_token_2. |
| POST   | `/api/v1/auth/recovery/no-sim/complete/`     | JWT  | Change MSISDN (phone number) with step_up_token_2.               |

### 7.3 User / Profile Endpoints

| Method | URL                              | Auth | Description                                                                        |
| ------ | -------------------------------- | ---- | ---------------------------------------------------------------------------------- |
| GET    | `/api/v1/users/get_info/`        | Yes  | Returns full user profile (User + UserAccount).                                    |
| POST   | `/api/v1/users/update/`          | Yes  | Update profile fields (first_name, last_name, username, dob, email_notifications). |
| POST   | `/api/v1/users/deactivate/`      | Yes  | Soft-deactivate account. Sets is_active=False, deactivated_at=now().               |
| POST   | `/api/v1/users/step-up/request/` | Yes  | Verify current passcode -> issue step_up_token for sensitive operation.            |
| POST   | `/api/v1/users/passcode/change/` | Yes  | Change passcode using step_up_token.                                               |
| POST   | `/api/v1/users/phone/change/`    | Yes  | Change MSISDN using step_up_token.                                                 |
| POST   | `/api/v1/users/email/change/`    | Yes  | Send/verify email OTP via step_up_token, then update email.                        |

### 7.4 Wallet Endpoints

| Method | URL                            | Auth | Description                                                                            |
| ------ | ------------------------------ | ---- | -------------------------------------------------------------------------------------- |
| GET    | `/api/v1/wallets/`             | Yes  | List all active wallets. MAIN first, then alphabetical.                                |
| POST   | `/api/v1/wallets/get_details/` | Yes  | Get single wallet details.                                                             |
| POST   | `/api/v1/wallets/create/`      | Yes  | Create new sub-wallet (is_main=False). Name must be unique per account.                |
| POST   | `/api/v1/wallets/update/`      | Yes  | Rename sub-wallet. MAIN wallet rename blocked.                                         |
| POST   | `/api/v1/wallets/deactivate/`  | Yes  | Soft-deactivate sub-wallet. Transfers balance to main. Blocked if MAIN or PENDING txs. |

### 7.5 Transaction Endpoints

| Method | URL                                                      | Auth       | Description                                                                                               |
| ------ | -------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------- |
| GET    | `/api/v1/transactions/`                                  | Yes        | Paginated list. Filters: status, type, date range. Sorted: latest first.                                  |
| POST   | `/api/v1/transactions/`                                  | Yes        | Single transaction detail.                                                                                |
| POST   | `/api/v1/transactions/transfer/`                         | Yes        | Initiate transfer. Inter-user (receiver_msisdn) -> PENDING. Intra-user (receiver_wallet_id) -> COMPLETED. |
| POST   | `/api/v1/transactions/accept/`                           | Yes        | Accept PENDING incoming transfer (receiver only).                                                         |
| POST   | `/api/v1/transactions/reject/`                           | Yes        | Reject PENDING incoming transfer with optional reason (receiver only).                                    |
| POST   | `/api/v1/transactions/cancel/`                           | Yes        | Cancel PENDING outgoing transfer (sender only).                                                           |
| POST   | `/api/v1/transactions/topup/create-session/`             | Yes        | Creates Stripe / fake Checkout session for MAIN wallet top-up.                                            |
| GET    | `/api/v1/transactions/topup/fake-checkout/<session_id>/` | None       | Fake checkout page (local dev, FAKE_STRIPE_CHECKOUT=True).                                                |
| POST   | `/api/v1/transactions/topup/webhook/`                    | Stripe sig | Receive Stripe (or fake) payment confirmation events.                                                     |
| GET    | `/api/v1/transactions/export/`                           | Yes        | Export transactions to CSV.                                                                               |

### 7.6 Notification Endpoints

| Method | URL                                | Auth | Description                                 |
| ------ | ---------------------------------- | ---- | ------------------------------------------- |
| GET    | `/api/v1/notifications/`           | Yes  | List all user notifications (UNREAD first). |
| POST   | `/api/v1/notifications/read/`      | Yes  | Mark single notification as READ.           |
| POST   | `/api/v1/notifications/read-all/`  | Yes  | Mark all UNREAD notifications as READ.      |
| POST   | `/api/v1/notifications/clear/`     | Yes  | Hard-delete a single notification.          |
| POST   | `/api/v1/notifications/clear-all/` | Yes  | Hard-delete all notifications for the user. |

---

## 8. Critical Test Cases

| Module       | Test Case                                                                               | Type               |
| ------------ | --------------------------------------------------------------------------------------- | ------------------ |
| users        | verify_account returns correct status for existing/non-existing MSISDN                  | Unit (service)     |
| users        | verify_phone_otp REGISTER path creates RegistrationSession, returns registration_token  | Integration        |
| users        | verify_phone_otp LOGIN path creates cached login_token                                  | Integration        |
| users        | complete_registration creates User + UserAccount + main Wallet + UserSession atomically | Integration        |
| users        | login_with_passcode wrong passcode -> FailedLoginAudit created, rate limit incremented  | Integration        |
| users        | login_with_passcode happy path -> UserSession created, JWT returned                     | Integration        |
| users        | refresh_access_token verifies bcrypt hash against UserSession.refresh_token_hash        | Unit (service)     |
| users        | refresh_access_token after logout (hash=None) -> rejected                               | Unit (service)     |
| users        | logout_user deactivates only the specific session; other device sessions stay active    | Unit (service)     |
| users        | unlock_session correct passcode -> state LOCKED to UNLOCKED, new token pair             | Unit (service)     |
| users        | issue_step_up_token wrong passcode -> rejected                                          | Unit (service)     |
| users        | forgot_passcode complete 3-step flow changes passcode successfully                      | Integration        |
| users        | @api_auth blocks AnonymousUser                                                          | Unit (decorator)   |
| users        | @api_auth blocks inactive UserSession (is_active=False)                                 | Unit (decorator)   |
| users        | @api_auth returns session_locked error for LOCKED session with session_id in payload    | Unit (decorator)   |
| users        | @api_auth auto-locks session and returns locked error when idle timeout exceeded        | Unit (decorator)   |
| wallets      | create_wallet blocks name "Main"                                                        | Unit (service)     |
| wallets      | create_wallet blocks duplicate name in same account                                     | Unit (service)     |
| wallets      | deactivate_wallet blocks MAIN wallet                                                    | Unit (service)     |
| wallets      | deactivate_wallet blocks wallet with in_transfer > 0                                    | Unit (service)     |
| wallets      | deactivate_wallet transfers balance to main wallet atomically                           | Integration        |
| transactions | initiate_transfer inter-user -> PENDING, two LedgerEntries created                      | Integration        |
| transactions | initiate_transfer intra-user -> COMPLETED immediately, no LedgerEntries                 | Integration        |
| transactions | initiate_transfer insufficient balance -> error                                         | Unit (service)     |
| transactions | accept_transfer -> COMPLETED, balances updated, ledgers POSTED                          | Integration        |
| transactions | reject_transfer -> REJECTED, sender refunded, ledgers VOIDED                            | Integration        |
| transactions | cancel_transfer -> CANCELLED, sender refunded, revoked_dt set, ledgers VOIDED           | Integration        |
| transactions | Stripe webhook idempotent: already-COMPLETED tx -> ignored (returns 200)                | Integration (view) |
| jwt          | Expired access token -> middleware sets AnonymousUser -> @api_auth rejects              | Unit (middleware)  |
| jwt          | Access token with non-existent session sid -> @api_auth rejects                         | Unit (decorator)   |

---

## 9. Security & Financial Integrity

### 9.1 Atomic Transactions Map

| Operation                                 | Atomic? | Why                                                                        |
| ----------------------------------------- | ------- | -------------------------------------------------------------------------- |
| User + UserAccount + main Wallet creation | YES     | All three must be consistent — partial creation is invalid.                |
| Registration completion + UserSession     | YES     | Account and first session record must commit together.                     |
| Inter-user transfer initiation            | YES     | Balance deduction + in_transfer + Transaction + LedgerEntries in one unit. |
| Transfer accept / reject / cancel         | YES     | Status change + balance mutation + ledger transition must be inseparable.  |
| Wallet deactivation + balance transfer    | YES     | Balance move to main wallet and deactivation flag must commit together.    |
| Stripe webhook handling                   | YES     | Transaction status + wallet credit must succeed together or roll back.     |
| Mark notification read                    | NO      | Single-row update — atomicity not needed.                                  |

### 9.2 SELECT FOR UPDATE Usage

```python
# transactions/services.py — inside @db_tx.atomic
wallet = Wallet.objects.select_for_update().get(
    wallet_id=sender_wallet_id, user_account__user=sender_user, is_active=True
)
# Concurrent transfers from the same wallet queue behind this lock.
# Lock releases when the outer atomic transaction commits or rolls back.
```

### 9.3 JWT Lifecycle & Session Binding

#### Token Lifetimes

```
Access Token  -> expires in 60 minutes   (JWT_ACCESS_TOKEN_LIFETIME_MINUTES)
Refresh Token -> expires in 7 days       (JWT_REFRESH_TOKEN_LIFETIME_DAYS)
```

#### Custom Token — `users/tokens.py`

```python
class CustomRefreshToken(RefreshToken):
    @classmethod
    def for_user_session(cls, user: User, user_session: UserSession) -> "CustomRefreshToken":
        token = cls()
        token["user_id"] = str(user.public_id)
        token["sid"] = str(user_session.public_id)   # session binding
        return token
```

Every access token carries `user_id` and `sid`. The middleware reads `sid` from the access token to populate `request.auth_session_id`.

#### JWT Middleware Logic — `core/middleware.py`

```python
class JWTAuthMiddleware:
    def process_request(self, request):
        token = extract_bearer_token(request)
        if not token:
            request.user = AnonymousUser()
            return
        try:
            payload = AccessToken(token)                     # validates signature + expiry
            user = User.objects.get(public_id=payload["user_id"])
            request.user = user
            request.auth_session_id = payload.get("sid")    # passed to @api_auth
        except (InvalidToken, TokenExpired, User.DoesNotExist):
            request.user = AnonymousUser()
```

#### Full Token Lifecycle

```
1. LOGIN
   POST /api/v1/auth/login/passcode/
   -> UserSession created/reused; refresh_token_hash = bcrypt(refresh_token)
   -> Returns {access_token, refresh_token}

2. AUTHENTICATED REQUEST
   Request + Authorization: Bearer <access_token>
   -> Middleware: validates signature + expiry, extracts user_id + sid
   -> @api_auth: fetches UserSession by sid, checks is_active + state + idle timeout
   -> Passes: updates session.last_seen_at

3. TOKEN REFRESH
   POST /api/v1/auth/token/refresh/
   -> Decode refresh token -> extract sid -> fetch UserSession
   -> bcrypt.checkpw(refresh_token, session.refresh_token_hash)  <- per-session revocation
   -> Issue new access token + new refresh token
   -> Update session.refresh_token_hash with new bcrypt hash
   -> Returns {access_token, refresh_token}

4. SESSION LOCKED (idle timeout exceeded)
   -> @api_auth detects elapsed > SESSION_IDLE_TIMEOUT_MINUTES
   -> session.state = LOCKED; returns {SESSION_LOCKED, session_id}

5. SESSION UNLOCK
   POST /api/v1/auth/session/unlock/
   -> Validate session_id + passcode
   -> session.state = UNLOCKED; issue new token pair

6. LOGOUT
   POST /api/v1/auth/logout/
   -> session.is_active=False, session.refresh_token_hash=None, state=LOCKED
   -> All future token refreshes for this session rejected (hash is null)
   -> Other device sessions unaffected
```

#### Key Design Decisions

| Decision                        | Reason                                                       |
| ------------------------------- | ------------------------------------------------------------ |
| sid claim in JWT                | Ties the token to a specific UserSession row                 |
| refresh_token_hash (bcrypt)     | Per-session revocation without a blacklist table             |
| Session state (LOCKED/UNLOCKED) | Protects unattended devices; re-auth without full re-login   |
| Idle timeout -> auto-lock       | Reduces risk if device left unlocked                         |
| Short access token (60 min)     | Limits exposure window if token stolen                       |
| Long refresh token (7 days)     | Good UX — stays logged in without re-entering passcode daily |

### 9.4 Rate Limiting & Abuse Protection

**Redis counters (no DB writes during hot path):**

OTP requests — rate-limited per `msisdn + device_id`:

- Track number of OTP requests per window per device.
- Exceeding threshold blocks device temporarily (TTL auto-reset).

Failed passcode login — progressive backoff (key = `msisdn + device_id`):

```python
# settings/base.py
PENALTY_RULES = {
    0: 15 * 60,       # 15 minutes
    1: 30 * 60,       # 30 minutes
    2: 60 * 60,       # 60 minutes
    3: 24 * 60 * 60,  # 24 hours
}
MAX_PENALTY_LEVEL = 4
```

| Level | Condition           | Action         |
| ----- | ------------------- | -------------- |
| L0    | < 5 fails / 10 min  | Allow          |
| L1    | 5 fails / 10 min    | Block 15 min   |
| L2    | Repeat after unlock | Block 30 min   |
| L3    | Repeat again        | Block 60 min   |
| L4    | Repeat again        | Block 24 hours |

**Audit logs:** All failed logins persisted to `FailedLoginAudit` with msisdn, device_id, IP, user_agent, failure_reason.

**Transfer limits** (env-var thresholds):

| Limit         | Env Var                   | Default   |
| ------------- | ------------------------- | --------- |
| Daily send    | `DAILY_SEND_LIMIT_USD`    | 5000 USD  |
| Monthly send  | `MONTHLY_SEND_LIMIT_USD`  | 20000 USD |
| Daily receive | `DAILY_RECEIVE_LIMIT_USD` | 10000 USD |
| Min transfer  | `MIN_TRANSFER_AMOUNT_USD` | 1 USD     |
| Max top-up    | `MAX_TOPUP_AMOUNT_USD`    | 10000 USD |

---

## 10. Data Flow Diagrams

### 10.1 Inter-User Transfer Flow

```
POST /api/v1/transactions/transfer/
|
|-- @csrf_exempt
|-- @params_required(POST_LIST=['sender_wallet_id', 'receiver_msisdn', 'amount'])
|-- @api_auth -> maintenance -> user.is_active -> session_id -> active/unlocked -> idle check
|-- @api_return -> wraps in try/except
|
+-- transactions.services.initiate_transfer()
    |
    |-- Validate receiver exists (User.objects.get(msisdn=receiver_msisdn))
    |-- Validate sender owns wallet (wallet.user_account.user == sender_user)
    |-- Check daily/monthly send limits + daily receive limit via Redis aggregates
    |-- @db_tx.atomic:
    |   |-- SELECT FOR UPDATE on sender wallet
    |   |-- Check wallet.balance >= amount
    |   |-- sender_wallet.balance -= amount
    |   |-- sender_wallet.in_transfer += amount
    |   |-- Transaction.objects.create(from_wallet, to_wallet, amount, status=PENDING)
    |   |-- LedgerEntry(sender_account, DEBIT, PENDING)
    |   +-- LedgerEntry(receiver_account, CREDIT, PENDING)
    |
    +-- notify_transfer_initiated.delay(tx.public_id)  <- Celery (notifications queue)

Celery worker (async):
|-- create_notification(sender, "Transfer initiated", ..., TRANSFER_INITIATED, tx)
|-- create_notification(receiver, "Transfer received", ..., TRANSFER_RECEIVED, tx)
+-- send email to receiver if email_notifications=True
```

### 10.2 Transfer Accept Flow

```
POST /api/v1/transactions/accept/
+-- transactions.services.accept_transfer()
    +-- @db_tx.atomic:
        |-- SELECT FOR UPDATE on transaction
        |-- Validate status=PENDING, receiver_user owns to_wallet
        |-- sender_wallet.in_transfer -= amount
        |-- receiver_wallet.balance += amount
        |-- tx.status=COMPLETED, completed_dt=now()
        |-- LedgerEntry(DEBIT) -> POSTED
        |-- LedgerEntry(CREDIT) -> POSTED
        +-- _sync_account_totals(sender_account) + _sync_account_totals(receiver_account)
    +-- notify_transfer_completed.delay(tx.public_id)
```

### 10.3 Stripe Top-Up Flow

```
POST /api/v1/transactions/topup/create-session/
-> Validate wallet is MAIN
-> FAKE_STRIPE_CHECKOUT=True: generate fake session_id, local URL /fake-checkout/<id>/
-> Transaction(status=PENDING, type=TOP_UP, stripe_session_id=session_id)
-> Return {session_url}

Client opens session_url (fake checkout page in local dev)

POST /api/v1/transactions/topup/webhook/
-> FAKE_STRIPE_CHECKOUT=True: parse JSON body directly
-> On checkout.session.completed:
   @db_tx.atomic:
   |-- SELECT FOR UPDATE tx by stripe_session_id
   |-- Guard: if status != PENDING -> return 200 (idempotent)
   |-- to_wallet.balance += amount
   |-- tx.status=COMPLETED, completed_dt=now()
   +-- _sync_account_totals(account)
-> notify_topup_completed.delay(tx.public_id)
```

### 10.4 Session Lock / Unlock Flow

```
Every @api_auth request:
|-- Fetch UserSession by sid (from JWT auth_session_id)
|-- If session.state == LOCKED:
|   +-- Return {SESSION_LOCKED, session_id}
|-- If now() - last_seen_at > SESSION_IDLE_TIMEOUT_MINUTES:
|   |-- session.state = LOCKED
|   +-- Return {SESSION_LOCKED, session_id}
+-- session.last_seen_at = now() -> request proceeds

Client calls POST /api/v1/auth/session/unlock/
|-- Provide: session_id + passcode
|-- user.check_password(passcode) -> must pass
|-- session.state = UNLOCKED; session.save()
+-- Issue new {access_token, refresh_token}
```

---

## 11. Seed Data Migration

Countries are seeded via `users/migrations/0002_seed_initial_data.py`.

```python
COUNTRIES = [
    {"name": "Lebanon", "iso_2": "LB", "iso_phone_code": "+961"},
    {"name": "United States", "iso_2": "US", "iso_phone_code": "+1"},
    # ... more countries
]

def seed_countries(apps, schema_editor):
    Country = apps.get_model("users", "Country")
    for c in COUNTRIES:
        Country.objects.get_or_create(iso_2=c["iso_2"], defaults=c)
```

> There are **no** Role, Permission, or RolePermission models in the codebase. No such seed data.

---

## 12. CI/CD Pipeline

```
Push Code
  |
  v
GitHub Actions
  |-- python manage.py check                    OK
  |-- python manage.py makemigrations --check   OK
  |-- pytest                                    OK
  +-- docker build                              OK
  |
  v
Deploy Environment (local only)
```

**Pre-commit hooks** (`.pre-commit-config.yaml`):

| Hook                 | Description                                 |
| -------------------- | ------------------------------------------- |
| trailing-whitespace  | Remove trailing whitespace                  |
| end-of-file-fixer    | Ensure files end with newline               |
| check-json           | Validate JSON syntax                        |
| check-yaml           | Validate YAML syntax                        |
| check-merge-conflict | Block merge conflict markers                |
| debug-statements     | Block debug/pdb imports                     |
| ruff                 | Lint and auto-fix Python code (ruff 0.12.0) |
| pip-audit            | Audit requirements.txt for known CVEs       |
| gitlint              | Enforce conventional commit message format  |

---

## 13. Config File Examples

### 13.1 `.env.local`

```env
# -- Django
DJANGO_SETTINGS_MODULE=app.settings.dev
SECRET_KEY=change-me-in-production-use-50-char-random-string
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# -- Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# -- JWT
JWT_SECRET_KEY=change-me-jwt-secret
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=60
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7
SESSION_IDLE_TIMEOUT_MINUTES=15

# -- Firebase (OTP)
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_SERVICE_ACCOUNT_JSON=/app/secrets/firebase-sa.json
# FIREBASE_AUTH_EMULATOR_HOST=localhost:9099   # enable for local emulator

# -- Stripe
STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxx
STRIPE_CURRENCY=usd
FAKE_STRIPE_CHECKOUT=True

# -- Email
DEFAULT_FROM_EMAIL=no-reply@digitalwallet.local

# -- App Business Rules
TRANSACTION_TIMEOUT_DAYS=30
DAILY_SEND_LIMIT_USD=5000
MONTHLY_SEND_LIMIT_USD=20000
DAILY_RECEIVE_LIMIT_USD=10000
MIN_TRANSFER_AMOUNT_USD=1
MAX_TOPUP_AMOUNT_USD=10000

# -- Sentry
SENTRY_DSN=https://xxxx@sentry.io/project-id

# -- Maintenance
IS_MAINTENANCE=False
MAINTENANCE_MESSAGE=System is under maintenance. Please try later.

# -- OTP Rate Limiting
OTP_MAX_REQUESTS_PER_DEVICE=5
OTP_WINDOW_SECONDS=3600
OTP_LOCK_DURATION_SECONDS=3600
```

### 13.2 `app/settings/base.py` (key sections)

```python
AUTH_USER_MODEL = "users.User"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_celery_beat",
    "app.core",
    "app.users",
    "app.wallets",
    "app.transactions",
    "app.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "app.core.middleware.JWTAuthMiddleware",   # populates request.user + request.auth_session_id
    "django.contrib.messages.middleware.MessageListMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":  timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", 60))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_TOKEN_LIFETIME_DAYS", 7))),
    "ROTATE_REFRESH_TOKENS":  False,
    "AUTH_HEADER_TYPES":      ("Bearer",),
}

SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", 15))

CACHES = {
    "default": {
        "BACKEND":  "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://redis:6379/0"),
    }
}

CELERY_BROKER_URL     = os.getenv("CELERY_BROKER_URL",     "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
CELERY_ACCEPT_CONTENT  = ["json"]
CELERY_TASK_SERIALIZER = "json"

TRANSACTION_TIMEOUT_DAYS = int(os.getenv("TRANSACTION_TIMEOUT_DAYS", 30))
DAILY_SEND_LIMIT_USD     = int(os.getenv("DAILY_SEND_LIMIT_USD",      5000))
MONTHLY_SEND_LIMIT_USD   = int(os.getenv("MONTHLY_SEND_LIMIT_USD",    20000))
DAILY_RECEIVE_LIMIT_USD  = int(os.getenv("DAILY_RECEIVE_LIMIT_USD",   10000))
MIN_TRANSFER_AMOUNT_USD  = int(os.getenv("MIN_TRANSFER_AMOUNT_USD",   1))
MAX_TOPUP_AMOUNT_USD     = int(os.getenv("MAX_TOPUP_AMOUNT_USD",      10000))

PENALTY_RULES = {0: 15*60, 1: 30*60, 2: 60*60, 3: 24*60*60}
MAX_PENALTY_LEVEL = 4

IS_MAINTENANCE        = os.getenv("IS_MAINTENANCE", "False") == "True"
MAINTENANCE_MESSAGE   = os.getenv("MAINTENANCE_MESSAGE", "System is under maintenance.")
FAKE_STRIPE_CHECKOUT  = os.getenv("FAKE_STRIPE_CHECKOUT", "False") == "True"
```

### 13.3 `app/settings/dev.py`

```python
from .base import *

DEBUG = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
CORS_ALLOW_ALL_ORIGINS = True
SENTRY_DSN = None
```

### 13.4 `app/settings/prod.py`

```python
from .base import *

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE":   os.getenv("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME":     os.getenv("DB_NAME"),
        "USER":     os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST":     os.getenv("DB_HOST"),
        "PORT":     os.getenv("DB_PORT", "5432"),
    }
}

EMAIL_BACKEND       = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST          = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT          = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USE_TLS       = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER     = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL  = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@mywalletapp.com")

SECURE_BROWSER_XSS_FILTER   = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS              = "DENY"
SECURE_SSL_REDIRECT          = True
SESSION_COOKIE_SECURE        = True
CSRF_COOKIE_SECURE           = True
CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
```
