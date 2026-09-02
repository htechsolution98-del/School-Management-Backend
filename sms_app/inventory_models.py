from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import uuid


class InventoryCategory(models.Model):
    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_categories')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_categories'
        ordering = ['name']
        unique_together = ('school', 'name')

    def __str__(self):
        return self.name


class InventorySubCategory(models.Model):
    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_subcategories')
    category = models.ForeignKey(InventoryCategory, on_delete=models.CASCADE, related_name='subcategories')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_sub_categories'
        ordering = ['name']
        unique_together = ('category', 'name')

    def __str__(self):
        return f"{self.category.name} - {self.name}"


class InventoryUnit(models.Model):
    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_units')
    name = models.CharField(max_length=50) # e.g. Pieces, Pair, Box, Kg, Meter, Ream
    symbol = models.CharField(max_length=20) # e.g. PCS, PR, BOX, KG, M, RM
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'inventory_units'
        unique_together = ('school', 'name')

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class InventoryItem(models.Model):
    ITEM_TYPE_CHOICES = [
        ('CONSUMABLE', 'Consumable'),
        ('STUDENT_ITEM', 'Student Item (Uniform, Shoes, etc.)'),
        ('ASSET', 'Asset'),
        ('LIBRARY', 'Library Item'),
        ('LABORATORY', 'Laboratory Item'),
        ('SPORTS', 'Sports Item'),
        ('MAINTENANCE', 'Maintenance Item'),
        ('CLEANING', 'Cleaning Material'),
        ('STATIONERY', 'Stationery'),
        ('OTHER', 'Other'),
    ]

    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_items')
    item_code = models.CharField(max_length=50)
    item_name = models.CharField(max_length=200)
    category = models.ForeignKey(InventoryCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='items')
    sub_category = models.ForeignKey(InventorySubCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='items')
    item_type = models.CharField(max_length=50, choices=ITEM_TYPE_CHOICES, default='CONSUMABLE')
    description = models.TextField(blank=True, null=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    model_number = models.CharField(max_length=100, blank=True, null=True)
    sku = models.CharField(max_length=100, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    unit = models.CharField(max_length=50, default='PCS')

    track_individual = models.BooleanField(default=False)
    track_size = models.BooleanField(default=False)
    track_color = models.BooleanField(default=False)

    minimum_stock = models.PositiveIntegerField(default=10)
    reorder_level = models.PositiveIntegerField(default=20)
    maximum_stock = models.PositiveIntegerField(default=500)

    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    issue_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    gst_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_items'
        ordering = ['item_name']
        unique_together = ('school', 'item_code')

    def __str__(self):
        return f"{self.item_name} ({self.item_code})"

    @property
    def total_stock(self):
        return self.stock_balances.aggregate(total=models.Sum('available_quantity'))['total'] or 0


class InventoryItemVariant(models.Model):
    GENDER_CHOICES = [
        ('BOYS', 'Boys'),
        ('GIRLS', 'Girls'),
        ('UNISEX', 'Unisex'),
    ]

    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='variants')
    variant_code = models.CharField(max_length=100)
    size = models.CharField(max_length=50, blank=True, null=True) # e.g. 28, 30, 32, 6, 7, S, M, L
    color = models.CharField(max_length=50, blank=True, null=True) # e.g. White, Navy Blue
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, default='UNISEX')
    applicable_class = models.ForeignKey('sms_app.SchoolClass', on_delete=models.SET_NULL, null=True, blank=True)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    issue_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    minimum_stock = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'inventory_item_variants'
        unique_together = ('item', 'variant_code')

    def __str__(self):
        details = []
        if self.size:
            details.append(f"Size: {self.size}")
        if self.color:
            details.append(f"Color: {self.color}")
        if self.gender:
            details.append(f"Gender: {self.gender}")
        suffix = f" ({', '.join(details)})" if details else ""
        return f"{self.item.item_name}{suffix}"

    @property
    def total_stock(self):
        return self.stock_balances.aggregate(total=models.Sum('available_quantity'))['total'] or 0


class InventoryWarehouse(models.Model):
    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_warehouses')
    warehouse_code = models.CharField(max_length=50)
    warehouse_name = models.CharField(max_length=100)
    location = models.CharField(max_length=200, blank=True, null=True)
    incharge_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_warehouses')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_warehouses'
        unique_together = ('school', 'warehouse_code')

    def __str__(self):
        return f"{self.warehouse_name} ({self.warehouse_code})"


class InventorySupplier(models.Model):
    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_suppliers')
    name = models.CharField(max_length=150)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    gst_number = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_suppliers'
        ordering = ['name']

    def __str__(self):
        return self.name


class InventoryPurchase(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PARTIAL', 'Partial'),
        ('PAID', 'Paid'),
    ]

    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_purchases')
    purchase_number = models.CharField(max_length=100, unique=True)
    supplier = models.ForeignKey(InventorySupplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchases')
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    invoice_date = models.DateField(null=True, blank=True)
    purchase_date = models.DateField(default=timezone.now)
    warehouse = models.ForeignKey(InventoryWarehouse, on_delete=models.CASCADE, related_name='purchases')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    status = models.CharField(max_length=20, choices=[('ORDERED', 'Ordered'), ('RECEIVED', 'Received'), ('CANCELLED', 'Cancelled')], default='RECEIVED')
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_purchase'
        ordering = ['-purchase_date', '-id']

    def __str__(self):
        return f"PO #{self.purchase_number} - {self.total_amount}"


class InventoryPurchaseItem(models.Model):
    purchase = models.ForeignKey(InventoryPurchase, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    variant = models.ForeignKey(InventoryItemVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    received_quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    expiry_date = models.DateField(blank=True, null=True)

    class Meta:
        db_table = 'inventory_purchase_items'


class PurchaseRequest(models.Model):
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('FULFILLED', 'Fulfilled'),
    ]

    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='purchase_requests')
    request_number = models.CharField(max_length=100, unique=True)
    requested_by = models.ForeignKey('sms_app.Staff', on_delete=models.SET_NULL, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    request_date = models.DateField(default=timezone.now)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='MEDIUM')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'purchase_requests'
        ordering = ['-request_date', '-id']

    def __str__(self):
        return f"PR #{self.request_number} ({self.status})"


class PurchaseRequestItem(models.Model):
    purchase_request = models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    variant = models.ForeignKey(InventoryItemVariant, on_delete=models.SET_NULL, null=True, blank=True)
    requested_quantity = models.PositiveIntegerField(default=1)
    approved_quantity = models.PositiveIntegerField(default=0)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'purchase_request_items'


class InventoryOpeningStock(models.Model):
    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_opening_stocks')
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='opening_stocks')
    variant = models.ForeignKey(InventoryItemVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name='opening_stocks')
    warehouse = models.ForeignKey(InventoryWarehouse, on_delete=models.CASCADE, related_name='opening_stocks')
    quantity = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    opening_date = models.DateField(default=timezone.now)
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_opening_stock'


class InventoryTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('OPENING_STOCK', 'Opening Stock Entry'),
        ('PURCHASE_IN', 'Stock Purchase Receipt'),
        ('STOCK_ADJUSTMENT_IN', 'Stock Adjustment (+IN)'),
        ('STOCK_ADJUSTMENT_OUT', 'Stock Adjustment (-OUT)'),
        ('STUDENT_ISSUE', 'Issued to Student'),
        ('STUDENT_RETURN', 'Returned by Student'),
        ('STAFF_ISSUE', 'Issued to Staff'),
        ('DEPARTMENT_ISSUE', 'Issued to Department'),
        ('TRANSFER_OUT', 'Warehouse Transfer (Out)'),
        ('TRANSFER_IN', 'Warehouse Transfer (In)'),
        ('DAMAGED', 'Damaged Stock'),
        ('LOST', 'Lost Stock'),
        ('EXPIRED', 'Expired Stock'),
        ('RETURN_TO_SUPPLIER', 'Returned to Supplier'),
        ('MAINTENANCE_OUT', 'Sent for Maintenance'),
        ('MAINTENANCE_RETURN', 'Returned from Maintenance'),
    ]

    DIRECTION_CHOICES = [
        ('IN', 'IN (+)'),
        ('OUT', 'OUT (-)'),
    ]

    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_transactions')
    transaction_number = models.CharField(max_length=100, unique=True)
    transaction_type = models.CharField(max_length=50, choices=TRANSACTION_TYPE_CHOICES)
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='transactions')
    variant = models.ForeignKey(InventoryItemVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    warehouse = models.ForeignKey(InventoryWarehouse, on_delete=models.CASCADE, related_name='transactions_source')
    to_warehouse = models.ForeignKey(InventoryWarehouse, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions_dest')
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    balance_after = models.IntegerField(default=0)
    reference_type = models.CharField(max_length=50, blank=True, null=True) # e.g. Student, Purchase, Adjustment, Return
    reference_id = models.PositiveIntegerField(blank=True, null=True)
    transaction_date = models.DateTimeField(default=timezone.now)
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_transactions'
        ordering = ['-transaction_date', '-id']

    def __str__(self):
        return f"{self.transaction_number} | {self.transaction_type} | {self.direction} {self.quantity}"


class InventoryStockBalance(models.Model):
    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='stock_balances')
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='stock_balances')
    variant = models.ForeignKey(InventoryItemVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_balances')
    warehouse = models.ForeignKey(InventoryWarehouse, on_delete=models.CASCADE, related_name='stock_balances')
    opening_quantity = models.PositiveIntegerField(default=0)
    quantity_in = models.PositiveIntegerField(default=0)
    quantity_out = models.PositiveIntegerField(default=0)
    damaged_quantity = models.PositiveIntegerField(default=0)
    reserved_quantity = models.PositiveIntegerField(default=0)
    available_quantity = models.IntegerField(default=0)
    last_transaction = models.ForeignKey(InventoryTransaction, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_stock_balance'
        unique_together = ('item', 'variant', 'warehouse')

    def __str__(self):
        var_txt = f" - {self.variant.variant_code}" if self.variant else ""
        return f"{self.item.item_name}{var_txt} @ {self.warehouse.warehouse_name}: {self.available_quantity}"


class StudentInventoryIssue(models.Model):
    PAYMENT_STATUS = [
        ('PAID', 'Paid'),
        ('PENDING', 'Pending'),
        ('FREE', 'Free / Included'),
    ]

    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='student_inventory_issues')
    issue_number = models.CharField(max_length=100, unique=True)
    student = models.ForeignKey('sms_app.Student', on_delete=models.CASCADE, related_name='inventory_issues')
    academic_year = models.ForeignKey('sms_app.AcademicYear', on_delete=models.SET_NULL, null=True, blank=True)
    warehouse = models.ForeignKey(InventoryWarehouse, on_delete=models.CASCADE, default=1)
    issue_date = models.DateField(default=timezone.now)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='PAID')
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'student_inventory_issues'
        ordering = ['-issue_date', '-id']

    def __str__(self):
        return f"Issue #{self.issue_number} to {self.student.name}"


class StudentInventoryIssueItem(models.Model):
    student_issue = models.ForeignKey(StudentInventoryIssue, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    variant = models.ForeignKey(InventoryItemVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_returnable = models.BooleanField(default=False)
    condition_at_issue = models.CharField(max_length=50, default='New')
    returned_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'student_inventory_issue_items'


class StudentIDCard(models.Model):
    CARD_STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('LOST', 'Lost'),
        ('DAMAGED', 'Damaged'),
        ('REPLACED', 'Replaced'),
    ]

    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='student_id_cards')
    student = models.ForeignKey('sms_app.Student', on_delete=models.CASCADE, related_name='id_cards')
    card_number = models.CharField(max_length=100, unique=True)
    card_serial_number = models.CharField(max_length=100, blank=True, null=True)
    issue_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
    issue_status = models.CharField(max_length=20, choices=CARD_STATUS_CHOICES, default='ACTIVE')
    previous_card = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='replacement_cards')
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'student_id_cards'
        ordering = ['-issue_date', '-id']

    def __str__(self):
        return f"ID Card: {self.card_number} - {self.student.name} ({self.issue_status})"


class InventoryBundle(models.Model):
    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_bundles')
    bundle_code = models.CharField(max_length=100)
    bundle_name = models.CharField(max_length=200) # e.g. Grade 1-5 Complete Uniform Kit
    description = models.TextField(blank=True, null=True)
    applicable_class = models.ForeignKey('sms_app.SchoolClass', on_delete=models.SET_NULL, null=True, blank=True)
    applicable_gender = models.CharField(max_length=20, choices=[('BOYS', 'Boys'), ('GIRLS', 'Girls'), ('UNISEX', 'Unisex')], default='UNISEX')
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_bundles'
        unique_together = ('school', 'bundle_code')

    def __str__(self):
        return f"{self.bundle_name} ({self.bundle_code})"


class InventoryBundleItem(models.Model):
    bundle = models.ForeignKey(InventoryBundle, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    variant = models.ForeignKey(InventoryItemVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'inventory_bundle_items'


class InventoryReturn(models.Model):
    RETURN_TYPE_CHOICES = [
        ('STUDENT', 'Student Return'),
        ('STAFF', 'Staff Return'),
        ('SUPPLIER', 'Return to Supplier'),
    ]
    CONDITION_CHOICES = [
        ('GOOD', 'Good / Reusable (Restock +1)'),
        ('DAMAGED', 'Damaged / Not Reusable'),
        ('SCRAP', 'Scrap / Disposed'),
    ]

    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_returns')
    return_number = models.CharField(max_length=100, unique=True)
    student = models.ForeignKey('sms_app.Student', on_delete=models.SET_NULL, null=True, blank=True)
    staff = models.ForeignKey('sms_app.Staff', on_delete=models.SET_NULL, null=True, blank=True)
    return_type = models.CharField(max_length=20, choices=RETURN_TYPE_CHOICES, default='STUDENT')
    warehouse = models.ForeignKey(InventoryWarehouse, on_delete=models.CASCADE)
    return_date = models.DateField(default=timezone.now)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='GOOD')
    is_restocked = models.BooleanField(default=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_returns'
        ordering = ['-return_date', '-id']

    def __str__(self):
        return f"Return #{self.return_number} ({self.condition})"


class InventoryReturnItem(models.Model):
    inventory_return = models.ForeignKey(InventoryReturn, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    variant = models.ForeignKey(InventoryItemVariant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    condition = models.CharField(max_length=50, default='GOOD')
    is_restocked = models.BooleanField(default=True)
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'inventory_return_items'


class InventoryStockAdjustment(models.Model):
    REASON_CHOICES = [
        ('PHYSICAL_COUNT', 'Physical Count Discrepancy'),
        ('DAMAGED', 'Damaged Items Write-off'),
        ('LOST', 'Lost Items Write-off'),
        ('THEFT', 'Theft / Missing Items'),
        ('EXPIRED', 'Expired Materials'),
        ('DATA_CORRECTION', 'Data Entry Correction'),
        ('OTHER', 'Other Reason'),
    ]

    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_adjustments')
    adjustment_number = models.CharField(max_length=100, unique=True)
    warehouse = models.ForeignKey(InventoryWarehouse, on_delete=models.CASCADE)
    adjustment_date = models.DateField(default=timezone.now)
    reason = models.CharField(max_length=50, choices=REASON_CHOICES, default='PHYSICAL_COUNT')
    remarks = models.TextField(blank=True, null=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_adjustments')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_adjustments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_stock_adjustments'
        ordering = ['-adjustment_date', '-id']

    def __str__(self):
        return f"Adj #{self.adjustment_number} ({self.reason})"


class InventoryStockAdjustmentItem(models.Model):
    adjustment = models.ForeignKey(InventoryStockAdjustment, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    variant = models.ForeignKey(InventoryItemVariant, on_delete=models.SET_NULL, null=True, blank=True)
    system_quantity = models.PositiveIntegerField(default=0)
    physical_quantity = models.PositiveIntegerField(default=0)
    difference_quantity = models.IntegerField(default=0) # positive if gain (+IN), negative if loss (-OUT)
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'inventory_stock_adjustment_items'


class InventoryBudget(models.Model):
    school = models.ForeignKey('sms_app.School', on_delete=models.CASCADE, related_name='inventory_budgets')
    academic_year = models.ForeignKey('sms_app.AcademicYear', on_delete=models.SET_NULL, null=True, blank=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    category = models.ForeignKey(InventoryCategory, on_delete=models.SET_NULL, null=True, blank=True)
    allocated_budget = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    utilized_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_budgets'

    def __str__(self):
        return f"Budget: {self.department or 'General'} - {self.allocated_budget}"
