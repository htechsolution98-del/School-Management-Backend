from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum

from .inventory_models import (
    Item, ItemPricing, Purchase, StockTransaction,
    StudentItemEntitlement, StudentItemIssue, ReplacementRequest,
    StudentItemReturn, StockAdjustment, InventoryAuditLog
)

class InventoryService:

    @staticmethod
    def get_item_stock(item_id, size_id=None, color_id=None):
        """Calculate live available stock for an item or specific variant"""
        qs = StockTransaction.objects.filter(item_id=item_id)
        if size_id:
            qs = qs.filter(size_id=size_id)
        if color_id:
            qs = qs.filter(color_id=color_id)
        total = qs.aggregate(total=Sum('quantity'))['total'] or 0
        return max(0, total)

    @classmethod
    @transaction.atomic
    def process_purchase_confirmation(cls, purchase: Purchase, user=None):
        """Confirm a purchase order and create inward stock transactions"""
        if purchase.status == 'CONFIRMED':
            return purchase

        for p_item in purchase.items.all():
            StockTransaction.objects.create(
                school=purchase.school,
                item=p_item.item,
                academic_year=purchase.academic_year,
                size=p_item.size,
                color=p_item.color,
                transaction_type='PURCHASE',
                quantity=p_item.quantity,
                unit_purchase_cost=p_item.unit_cost,
                reference_type='Purchase',
                reference_id=str(purchase.id),
                transaction_date=purchase.purchase_date,
                remarks=f"Purchase PO #{purchase.invoice_number}",
                created_by=user
            )

        purchase.status = 'CONFIRMED'
        purchase.save()
        return purchase

    @classmethod
    @transaction.atomic
    def issue_item_single(cls, school, academic_year, student, item, quantity=1, size=None, color=None,
                          charging_type=None, charged_amount=None, issue_reason='INITIAL_ISSUE',
                          remarks='', user=None):
        """Atomically issue item to a single student with stock check and price snapshotting"""
        # 1. Lock and verify stock
        current_stock = cls.get_item_stock(item.id, size.id if size else None, color.id if color else None)
        if current_stock < quantity:
            raise ValidationError(f"Insufficient stock for '{item.item_name}'. Available: {current_stock}, Requested: {quantity}")

        # 2. Get active pricing snapshot
        active_pricing = ItemPricing.objects.filter(
            item=item,
            academic_year=academic_year,
            is_active=True
        ).first()

        unit_purchase_cost = active_pricing.purchase_cost if active_pricing else Decimal('0.00')
        unit_selling_price = active_pricing.selling_price if active_pricing else Decimal('0.00')
        effective_charging_type = charging_type or (active_pricing.charging_type if active_pricing else 'SEPARATE_CHARGE')

        if charged_amount is None:
            if effective_charging_type == 'FREE' or effective_charging_type == 'INCLUDED_IN_FEE':
                charged_amount = Decimal('0.00')
            else:
                charged_amount = unit_selling_price * quantity

        # 3. Create Issue Record
        issue_record = StudentItemIssue.objects.create(
            school=school,
            academic_year=academic_year,
            student=student,
            item=item,
            size=size,
            color=color,
            quantity=quantity,
            unit_purchase_cost=unit_purchase_cost,
            unit_selling_price=unit_selling_price,
            charging_type=effective_charging_type,
            charged_amount=charged_amount,
            issue_date=timezone.now().date(),
            issue_reason=issue_reason,
            remarks=remarks,
            issued_by=user
        )

        # 4. Create Negative Stock Outflow
        StockTransaction.objects.create(
            school=school,
            item=item,
            academic_year=academic_year,
            size=size,
            color=color,
            transaction_type='ISSUE',
            quantity=-abs(quantity),
            unit_purchase_cost=unit_purchase_cost,
            unit_selling_price=unit_selling_price,
            reference_type='StudentItemIssue',
            reference_id=str(issue_record.id),
            transaction_date=timezone.now().date(),
            remarks=f"Issued to {student.name} {student.surname} (Roll {student.roll_no})",
            created_by=user
        )

        # 5. Update entitlement if matched
        entitlement = StudentItemEntitlement.objects.filter(
            student=student,
            item=item,
            academic_year=academic_year,
            status__in=['PENDING', 'PARTIALLY_ISSUED']
        ).first()

        if entitlement:
            entitlement.issued_quantity += quantity
            if entitlement.issued_quantity >= entitlement.entitled_quantity:
                entitlement.status = 'FULLY_ISSUED'
            else:
                entitlement.status = 'PARTIALLY_ISSUED'
            entitlement.save()

        return issue_record

    @classmethod
    @transaction.atomic
    def issue_item_bulk(cls, school, academic_year, item, student_ids, quantity_per_student=1,
                        size=None, color=None, user=None):
        """Atomically issue items to multiple students with total stock pre-validation"""
        total_required = len(student_ids) * quantity_per_student
        current_stock = cls.get_item_stock(item.id, size.id if size else None, color.id if color else None)

        if current_stock < total_required:
            raise ValidationError(
                f"Insufficient stock for bulk issue. Available: {current_stock}, Required: {total_required} ({len(student_ids)} students x {quantity_per_student} qty)"
            )

        from .models import Student
        students = Student.objects.filter(id__in=student_ids, school=school)
        issued_records = []

        for student in students:
            record = cls.issue_item_single(
                school=school,
                academic_year=academic_year,
                student=student,
                item=item,
                quantity=quantity_per_student,
                size=size,
                color=color,
                issue_reason='INITIAL_ISSUE',
                remarks='Bulk Issue',
                user=user
            )
            issued_records.append(record)

        return issued_records

    @classmethod
    @transaction.atomic
    def process_replacement_issue(cls, replacement: ReplacementRequest, charging_type='FREE',
                                  charged_amount=Decimal('0.00'), user=None):
        """Process approved replacement by dispensing item and updating stock"""
        item = replacement.item
        size = replacement.requested_size or replacement.current_size
        color = replacement.requested_color or replacement.current_color
        qty = replacement.quantity

        current_stock = cls.get_item_stock(item.id, size.id if size else None, color.id if color else None)
        if current_stock < qty:
            raise ValidationError(f"Insufficient stock for replacement. Available: {current_stock}, Required: {qty}")

        issue_record = cls.issue_item_single(
            school=replacement.school,
            academic_year=replacement.academic_year,
            student=replacement.student,
            item=item,
            quantity=qty,
            size=size,
            color=color,
            charging_type=charging_type,
            charged_amount=charged_amount,
            issue_reason='REPLACEMENT',
            remarks=f"Replacement #{replacement.id} - Reason: {replacement.reason}",
            user=user
        )

        replacement.status = 'ISSUED'
        replacement.reviewed_at = timezone.now()
        replacement.reviewed_by = user
        replacement.save()

        return issue_record

    @classmethod
    @transaction.atomic
    def process_return(cls, return_obj: StudentItemReturn, user=None):
        """Process returned item and adjust stock if good condition"""
        if return_obj.condition == 'GOOD':
            StockTransaction.objects.create(
                school=return_obj.school,
                item=return_obj.item,
                size=return_obj.size,
                color=return_obj.color,
                transaction_type='RETURN',
                quantity=return_obj.quantity,
                reference_type='StudentItemReturn',
                reference_id=str(return_obj.id),
                transaction_date=return_obj.return_date,
                remarks=f"Returned in Good Condition by {return_obj.student.name} {return_obj.student.surname}",
                created_by=user
            )
        elif return_obj.condition in ['DAMAGED', 'UNUSABLE']:
            StockTransaction.objects.create(
                school=return_obj.school,
                item=return_obj.item,
                size=return_obj.size,
                color=return_obj.color,
                transaction_type='DAMAGE',
                quantity=0,  # Recorded without restoring available stock
                reference_type='StudentItemReturn',
                reference_id=str(return_obj.id),
                transaction_date=return_obj.return_date,
                remarks=f"Returned in Damaged/Unusable condition by {return_obj.student.name}",
                created_by=user
            )
        return return_obj

    @classmethod
    @transaction.atomic
    def process_adjustment(cls, adjustment: StockAdjustment, user=None):
        """Record manual adjustment and create ledger transaction"""
        qty = adjustment.quantity
        if adjustment.adjustment_type in ['ADJUSTMENT_OUT', 'DAMAGE', 'LOST']:
            signed_qty = -abs(qty)
        else:
            signed_qty = abs(qty)

        StockTransaction.objects.create(
            school=adjustment.school,
            item=adjustment.item,
            size=adjustment.size,
            color=adjustment.color,
            transaction_type=adjustment.adjustment_type,
            quantity=signed_qty,
            reference_type='StockAdjustment',
            reference_id=str(adjustment.id),
            transaction_date=adjustment.adjustment_date,
            remarks=f"{adjustment.reason}: {adjustment.remarks or ''}".strip(),
            created_by=user
        )
        return adjustment
