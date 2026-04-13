REFACTOR

Refactor exsisting to match below new requirements and changes.
Do not change notifications logic.

Affected are some models, logic, security enhancement.

//Modeling SAMPLES (just samples, may require changes as per described logic in this document)

\-core app models sample:

class BaseModel(models.Model):

&#x20; public_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

&#x20; created_dt = models.DateTimeField(auto_now_add=True, db_index=True)

&#x20; updated_dt = models.DateTimeField(auto_now=True)

\-users app models sample:

class UserManager(BaseUserManager): # initialize UserAccount and Main Wallet at user creation.

&#x20; def \_create_user(self, msisdn, country):

&#x20; with transaction.atomic():

&#x20; # 1. Create user

&#x20; user = self.model(

&#x20; msisdn=msisdn,

&#x20; country=country,

&#x20; )

&#x20; user.set_unusable_password()

&#x20; user.save(using=self.\_db)

&#x20; # 2. Create account

&#x20; account = UserAccount.objects.create(user=user)

&#x20; # 3. Create MAIN wallet

&#x20; Wallet.objects.create(

&#x20; user_account=account,

&#x20; is_main=True,

&#x20; )

&#x20; return user

&#x20; def create_user(self, msisdn, country):

&#x20; return self.\_create_user(msisdn=msisdn, country=country)

class User(AbstractBaseUser, BaseModel):

&#x20; username = models.CharField(max_length=50, unique=True, db_index=True, null=True, blank=True)

&#x20; email = models.EmailField(unique=True, null=True, blank=True, db_index=True)

&#x20; first_name = models.CharField(max_length=100, blank=True, default="")

&#x20; last_name = models.CharField(max_length=100, blank=True, default="")

&#x20; msisdn = models.CharField(max_length=20, unique=True, db_index=True)

&#x20; dob = models.DateField(null=True, blank=True)

&#x20; country = models.ForeignKey(Country, on_delete=models.PROTECT, db_index=True)

&#x20; is_active = models.BooleanField(default=True, db_index=True)

&#x20; deactivated_at = models.DateTimeField(null=True, blank=True)

&#x20; consent = models.BooleanField(default=False)

&#x20; kyc_verified = models.BooleanField(default=False) # for testing will set this to True as I won't setup the KYC flow/logic in this project. I just add it to show the interviewer that I am aware about KYC importance.

&#x20; kyc_verified_dt = models.DateTimeField(blank=True, null=True)

&#x20; email_status = models.CharField(

&#x20; max_length=20,

&#x20; choices=EmailStatus.choices,

&#x20; default=EmailStatus.UNVERIFIED,

&#x20; )

&#x20; objects = UserManager()

&#x20; USERNAME_FIELD = "msisdn"

&#x20; REQUIRED_FIELDS = \["msisdn"]

class RegistrationSession(BaseModel):

&#x20; msisdn = models.CharField(max_length=20)

&#x20; email = models.EmailField(null=True, blank=True)

&#x20; phone_verified = models.BooleanField(default=True)

&#x20; email_verified = models.BooleanField(default=False)

&#x20; status = models.CharField(max_length=20, default="EMAIL_PENDING") # once email verified will be "EMAIL_VERIFIED"

&#x20; expires_at = models.DateTimeField()

class UserSession(BaseModel):

&#x20; user = models.ForeignKey(User, on_delete=models.PROTECT)

&#x20; device_id = models.CharField(max_length=128, db_index=True)

&#x20; ip_address = models.GenericIPAddressField()

&#x20; refresh_token_hash = # jwt refresh token

&#x20; is_active = models.BooleanField(default=True)

&#x20; last_seen_at = models.DateTimeField(blank=True, null=True)

&#x20; state = models.CharField(choices=\["LOCKED", "UNLOCKED"]) # default UNLOCKED

class UserAccount(BaseModel): # only 1 account per user is allowed.

&#x20; account_id = models.CharField(

&#x20; max_length=11,

&#x20; unique=True,

&#x20; editable=False,

&#x20; default=generate_unique_account_id,

&#x20; db_index=True,

&#x20; ) # this should be fixed, never deleted , never edited, perminant.

&#x20; user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="account", db_index=True)

&#x20; currency = models.CharField(max_length=3, default="USD")

&#x20; balance = models.DecimalField(max_digits=18, decimal_places=2, default=0) # sum of all related wallets balances

&#x20; in_transfer = models.DecimalField(max_digits=18, decimal_places=2, default=0) # sum of all related wallets in_transfer

class FailedLoginAudit(BaseModel):

&#x20; msisdn = models.CharField(max_length=20) # use msisdn not User

&#x20; device_id = models.CharField(max_length=100)

&#x20; ip_address = models.GenericIPAddressField()

&#x20; user_agent = models.TextField(blank=True, null=True)

&#x20; failure_reason = models.CharField(max_length=50)

\-wallets app models sample:

class Wallet(BaseModel):

&#x20; wallet_id = models.CharField(

&#x20; max_length=11,

&#x20; unique=True,

&#x20; editable=False,

&#x20; default=generate_unique_wallet_id,

&#x20; db_index=True,

&#x20; ) # this should be fixed, never deleted , never edited, permanent.

&#x20; name = models.CharField(max_length=100) # example ("main, savings, travel, etc..), should be unique name per user_account.

&#x20; user_account = models.ForeignKey("users.UserAccount", on_delete=models.PROTECT, related_name="wallets")

&#x20; balance = models.DecimalField(max_digits=18, decimal_places=2, default=0) # wallet transferable balance

&#x20; in_transfer = models.DecimalField(max_digits=18, decimal places=2, default=0) # wallet booked balance

&#x20; is_active = models.BooleanField(default=True, db_index=True)

&#x20; deactivated_at = models.DateTimeField(null=True, blank=True)

&#x20; is_main = models.BooleanField(default=False, db_index=True) # main wallet will have is_main = True

\-transactions app models sample:

class Transaction(BaseModel):

&#x20; transaction_id = models.CharField(

&#x20; max_length=11,

&#x20; unique=True,

&#x20; editable=False,

&#x20; default=generate_unique_tx_id,

&#x20; db_index=True,

&#x20; ) # can never be deleted or edited.

&#x20; from_wallet = models.ForeignKey(

&#x20; "wallets.Wallet",

&#x20; on_delete=models.PROTECT,

&#x20; related_name="sent_transactions",

&#x20; null=True,

&#x20; blank=True,

&#x20; ) # can never be deleted or edited , updated only when a transfer is created

&#x20; to_wallet = models.ForeignKey(

&#x20; "wallets.Wallet",

&#x20; on_delete=models.PROTECT,

&#x20; related_name="received_transactions",

&#x20; null=True,

&#x20; blank=True,

&#x20; ) # can never be deleted or edited , updated only when a transfer is created (could be another user's wallet or another wallet for same user)

&#x20; amount = models.DecimalField(max_digits=18, decimal_places=2)

&#x20; currency = models.CharField(max_length=10, default="USD")

&#x20; transaction_type = models.CharField(max_length=20, choices=TransactionType.choices) # TOP_UP | TRANSFER

&#x20; status = models.CharField(

&#x20; max_length=20,

&#x20; choices=TransactionStatus.choices,

&#x20; default=TransactionStatus.PENDING,

&#x20; )

&#x20; stripe_session_id = models.CharField(max_length=255, null=True, blank=True, db_index=True) # received by stripe

&#x20; payment_method_id = models.CharField(max_length=255, null=True, blank=True) # received by stripe

&#x20; card_brand = models.CharField(max_length=20, null=True, blank=True) # received by stripe

&#x20; card_last4 = models.CharField(max_length=4, null=True, blank=True) # received by stripe

&#x20; reject_reason = models.TextField(null=True, blank=True) # reason for failed stripe payment | reason for Receiver Rejecting transaction (optional).

&#x20; completed_dt = models.DateTimeField(null=True, blank=True) # date-time when status changed to COMPELTED

&#x20; rejected_dt = models.DateTimeField(null=True, blank=True) # date-time when status changed to REJECTED

&#x20; revoked_dt = models.DateTimeField(null=True, blank=True) # date-time when status changed to EXPIRED | REVOKED

&#x20;

class LedgerEntry(models.Model):

&#x20; user_account = models.ForeignKey(UserAccount, on_delete=models.PROTECT)

&#x20; transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT)

&#x20; type = models.CharField(choices=\["DEBIT", "CREDIT"])

&#x20; amount = models.DecimalField(max_digits=18, decimal_places=2) # for debit type will be negative

&#x20; status = models.CharField(choices=\["PENDING", "POSTED", "VOIDED"]) # default is PENDING

//ACCOUNT

\- No more register /login by username and password. New flows are described below in this document.

\- Password regulations changes from a normal password to a passcode (4 digits passcode)

\- Passcode must be hashed for sure

- All fields are optional for User model except msisdn, email and passcode are mandatory to complete registration.

\- No more blacklist option needed

\- No more email status needed

- No more is_profile_completed, is_phone_verified needed
- New API to deactivate account -> user.is_active = False, deactivate_at=now. Deativated accounts can not accept anymore transfers. Deactivated user can not login, will get message about his account being deactivated and will have option to reactivate his account.
- New API to reactivate account -> same LOGIN FLOW described below -> user.is_active=True.

//SECURITY AND RATE LIMIT:

&#x20;- Use same security validations (like validating ownership for example) and same rate limits for OTP or Passcode attempts but use phone number instead of username now.

&#x20;- Setup security enhancements described later in this document in section "SECURITY ENHANCEMENTS"

//WALLETS

\-Main Wallet:

&#x20;- can not be edited (user can not change name), default name = "Main"

&#x20;- Can not be deactivated.

&#x20;- When user top up his account, received amount will be added to Main Wallet balance only once transaction is COMPLETED.

&#x20;- When user receives amount from another user's wallet then also received amount will be added to Main Wallet balance only once transaction is COMPLETED.

\-Other Wallet/s (not main):

&#x20;- Can be deactivated only if no related PENDING transaction exists (no in_transfer balance). Once deactivated can not receive anymore transfers. Remaining balance in this case will be added to Main Wallet balance.

&#x20;- Can be edited (user can change name).

//TOP_UP OPTIONS

&#x20; - Stripe payment.

//TRANSAFER OPTIONS

&#x20; - from wallet A to wallet B for same UserAccount (internal account wallet balance transfer between any wallets)

&#x20; - from User A wallet (any of his wallets) -> User B Main Wallet (user A enter amount to be transferred and User B phone number to initiate transfer).

&#x20; - Can not transfer to deactivated account. When user A enter User's B phone number during a transfer -> system validates User B account if exists and active.

//TRANSACTIONS

&#x20; - Status choices: PENDING | COMPLETED | REJECTED | EXPIRED | CANCELLED. PENDING by default.

&#x20; - UserAccount ID never exposed in transaction details, only Main wallet ID:

&#x20; USER A will see transaction record= "tx-id", "from wallet_id(senders main wallet)", "to wallet_id(receivers main wallet)", "receiver phone number", "amount", direction(IN/OUT), "created_dt", "updated_dt", "status"

&#x20; USER B will see transaction record= "tx-id", "from wallet_id(senders main wallet)", "to wallet_id(receivers main wallet)", "senders phone number", "amount", direction(IN/OUT), "created_dt", "updated_dt", "status"

&#x20; - For inner account transfers (transfer between same account wallets) the transaction is directly created as COMPLETED.

&#x20; - To return value for direction user this logic:

&#x20; if wallet_id == from_wallet_id:

&#x20; direction = "DEBIT"

&#x20; elif wallet_id == to_wallet_id:

&#x20; direction = "CREDIT"

//LEDGERS

&#x20; - Once a transaction is created -> should create ledgers

&#x20; - In case of top_up -> create single ledger (type=credit) with positive amount

&#x20; - In case of transfer -> create 2 ledgers:

&#x20; - first one holding transaction_id, sender useraccount id and type=debit and negative amount.

&#x20; - second one holding transaction_id, receiver useraccount id and type=credit and positive amount.

- Default status = PENDING
- When transaction COMPLETED -> status -> POSTED
- When transaction -> status -> VOIDED
- Ledgers are only for admins/accounting not for customers(users).

//SESSIONS

\- Now with UserSession no need for token version anymore.

&#x20;-stateful session control

&#x20;-per-device tracking

&#x20;-token revocation

\- When to create a NEW UserSession

&#x20;Only when:

&#x20;- Case 1: user logs in after logout

&#x20;- Case 2: session expired / revoked

&#x20;- Case 3: device re-authentication required

\- When NOT to create UserSession

&#x20; Do NOT create new session when:

&#x20; - app reopens

&#x20; - refresh token used

&#x20; - access token renewed

&#x20; - user already has active session on same device

//REGISTRATION FLOW

Steps:

1\. send OTP to phone (Firebase)

2\. verify OTP

&#x20;→ issue REGISTRATION_TOKEN

3. create REGISTRATION_SESSION

&#x20; → phone_verified = True

4. user enters email

5. send OTP to email

6. verify OTP + REGISTRATION_TOKEN

&#x20; → update REGISTRATION_SESSION email_verified = True

7. user enter and submit passcode + REGISTRATION_TOKEN

8. create User + UserAccount + Wallet (Main)

9. create UserSession + last_seen_dt = now

10\. issue JWT (access and refresh tokens and send to client)

//LOGIN FLOW

Steps:

1. send OTP to phone (Firebase)

2. verify OTP

&#x20; → issue LOGIN_TOKEN

3. user enters passcode

4. verify passcode + LOGIN_TOKEN

5. create UserSession + Session last_seen_dt = now + state = UNLOCKED
6. issue JWT (access and refresh tokens and send to client)

//API AUTHORIZATION FLOW

- APP_IDLE_TIME = 5 minutes (defined in app settings)
- no more auth version check needed

1. API_AUTH decorator stays the same, only add one final check:

- Verify User Session:

&#x20; -> Extract UserSession id from access token
-> Validate session is active
-> Validate access token signature (the regular JWT token validation) #if expired then client → POST /refresh_token with refresh_token
-> Validate session state:
A. If state = UNLOCKED:
-> check if (now - last_seen_at) > APP_IDLE_TIME
a. If False -> session.last_seen_at = now -> continue
b. If True -> session.state = LOCKED -> session.last_seen_at = now -> return error message

&#x20; B. If state = LOCKED -> return error message

2. If API doesn't have api_auth decorator -> continue

//APP ACCESS FLOW

Steps:

1. User opens app

2\. Client will check:
A. If has refresh token (returning user):
a. Call refresh_token API + refresh token -> get new tokens
b. Failed to refresh -> Login Flow

&#x20; c. new tokens but session state=LOCKED -> User enters Passcode -> Verify -> UNLOCK session + last_seen_at=now.

&#x20; B. If no refresh token (first time access on device or logged out or not registered): 1. User enters phone number
-> call verify_account api (this api has no api_auth) 2. System tries to verify if account exists
a. If no account -> Registration Flow
b. If account exists -> Login Flow

//LOGOUT FLOW

LOGOUT -> SESSION REVOKED -> OTP REQUIRED NEXT LOGIN

&#x20; - extract session_id from access token (sent in post request)

&#x20; - find UserSession

&#x20; - set session is_active = False and last_seen_at=now

&#x20; - delete / null refresh_token_hash

&#x20; - return success (so that client will clear tokens also from his side)

//JWT TOKEN PATTERN (lifetime)

&#x20; - access tokenlifetime: 5 min (stateless, not saved in db)

&#x20; - refresh token lifetime: 7 days

&#x20; - Refresh token flow when access token expires:

1\. client → POST /refresh_token with refresh_token

2\. backend:

&#x20; - find UserSession

&#x20; - verify refresh_token (hash match)

&#x20; - check is_active = True

3\. rotate:

&#x20; - invalidate old refresh_token

&#x20; - generate new refresh_token

&#x20; - store new hash

4\. issue:

&#x20; - new access_token

&#x20; - new refresh_token

5\. return both to client

//SECURITY ENHANCEMENTS

Required rules for some security events

Every sensitive flow must use:

step-up authentication state (short-lived secure token)

STEP_UP_TOKEN (step-up authentication state - short-lived secure token) issued after first verified factor)

short TTL (5–10 min)

single-use

A) Change passcode (logged in)

1\. logged in

2\. re-enter old passcode

3\. verify old passcode

&#x20; → issue STEP_UP_TOKEN

4\. set new passcode + STEP_UP_TOKEN

5\. revoke all active sessions

6\. Apply cooldown on sensitive actions

B) Change phone (logged in)

1\. logged in

2\. re-enter passcode

&#x20; → STEP_UP_TOKEN

3\. enter new phone

4\. OTP new phone + STEP_UP_TOKEN

5\. update phone

6\. revoke all active sessions

7\. Apply cooldown on sensitive actions

C) Change email (logged in)

1\. logged in

2\. re-enter passcode

&#x20; → STEP_UP_TOKEN

3\. enter new email

4\. OTP new email + STEP_UP_TOKEN

5\. update email

6\. notify old email and add user notification in app notifications

7\. revoke all active sessions

8\. Apply cooldown on sensitive actions

D) Forgot passcode reset

1\. phone OTP

&#x20; → STEP_UP_TOKEN_1

2\. email OTP + STEP_UP_TOKEN_1

&#x20; → STEP_UP_TOKEN_2

3\. set new passcode + STEP_UP_TOKEN_2

4\. revoke all active sessions

5\. Apply cooldown on sensitive actions

E) No SIM + not logged in (phone change recovery)

1\. enter phone number

2\. verify passcode

&#x20; → STEP_UP_TOKEN_1

3\. email OTP + STEP_UP_TOKEN_1

&#x20; → STEP_UP_TOKEN_2

4\. enter new phone

5\. OTP new phone + STEP_UP_TOKEN_2

6\. update phone (mandatory step)

7\. revoke all active sessions

8\. Apply cooldown on sensitive actions
