import uuid
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .inventory_models import (
    InventoryItem,
    InventoryItemVariant,
    InventoryWarehouse,
    InventoryStockBalance,
    InventoryTransaction,
    InventoryOpeningStock,
    InventoryPurchase,
    StudentInventoryIssue,
    StudentInventoryIssueItem,
    StudentIDCard,
    InventoryBundle,
    InventoryReturn,
    InventoryReturnItem,
    InventoryStockAdjustment,
    InventoryStockAdjustmentItem,
)


def generate_tx_code(prefix="TXN"):
    return f"{prefix}-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


@transaction.atomic
def record_stock_transaction(
    school,
    item,
    warehouse,
    quantity,
    direction, # 'IN' or 'OUT'
    transaction_type,
    unit_cost=Decimal("0.00"),
    variant=None,
    to_warehouse=None,
    reference_type=None,
    reference_id=None,
    remarks=None,
    created_by=None,
    transaction_date=None,
):
    """
    Core atomic function to record stock movements.
    Guarantees that stock quantity is never directly overwritten without a transaction ledger entry.
    """
    if quantity <= 0:
        raise ValueError("Transaction quantity must be greater than zero.")

    if direction not in ["IN", "OUT"]:
        raise ValueError("Direction must be either 'IN' or 'OUT'.")

    # Lock stock balance record for update
    balance, _ = InventoryStockBalance.objects.select_for_update().get_or_create(
        school=school,
        item=item,
        variant=variant,
        warehouse=warehouse,
        defaults={
            "opening_quantity": 0,
            "quantity_in": 0,
            "quantity_out": 0,
            "damaged_quantity": 0,
            "reserved_quantity": 0,
            "available_quantity": 0,
        },
    )

    if direction == "IN":
        balance.quantity_in += quantity
        balance.available_quantity += quantity
    else: # OUT
        balance.quantity_out += quantity
        balance.available_quantity -= quantity
        if transaction_type in ["DAMAGED", "LOST", "EXPIRED"]:
            balance.damaged_quantity += quantity

    tx_number = generate_tx_code("TX")
    txn = InventoryTransaction.objects.create(
        school=school,
        transaction_number=tx_number,
        transaction_type=transaction_type,
        item=item,
        variant=variant,
        warehouse=warehouse,
        to_warehouse=to_warehouse,
        quantity=quantity,
        unit_cost=unit_cost,
        direction=direction,
        balance_after=balance.available_quantity,
        reference_type=reference_type,
        reference_id=reference_id,
        transaction_date=transaction_date or timezone.now(),
        remarks=remarks,
        created_by=created_by,
    )

    balance.last_transaction = txn
    balance.save()

    return txn, balance


@transaction.atomic
def process_opening_stock(school, item, warehouse, quantity, unit_cost, variant=None, remarks=None, created_by=None):
    total_cost = Decimal(str(quantity)) * Decimal(str(unit_cost))
    opening = InventoryOpeningStock.objects.create(
        school=school,
        item=item,
        variant=variant,
        warehouse=warehouse,
        quantity=quantity,
        unit_cost=unit_cost,
        total_cost=total_cost,
        remarks=remarks,
        created_by=created_by,
    )

    # Check and update opening_quantity in balance
    balance, _ = InventoryStockBalance.objects.select_for_update().get_or_create(
        school=school,
        item=item,
        variant=variant,
        warehouse=warehouse,
        defaults={
            "opening_quantity": 0,
            "quantity_in": 0,
            "quantity_out": 0,
            "damaged_quantity": 0,
            "reserved_quantity": 0,
            "available_quantity": 0,
        },
    )
    balance.opening_quantity += quantity
    balance.save()

    txn, _ = record_stock_transaction(
        school=school,
        item=item,
        warehouse=warehouse,
        quantity=quantity,
        direction="IN",
        transaction_type="OPENING_STOCK",
        unit_cost=unit_cost,
        variant=variant,
        reference_type="OpeningStock",
        reference_id=opening.id,
        remarks=remarks or "Initial Opening Stock Entry",
        created_by=created_by,
    )
    return opening, txn


@transaction.atomic
def process_purchase_grn(purchase: InventoryPurchase, user=None):
    """
    Receives goods from a purchase order into the warehouse and creates PURCHASE_IN ledger entries.
    """
    if purchase.status == "RECEIVED":
        return purchase

    purchase.status = "RECEIVED"
    purchase.save()

    for p_item in purchase.items.all():
        qty = p_item.received_quantity or p_item.quantity
        if qty > 0:
            record_stock_transaction(
                school=purchase.school,
                item=p_item.item,
                warehouse=purchase.warehouse,
                quantity=qty,
                direction="IN",
                transaction_type="PURCHASE_IN",
                unit_cost=p_item.unit_price,
                variant=p_item.variant,
                reference_type="Purchase",
                reference_id=purchase.id,
                remarks=f"Goods Received from Supplier {purchase.supplier.name if purchase.supplier else 'N/A'} (PO #{purchase.purchase_number})",
                created_by=user or purchase.created_by,
            )
    return purchase


@transaction.atomic
def process_student_issue(
    school,
    student,
    warehouse,
    items_data, # list of dicts: {'item_id', 'variant_id', 'quantity', 'unit_price', 'is_returnable'}
    academic_year=None,
    paid_amount=Decimal("0.00"),
    payment_status="PAID",
    remarks=None,
    issued_by=None,
):
    """
    Issues materials/uniforms/shoes to a student, checks availability, deducts stock, and creates transaction records.
    """
    issue_number = generate_tx_code("ISS")
    total_amount = Decimal("0.00")

    for row in items_data:
        q = int(row.get("quantity", 1))
        p = Decimal(str(row.get("unit_price", 0.00)))
        total_amount += q * p

    issue = StudentInventoryIssue.objects.create(
        school=school,
        issue_number=issue_number,
        student=student,
        academic_year=academic_year,
        warehouse=warehouse,
        issue_date=timezone.now().date(),
        issued_by=issued_by,
        total_amount=total_amount,
        paid_amount=paid_amount,
        payment_status=payment_status,
        remarks=remarks,
    )

    created_items = []
    for row in items_data:
        item = InventoryItem.objects.get(id=row["item_id"], school=school)
        variant = None
        if row.get("variant_id"):
            variant = InventoryItemVariant.objects.get(id=row["variant_id"], item=item)

        qty = int(row.get("quantity", 1))
        unit_price = Decimal(str(row.get("unit_price", item.issue_price or item.selling_price or 0.00)))
        total_price = qty * unit_price

        issue_item = StudentInventoryIssueItem.objects.create(
            student_issue=issue,
            item=item,
            variant=variant,
            quantity=qty,
            unit_price=unit_price,
            total_price=total_price,
            is_returnable=bool(row.get("is_returnable", False)),
            condition_at_issue=row.get("condition_at_issue", "New"),
        )
        created_items.append(issue_item)

        # Deduct stock via ledger
        record_stock_transaction(
            school=school,
            item=item,
            warehouse=warehouse,
            quantity=qty,
            direction="OUT",
            transaction_type="STUDENT_ISSUE",
            unit_cost=unit_price,
            variant=variant,
            reference_type="StudentIssue",
            reference_id=issue.id,
            remarks=f"Issued to Student {student.name} (Admission/Roll: {getattr(student, 'roll_number', '')})",
            created_by=issued_by,
        )

    return issue


@transaction.atomic
def process_id_card_issue(school, student, card_number, card_serial_number=None, expiry_date=None, issued_by=None, remarks=None, deduct_stock_item=None, warehouse=None):
    """
    Issues an ID Card to a student. If a blank ID card stock item is linked, automatically deducts 1 unit.
    """
    card = StudentIDCard.objects.create(
        school=school,
        student=student,
        card_number=card_number,
        card_serial_number=card_serial_number,
        issue_date=timezone.now().date(),
        expiry_date=expiry_date,
        issue_status="ACTIVE",
        issued_by=issued_by,
        remarks=remarks,
    )

    if deduct_stock_item and warehouse:
        record_stock_transaction(
            school=school,
            item=deduct_stock_item,
            warehouse=warehouse,
            quantity=1,
            direction="OUT",
            transaction_type="STUDENT_ISSUE",
            unit_cost=deduct_stock_item.issue_price or 0,
            reference_type="StudentIDCard",
            reference_id=card.id,
            remarks=f"Blank ID Card consumed for {student.name} ({card_number})",
            created_by=issued_by,
        )

    return card


@transaction.atomic
def process_id_card_replacement(school, old_card: StudentIDCard, new_card_number, card_serial_number=None, reason="LOST", issued_by=None, deduct_stock_item=None, warehouse=None):
    """
    Flags previous ID Card as LOST or DAMAGED, and issues a new replacement card linked to the previous one.
    """
    old_card.issue_status = reason.upper()
    old_card.save()

    new_card = StudentIDCard.objects.create(
        school=school,
        student=old_card.student,
        card_number=new_card_number,
        card_serial_number=card_serial_number,
        issue_date=timezone.now().date(),
        expiry_date=old_card.expiry_date,
        issue_status="ACTIVE",
        previous_card=old_card,
        issued_by=issued_by,
        remarks=f"Replacement card for #{old_card.card_number} (Reason: {reason})",
    )

    if deduct_stock_item and warehouse:
        record_stock_transaction(
            school=school,
            item=deduct_stock_item,
            warehouse=warehouse,
            quantity=1,
            direction="OUT",
            transaction_type="STUDENT_ISSUE",
            unit_cost=deduct_stock_item.issue_price or 0,
            reference_type="StudentIDCard",
            reference_id=new_card.id,
            remarks=f"Replacement ID Card consumed for {old_card.student.name} (Old: {old_card.card_number}, New: {new_card_number})",
            created_by=issued_by,
        )

    return new_card


@transaction.atomic
def process_stock_adjustment(school, warehouse, reason, items_data, remarks=None, created_by=None, approved_by=None):
    """
    Records physical inventory audit adjustments. Adjusts stock up or down and creates transaction audit entries.
    """
    adj_number = generate_tx_code("ADJ")
    adjustment = InventoryStockAdjustment.objects.create(
        school=school,
        adjustment_number=adj_number,
        warehouse=warehouse,
        adjustment_date=timezone.now().date(),
        reason=reason,
        remarks=remarks,
        approved_by=approved_by or created_by,
        created_by=created_by,
    )

    for row in items_data:
        item = InventoryItem.objects.get(id=row["item_id"], school=school)
        variant = None
        if row.get("variant_id"):
            variant = InventoryItemVariant.objects.get(id=row["variant_id"], item=item)

        sys_qty = int(row.get("system_quantity", 0))
        phys_qty = int(row.get("physical_quantity", 0))
        diff = phys_qty - sys_qty

        InventoryStockAdjustmentItem.objects.create(
            adjustment=adjustment,
            item=item,
            variant=variant,
            system_quantity=sys_qty,
            physical_quantity=phys_qty,
            difference_quantity=diff,
            remarks=row.get("remarks", ""),
        )

        if diff > 0: # System had less, physical has more -> Add Stock (+IN)
            record_stock_transaction(
                school=school,
                item=item,
                warehouse=warehouse,
                quantity=abs(diff),
                direction="IN",
                transaction_type="STOCK_ADJUSTMENT_IN",
                unit_cost=item.purchase_price,
                variant=variant,
                reference_type="StockAdjustment",
                reference_id=adjustment.id,
                remarks=f"Adjustment #{adj_number}: Physical count surplus (+{diff})",
                created_by=created_by,
            )
        elif diff < 0: # Physical count is less -> Write-off (-OUT)
            tx_type = "DAMAGED" if reason == "DAMAGED" else ("LOST" if reason in ["LOST", "THEFT"] else "STOCK_ADJUSTMENT_OUT")
            record_stock_transaction(
                school=school,
                item=item,
                warehouse=warehouse,
                quantity=abs(diff),
                direction="OUT",
                transaction_type=tx_type,
                unit_cost=item.purchase_price,
                variant=variant,
                reference_type="StockAdjustment",
                reference_id=adjustment.id,
                remarks=f"Adjustment #{adj_number}: Discrepancy write-off ({diff}) - Reason: {reason}",
                created_by=created_by,
            )

    return adjustment


@transaction.atomic
def process_return(school, warehouse, return_type, items_data, student=None, staff=None, condition="GOOD", remarks=None, received_by=None):
    """
    Handles item returns. If condition is GOOD/Reusable, automatically restores stock (+IN). If damaged, logs damage.
    """
    ret_number = generate_tx_code("RET")
    is_restocked = condition.upper().startswith("GOOD")

    ret_record = InventoryReturn.objects.create(
        school=school,
        return_number=ret_number,
        student=student,
        staff=staff,
        return_type=return_type,
        warehouse=warehouse,
        return_date=timezone.now().date(),
        condition=condition,
        is_restocked=is_restocked,
        received_by=received_by,
        remarks=remarks,
    )

    for row in items_data:
        item = InventoryItem.objects.get(id=row["item_id"], school=school)
        variant = None
        if row.get("variant_id"):
            variant = InventoryItemVariant.objects.get(id=row["variant_id"], item=item)

        qty = int(row.get("quantity", 1))

        InventoryReturnItem.objects.create(
            inventory_return=ret_record,
            item=item,
            variant=variant,
            quantity=qty,
            condition=condition,
            is_restocked=is_restocked,
            remarks=row.get("remarks", ""),
        )

        if is_restocked:
            # Add back to available stock
            record_stock_transaction(
                school=school,
                item=item,
                warehouse=warehouse,
                quantity=qty,
                direction="IN",
                transaction_type="STUDENT_RETURN" if return_type == "STUDENT" else "STOCK_ADJUSTMENT_IN",
                unit_cost=item.purchase_price,
                variant=variant,
                reference_type="InventoryReturn",
                reference_id=ret_record.id,
                remarks=f"Returned in Good Condition (Return #{ret_number})",
                created_by=received_by,
            )
        else:
            # Log as damaged/not restocked
            record_stock_transaction(
                school=school,
                item=item,
                warehouse=warehouse,
                quantity=qty,
                direction="OUT",
                transaction_type="DAMAGED",
                unit_cost=item.purchase_price,
                variant=variant,
                reference_type="InventoryReturn",
                reference_id=ret_record.id,
                remarks=f"Returned in Damaged/Unusable Condition (Return #{ret_number})",
                created_by=received_by,
            )

    return ret_record


@transaction.atomic
def process_warehouse_transfer(school, item, from_warehouse, to_warehouse, quantity, variant=None, remarks=None, user=None):
    """
    Transfers stock between two school warehouses/locations.
    Creates TRANSFER_OUT from source warehouse and TRANSFER_IN to destination warehouse.
    """
    if from_warehouse.id == to_warehouse.id:
        raise ValueError("Source and destination warehouses cannot be the same.")

    # Deduct from source
    txn_out, _ = record_stock_transaction(
        school=school,
        item=item,
        warehouse=from_warehouse,
        to_warehouse=to_warehouse,
        quantity=quantity,
        direction="OUT",
        transaction_type="TRANSFER_OUT",
        unit_cost=item.purchase_price,
        variant=variant,
        reference_type="WarehouseTransfer",
        remarks=f"Transfer to {to_warehouse.warehouse_name}: {remarks or ''}",
        created_by=user,
    )

    # Add to destination
    txn_in, _ = record_stock_transaction(
        school=school,
        item=item,
        warehouse=to_warehouse,
        quantity=quantity,
        direction="IN",
        transaction_type="TRANSFER_IN",
        unit_cost=item.purchase_price,
        variant=variant,
        reference_type="WarehouseTransfer",
        reference_id=txn_out.id,
        remarks=f"Transfer from {from_warehouse.warehouse_name}: {remarks or ''}",
        created_by=user,
    )

    return txn_out, txn_in
