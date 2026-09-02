from django.conf import settings
import razorpay
import random

# Default fallback client
client = razorpay.Client(auth=(settings.RAZOR_PAY_KEY_ID, settings.RAZOR_PAY_SECRET_KEY))

def get_school_razorpay(school=None):
    """
    Returns (razorpay_client, key_id, secret_key) for the given school.
    If school has custom RazorPayData configured, uses its credentials.
    Otherwise falls back to default settings credentials.
    """
    if school:
        from .models import RazorPayData
        school_id = getattr(school, 'id', school)
        try:
            record = RazorPayData.objects.filter(school_id=school_id).first()
            if record and record.razorpay_key_id and record.razorpay_secret_key:
                key_id = record.razorpay_key_id.strip()
                secret = record.razorpay_secret_key.strip()
                dynamic_client = razorpay.Client(auth=(key_id, secret))
                return dynamic_client, key_id, secret
        except Exception as e:
            print("Error loading school RazorPayData:", e)

    return client, settings.RAZOR_PAY_KEY_ID, settings.RAZOR_PAY_SECRET_KEY