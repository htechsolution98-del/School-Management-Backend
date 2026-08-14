from django.apps import AppConfig


class SmsAppConfig(AppConfig):
    name = "sms_app"

    def ready(self):
        try:
            import sms_app.signals
        except ImportError:
            pass
