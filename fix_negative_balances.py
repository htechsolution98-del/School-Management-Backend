import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms.settings')
django.setup()

from sms_app.models import StudentFee

fees = StudentFee.objects.all()
for fee in fees:
    # If the balance is negative, it means they paid more than payable_amount.
    # Usually this happens if the fine_amount was reset to 0 after payment.
    balance = fee.payable_amount - fee.paid_amount
    if balance < 0:
        # The extra paid amount must have been the fine.
        missing_fine = abs(balance)
        fee.fine_amount = fee.fine_amount + missing_fine
        fee.save(update_fields=['fine_amount'])
        print(f"Fixed fee ID {fee.id}: added {missing_fine} to fine_amount.")
