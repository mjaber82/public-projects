from django.apps import AppConfig
from app.core.firebase import initialize_firebase


class CoreConfig(AppConfig):
    name = "app.core"

    def ready(self):
        initialize_firebase()
