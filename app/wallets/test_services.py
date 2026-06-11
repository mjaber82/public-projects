from decimal import Decimal

from django.test import TestCase

from app.users.models import Country, User
from app.wallets.models import Wallet
from app.wallets.services import (
    create_wallet,
    deactivate_wallet,
    ensure_main_wallet,
    get_wallet_detail,
    get_wallet_list,
    update_wallet_name,
)


class EnsureMainWalletTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550301",
            country=self.country,
            email="wallet_test@example.com",
            passcode="1234",
        )

    def test_returns_existing_main_wallet(self) -> None:
        wallet = ensure_main_wallet(self.user)
        self.assertTrue(wallet.is_main)
        self.assertEqual(wallet.name, "Main")

        # Calling again returns the same wallet
        wallet2 = ensure_main_wallet(self.user)
        self.assertEqual(wallet.pk, wallet2.pk)


class CreateWalletTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550302",
            country=self.country,
            email="wallet_create@example.com",
            passcode="1234",
        )

    def test_create_wallet_success(self) -> None:
        wallet, error = create_wallet(self.user, "Travel")
        self.assertIsNone(error)
        self.assertIsNotNone(wallet)
        self.assertEqual(wallet.name, "Travel")
        self.assertFalse(wallet.is_main)

    def test_create_wallet_empty_name(self) -> None:
        wallet, error = create_wallet(self.user, "")
        self.assertIsNone(wallet)
        self.assertEqual(error, "Wallet name cannot be empty")

    def test_create_wallet_whitespace_name(self) -> None:
        wallet, error = create_wallet(self.user, "   ")
        self.assertIsNone(wallet)
        self.assertEqual(error, "Wallet name cannot be empty")

    def test_create_wallet_main_name_rejected(self) -> None:
        wallet, error = create_wallet(self.user, "main")
        self.assertIsNone(wallet)
        self.assertEqual(error, "Main wallet already exists")

    def test_create_wallet_duplicate_name(self) -> None:
        create_wallet(self.user, "Savings")
        wallet, error = create_wallet(self.user, "Savings")
        self.assertIsNone(wallet)
        self.assertEqual(error, "Wallet name already exists for this user")


class GetWalletListTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550303",
            country=self.country,
            email="wallet_list@example.com",
            passcode="1234",
        )

    def test_returns_active_wallets(self) -> None:
        create_wallet(self.user, "Travel")
        create_wallet(self.user, "Savings")
        wallets = get_wallet_list(self.user)
        self.assertEqual(len(wallets), 3)  # Main + Travel + Savings

    def test_main_wallet_first(self) -> None:
        create_wallet(self.user, "Alpha")
        wallets = get_wallet_list(self.user)
        self.assertTrue(wallets[0].is_main)


class GetWalletDetailTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550304",
            country=self.country,
            email="wallet_detail@example.com",
            passcode="1234",
        )

    def test_found(self) -> None:
        wallet, _ = create_wallet(self.user, "Detail")
        found, error = get_wallet_detail(self.user, str(wallet.public_id))
        self.assertIsNone(error)
        self.assertEqual(found.pk, wallet.pk)

    def test_not_found(self) -> None:
        found, error = get_wallet_detail(self.user, "00000000-0000-0000-0000-000000000000")
        self.assertIsNone(found)
        self.assertEqual(error, "Wallet not found")


class UpdateWalletNameTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550305",
            country=self.country,
            email="wallet_update@example.com",
            passcode="1234",
        )

    def test_update_success(self) -> None:
        wallet, _ = create_wallet(self.user, "Old Name")
        updated, error = update_wallet_name(self.user, str(wallet.public_id), "New Name")
        self.assertIsNone(error)
        self.assertEqual(updated.name, "New Name")

    def test_update_empty_name(self) -> None:
        wallet, _ = create_wallet(self.user, "Something")
        updated, error = update_wallet_name(self.user, str(wallet.public_id), "")
        self.assertIsNone(updated)
        self.assertEqual(error, "Wallet name cannot be empty")

    def test_update_main_wallet_rejected(self) -> None:
        main_wallet = Wallet.objects.get(user_account=self.user.account, is_main=True)
        updated, error = update_wallet_name(self.user, str(main_wallet.public_id), "Custom")
        self.assertIsNone(updated)
        self.assertEqual(error, "Main wallet name cannot be changed")

    def test_update_nonexistent_wallet(self) -> None:
        updated, error = update_wallet_name(self.user, "00000000-0000-0000-0000-000000000000", "Name")
        self.assertIsNone(updated)
        self.assertEqual(error, "Wallet not found")

    def test_update_duplicate_name(self) -> None:
        create_wallet(self.user, "Existing")
        wallet2, _ = create_wallet(self.user, "Other")
        updated, error = update_wallet_name(self.user, str(wallet2.public_id), "Existing")
        self.assertIsNone(updated)
        self.assertEqual(error, "Wallet name already exists for this user")


class DeactivateWalletTests(TestCase):
    def setUp(self) -> None:
        self.country = Country.objects.get(iso_2="US")
        self.user = User.objects.create_user(
            msisdn="+12025550306",
            country=self.country,
            email="wallet_deactivate@example.com",
            passcode="1234",
        )

    def test_deactivate_success_zero_balance(self) -> None:
        wallet, _ = create_wallet(self.user, "ToDeactivate")
        success, error = deactivate_wallet(self.user, str(wallet.public_id))
        self.assertTrue(success)
        self.assertIsNone(error)

        wallet.refresh_from_db()
        self.assertFalse(wallet.is_active)
        self.assertIsNotNone(wallet.deactivated_at)

    def test_deactivate_transfers_balance_to_main(self) -> None:
        wallet, _ = create_wallet(self.user, "WithBalance")
        wallet.balance = Decimal("50.00")
        wallet.save()

        main_wallet = Wallet.objects.get(user_account=self.user.account, is_main=True)
        original_main_balance = main_wallet.balance

        success, error = deactivate_wallet(self.user, str(wallet.public_id))
        self.assertTrue(success)

        main_wallet.refresh_from_db()
        self.assertEqual(main_wallet.balance, original_main_balance + Decimal("50.00"))

    def test_deactivate_main_wallet_rejected(self) -> None:
        main_wallet = Wallet.objects.get(user_account=self.user.account, is_main=True)
        success, error = deactivate_wallet(self.user, str(main_wallet.public_id))
        self.assertFalse(success)
        self.assertEqual(error, "Main wallet cannot be deactivated")

    def test_deactivate_nonexistent_wallet(self) -> None:
        success, error = deactivate_wallet(self.user, "00000000-0000-0000-0000-000000000000")
        self.assertFalse(success)
        self.assertEqual(error, "Wallet not found or already inactive")

    def test_deactivate_wallet_with_in_transfer_balance(self) -> None:
        wallet, _ = create_wallet(self.user, "InTransfer")
        wallet.in_transfer = Decimal("10.00")
        wallet.save()

        success, error = deactivate_wallet(self.user, str(wallet.public_id))
        self.assertFalse(success)
        self.assertEqual(error, "Wallet has booked balance in transfer")
