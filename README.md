# Digital Wallet App

Architected as a modular monolith with clear domain boundaries, designed so individual
modules can be independently extracted into microservices as the system scales.

Production and staging environments would be separated via environment variables
and protected deployment workflows.

## Run in One Command

# 1. Clone repository

git clone <repo-url> && cd digital_wallet

# 2. Create .env from template

cp .env.local .env

# (Optional but recommended) Generate your own Django secret key

python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Edit .env — set STRIPE keys, FIREBASE config, email credentials

# 3. Start all services

docker compose up --build

# Migrations run automatically. Country seed data loaded on startup.

# 4. Set up pre-commit hooks (optional but recommended)

pre-commit install
pre-commit install --hook-type commit-msg

# 5. Access API

http://localhost:8000/api/v1/

# 6. Run tests

docker compose exec web pytest app/ -v --cov=app/ --cov-report=term

## Fake Stripe Checkout For Local Testing

The project supports a fake Stripe checkout mode for local testing and automated tests.

- `FAKE_STRIPE_CHECKOUT` defaults to `True` when `STRIPE_SECRET_KEY` is not configured.
- `POST /api/v1/transactions/topup/create-session/` returns a local fake checkout URL instead of a live Stripe URL.
- `GET /api/v1/transactions/topup/fake-checkout/<session_id>/` returns the fake checkout session details.
- `POST /api/v1/transactions/topup/fake-checkout/<session_id>/` accepts an `action` of `complete`, `cancel`, or `expire`.
- Fake webhook payloads can still be sent to `POST /api/v1/transactions/topup/webhook/` with any `Stripe-Signature` header.

## Firebase Configuration

The project uses two different Firebase credential types for different responsibilities.

- `FIREBASE_WEB_API_KEY`
  Required for phone OTP endpoints that call Firebase Auth REST APIs:

  - `POST /api/v1/auth/otp/request/`
  - `POST /api/v1/auth/otp/verify/`
    When using the Firebase Auth emulator locally, this key can be omitted and the backend will use a local emulator-safe placeholder key.

- `FIREBASE_SERVICE_ACCOUNT_JSON`
  Optional for the current OTP-only setup.
  It is only needed when using Firebase Admin SDK features such as server-side token verification,
  custom claims, admin user management, or FCM.

- `FIREBASE_AUTH_EMULATOR_HOST`
  Optional and local-only.
  Set this to your Firebase Auth emulator host, for example `127.0.0.1:9099`.
  When set, phone OTP requests are sent to the emulator instead of the live Firebase Auth service.

Current behavior:

- If `FIREBASE_SERVICE_ACCOUNT_JSON` is not configured, Firebase Admin initialization is skipped.
- The OTP flow still works with only `FIREBASE_WEB_API_KEY`, assuming Firebase Phone Auth is enabled
  and the client provides a valid `recaptcha_token`.
- If `FIREBASE_AUTH_EMULATOR_HOST` is configured, the OTP flow uses the local Auth emulator and does not require `recaptcha_token`.

### Local Docker Testing (Auth Emulator)

`docker compose up --build` now starts the Firebase Auth emulator alongside app services.

- The app containers use `FIREBASE_AUTH_EMULATOR_HOST=firebase-auth-emulator:9099`.
- Phone OTP endpoints use the emulator locally and skip reCAPTCHA requirement.
- Emulator REST endpoint is exposed on host port `9099`.

To inspect generated SMS verification codes during local tests:

- `GET http://localhost:9099/emulator/v1/projects/<your-project-id>/verificationCodes`

## Authentication & Registration Flow

### Multi-Step Registration (New User)

Registration uses a **4-digit passcode** (not a password) and multi-step phone + email verification:

```
Step 1: POST /api/v1/auth/verify-account/
   -> Check if MSISDN is available

Step 2: POST /api/v1/auth/otp/request/
   -> Firebase sends SMS OTP to the phone number

Step 3: POST /api/v1/auth/otp/verify/
   -> Verify the SMS OTP code
   -> Returns {registration_token}

Step 4: POST /api/v1/auth/register/email/request/
   -> Sends email OTP to the provided email address

Step 5: POST /api/v1/auth/register/email/verify/
   -> Verify the email OTP code
   -> Marks email as verified

Step 6: POST /api/v1/auth/register/complete/
   -> Completes registration with 4-digit passcode
   -> Creates User, UserAccount, main Wallet, and UserSession
   -> Returns {access_token, refresh_token}
```

### Login (Existing User)

```
Step 1: POST /api/v1/auth/otp/request/
   -> Firebase sends SMS OTP
   -> Body: {msisdn, purpose: "LOGIN"}

Step 2: POST /api/v1/auth/otp/verify/
   -> Verify SMS OTP code
   -> Returns {login_token}

Step 3: POST /api/v1/auth/login/passcode/
   -> Login with login_token + 4-digit passcode
   -> Returns {access_token, refresh_token, user_data}
```

### Token Refresh

```
POST /api/v1/auth/token/refresh/
   -> Refresh the access token using the refresh token
   -> Validates the refresh token via bcrypt hash in the UserSession
   -> Returns {access_token, refresh_token}
```

## Session Management

### Session State (LOCKED/UNLOCKED)

Each login creates a `UserSession` tied to a specific `device_id`. Sessions can be locked for security:

- **UNLOCKED**: Normal authenticated state. All requests allowed.
- **LOCKED**: Session locked due to idle timeout. User must re-enter passcode.

### Idle Timeout

If a session is idle for longer than `SESSION_IDLE_TIMEOUT_MINUTES` (default: 15 min), any authenticated request will:

1. Detect the idle timeout
2. Auto-lock the session (set state → LOCKED)
3. Return error: `{status: SESSION_LOCKED, session_id: ...}`

### Unlock a Locked Session

```
POST /api/v1/auth/session/unlock/
   -> Body: {session_id, passcode}
   -> Validates the passcode
   -> Sets session state → UNLOCKED
   -> Returns {access_token, refresh_token}
```

### Logout

```
POST /api/v1/auth/logout/
   -> Deactivates the current session
   -> Sets: is_active=False, refresh_token_hash=None, state=LOCKED
   -> Future token refreshes for this session will be rejected
   -> Other device sessions remain unaffected
```

## .env Configuration Guide

All configuration is environment-variable driven. See `.env.local` for defaults.

### Django & Database

```env
DJANGO_SETTINGS_MODULE=app.settings.dev    # or app.settings.prod
SECRET_KEY=<50-char-random-string>
DEBUG=True                                  # False in production
ALLOWED_HOSTS=localhost,127.0.0.1
```

### Redis & Celery

```env
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

### JWT & Session

```env
JWT_SECRET_KEY=<your-jwt-secret>
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=60       # access token valid for 1 hour
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7          # refresh token valid for 7 days
SESSION_IDLE_TIMEOUT_MINUTES=15            # auto-lock session after 15 min inactivity
```

### Firebase Authentication (OTP)

```env
FIREBASE_PROJECT_ID=<your-firebase-project>
FIREBASE_SERVICE_ACCOUNT_JSON=/app/secrets/firebase-sa.json
FIREBASE_AUTH_EMULATOR_HOST=localhost:9099  # optional: local emulator for testing
```

### Stripe Payments

```env
STRIPE_SECRET_KEY=sk_test_xxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxx
STRIPE_CURRENCY=usd
FAKE_STRIPE_CHECKOUT=True                  # use fake checkout in local dev
MAX_TOPUP_AMOUNT_USD=10000
```

### Email

```env
DEFAULT_FROM_EMAIL=no-reply@digitalwallet.local
# In dev: uses console backend (prints emails to console)
# In prod: configure SMTP
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=app-specific-password
```

### Business Rules (Transfer Limits)

```env
TRANSACTION_TIMEOUT_DAYS=30
DAILY_SEND_LIMIT_USD=5000
MONTHLY_SEND_LIMIT_USD=20000
DAILY_RECEIVE_LIMIT_USD=10000
MIN_TRANSFER_AMOUNT_USD=1
```

### OTP Rate Limiting

```env
OTP_MAX_REQUESTS_PER_DEVICE=5              # max OTP requests per device per window
OTP_WINDOW_SECONDS=3600                    # 1 hour window
OTP_LOCK_DURATION_SECONDS=3600             # lock device for 1 hour if exceeded
```

### Maintenance Mode

```env
IS_MAINTENANCE=False
MAINTENANCE_MESSAGE=System is under maintenance. Please try later.
```

### Monitoring (Sentry)

```env
SENTRY_DSN=https://xxxx@sentry.io/project-id  # optional
```

## Pre-Commit Hooks

The project uses **pre-commit** for code quality checks on every commit.

### Setup

```bash
# Install pre-commit globally (if not already installed)
pip install pre-commit

# Install hooks in your local repo
pre-commit install
pre-commit install --hook-type commit-msg  # for commit message linting
```

### What Hooks Run

On every `git commit`, these checks run automatically:

- **trailing-whitespace**: Removes trailing whitespace
- **end-of-file-fixer**: Ensures files end with newline
- **check-json**: Validates JSON syntax
- **check-yaml**: Validates YAML syntax
- **ruff**: Lints and auto-fixes Python code (Django-friendly)
- **pip-audit**: Checks `requirements.txt` for known CVEs
- **gitlint**: Enforces conventional commit message format

### Run Hooks Manually

```bash
# Run all hooks on all files
pre-commit run --all-files

# Run specific hook
pre-commit run ruff --all-files
pre-commit run pip-audit --all-files
```

### Bypass Hooks (Not Recommended)

```bash
git commit --no-verify
```

## Troubleshooting

### Windows + WSL Issues

**Problem:** Pre-commit hooks fail with "bash: No such file or directory"

**Cause:** Windows with broken/missing WSL; pre-commit tries to invoke bash for shell-based hooks.

**Solution:**

- Ensure WSL is properly installed: `wsl --status`
- Most hooks (ruff, pip-audit, gitlint) work without WSL
- Comment out problematic shell-based hooks in `.pre-commit-config.yaml` temporarily

### Django Migrations Issues

**Problem:** "Migration already exists" or migration conflicts

**Solution:**

```bash
# Check migration status
docker compose exec web python manage.py migrate --plan

# Reset database (local dev only)
rm db.sqlite3
docker compose down -v
docker compose up --build
```

### Pytest Failures in Docker

**Problem:** Tests pass locally but fail in Docker

**Solution:**

```bash
# Ensure containers are built fresh
docker compose build --no-cache

# Run tests with verbose output
docker compose exec web pytest app/ -v --tb=short

# Run specific test
docker compose exec web pytest app/users/tests.py::test_login -v
```

### Firebase Emulator Not Connecting

**Problem:** "Failed to connect to Firebase emulator"

**Solution:**

- Check `FIREBASE_AUTH_EMULATOR_HOST` is set to `firebase-auth-emulator:9099` in Docker
- Or set to `localhost:9099` if running emulator locally outside Docker
- Verify emulator is running: `curl http://localhost:9099/emulator/v1/projects`

### Rate Limiting Blocking OTP

**Problem:** "Too many OTP requests" even on first try

**Solution:**

```bash
# Clear Redis cache (local dev only)
docker compose exec redis redis-cli FLUSHDB

# Restart containers
docker compose restart
```

### Port Already in Use

**Problem:** "Port 8000 is already in use"

**Solution:**

```bash
# Find and kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Or use a different port
docker compose -p "myproject" up
```
