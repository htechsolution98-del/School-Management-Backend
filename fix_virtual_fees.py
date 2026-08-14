import os
import re

file_path = "sms_app/finance_ledger_views.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# I will replace the StudentLedgerScheduleView's post method
# We need to import datetime and timezone at the top if they are missing
if "from datetime import datetime, timedelta" not in content:
    content = "from datetime import datetime, timedelta\n" + content

if "from django.utils import timezone" not in content:
    content = "from django.utils import timezone\n" + content

def generate_virtual_fee_code():
    return """
        today = timezone.localdate()
        
        def calculate_virtual_penalty(structure, due_date_str):
            if not structure.late_fee_enabled: return Decimal('0.00')
            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                penalty_start = due_date + timedelta(days=structure.grace_days)
                if today > penalty_start:
                    if structure.late_fee_type == "fixed":
                        late_fee = structure.late_fee_amount
                    elif structure.late_fee_type == "per_day":
                        late_fee = structure.late_fee_amount * (today - penalty_start).days
                    else:
                        late_fee = Decimal('0.00')
                    if structure.max_late_fee is not None:
                        late_fee = min(late_fee, structure.max_late_fee)
                    return late_fee
            except Exception:
                pass
            return Decimal('0.00')

        projected_ledger = []
        
        for structure in fee_structures:
            if structure.feetype.billing_cycle == 'monthly':
                for year, month in months_list:
                    billing_period = f"{year}-{month:02d}"
                    key = f"{structure.feetype_id}_{billing_period}"
                    
                    if key in actual_fees_by_key:
                        actual_fee = actual_fees_by_key[key]
                        data = StudentFeeSerializer(actual_fee, context={"request": request}).data
                        data["is_virtual"] = False
                        projected_ledger.append(data)
                    else:
                        month_name = calendar.month_abbr[month]
                        due_date_str = f"{year}-{month:02d}-10"
                        penalty = calculate_virtual_penalty(structure, due_date_str)
                        payable = structure.amount + penalty
                        
                        data = {
                            "id": f"virtual_{key}",
                            "is_virtual": True,
                            "feetype": structure.feetype_id,
                            "feetype_name": structure.feetype.name,
                            "fee_wise_class": structure.id,
                            "billing_period": billing_period,
                            "amount": str(structure.amount),
                            "discount_amount": "0.00",
                            "late_fee_amount": str(structure.late_fee_amount) if structure.late_fee_amount else "0.00",
                            "fine_amount": str(penalty),
                            "paid_amount": "0.00",
                            "balance_amount": str(payable),
                            "payable_amount": str(payable),
                            "status": "Pending Generation",
                            "late_fee_enabled": structure.late_fee_enabled,
                            "grace_days": structure.grace_days,
                            "late_fee_type": structure.late_fee_type,
                            "due_date": due_date_str,
                        }
                        projected_ledger.append(data)
                        
            elif structure.feetype.billing_cycle in ['yearly', 'single']:
                billing_period = academic_year.name
                key = f"{structure.feetype_id}_{billing_period}"
                
                if key in actual_fees_by_key:
                    actual_fee = actual_fees_by_key[key]
                    data = StudentFeeSerializer(actual_fee, context={"request": request}).data
                    data["is_virtual"] = False
                    projected_ledger.append(data)
                else:
                    due_date_str = f"{start_year}-{start_month:02d}-15"
                    penalty = calculate_virtual_penalty(structure, due_date_str)
                    payable = structure.amount + penalty

                    data = {
                        "id": f"virtual_{key}",
                        "is_virtual": True,
                        "feetype": structure.feetype_id,
                        "feetype_name": structure.feetype.name,
                        "fee_wise_class": structure.id,
                        "billing_period": billing_period,
                        "amount": str(structure.amount),
                        "discount_amount": "0.00",
                        "late_fee_amount": str(structure.late_fee_amount) if structure.late_fee_amount else "0.00",
                        "fine_amount": str(penalty),
                        "paid_amount": "0.00",
                        "balance_amount": str(payable),
                        "payable_amount": str(payable),
                        "status": "Pending Generation",
                        "late_fee_enabled": structure.late_fee_enabled,
                        "grace_days": structure.grace_days,
                        "late_fee_type": structure.late_fee_type,
                        "due_date": due_date_str,
                    }
                    projected_ledger.append(data)

        return Response(projected_ledger)"""

# Use regex to find and replace the content of projected_ledger loop
pattern = re.compile(r'projected_ledger = \[\]\s+for structure in fee_structures:.*?return Response\(projected_ledger\)', re.DOTALL)
new_content = pattern.sub(generate_virtual_fee_code(), content)

# Check if we also need to import Decimal
if "from decimal import Decimal" not in new_content:
    new_content = "from decimal import Decimal\n" + new_content

with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Updated successfully")
