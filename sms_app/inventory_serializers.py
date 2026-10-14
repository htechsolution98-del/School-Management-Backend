from rest_framework import serializers
from decimal import Decimal
import re
from .inventory_models import (
    ItemCategory, ItemSize, ItemColor, Item, ItemPricing,
    Supplier, Purchase, PurchaseItem, StockTransaction,
    StudentItemEntitlement, StudentItemIssue, ReplacementRequest,
    StudentItemReturn, StockAdjustment, InventoryAuditLog
)
from .models import School, AcademicYear, SchoolClass, Student, FeeType
from django.db.models import Sum
from django.db import transaction
from rest_framework.exceptions import ValidationError


class ItemCategorySerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = ItemCategory
        fields = ['id', 'school', 'name', 'description', 'is_active', 'items_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'school', 'created_at', 'updated_at']

    def get_items_count(self, obj):
        return obj.items.filter(is_active=True).count()


class ItemSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemSize
        fields = ['id', 'school', 'name', 'size_type', 'is_active', 'created_at']
        read_only_fields = ['id', 'school', 'created_at']


class ItemColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemColor
        fields = ['id', 'school', 'name', 'hex_code', 'is_active', 'created_at']
        read_only_fields = ['id', 'school', 'created_at']


class ItemPricingSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    school_class_name = serializers.CharField(source='school_class.school_class', read_only=True)
    included_fee_type_name = serializers.CharField(source='included_fee_type.name', read_only=True)
    item_name = serializers.CharField(source='item.item_name', read_only=True)

    class Meta:
        model = ItemPricing
        fields = [
            'id', 'school', 'item', 'item_name', 'academic_year', 'academic_year_name',
            'school_class', 'school_class_name', 'purchase_cost', 'selling_price',
            'charging_type', 'included_fee_type', 'included_fee_type_name',
            'effective_from', 'effective_to', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'created_at', 'updated_at']

    def validate(self, attrs):
        school = self.context.get('school')
        item = attrs.get('item', getattr(self.instance, 'item', None))
        year = attrs.get('academic_year', getattr(self.instance, 'academic_year', None))
        school_class = attrs.get('school_class', getattr(self.instance, 'school_class', None))
        if school and item and item.school_id != school.id:
            raise ValidationError({'item': 'Item must belong to this school.'})
        if school and year and year.school_id != school.id:
            raise ValidationError({'academic_year': 'Academic year must belong to this school.'})
        if school and school_class and school_class.school_id != school.id:
            raise ValidationError({'school_class': 'Class must belong to this school.'})
        return attrs


class ItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    current_stock = serializers.SerializerMethodField()
    active_pricing = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            'id', 'school', 'item_code', 'item_name', 'category', 'category_name',
            'description', 'unit', 'has_size', 'has_color', 'is_returnable',
            'minimum_stock_level', 'maximum_stock_level', 'is_active',
            'current_stock', 'stock_status', 'active_pricing',
            'created_by', 'updated_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'created_by', 'updated_by', 'created_at', 'updated_at']

    def validate(self, attrs):
        school = self.context.get('school')
        category = attrs.get('category', getattr(self.instance, 'category', None))
        if school and category and category.school_id != school.id:
            raise ValidationError({'category': 'Category must belong to this school.'})
        return attrs

    def get_current_stock(self, obj):
        total = obj.stock_transactions.aggregate(total_qty=Sum('quantity'))['total_qty'] or 0
        return max(0, total)

    def get_stock_status(self, obj):
        stock = self.get_current_stock(obj)
        if stock <= 0:
            return "OUT_OF_STOCK"
        elif stock <= obj.minimum_stock_level:
            return "LOW_STOCK"
        return "IN_STOCK"

    def get_active_pricing(self, obj):
        pricing = obj.pricings.filter(is_active=True).order_by('-academic_year__id').first()
        if pricing:
            return ItemPricingSerializer(pricing).data
        return None


class SupplierSerializer(serializers.ModelSerializer):
    total_purchases_count = serializers.SerializerMethodField()
    total_purchases_amount = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = [
            'id', 'school', 'supplier_name', 'contact_person', 'phone', 'email',
            'address', 'gst_number', 'is_active', 'total_purchases_count',
            'total_purchases_amount', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'created_at', 'updated_at']

    def validate_phone(self, value):
        phone = value or ""
        if not phone:
            return ""

        if not re.fullmatch(r"[6-9][0-9]{9}", phone):
            raise serializers.ValidationError(
                "Enter exactly 10 digits for an Indian mobile number, starting with 6–9."
            )
        return phone

    def get_total_purchases_count(self, obj):
        return obj.purchases.count()

    def get_total_purchases_amount(self, obj):
        return obj.purchases.filter(status='CONFIRMED').aggregate(total=Sum('grand_total'))['total'] or 0.00


class PurchaseItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    size_name = serializers.CharField(source='size.name', read_only=True)
    color_name = serializers.CharField(source='color.name', read_only=True)

    class Meta:
        model = PurchaseItem
        fields = [
            'id', 'purchase', 'item', 'item_name', 'item_code', 'size', 'size_name',
            'color', 'color_name', 'quantity', 'unit_cost', 'tax', 'discount', 'total_amount'
        ]
        read_only_fields = ['id', 'purchase']

    def validate(self, attrs):
        purchase = attrs.get('purchase') or getattr(self.instance, 'purchase', None)
        school = purchase.school if purchase else self.context.get('school')
        item = attrs.get('item', getattr(self.instance, 'item', None))
        size = attrs.get('size', getattr(self.instance, 'size', None))
        color = attrs.get('color', getattr(self.instance, 'color', None))
        if school and item and item.school_id != school.id:
            raise ValidationError({'item': 'Item must belong to the purchase school.'})
        if school and size and size.school_id != school.id:
            raise ValidationError({'size': 'Size must belong to the purchase school.'})
        if school and color and color.school_id != school.id:
            raise ValidationError({'color': 'Color must belong to the purchase school.'})
        if attrs.get('quantity', 1) <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        for field in ('unit_cost', 'tax', 'discount', 'total_amount'):
            if attrs.get(field, 0) < 0:
                raise ValidationError({field: 'Amount cannot be negative.'})
        return attrs


class PurchaseSerializer(serializers.ModelSerializer):
    items = PurchaseItemSerializer(many=True, required=True)
    supplier_name = serializers.CharField(source='supplier.supplier_name', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)

    class Meta:
        model = Purchase
        fields = [
            'id', 'school', 'supplier', 'supplier_name', 'academic_year', 'academic_year_name',
            'invoice_number', 'purchase_date', 'subtotal', 'discount', 'tax',
            'grand_total', 'payment_status', 'status', 'notes', 'items',
            'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'created_by', 'created_at', 'updated_at']

    def validate(self, attrs):
        school = self.context.get('school')
        supplier = attrs.get('supplier', getattr(self.instance, 'supplier', None))
        academic_year = attrs.get('academic_year', getattr(self.instance, 'academic_year', None))
        if school and supplier and supplier.school_id != school.id:
            raise ValidationError({'supplier': 'Supplier must belong to this school.'})
        if school and academic_year and academic_year.school_id != school.id:
            raise ValidationError({'academic_year': 'Academic year must belong to this school.'})
        invoice_number = attrs.get('invoice_number', getattr(self.instance, 'invoice_number', None))
        if school and invoice_number:
            duplicate = Purchase.objects.filter(school=school, invoice_number=invoice_number)
            if self.instance:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise ValidationError({'invoice_number': 'This invoice number already exists for this school.'})
        line_items = attrs.get('items')
        if line_items is not None and not line_items:
            raise ValidationError({'items': 'Add at least one purchase line item.'})
        if line_items is not None and school:
            for index, line in enumerate(line_items):
                item = line.get('item')
                if item and item.school_id != school.id:
                    raise ValidationError({'items': {index: {'item': 'Item must belong to this school.'}}})
                if item and item.has_size and not line.get('size'):
                    raise ValidationError({'items': {index: {'size': 'Select a size for this item.'}}})
                if item and item.has_color and not line.get('color'):
                    raise ValidationError({'items': {index: {'color': 'Select a color for this item.'}}})
                for field in ('size', 'color'):
                    variant = line.get(field)
                    if variant and variant.school_id != school.id:
                        raise ValidationError({'items': {index: {field: f'{field.title()} must belong to this school.'}}})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        line_items = validated_data.pop('items', [])
        school = validated_data['school']
        purchase = Purchase.objects.create(**validated_data)
        subtotal = Decimal('0.00')
        discount = Decimal('0.00')
        tax = Decimal('0.00')
        grand_total = Decimal('0.00')
        for line in line_items:
            line_subtotal = line['unit_cost'] * line['quantity']
            subtotal += line_subtotal
            discount += line.get('discount', Decimal('0.00'))
            tax += line.get('tax', Decimal('0.00'))
            line_total = line.get('total_amount')
            # Recalculate the line total on the server; the client value is advisory only.
            line_total = line_subtotal + line.get('tax', Decimal('0.00')) - line.get('discount', Decimal('0.00'))
            if line_total < 0:
                raise ValidationError({'items': 'A purchase line total cannot be negative.'})
            grand_total += line_total
            line['total_amount'] = line_total
            PurchaseItem.objects.create(purchase=purchase, **line)
        purchase.subtotal = subtotal
        purchase.discount = discount
        purchase.tax = tax
        purchase.grand_total = grand_total
        purchase.save(update_fields=['subtotal', 'discount', 'tax', 'grand_total', 'updated_at'])
        return purchase


class StockTransactionSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    category_name = serializers.CharField(source='item.category.name', read_only=True)
    size_name = serializers.CharField(source='size.name', read_only=True)
    color_name = serializers.CharField(source='color.name', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)

    class Meta:
        model = StockTransaction
        fields = [
            'id', 'school', 'item', 'item_name', 'item_code', 'category_name',
            'academic_year', 'academic_year_name', 'size', 'size_name', 'color', 'color_name',
            'transaction_type', 'quantity', 'unit_purchase_cost', 'unit_selling_price',
            'reference_type', 'reference_id', 'transaction_date', 'remarks',
            'created_by', 'created_at'
        ]
        read_only_fields = ['id', 'school', 'created_by', 'created_at']


class StudentItemEntitlementSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_roll = serializers.CharField(source='student.roll_no', read_only=True)
    student_class = serializers.CharField(source='student.school_class.school_class', read_only=True)
    student_division = serializers.CharField(source='student.division', read_only=True)
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    size_name = serializers.CharField(source='size.name', read_only=True)
    color_name = serializers.CharField(source='color.name', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    fee_type_name = serializers.CharField(source='fee_type.name', read_only=True)
    remaining_quantity = serializers.ReadOnlyField()

    class Meta:
        model = StudentItemEntitlement
        fields = [
            'id', 'school', 'academic_year', 'academic_year_name', 'student',
            'student_name', 'student_roll', 'student_class', 'student_division',
            'item', 'item_name', 'item_code', 'size', 'size_name', 'color', 'color_name',
            'entitled_quantity', 'issued_quantity', 'remaining_quantity',
            'charging_type', 'fee_type', 'fee_type_name', 'status',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'created_at', 'updated_at']

    def get_student_name(self, obj):
        return f"{obj.student.first_name if hasattr(obj.student, 'first_name') else obj.student.name} {obj.student.surname}".strip()


class StudentItemIssueSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_roll = serializers.CharField(source='student.roll_no', read_only=True)
    student_class = serializers.CharField(source='student.school_class.school_class', read_only=True)
    student_division = serializers.CharField(source='student.division', read_only=True)
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    size_name = serializers.CharField(source='size.name', read_only=True)
    color_name = serializers.CharField(source='color.name', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    profit = serializers.SerializerMethodField()

    class Meta:
        model = StudentItemIssue
        fields = [
            'id', 'school', 'academic_year', 'academic_year_name', 'student',
            'student_name', 'student_roll', 'student_class', 'student_division',
            'item', 'item_name', 'item_code', 'size', 'size_name', 'color', 'color_name',
            'quantity', 'unit_purchase_cost', 'unit_selling_price', 'charging_type',
            'charged_amount', 'profit', 'issue_date', 'issue_reason', 'remarks',
            'issued_by', 'created_at'
        ]
        read_only_fields = ['id', 'school', 'issued_by', 'created_at']

    def get_student_name(self, obj):
        return f"{obj.student.name or ''} {obj.student.surname or ''}".strip()

    def get_profit(self, obj):
        cost = (obj.unit_purchase_cost or 0) * obj.quantity
        charged = obj.charged_amount or 0
        return charged - cost


class ReplacementRequestSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_roll = serializers.CharField(source='student.roll_no', read_only=True)
    student_class = serializers.CharField(source='student.school_class.school_class', read_only=True)
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    current_size_name = serializers.CharField(source='current_size.name', read_only=True)
    requested_size_name = serializers.CharField(source='requested_size.name', read_only=True)
    current_color_name = serializers.CharField(source='current_color.name', read_only=True)
    requested_color_name = serializers.CharField(source='requested_color.name', read_only=True)

    class Meta:
        model = ReplacementRequest
        fields = [
            'id', 'school', 'academic_year', 'student', 'student_name', 'student_roll', 'student_class',
            'item', 'item_name', 'current_size', 'current_size_name', 'requested_size', 'requested_size_name',
            'current_color', 'current_color_name', 'requested_color', 'requested_color_name',
            'quantity', 'reason', 'description', 'status', 'requested_at',
            'reviewed_at', 'reviewed_by', 'admin_remarks'
        ]
        read_only_fields = ['id', 'school', 'status', 'requested_at', 'reviewed_at', 'reviewed_by', 'admin_remarks']

    def validate(self, attrs):
        school = self.context.get('school')
        student = attrs.get('student', getattr(self.instance, 'student', None))
        item = attrs.get('item', getattr(self.instance, 'item', None))
        academic_year = attrs.get('academic_year', getattr(self.instance, 'academic_year', None))
        if school and student and student.school_id != school.id:
            raise ValidationError({'student': 'Student must belong to this school.'})
        if school and item and item.school_id != school.id:
            raise ValidationError({'item': 'Item must belong to this school.'})
        if school and academic_year and academic_year.school_id != school.id:
            raise ValidationError({'academic_year': 'Academic year must belong to this school.'})
        if attrs.get('quantity', 1) <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        for field in ('current_size', 'requested_size', 'current_color', 'requested_color'):
            variant = attrs.get(field)
            if school and variant and variant.school_id != school.id:
                raise ValidationError({field: 'Selected variant must belong to this school.'})
        return attrs

    def get_student_name(self, obj):
        return f"{obj.student.name or ''} {obj.student.surname or ''}".strip()


class StudentItemReturnSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    size_name = serializers.CharField(source='size.name', read_only=True)
    color_name = serializers.CharField(source='color.name', read_only=True)

    class Meta:
        model = StudentItemReturn
        fields = [
            'id', 'school', 'student', 'student_name', 'item', 'item_name',
            'size', 'size_name', 'color', 'color_name', 'quantity',
            'return_date', 'condition', 'reason', 'received_by', 'remarks', 'created_at'
        ]
        read_only_fields = ['id', 'school', 'received_by', 'created_at']

    def get_student_name(self, obj):
        return f"{obj.student.name or ''} {obj.student.surname or ''}".strip()


class StockAdjustmentSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    size_name = serializers.CharField(source='size.name', read_only=True)
    color_name = serializers.CharField(source='color.name', read_only=True)

    class Meta:
        model = StockAdjustment
        fields = [
            'id', 'school', 'item', 'item_name', 'item_code', 'size', 'size_name',
            'color', 'color_name', 'adjustment_type', 'quantity', 'reason',
            'remarks', 'adjustment_date', 'created_by', 'created_at'
        ]
        read_only_fields = ['id', 'school', 'created_by', 'created_at']


class InventoryAuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = InventoryAuditLog
        fields = ['id', 'school', 'user', 'user_name', 'action', 'entity_type', 'entity_id', 'old_values', 'new_values', 'created_at']
        read_only_fields = ['id', 'school', 'created_at']
