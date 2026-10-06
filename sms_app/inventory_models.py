from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal

# Import existing related core models
from .models import School, AcademicYear, SchoolClass, Student, FeeType

class ItemCategory(models.Model):
    """Category master for grouping inventory items (e.g. Uniform, Footwear, Stationery)"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="inventory_categories")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_item_category"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_school_item_category")
        ]

    def __str__(self):
        return self.name


class ItemSize(models.Model):
    """Size master for variant items (e.g. S, M, L, XL, UK 4, UK 5, etc.)"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="inventory_sizes")
    name = models.CharField(max_length=50)
    size_type = models.CharField(max_length=50, blank=True, null=True, default="General")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_item_size"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name", "size_type"], name="unique_school_size_variant")
        ]

    def __str__(self):
        return f"{self.name} ({self.size_type})" if self.size_type else self.name


class ItemColor(models.Model):
    """Color master for variant items (e.g. White, Navy Blue, Maroon)"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="inventory_colors")
    name = models.CharField(max_length=50)
    hex_code = models.CharField(max_length=10, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_item_color"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_school_color")
        ]

    def __str__(self):
        return self.name


class Item(models.Model):
    """Item Master representing physical articles (Uniform, Tie, Shoes, Notebooks)"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="inventory_items")
    item_code = models.CharField(max_length=100)
    item_name = models.CharField(max_length=200)
    category = models.ForeignKey(ItemCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="items")
    description = models.TextField(blank=True, null=True)
    unit = models.CharField(max_length=50, default="Pcs")  # Pcs, Pair, Set, Box, Meter
    has_size = models.BooleanField(default=False)
    has_color = models.BooleanField(default=False)
    is_returnable = models.BooleanField(default=False)
    minimum_stock_level = models.IntegerField(default=5)
    maximum_stock_level = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_inventory_items")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="updated_inventory_items")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_item"
        ordering = ["item_name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "item_code"], name="unique_school_item_code")
        ]

    def __str__(self):
        return f"{self.item_name} ({self.item_code})"


class ItemPricing(models.Model):
    """Academic-year & class-wise historical pricing & fee integration mapping"""
    CHARGING_TYPE_CHOICES = [
        ("INCLUDED_IN_FEE", "Included In Fee"),
        ("SEPARATE_CHARGE", "Separate Charge"),
        ("FREE", "Free"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="inventory_pricings")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="pricings")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="inventory_pricings")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.SET_NULL, null=True, blank=True, related_name="inventory_pricings")
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    charging_type = models.CharField(max_length=30, choices=CHARGING_TYPE_CHOICES, default="SEPARATE_CHARGE")
    included_fee_type = models.ForeignKey(FeeType, on_delete=models.SET_NULL, null=True, blank=True, related_name="included_inventory_items")
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_item_pricing"
        ordering = ["-academic_year__id", "item__item_name"]

    def __str__(self):
        return f"{self.item.item_name} - {self.academic_year.name} ({self.charging_type})"


class Supplier(models.Model):
    """Vendors / Suppliers providing inventory items to the school"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="inventory_suppliers")
    supplier_name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=150, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    gst_number = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_supplier"
        ordering = ["supplier_name"]

    def __str__(self):
        return self.supplier_name


class Purchase(models.Model):
    """Purchase invoice / PO record from supplier"""
    PAYMENT_STATUS_CHOICES = [
        ("PAID", "Paid"),
        ("PARTIALLY_PAID", "Partially Paid"),
        ("UNPAID", "Unpaid"),
    ]
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("CONFIRMED", "Confirmed"),
        ("CANCELLED", "Cancelled"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="inventory_purchases")
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchases")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="inventory_purchases")
    invoice_number = models.CharField(max_length=100)
    purchase_date = models.DateField(default=timezone.now)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default="UNPAID")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="CONFIRMED")
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_purchase"
        ordering = ["-purchase_date", "-id"]

    def __str__(self):
        return f"PO #{self.invoice_number} - {self.supplier.supplier_name if self.supplier else 'N/A'}"


class PurchaseItem(models.Model):
    """Line items for a purchase invoice"""
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="purchase_items")
    size = models.ForeignKey(ItemSize, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.ForeignKey(ItemColor, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "inventory_purchase_item"

    def __str__(self):
        return f"{self.item.item_name} x {self.quantity}"


class StockTransaction(models.Model):
    """Atomic Stock ledger recording all physical inflows and outflows"""
    TRANSACTION_TYPE_CHOICES = [
        ("OPENING", "Opening Stock"),
        ("PURCHASE", "Purchase"),
        ("ISSUE", "Student Issue"),
        ("RETURN", "Student Return"),
        ("ADJUSTMENT_IN", "Adjustment In"),
        ("ADJUSTMENT_OUT", "Adjustment Out"),
        ("DAMAGE", "Damaged Stock"),
        ("LOST", "Lost Stock"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="stock_transactions")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="stock_transactions")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, null=True, blank=True, related_name="stock_transactions")
    size = models.ForeignKey(ItemSize, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.ForeignKey(ItemColor, on_delete=models.SET_NULL, null=True, blank=True)
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPE_CHOICES)
    quantity = models.IntegerField()  # Inflow is positive, Outflow is negative
    unit_purchase_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    unit_selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    reference_type = models.CharField(max_length=50, blank=True, null=True)
    reference_id = models.CharField(max_length=100, blank=True, null=True)
    transaction_date = models.DateField(default=timezone.now)
    remarks = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_stock_transaction"
        ordering = ["-transaction_date", "-id"]
        indexes = [
            models.Index(fields=["school", "item"]),
            models.Index(fields=["school", "transaction_date"]),
            models.Index(fields=["transaction_type"]),
        ]

    def __str__(self):
        return f"{self.transaction_type}: {self.item.item_name} ({self.quantity})"


class StudentItemEntitlement(models.Model):
    """Rules defining what items each student is eligible to receive for an academic year"""
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("PARTIALLY_ISSUED", "Partially Issued"),
        ("FULLY_ISSUED", "Fully Issued"),
        ("CANCELLED", "Cancelled"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="student_entitlements")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="student_entitlements")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="item_entitlements")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="student_entitlements")
    size = models.ForeignKey(ItemSize, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.ForeignKey(ItemColor, on_delete=models.SET_NULL, null=True, blank=True)
    entitled_quantity = models.IntegerField(default=1)
    issued_quantity = models.IntegerField(default=0)
    charging_type = models.CharField(max_length=30, choices=ItemPricing.CHARGING_TYPE_CHOICES, default="INCLUDED_IN_FEE")
    fee_type = models.ForeignKey(FeeType, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_student_entitlement"
        ordering = ["student__surname", "item__item_name"]

    @property
    def remaining_quantity(self):
        return max(0, self.entitled_quantity - self.issued_quantity)

    def __str__(self):
        return f"{self.student} - {self.item.item_name} ({self.issued_quantity}/{self.entitled_quantity})"


class StudentItemIssue(models.Model):
    """Actual physical handover of items to students with price snapshotting"""
    ISSUE_REASON_CHOICES = [
        ("INITIAL_ISSUE", "Initial Issue"),
        ("REPLACEMENT", "Replacement"),
        ("ADDITIONAL", "Additional"),
        ("SPECIAL_CASE", "Special Case"),
        ("OTHER", "Other"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="student_item_issues")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="student_item_issues")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="item_issues")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="item_issues")
    size = models.ForeignKey(ItemSize, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.ForeignKey(ItemColor, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    unit_purchase_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    unit_selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    charging_type = models.CharField(max_length=30, choices=ItemPricing.CHARGING_TYPE_CHOICES, default="SEPARATE_CHARGE")
    charged_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    issue_date = models.DateField(default=timezone.now)
    issue_reason = models.CharField(max_length=30, choices=ISSUE_REASON_CHOICES, default="INITIAL_ISSUE")
    remarks = models.TextField(blank=True, null=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_student_issue"
        ordering = ["-issue_date", "-id"]

    def __str__(self):
        return f"{self.student} - {self.item.item_name} x {self.quantity}"


class ReplacementRequest(models.Model):
    """Student/parent request for exchanging or replacing an item"""
    REASON_CHOICES = [
        ("DAMAGED", "Damaged"),
        ("LOST", "Lost"),
        ("WRONG_SIZE", "Wrong Size"),
        ("DEFECTIVE", "Defective"),
        ("WORN_OUT", "Worn Out"),
        ("OTHER", "Other"),
    ]
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("ISSUED", "Issued"),
        ("CANCELLED", "Cancelled"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="replacement_requests")
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name="replacement_requests")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="replacement_requests")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="replacement_requests")
    current_size = models.ForeignKey(ItemSize, on_delete=models.SET_NULL, null=True, blank=True, related_name="current_replacement_requests")
    requested_size = models.ForeignKey(ItemSize, on_delete=models.SET_NULL, null=True, blank=True, related_name="requested_replacement_requests")
    current_color = models.ForeignKey(ItemColor, on_delete=models.SET_NULL, null=True, blank=True, related_name="current_replacement_requests")
    requested_color = models.ForeignKey(ItemColor, on_delete=models.SET_NULL, null=True, blank=True, related_name="requested_replacement_requests")
    quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="PENDING")
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_replacements")
    admin_remarks = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "inventory_replacement_request"
        ordering = ["-requested_at"]

    def __str__(self):
        return f"Replacement #{self.id}: {self.student} - {self.item.item_name} ({self.status})"


class StudentItemReturn(models.Model):
    """Return of issued returnable items (blazers, sports gear, etc.)"""
    CONDITION_CHOICES = [
        ("GOOD", "Good (Restockable)"),
        ("DAMAGED", "Damaged"),
        ("UNUSABLE", "Unusable"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="student_item_returns")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="item_returns")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="item_returns")
    size = models.ForeignKey(ItemSize, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.ForeignKey(ItemColor, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    return_date = models.DateField(default=timezone.now)
    condition = models.CharField(max_length=30, choices=CONDITION_CHOICES, default="GOOD")
    reason = models.TextField(blank=True, null=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_student_return"
        ordering = ["-return_date", "-id"]

    def __str__(self):
        return f"Return: {self.student} - {self.item.item_name} ({self.condition})"


class StockAdjustment(models.Model):
    """Manual adjustment / inventory reconciliation records"""
    ADJUSTMENT_TYPE_CHOICES = [
        ("ADJUSTMENT_IN", "Adjustment In (+)"),
        ("ADJUSTMENT_OUT", "Adjustment Out (-)"),
        ("DAMAGE", "Damage (-)"),
        ("LOST", "Lost (-)"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="stock_adjustments")
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="stock_adjustments")
    size = models.ForeignKey(ItemSize, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.ForeignKey(ItemColor, on_delete=models.SET_NULL, null=True, blank=True)
    adjustment_type = models.CharField(max_length=30, choices=ADJUSTMENT_TYPE_CHOICES)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    reason = models.CharField(max_length=255)
    remarks = models.TextField(blank=True, null=True)
    adjustment_date = models.DateField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_stock_adjustment"
        ordering = ["-adjustment_date", "-id"]

    def __str__(self):
        return f"{self.adjustment_type}: {self.item.item_name} ({self.quantity})"


class InventoryAuditLog(models.Model):
    """Audit trail for inventory entity mutations"""
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="inventory_audit_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50)
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=100)
    old_values = models.JSONField(blank=True, null=True)
    new_values = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_audit_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Audit: {self.action} on {self.entity_type} #{self.entity_id}"
