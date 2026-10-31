from django.apps import AppConfig

class SmsAppConfig(AppConfig):
    name = "sms_app"

    def ready(self):
        try:
            import sms_app.signals
        except ImportError:
            pass
        from sms_app.text_normalization import connect_normalization_signals

        connect_normalization_signals()
