import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from django.test.client import RequestFactory
from django.urls import resolve, reverse

from app.wallets import views


class WalletsEndpointWiringTests(SimpleTestCase):
    ENDPOINTS = [
        ("wallets-list", "/api/v1/wallets/", views.wallet_list),
        ("wallets-detail", "/api/v1/wallets/get_details/", views.wallet_detail),
        ("wallets-create", "/api/v1/wallets/create/", views.create_wallet),
        ("wallets-update", "/api/v1/wallets/update/", views.update_wallet),
        (
            "wallets-deactivate",
            "/api/v1/wallets/deactivate/",
            views.deactivate_wallet_view,
        ),
    ]

    def test_endpoint_reverse_paths(self) -> None:
        for route_name, expected_path, _ in self.ENDPOINTS:
            with self.subTest(route_name=route_name):
                self.assertEqual(reverse(route_name), expected_path)

    def test_endpoint_resolve_targets(self) -> None:
        for _, endpoint_path, expected_view in self.ENDPOINTS:
            with self.subTest(endpoint_path=endpoint_path):
                match = resolve(endpoint_path)
                self.assertIs(match.func, expected_view)


class WalletsViewTests(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.factory = RequestFactory()
        self.user = object()

    def _raw_get(self, path: str):
        request = self.factory.get(path)
        request.user = self.user
        return request

    def _raw_post(self, path: str, payload: dict):
        request = self.factory.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )
        request.user = self.user
        return request

    @patch("app.wallets.views.WalletSerializer")
    @patch("app.wallets.views.get_wallet_list")
    def test_wallet_list_success(self, get_wallet_list_mock, wallet_serializer_mock) -> None:
        request = self._raw_get(reverse("wallets-list"))
        wallets = [Mock()]
        get_wallet_list_mock.return_value = wallets
        wallet_serializer_mock.return_value.data = [{"name": "Main"}]

        response = views.wallet_list.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        get_wallet_list_mock.assert_called_once_with(self.user)
        wallet_serializer_mock.assert_called_once_with(wallets, many=True)
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Success")
        self.assertEqual(body["payload"]["wallets"], [{"name": "Main"}])

    @patch("app.wallets.views.WalletSerializer")
    @patch("app.wallets.views.get_wallet_detail")
    def test_wallet_detail_success(self, get_wallet_detail_mock, wallet_serializer_mock) -> None:
        request = self._raw_post(reverse("wallets-detail"), {"key": "11111111-1111-1111-1111-111111111111"})
        wallet = Mock()
        get_wallet_detail_mock.return_value = (wallet, None)
        wallet_serializer_mock.return_value.data = {"name": "Savings"}

        response = views.wallet_detail.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        get_wallet_detail_mock.assert_called_once_with(self.user, get_wallet_detail_mock.call_args.args[1])
        wallet_serializer_mock.assert_called_once_with(wallet)
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Success")
        self.assertEqual(body["payload"]["wallet"], {"name": "Savings"})

    @patch("app.wallets.views.get_wallet_detail")
    def test_wallet_detail_fail(self, get_wallet_detail_mock) -> None:
        request = self._raw_post(reverse("wallets-detail"), {"key": "11111111-1111-1111-1111-111111111111"})
        get_wallet_detail_mock.return_value = (None, "Wallet not found")

        response = views.wallet_detail.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "Wallet not found")

    @patch("app.wallets.views.WalletSerializer")
    @patch("app.wallets.views.create_wallet_service")
    def test_create_wallet_success(self, create_wallet_service_mock, wallet_serializer_mock) -> None:
        request = self._raw_post(reverse("wallets-create"), {"name": "Travel"})
        wallet = Mock()
        create_wallet_service_mock.return_value = (wallet, None)
        wallet_serializer_mock.return_value.data = {"name": "Travel"}

        response = views.create_wallet.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        create_wallet_service_mock.assert_called_once_with(self.user, "Travel")
        wallet_serializer_mock.assert_called_once_with(wallet)
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Wallet created")
        self.assertEqual(body["payload"]["wallet"], {"name": "Travel"})

    @patch("app.wallets.views.create_wallet_service")
    def test_create_wallet_fail(self, create_wallet_service_mock) -> None:
        request = self._raw_post(reverse("wallets-create"), {"name": "Travel"})
        create_wallet_service_mock.return_value = (None, "Wallet name already exists")

        response = views.create_wallet.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "Wallet name already exists")

    @patch("app.wallets.views.WalletSerializer")
    @patch("app.wallets.views.update_wallet_name")
    def test_update_wallet_success(self, update_wallet_name_mock, wallet_serializer_mock) -> None:
        request = self._raw_post(
            reverse("wallets-update"),
            {"key": "11111111-1111-1111-1111-111111111111", "name": "Bills"},
        )
        wallet = Mock()
        update_wallet_name_mock.return_value = (wallet, None)
        wallet_serializer_mock.return_value.data = {"name": "Bills"}

        response = views.update_wallet.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        update_wallet_name_mock.assert_called_once_with(self.user, update_wallet_name_mock.call_args.args[1], "Bills")
        wallet_serializer_mock.assert_called_once_with(wallet)
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Wallet updated")
        self.assertEqual(body["payload"]["wallet"], {"name": "Bills"})

    @patch("app.wallets.views.update_wallet_name")
    def test_update_wallet_fail(self, update_wallet_name_mock) -> None:
        request = self._raw_post(
            reverse("wallets-update"),
            {"key": "11111111-1111-1111-1111-111111111111", "name": "Bills"},
        )
        update_wallet_name_mock.return_value = (None, "Wallet not found")

        response = views.update_wallet.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "Wallet not found")

    @patch("app.wallets.views.deactivate_wallet")
    def test_deactivate_wallet_success(self, deactivate_wallet_mock) -> None:
        request = self._raw_post(
            reverse("wallets-deactivate"),
            {"key": "11111111-1111-1111-1111-111111111111"},
        )
        deactivate_wallet_mock.return_value = (True, None)

        response = views.deactivate_wallet_view.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        deactivate_wallet_mock.assert_called_once_with(self.user, deactivate_wallet_mock.call_args.args[1])
        self.assertEqual(body["status"], "SUCCESS")
        self.assertEqual(body["message"], "Wallet deactivated")

    @patch("app.wallets.views.deactivate_wallet")
    def test_deactivate_wallet_fail(self, deactivate_wallet_mock) -> None:
        request = self._raw_post(
            reverse("wallets-deactivate"),
            {"key": "11111111-1111-1111-1111-111111111111"},
        )
        deactivate_wallet_mock.return_value = (
            False,
            "Main wallet cannot be deactivated",
        )

        response = views.deactivate_wallet_view.__wrapped__.__wrapped__(request)
        body = json.loads(response.content)

        self.assertEqual(body["status"], "FAIL")
        self.assertEqual(body["message"], "Main wallet cannot be deactivated")
