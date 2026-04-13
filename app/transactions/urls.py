from django.urls import path

from . import views

urlpatterns = [
    path("transactions/", views.transactions_root, name="transactions-root"),
    path("transactions/transfer/", views.transfer, name="transactions-transfer"),
    path("transactions/accept/", views.accept, name="transactions-accept"),
    path("transactions/reject/", views.reject, name="transactions-reject"),
    path("transactions/cancel/", views.cancel, name="transactions-cancel"),
    path(
        "transactions/topup/create-session/",
        views.create_topup_session,
        name="transactions-topup-create-session",
    ),
    path(
        "transactions/topup/fake-checkout/<str:session_id>/",
        views.fake_topup_checkout,
        name="transactions-topup-fake-checkout",
    ),
    path(
        "transactions/topup/webhook/",
        views.stripe_webhook,
        name="transactions-topup-webhook",
    ),
    path("transactions/export/", views.export_transactions, name="transactions-export"),
]
