from django.urls import path

from . import views

urlpatterns = [
    path("notifications/", views.notification_list, name="notifications-list"),
    path("notifications/read/", views.mark_notification_read, name="notifications-read"),
    path("notifications/read-all/", views.mark_all_read, name="notifications-read-all"),
    path(
        "notifications/clear/",
        views.clear_notification_view,
        name="notifications-clear",
    ),
    path(
        "notifications/clear-all/",
        views.clear_all_notifications,
        name="notifications-clear-all",
    ),
]
