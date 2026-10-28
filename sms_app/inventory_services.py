from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from django.core.exceptions import ValidationError

from .inventory_models import (
    Item, ItemPricing, Purchase, StockTransaction,
    StudentItemEntitlement, StudentItemIssue, ReplacementRequest,
    StudentItemReturn, StockAdjustment, InventoryAuditLog
)

class InventoryService:

    @staticmethod
    def log_stock_transaction(transaction_record, user=None):
        InventoryAuditLog.objects.create(
            school=transaction_record.school,
            user=user,
            action='POSTED',
            entity_type='StockTransaction',
            entity_id=str(transaction_record.id),
            new_values={
                'item_id': transaction_record.item_id,
                'transaction_type': transaction_record.transaction_type,
                'quantity': transaction_record.quantity,
                'reference_type': transaction_record.reference_type,
                'reference_id': transaction_record.reference_id,
                'transaction_date': str(transaction_record.transaction_date),
            },
        )

    @staticmethod
    def get_item_stock(item_id, size_id=None, color_id=None):
        """Calculate live available stock for an item or specific variant"""
        qs = StockTransaction.objects.filter(item_id=item_id)
        if size_id is not None:
            qs = qs.filter(size_id=size_id)
        if color_id is not None:
            qs = qs.filter(color_id=color_id)
        total = qs.aggregate(total=Sum('quantity'))['total'] or 0
        return max(0, total)

    @classmethod
    @transaction.atomic
    def process_purchase_confirmation(cls, purchase: Purchase, user=None):
        """Confirm a purchase order and create inward stock transactions"""
        if purchase.status == 'CANCELLED':
            raise ValidationError("A cancelled purchase cannot be confirmed.")

        # Existing confirmed invoices may have been created before the stock-posting
        # fix. Check the ledger reference, not just the status, to avoid duplicate stock.
        if StockTransaction.objects.filter(
            school=purchase.school,
            reference_type='Purchase',
            reference_id=str(purchase.id),
        ).exists():
            if purchase.status != 'CONFIRMED':
                purchase.status = 'CONFIRMED'
                purchase.save(update_fields=['status', 'updated_at'])
            return purchase

        purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
        if StockTransaction.objects.filter(
            school=purchase.school,
            reference_type='Purchase',
            reference_id=str(purchase.id),
        ).exists():
            return purchase

        line_items = list(purchase.items.select_related('item').all())
        if not line_items:
            raise ValidationError("A purchase must contain at least one line item.")
        for p_item in line_items:
            if p_item.item.school_id != purchase.school_id:
                raise ValidationError("All purchased items must belong to the purchase school.")
            transaction_record = StockTransaction.objects.create(
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
            cls.log_stock_transaction(transaction_record, user)

        purchase.status = 'CONFIRMED'
        purchase.save(update_fields=['status', 'updated_at'])
        return purchase

    @classmethod
    @transaction.atomic
    def issue_item_single(cls, school, academic_year, student, item, quantity=1, size=None, color=None,
                          charging_type=None, charged_amount=None, issue_reason='INITIAL_ISSUE',
                          remarks='', user=None):
        """Atomically issue item to a single student with stock check and price snapshotting"""
        # 1. Lock and verify stock
        if quantity <= 0:
            raise ValidationError("Issue quantity must be greater than zero.")
        if item.school_id != school.id or student.school_id != school.id or academic_year.school_id != school.id:
            raise ValidationError("Student, item, academic year, and inventory school must match.")
        if size and size.school_id != school.id:
            raise ValidationError("Selected size does not belong to this school.")
        if color and color.school_id != school.id:
            raise ValidationError("Selected color does not belong to this school.")
        if item.has_size and not size:
            raise ValidationError("Select a size for this item.")
        if item.has_color and not color:
            raise ValidationError("Select a color for this item.")
        if charging_type and charging_type not in {'INCLUDED_IN_FEE', 'SEPARATE_CHARGE', 'FREE'}:
            raise ValidationError("Invalid charging type.")
        if charged_amount is not None and charged_amount < 0:
            raise ValidationError("Charged amount cannot be negative.")
        Item.objects.select_for_update().get(pk=item.pk)
        current_stock = cls.get_item_stock(item.id, size.id if size else None, color.id if color else None)
        if current_stock < quantity:
            raise ValidationError(f"Insufficient stock for '{item.item_name}'. Available: {current_stock}, Requested: {quantity}")

        # 2. Get active pricing snapshot
        active_pricing = ItemPricing.objects.filter(
            item=item,
            academic_year=academic_year,
            is_active=True
        ).filter(Q(effective_from__isnull=True) | Q(effective_from__lte=timezone.now().date())) \
         .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=timezone.now().date())) \
         .order_by('-school_class_id')
        if student.school_class_id:
            active_pricing = active_pricing.filter(Q(school_class_id=student.school_class_id) | Q(school_class__isnull=True))
        else:
            active_pricing = active_pricing.filter(school_class__isnull=True)
        active_pricing = active_pricing.first()

        unit_purchase_cost = active_pricing.purchase_cost if (active_pricing and active_pricing.purchase_cost > Decimal('0.00')) else Decimal('0.00')
        if unit_purchase_cost <= Decimal('0.00'):
            alt_pricing = item.pricings.filter(is_active=True, purchase_cost__gt=0).order_by('-academic_year__id').first()
            if alt_pricing and alt_pricing.purchase_cost > Decimal('0.00'):
                unit_purchase_cost = alt_pricing.purchase_cost
            else:
                last_pi = item.purchase_items.filter(unit_cost__gt=0).order_by('-purchase__purchase_date', '-id').first()
                if last_pi and last_pi.unit_cost > Decimal('0.00'):
                    unit_purchase_cost = last_pi.unit_cost
                else:
                    last_tx = item.stock_transactions.filter(
                        transaction_type__in=['PURCHASE', 'OPENING'],
                        unit_purchase_cost__gt=0
                    ).order_by('-transaction_date', '-id').first()
                    if last_tx and last_tx.unit_purchase_cost:
                        unit_purchase_cost = last_tx.unit_purchase_cost
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
        transaction_record = StockTransaction.objects.create(
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
        cls.log_stock_transaction(transaction_record, user)

        # 5. Update entitlement if matched
        entitlement = StudentItemEntitlement.objects.filter(
            student=student,
            item=item,
            academic_year=academic_year,
            status__in=['PENDING', 'PARTIALLY_ISSUED']
        ).filter(size=size, color=color).first()

        if entitlement:
            if entitlement.remaining_quantity < quantity:
                raise ValidationError(
                    f"Issue exceeds the student's remaining entitlement ({entitlement.remaining_quantity})."
                )
            entitlement.issued_quantity += quantity
            if entitlement.issued_quantity >= entitlement.entitled_quantity:
                entitlement.status = 'FULLY_ISSUED'
            else:
                entitlement.status = 'PARTIALLY_ISSUED'
            entitlement.save()

        # 6. Automatic Fee Ledger Integration for SEPARATE_CHARGE items
        if effective_charging_type == 'SEPARATE_CHARGE':
            total_fee_amount = charged_amount if (charged_amount is not None and charged_amount > Decimal('0.00')) else (unit_selling_price * quantity)
            if total_fee_amount > Decimal('0.00'):
                from .models import FeeType, StudentFee, FeeWiseClass

                # Check if item pricing specified an included_fee_type or look for an existing Inventory FeeType
                feetype = None
                if active_pricing and active_pricing.included_fee_type:
                    feetype = active_pricing.included_fee_type
                else:
                    feetype = FeeType.objects.filter(school=school, name__iexact="Inventory Fee").first()
                    if not feetype:
                        feetype = FeeType.objects.filter(school=school, name__icontains="Inventory").first()
                    if not feetype:
                        feetype = FeeType.objects.create(
                            school=school,
                            name="Inventory Fee",
                            billing_cycle="single",
                            is_rte_applicable=True
                        )

                fee_wise_class = None
                if student.school_class_id and feetype:
                    fee_wise_class = FeeWiseClass.objects.filter(
                        school=school, feetype=feetype, school_class_id=student.school_class_id
                    ).first()

                description = f"Inventory Issue: {item.item_name}"
                if size and getattr(size, 'size_name', None):
                    description += f" (Size {size.size_name})"
                if color and getattr(color, 'color_name', None):
                    description += f" (Color {color.color_name})"

                StudentFee.objects.create(
                    school=school,
                    academic_year=academic_year,
                    student=student,
                    feetype=feetype,
                    fee_wise_class=fee_wise_class,
                    amount=total_fee_amount,
                    discount_amount=Decimal('0.00'),
                    discount_reference=description[:255],
                    discount_note=description,
                    billing_period=f"INV-{issue_record.id}"[:20],
                    transaction_id=f"INV-ISSUE-{issue_record.id}"[:255],
                    status="pending",
                    due_date=timezone.now().date()
                )

        return issue_record

    @classmethod
    @transaction.atomic
    def issue_item_bulk(cls, school, academic_year, item, student_ids, quantity_per_student=1,
                        size=None, color=None, user=None):
        """Atomically issue items to multiple students with total stock pre-validation"""
        if quantity_per_student <= 0:
            raise ValidationError("Quantity per student must be greater than zero.")
        if not student_ids:
            raise ValidationError("Select at least one student.")
        student_ids = list(dict.fromkeys(student_ids))
        total_required = len(student_ids) * quantity_per_student
        current_stock = cls.get_item_stock(item.id, size.id if size else None, color.id if color else None)

        if current_stock < total_required:
            raise ValidationError(
                f"Insufficient stock for bulk issue. Available: {current_stock}, Required: {total_required} ({len(student_ids)} students x {quantity_per_student} qty)"
            )

        from .models import Student
        students = list(Student.objects.filter(id__in=student_ids, school=school, is_active=True))
        if len(students) != len(student_ids):
            raise ValidationError("One or more selected students are inactive or belong to another school.")
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
        replacement = ReplacementRequest.objects.select_for_update().get(pk=replacement.pk)
        if replacement.status != 'APPROVED':
            raise ValidationError("Only an approved replacement can be issued.")
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
        if return_obj.quantity <= 0:
            raise ValidationError("Return quantity must be greater than zero.")
        if return_obj.student.school_id != return_obj.school_id or return_obj.item.school_id != return_obj.school_id:
            raise ValidationError("Student and item must belong to the return school.")
        if not return_obj.item.is_returnable:
            raise ValidationError("This item is not configured for returns.")
        if return_obj.size and return_obj.size.school_id != return_obj.school_id:
            raise ValidationError("Selected size does not belong to this school.")
        if return_obj.color and return_obj.color.school_id != return_obj.school_id:
            raise ValidationError("Selected color does not belong to this school.")
        Item.objects.select_for_update().get(pk=return_obj.item_id)
        already_returned = StudentItemReturn.objects.filter(
            school=return_obj.school, student=return_obj.student, item=return_obj.item,
            size=return_obj.size, color=return_obj.color,
        ).exclude(pk=return_obj.pk).aggregate(total=Sum('quantity'))['total'] or 0
        issued = StudentItemIssue.objects.filter(
            school=return_obj.school, student=return_obj.student, item=return_obj.item,
            size=return_obj.size, color=return_obj.color,
        ).aggregate(total=Sum('quantity'))['total'] or 0
        if already_returned + return_obj.quantity > issued:
            raise ValidationError("Return quantity exceeds the student's recorded issued quantity.")
        if return_obj.condition == 'GOOD':
            transaction_record = StockTransaction.objects.create(
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
            cls.log_stock_transaction(transaction_record, user)
        elif return_obj.condition in ['DAMAGED', 'UNUSABLE']:
            transaction_record = StockTransaction.objects.create(
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
            cls.log_stock_transaction(transaction_record, user)
        return return_obj

    @classmethod
    @transaction.atomic
    def process_adjustment(cls, adjustment: StockAdjustment, user=None):
        """Record manual adjustment and create ledger transaction"""
        if adjustment.quantity <= 0:
            raise ValidationError("Adjustment quantity must be greater than zero.")
        if adjustment.item.school_id != adjustment.school_id:
            raise ValidationError("Item must belong to the adjustment school.")
        if adjustment.size and adjustment.size.school_id != adjustment.school_id:
            raise ValidationError("Selected size does not belong to this school.")
        if adjustment.color and adjustment.color.school_id != adjustment.school_id:
            raise ValidationError("Selected color does not belong to this school.")
        if adjustment.item.has_size and not adjustment.size:
            raise ValidationError("Select a size for this item.")
        if adjustment.item.has_color and not adjustment.color:
            raise ValidationError("Select a color for this item.")
        Item.objects.select_for_update().get(pk=adjustment.item_id)
        qty = adjustment.quantity
        if adjustment.adjustment_type in ['ADJUSTMENT_OUT', 'DAMAGE', 'LOST']:
            signed_qty = -abs(qty)
        else:
            signed_qty = abs(qty)

        if signed_qty < 0:
            current_stock = cls.get_item_stock(
                adjustment.item_id,
                adjustment.size_id,
                adjustment.color_id,
            )
            if current_stock < abs(signed_qty):
                raise ValidationError(f"Adjustment would make stock negative. Available: {current_stock}.")

        transaction_record = StockTransaction.objects.create(
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
        cls.log_stock_transaction(transaction_record, user)
        return adjustment
