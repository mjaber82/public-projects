from django.urls import path

from . import views

urlpatterns = [
    path("wallets/", views.wallet_list, name="wallets-list"),
    path("wallets/get_details/", views.wallet_detail, name="wallets-detail"),
    path("wallets/create/", views.create_wallet, name="wallets-create"),
    path("wallets/update/", views.update_wallet, name="wallets-update"),
    path("wallets/deactivate/", views.deactivate_wallet_view, name="wallets-deactivate"),
]
