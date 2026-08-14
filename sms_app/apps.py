from django.apps import AppConfig
from django.db.models.signals import post_migrate

def auto_seed_on_migrate(sender, **kwargs):
    from django.core.management import call_command
    try:
        call_command("create_admin")
    except Exception as e:
        print("Auto seed error:", e)

class SmsAppConfig(AppConfig):
    name = "sms_app"

    def ready(self):
        try:
            import sms_app.signals
        except ImportError:
            pass
        post_migrate.connect(auto_seed_on_migrate, sender=self)
