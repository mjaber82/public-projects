import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.test.client import RequestFactory, Client
from django.urls import resolve, reverse

from app.transactions import views
from app.transactions.models import Transaction
from app.transactions.services import create_stripe_session, handle_stripe_webhook
from app.users.models import Country, User, UserSession
from app.wallets.models import Wallet
from app.transactions.tasks import _send_transaction_email_to_user


class TransactionsEndpointWiringTests(SimpleTestCase):
    ENDPOINTS = [
        ("transactions-root", "/api/v1/transactions/", views.transactions_root),
        ("transactions-transfer", "/api/v1/transactions/transfer/", views.transfer),
        ("transactions-accept", "/api/v1/transactions/accept/", views.accept),
        ("transactions-reject", "/api/v1/transactions/reject/", views.reject),
        ("transactions-cancel", "/api/v1/transactions/cancel/", views.cancel),
        (
            "transactions-topup-create-session",
            "/api/v1/transactions/topup/create-session/",
            views.create_topup_session,
        ),
        (
            "transactions-topup-fake-checkout",
            "/api/v1/transactions/topup/fake-checkout/fake-session/",
            views.fake_topup_checkout,
        ),
        (
            "transactions-topup-webhook",
            "/api/v1/transactions/topup/webhook/",
            views.stripe_webhook,
        ),
        (
            "transactions-export",
            "/api/v1/transactions/export/",
            views.export_transactions,
        ),
    ]

    def test_endpoint_reverse_paths(self) -> None:
        for route_name, expected_path, _ in self.ENDPOINTS:
            with self.subTest(route_name=route_name):
                if route_name == "transactions-topup-fake-checkout":
                    self.assertEqual(
                        reverse(route_name, kwargs={"session_id": "fake-session"}),
                        expected_path,
                    )
                    continue
                self.assertEqual(reverse(route_name), expected_path)

    def test_endpoint_resolve_targets(self) -> None:
        for _, endpoint_path, expected_view in self.ENDPOINTS:
            with self.subTest(endpoint_path=endpoint_path):
                match = resolve(endpoint_path)
                self.assertIs(match.func, expected_view)


class TransactionEmailPreferenceTests(SimpleTestCase):
    @patch("app.transactions.tasks.send_mail")
    def test_transaction_email_skips_when_email_notifications_disabled(self, send_mail_mock) -> None:
        user = SimpleNamespace(email="user@example.com", email_notifications=False)

        _send_transaction_email_to_user(user, "Transfer completed", "Body")

        send_mail_mock.assert_not_called()

    @patch("app.transactions.tasks.send_mail")
    def test_transaction_email_sends_when_email_notifications_enabled(self, send_mail_mock) -> None:
        user = SimpleNamespace(email="user@example.com", email_notifications=True)

        _send_transaction_email_to_user(user, "Transfer completed", "Body")

        send_mail_mock.assert_called_once()


@override_settings(FAKE_STRIPE_CHECKOUT=True)
class FakeStripeCheckoutTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.factory = RequestFactory()
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550123",
            country=self.country,
            email="user@example.com",
            passcode="1234",
        )
        self.wallet = Wallet.objects.get(user_account=self.user.account, is_main=True)

    def test_create_stripe_session_returns_fake_checkout_url(self) -> None:
        session_url, error = create_stripe_session(self.user, str(self.wallet.public_id), Decimal("25.00"))

        self.assertIsNone(error)
        self.assertIsNotNone(session_url)
        self.assertIn("/api/v1/transactions/topup/fake-checkout/", session_url)

        tx = Transaction.objects.get(transaction_type="TOP_UP")
        self.assertEqual(tx.status, "PENDING")
        self.assertEqual(tx.amount, Decimal("25.00"))
        self.assertTrue(tx.stripe_session_id.startswith("fake_cs_"))

    def test_fake_checkout_complete_updates_wallet_and_transaction(self) -> None:
        session_url, _ = create_stripe_session(self.user, str(self.wallet.public_id), Decimal("25.00"))
        request = self.factory.post(
            session_url,
            data=json.dumps(
                {
                    "action": "complete",
                    "payment_method_id": "pm_fake_123",
                    "card_brand": "visa",
                    "card_last4": "4242",
                }
            ),
            content_type="application/json",
        )
        session_id = session_url.rstrip("/").split("/")[-1]

        response = views.fake_topup_checkout.__wrapped__(request, session_id=session_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["status"], "SUCCESS")

        tx = Transaction.objects.get(transaction_type="TOP_UP")
        self.wallet.refresh_from_db()
        self.assertEqual(tx.status, "COMPLETED")
        self.assertEqual(tx.payment_method_id, "pm_fake_123")
        self.assertEqual(tx.card_brand, "visa")
        self.assertEqual(tx.card_last4, "4242")
        self.assertEqual(self.wallet.balance, Decimal("25.00"))
        self.assertEqual(tx.ledgers.get().status, "POSTED")

    def test_fake_webhook_complete_updates_topup(self) -> None:
        _, _ = create_stripe_session(self.user, str(self.wallet.public_id), Decimal("50.00"))
        tx = Transaction.objects.get(transaction_type="TOP_UP")

        success, error = handle_stripe_webhook(
            json.dumps(
                {
                    "type": "checkout.session.completed",
                    "data": {
                        "object": {
                            "id": tx.stripe_session_id,
                            "payment_method": "pm_fake_webhook",
                            "payment_method_details": {"card": {"brand": "mastercard", "last4": "5555"}},
                        }
                    },
                }
            ).encode("utf-8"),
            "fake-signature",
        )

        self.assertTrue(success)
        self.assertIsNone(error)

        tx.refresh_from_db()
        self.wallet.refresh_from_db()
        self.assertEqual(tx.status, "COMPLETED")
        self.assertEqual(tx.payment_method_id, "pm_fake_webhook")
        self.assertEqual(tx.card_brand, "mastercard")
        self.assertEqual(tx.card_last4, "5555")
        self.assertEqual(self.wallet.balance, Decimal("50.00"))


@override_settings(FAKE_STRIPE_CHECKOUT=True)
class TransactionsViewTests(TestCase):
    """Comprehensive tests for all transaction views."""

    def setUp(self) -> None:
        super().setUp()
        self.client = Client()
        self.factory = RequestFactory()
        self.country = Country.objects.get(iso_2="US")

        # Create two users for transfers
        self.sender = User.objects.create_user(
            msisdn="+12025550001",
            country=self.country,
            email="sender@example.com",
            passcode="1234",
        )
        self.sender_wallet = Wallet.objects.get(user_account=self.sender.account, is_main=True)
        self.sender_wallet.balance = Decimal("100.00")
        self.sender_wallet.save()

        self.receiver = User.objects.create_user(
            msisdn="+12025550002",
            country=self.country,
            email="receiver@example.com",
            passcode="1234",
        )
        self.receiver_wallet = Wallet.objects.get(user_account=self.receiver.account, is_main=True)
        self.sender_session = UserSession.objects.create(
            user=self.sender,
            device_id="sender-device",
            ip_address="127.0.0.1",
            is_active=True,
            state="UNLOCKED",
        )
        self.receiver_session = UserSession.objects.create(
            user=self.receiver,
            device_id="receiver-device",
            ip_address="127.0.0.1",
            is_active=True,
            state="UNLOCKED",
        )

    def _post_with_auth(self, url, data=None, user=None):
        """Helper to POST with authorization."""
        if data is None:
            data = {}
        if user is None:
            user = self.sender
        request = self.factory.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
        )
        request.user = user
        request.auth_session_id = (
            self.sender_session.public_id if user == self.sender else self.receiver_session.public_id
        )
        return request

    def _get_with_auth(self, url, user=None):
        """Helper to GET with authorization."""
        if user is None:
            user = self.sender
        request = self.factory.get(url)
        request.user = user
        request.auth_session_id = (
            self.sender_session.public_id if user == self.sender else self.receiver_session.public_id
        )
        return request

    def _call_view(self, view_func, request):
        """Call a view function, unwrapping decorators if necessary."""
        # Unwrap @api_return and @api_auth decorators
        while hasattr(view_func, "__wrapped__"):
            view_func = view_func.__wrapped__
        return view_func(request)

    # Tests for transactions_root (GET list)
    def test_transactions_list_returns_user_transactions(self) -> None:
        from app.transactions.services import initiate_transfer

        # Create a transaction
        tx, _ = initiate_transfer(
            self.sender,
            str(self.sender_wallet.public_id),
            Decimal("25.00"),
            self.receiver.msisdn,
        )

        request = self._get_with_auth(reverse("transactions-root"))
        response = views.transactions_root(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "SUCCESS")
        self.assertIn("transactions", data["payload"])
        self.assertEqual(len(data["payload"]["transactions"]), 1)

    def test_transactions_list_empty_for_user_with_no_transactions(self) -> None:
        request = self._get_with_auth(reverse("transactions-root"))
        response = views.transactions_root(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(len(data["payload"]["transactions"]), 0)

    def test_transactions_list_filters_by_status(self) -> None:
        from app.transactions.services import initiate_transfer

        # Create transactions
        tx, _ = initiate_transfer(
            self.sender,
            str(self.sender_wallet.public_id),
            Decimal("25.00"),
            self.receiver.msisdn,
        )

        request = self._get_with_auth(reverse("transactions-root") + "?status=PENDING")
        response = views.transactions_root(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data["payload"]["transactions"]), 1)

    def test_transactions_list_filters_by_transaction_type(self) -> None:
        from app.transactions.services import initiate_transfer

        tx, _ = initiate_transfer(
            self.sender,
            str(self.sender_wallet.public_id),
            Decimal("25.00"),
            self.receiver.msisdn,
        )

        request = self._get_with_auth(reverse("transactions-root") + "?transaction_type=TRANSFER")
        response = views.transactions_root(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data["payload"]["transactions"]), 1)

    # Tests for transactions_root (POST detail)
    def test_transactions_detail_requires_key(self) -> None:
        request = self._post_with_auth(reverse("transactions-root"), {})
        response = views.transactions_root(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")
        self.assertIn("key is required", data["message"])

    def test_transactions_detail_returns_transaction_by_key(self) -> None:
        from app.transactions.services import initiate_transfer

        tx, _ = initiate_transfer(
            self.sender,
            str(self.sender_wallet.public_id),
            Decimal("25.00"),
            self.receiver.msisdn,
        )

        request = self._post_with_auth(reverse("transactions-root"), {"key": str(tx.public_id)})
        response = views.transactions_root(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "SUCCESS")
        self.assertEqual(data["payload"]["transaction"]["public_id"], str(tx.public_id))

    def test_transactions_detail_fails_for_invalid_key(self) -> None:
        request = self._post_with_auth(reverse("transactions-root"), {"key": "invalid-key"})
        response = views.transactions_root(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    # Tests for transfer
    def test_transfer_requires_sender_wallet_id(self) -> None:
        request = self._post_with_auth(
            reverse("transactions-transfer"),
            {
                "sender_wallet_id": "",
                "amount": "25.00",
                "receiver_msisdn": self.receiver.msisdn,
            },
        )
        response = views.transfer(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    def test_transfer_requires_valid_amount(self) -> None:
        request = self._post_with_auth(
            reverse("transactions-transfer"),
            {
                "sender_wallet_id": str(self.sender_wallet.public_id),
                "amount": "invalid",
                "receiver_msisdn": self.receiver.msisdn,
            },
        )
        response = views.transfer(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    def test_transfer_success(self) -> None:
        request = self._post_with_auth(
            reverse("transactions-transfer"),
            {
                "sender_wallet_id": str(self.sender_wallet.public_id),
                "amount": "25.00",
                "receiver_msisdn": self.receiver.msisdn,
            },
        )
        response = views.transfer(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "SUCCESS")
        self.assertIn("transaction", data["payload"])

    def test_transfer_fails_insufficient_balance(self) -> None:
        self.sender_wallet.balance = Decimal("10.00")
        self.sender_wallet.save()

        request = self._post_with_auth(
            reverse("transactions-transfer"),
            {
                "sender_wallet_id": str(self.sender_wallet.public_id),
                "amount": "25.00",
                "receiver_msisdn": self.receiver.msisdn,
            },
        )
        response = views.transfer(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    # Tests for accept
    def test_accept_requires_key(self) -> None:
        request = self._post_with_auth(reverse("transactions-accept"), {})
        response = views.accept(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    def test_accept_transfer_success(self) -> None:
        from app.transactions.services import initiate_transfer

        tx, _ = initiate_transfer(
            self.sender,
            str(self.sender_wallet.public_id),
            Decimal("25.00"),
            self.receiver.msisdn,
        )

        # Accept as receiver
        request = self._post_with_auth(
            reverse("transactions-accept"),
            {"key": str(tx.public_id)},
            user=self.receiver,
        )
        response = views.accept(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "SUCCESS")

        tx.refresh_from_db()
        self.assertEqual(tx.status, "COMPLETED")

    def test_accept_fails_for_invalid_transaction(self) -> None:
        request = self._post_with_auth(reverse("transactions-accept"), {"key": "invalid"})
        response = views.accept(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    # Tests for reject
    def test_reject_requires_key(self) -> None:
        request = self._post_with_auth(reverse("transactions-reject"), {})
        response = views.reject(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    def test_reject_transfer_success(self) -> None:
        from app.transactions.services import initiate_transfer

        tx, _ = initiate_transfer(
            self.sender,
            str(self.sender_wallet.public_id),
            Decimal("25.00"),
            self.receiver.msisdn,
        )

        # Reject as receiver
        request = self._post_with_auth(
            reverse("transactions-reject"),
            {"key": str(tx.public_id), "reason": "Not needed"},
            user=self.receiver,
        )
        response = views.reject(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "SUCCESS")

        tx.refresh_from_db()
        self.assertEqual(tx.status, "REJECTED")

    def test_reject_with_reason(self) -> None:
        from app.transactions.services import initiate_transfer

        tx, _ = initiate_transfer(
            self.sender,
            str(self.sender_wallet.public_id),
            Decimal("25.00"),
            self.receiver.msisdn,
        )

        request = self._post_with_auth(
            reverse("transactions-reject"),
            {"key": str(tx.public_id), "reason": "Duplicate transfer"},
            user=self.receiver,
        )
        response = views.reject(request)

        self.assertEqual(response.status_code, 200)

    # Tests for cancel
    def test_cancel_requires_key(self) -> None:
        request = self._post_with_auth(reverse("transactions-cancel"), {})
        response = views.cancel(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    def test_cancel_transfer_success(self) -> None:
        from app.transactions.services import initiate_transfer

        tx, _ = initiate_transfer(
            self.sender,
            str(self.sender_wallet.public_id),
            Decimal("25.00"),
            self.receiver.msisdn,
        )

        # Cancel as sender
        request = self._post_with_auth(
            reverse("transactions-cancel"),
            {"key": str(tx.public_id), "reason": "Changed my mind"},
        )
        response = views.cancel(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "SUCCESS")

        tx.refresh_from_db()
        self.assertEqual(tx.status, "CANCELLED")

    # Tests for create_topup_session
    def test_create_topup_session_requires_wallet_id(self) -> None:
        request = self._post_with_auth(reverse("transactions-topup-create-session"), {"amount": "50.00"})
        response = views.create_topup_session(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    def test_create_topup_session_requires_amount(self) -> None:
        request = self._post_with_auth(
            reverse("transactions-topup-create-session"),
            {"wallet_id": str(self.sender_wallet.public_id)},
        )
        response = views.create_topup_session(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    def test_create_topup_session_success(self) -> None:
        request = self._post_with_auth(
            reverse("transactions-topup-create-session"),
            {"wallet_id": str(self.sender_wallet.public_id), "amount": "50.00"},
        )
        response = views.create_topup_session(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "SUCCESS")
        self.assertIn("session_url", data["payload"])

    def test_create_topup_session_fails_with_invalid_amount(self) -> None:
        request = self._post_with_auth(
            reverse("transactions-topup-create-session"),
            {"wallet_id": str(self.sender_wallet.public_id), "amount": "invalid"},
        )
        response = views.create_topup_session(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    # Tests for fake_topup_checkout (GET)
    def test_fake_checkout_get_returns_session_details(self) -> None:
        session_url, _ = create_stripe_session(self.sender, str(self.sender_wallet.public_id), Decimal("50.00"))
        session_id = session_url.rstrip("/").split("/")[-1]

        request = self.factory.get(f"/api/v1/transactions/topup/fake-checkout/{session_id}/")
        response = views.fake_topup_checkout(request, session_id=session_id)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "SUCCESS")
        self.assertIn("session_id", data["payload"])

    def test_fake_checkout_get_fails_for_invalid_session(self) -> None:
        request = self.factory.get("/api/v1/transactions/topup/fake-checkout/invalid-session/")
        response = views.fake_topup_checkout(request, session_id="invalid-session")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    def test_fake_checkout_post_completes_payment(self) -> None:
        session_url, _ = create_stripe_session(self.sender, str(self.sender_wallet.public_id), Decimal("50.00"))
        session_id = session_url.rstrip("/").split("/")[-1]

        request = self.factory.post(
            f"/api/v1/transactions/topup/fake-checkout/{session_id}/",
            data=json.dumps({"action": "complete"}),
            content_type="application/json",
        )
        response = views.fake_topup_checkout(request, session_id=session_id)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "SUCCESS")

    # Tests for stripe_webhook
    def test_stripe_webhook_requires_signature(self) -> None:
        request = self.factory.post(
            reverse("transactions-topup-webhook"),
            data=json.dumps({"type": "checkout.session.completed"}),
            content_type="application/json",
        )
        response = views.stripe_webhook(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "FAIL")

    def test_stripe_webhook_processes_completion_event(self) -> None:
        session_url, _ = create_stripe_session(self.sender, str(self.sender_wallet.public_id), Decimal("50.00"))
        tx = Transaction.objects.get(transaction_type="TOP_UP")

        request = self.factory.post(
            reverse("transactions-topup-webhook"),
            data=json.dumps(
                {
                    "type": "checkout.session.completed",
                    "data": {
                        "object": {
                            "id": tx.stripe_session_id,
                            "payment_method": "pm_test",
                            "payment_method_details": {"card": {"brand": "visa", "last4": "4242"}},
                        }
                    },
                }
            ),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test-signature",
        )
        response = views.stripe_webhook(request)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "SUCCESS")

    # Tests for export_transactions
    def test_export_transactions_returns_csv(self) -> None:
        from app.transactions.services import initiate_transfer

        # Create transaction
        tx, _ = initiate_transfer(
            self.sender,
            str(self.sender_wallet.public_id),
            Decimal("25.00"),
            self.receiver.msisdn,
        )

        request = self._get_with_auth(reverse("transactions-export"))
        response = views.export_transactions(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("transactions.csv", response["Content-Disposition"])

    def test_export_transactions_empty_for_no_transactions(self) -> None:
        request = self._get_with_auth(reverse("transactions-export"))
        response = views.export_transactions(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])

    def test_export_transactions_filters_by_status(self) -> None:
        from app.transactions.services import initiate_transfer

        tx, _ = initiate_transfer(
            self.sender,
            str(self.sender_wallet.public_id),
            Decimal("25.00"),
            self.receiver.msisdn,
        )

        request = self._get_with_auth(reverse("transactions-export") + "?status=PENDING")
        response = views.export_transactions(request)

        self.assertEqual(response.status_code, 200)

    def test_export_transactions_filters_by_type(self) -> None:
        from app.transactions.services import initiate_transfer

        tx, _ = initiate_transfer(
            self.sender,
            str(self.sender_wallet.public_id),
            Decimal("25.00"),
            self.receiver.msisdn,
        )

        request = self._get_with_auth(reverse("transactions-export") + "?transaction_type=TRANSFER")
        response = views.export_transactions(request)

        self.assertEqual(response.status_code, 200)
