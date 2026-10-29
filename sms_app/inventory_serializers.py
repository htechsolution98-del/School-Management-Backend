from rest_framework import serializers
from decimal import Decimal
import re
from .inventory_models import (
    ItemCategory, ItemSize, ItemColor, Item, ItemPricing,
    Supplier, Purchase, PurchaseItem, StockTransaction,
    StudentItemEntitlement, StudentItemIssue, ReplacementRequest,
    StudentItemReturn, StockAdjustment, InventoryAuditLog, Requisition
)
from .models import School, AcademicYear, SchoolClass, Student, FeeType
from django.db.models import Sum
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError


class ItemCategorySerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()
    attached_items_list = serializers.SerializerMethodField()

    class Meta:
        model = ItemCategory
        fields = ['id', 'school', 'name', 'description', 'is_active', 'items_count', 'attached_items_list', 'created_at', 'updated_at']
        read_only_fields = ['id', 'school', 'created_at', 'updated_at']
        extra_kwargs = {
            'name': {
                'validators': [],
                'error_messages': {'unique': "A category with this name already exists."}
            },
        }

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise ValidationError("Category name is required and cannot be blank.")
        qs = ItemCategory.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A category with this name already exists.")
        return name

    def get_items_count(self, obj):
        if hasattr(obj, 'active_items'):
            return len(obj.active_items)
        return obj.items.filter(is_active=True).count()

    def get_attached_items_list(self, obj):
        items = getattr(obj, 'active_items', None)
        if items is None:
            items = obj.items.filter(is_active=True)
        return [
            {
                "id": item.id,
                "name": item.item_name,
                "item_name": item.item_name,
                "item_code": item.item_code,
            }
            for item in items
        ]


class ItemSizeSerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()
    attached_items_list = serializers.SerializerMethodField()

    class Meta:
        model = ItemSize
        fields = ['id', 'school', 'name', 'size_type', 'is_active', 'items_count', 'attached_items_list', 'created_at']
        read_only_fields = ['id', 'school', 'created_at']
        extra_kwargs = {
            'name': {
                'validators': [],
                'error_messages': {'unique': "A size variant with this name already exists."}
            },
        }

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise ValidationError("Size name is required and cannot be blank.")
        qs = ItemSize.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A size variant with this name already exists.")
        return name

    def validate(self, attrs):
        name = (attrs.get('name') or getattr(self.instance, 'name', '')).strip()
        if name:
            qs = ItemSize.objects.filter(name__iexact=name)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError({'name': "A size variant with this name already exists."})
        return attrs

    def get_items_count(self, obj):
        if hasattr(obj, 'active_allowed_items'):
            return len(obj.active_allowed_items)
        return obj.allowed_items.filter(is_active=True).count()

    def get_attached_items_list(self, obj):
        items = getattr(obj, 'active_allowed_items', None)
        if items is None:
            items = obj.allowed_items.filter(is_active=True)
        return [
            {
                "id": item.id,
                "name": item.item_name,
                "item_name": item.item_name,
                "item_code": item.item_code,
            }
            for item in items
        ]


class ItemColorSerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()
    attached_items_list = serializers.SerializerMethodField()

    class Meta:
        model = ItemColor
        fields = ['id', 'school', 'name', 'hex_code', 'is_active', 'items_count', 'attached_items_list', 'created_at']
        read_only_fields = ['id', 'school', 'created_at']
        extra_kwargs = {
            'name': {
                'validators': [],
                'error_messages': {'unique': "A color variant with this name already exists."}
            },
            'hex_code': {
                'validators': [],
                'error_messages': {'unique': "A color variant with this hex code already exists."}
            },
        }

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise ValidationError("Color name is required and cannot be blank.")
        qs = ItemColor.objects.filter(name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A color variant with this name already exists.")
        return name

    def validate_hex_code(self, value):
        hex_code = (value or "").strip()
        if not hex_code:
            return None
        qs = ItemColor.objects.filter(hex_code__iexact=hex_code)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A color variant with this hex code already exists.")
        return hex_code

    def validate(self, attrs):
        name = (attrs.get('name') or getattr(self.instance, 'name', '')).strip()
        if name:
            qs = ItemColor.objects.filter(name__iexact=name)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError({'name': "A color variant with this name already exists."})

        hex_code = (attrs.get('hex_code') or getattr(self.instance, 'hex_code', '') or '').strip()
        if hex_code:
            qs = ItemColor.objects.filter(hex_code__iexact=hex_code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError({'hex_code': "A color variant with this hex code already exists."})
        elif 'hex_code' in attrs:
            attrs['hex_code'] = None

        return attrs

    def get_items_count(self, obj):
        if hasattr(obj, 'active_allowed_items'):
            return len(obj.active_allowed_items)
        return obj.allowed_items.filter(is_active=True).count()

    def get_attached_items_list(self, obj):
        items = getattr(obj, 'active_allowed_items', None)
        if items is None:
            items = obj.allowed_items.filter(is_active=True)
        return [
            {
                "id": item.id,
                "name": item.item_name,
                "item_name": item.item_name,
                "item_code": item.item_code,
            }
            for item in items
        ]


class ItemPricingSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    school_class_name = serializers.CharField(source='school_class.school_class', read_only=True)
    included_fee_type_name = serializers.CharField(source='included_fee_type.name', read_only=True)
    item = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.all(),
        required=True,
        error_messages={'required': 'Please select an item.', 'null': 'Please select an item.', 'does_not_exist': 'Selected item was not found.'}
    )
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(),
        required=True,
        error_messages={'required': 'Please select an academic year.', 'null': 'Please select an academic year.', 'does_not_exist': 'Selected academic year was not found.'}
    )
    purchase_cost = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        min_value=Decimal('0.00'),
        error_messages={
            'required': 'Purchase cost is required.',
            'null': 'Purchase cost cannot be blank.',
            'invalid': 'Purchase cost must be a valid number.',
            'min_value': 'Purchase cost cannot be negative.'
        }
    )
    selling_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        min_value=Decimal('0.00'),
        error_messages={
            'required': 'Selling price is required.',
            'null': 'Selling price cannot be blank.',
            'invalid': 'Selling price must be a valid number.',
            'min_value': 'Selling price cannot be negative.'
        }
    )
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

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.copy()
            if 'charging_policy' in data and 'charging_type' not in data:
                data['charging_type'] = data['charging_policy']
            if 'applicable_class' in data and 'school_class' not in data:
                data['school_class'] = data['applicable_class']
        return super().to_internal_value(data)

    def validate(self, attrs):
        school = self.context.get('school')
        item = attrs.get('item', getattr(self.instance, 'item', None))
        year = attrs.get('academic_year', getattr(self.instance, 'academic_year', None))
        school_class = attrs.get('school_class', getattr(self.instance, 'school_class', None))
        purchase_cost = attrs.get('purchase_cost', getattr(self.instance, 'purchase_cost', None))
        selling_price = attrs.get('selling_price', getattr(self.instance, 'selling_price', None))
        charging_type = attrs.get('charging_type', getattr(self.instance, 'charging_type', None))
        fee_type = attrs.get('included_fee_type', getattr(self.instance, 'included_fee_type', None))

        if not item:
            raise ValidationError({'item': 'Please select an item.'})
        if not year:
            raise ValidationError({'academic_year': 'Please select an academic year.'})

        if charging_type in ('FREE', 'INCLUDED_IN_FEE'):
            attrs['selling_price'] = Decimal('0.00')
            selling_price = Decimal('0.00')
        elif charging_type == 'SEPARATE_CHARGE':
            if selling_price is None or selling_price <= Decimal('0.00'):
                raise ValidationError({'selling_price': 'Selling price must be greater than zero for Separate Charge items.'})

        if charging_type == 'INCLUDED_IN_FEE' and not fee_type:
            raise ValidationError({'included_fee_type': 'Please select an included fee type.'})

        if purchase_cost is not None and purchase_cost < Decimal('0.00'):
            raise ValidationError({'purchase_cost': 'Purchase cost cannot be negative.'})
        if selling_price is not None and selling_price < Decimal('0.00'):
            raise ValidationError({'selling_price': 'Selling price cannot be negative.'})

        if school and item and item.school_id != school.id:
            raise ValidationError({'item': 'Item must belong to this school.'})
        if school and year and year.school_id != school.id:
            raise ValidationError({'academic_year': 'Academic year must belong to this school.'})
        if school and school_class and school_class.school_id != school.id:
            raise ValidationError({'school_class': 'Class must belong to this school.'})
        return attrs


class ItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    allowed_sizes = serializers.PrimaryKeyRelatedField(
        many=True, queryset=ItemSize.objects.all(), required=False
    )
    allowed_colors = serializers.PrimaryKeyRelatedField(
        many=True, queryset=ItemColor.objects.all(), required=False
    )
    allowed_size_details = ItemSizeSerializer(source='allowed_sizes', many=True, read_only=True)
    allowed_color_details = ItemColorSerializer(source='allowed_colors', many=True, read_only=True)
    current_stock = serializers.SerializerMethodField()
    active_pricing = serializers.SerializerMethodField()
    stock_status = serializers.SerializerMethodField()
    variant_stock_matrix = serializers.SerializerMethodField()
    last_purchase_cost = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            'id', 'school', 'item_code', 'item_name', 'category', 'category_name',
            'description', 'unit', 'has_size', 'has_color',
            'allowed_sizes', 'allowed_colors', 'allowed_size_details', 'allowed_color_details',
            'is_returnable',
            'damaged_stock', 'minimum_stock_level', 'maximum_stock_level', 'is_active',
            'current_stock', 'stock_status', 'active_pricing', 'variant_stock_matrix',
            'last_purchase_cost',
            'created_by', 'updated_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'created_by', 'updated_by', 'created_at', 'updated_at']
        extra_kwargs = {
            'item_code': {
                'validators': [],
                'error_messages': {'unique': "An item with this Item Code already exists."}
            },
            'item_name': {
                'validators': [],
                'error_messages': {'unique': "An item with this Item Name already exists."}
            },
        }

    def validate_item_code(self, value):
        code = (value or "").strip()
        if not code:
            raise ValidationError("Item code is required and cannot be blank.")
        qs = Item.objects.filter(item_code__iexact=code)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("An item with this Item Code already exists.")
        return code

    def validate_item_name(self, value):
        name = (value or "").strip()
        if not name:
            raise ValidationError("Item name is required and cannot be blank.")
        qs = Item.objects.filter(item_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("An item with this Item Name already exists.")
        return name

    def validate_minimum_stock_level(self, value):
        if value is not None and value < 0:
            raise ValidationError("Minimum stock level cannot be negative.")
        return value

    def validate_maximum_stock_level(self, value):
        if value is not None and value < 0:
            raise ValidationError("Maximum stock level cannot be negative.")
        return value

    def validate(self, attrs):
        school = self.context.get('school')
        category = attrs.get('category', getattr(self.instance, 'category', None))
        if school and category and category.school_id != school.id:
            raise ValidationError({'category': 'Category must belong to this school.'})

        min_stock = attrs.get('minimum_stock_level', getattr(self.instance, 'minimum_stock_level', 0))
        max_stock = attrs.get('maximum_stock_level', getattr(self.instance, 'maximum_stock_level', None))
        if min_stock is not None and min_stock < 0:
            raise ValidationError({'minimum_stock_level': 'Minimum stock level cannot be negative.'})
        if max_stock is not None:
            if max_stock < 0:
                raise ValidationError({'maximum_stock_level': 'Maximum stock level cannot be negative.'})
            if min_stock is not None and max_stock < min_stock:
                raise ValidationError({'maximum_stock_level': 'Maximum stock level cannot be less than minimum stock level.'})

        item_code = attrs.get('item_code', getattr(self.instance, 'item_code', None))
        if item_code:
            qs = Item.objects.filter(item_code__iexact=str(item_code).strip())
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError({'item_code': "An item with this Item Code already exists."})

        item_name = attrs.get('item_name', getattr(self.instance, 'item_name', None))
        if item_name:
            qs = Item.objects.filter(item_name__iexact=str(item_name).strip())
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError({'item_name': "An item with this Item Name already exists."})

        has_size = attrs.get('has_size', getattr(self.instance, 'has_size', False))
        if has_size:
            allowed_sizes = attrs.get('allowed_sizes', None)
            if allowed_sizes is not None and len(allowed_sizes) == 0:
                raise ValidationError({'allowed_sizes': "Please select at least one size variant, or uncheck 'Has Sizes'."})
            elif allowed_sizes is None and self.instance and not self.instance.allowed_sizes.exists():
                raise ValidationError({'allowed_sizes': "Please select at least one size variant, or uncheck 'Has Sizes'."})

        has_color = attrs.get('has_color', getattr(self.instance, 'has_color', False))
        if has_color:
            allowed_colors = attrs.get('allowed_colors', None)
            if allowed_colors is not None and len(allowed_colors) == 0:
                raise ValidationError({'allowed_colors': "Please select at least one color variant, or uncheck 'Has Color Options'."})
            elif allowed_colors is None and self.instance and not self.instance.allowed_colors.exists():
                raise ValidationError({'allowed_colors': "Please select at least one color variant, or uncheck 'Has Color Options'."})

        return attrs

    def get_current_stock(self, obj):
        if hasattr(obj, 'annotated_stock'):
            return max(0, obj.annotated_stock or 0)
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
        # Use prefetched pricings cache if available to prevent N+1 queries
        if hasattr(obj, '_prefetched_objects_cache') and 'pricings' in obj._prefetched_objects_cache:
            active_pricings = [p for p in obj.pricings.all() if p.is_active]
            pricing = active_pricings[0] if active_pricings else None
        else:
            pricing = obj.pricings.filter(is_active=True).select_related(
                'academic_year', 'school_class', 'included_fee_type'
            ).order_by('-academic_year__id').first()
        if pricing:
            return ItemPricingSerializer(pricing).data
        return None

    def get_variant_stock_matrix(self, obj):
        # Optimization: Non-variant items have zero variant sub-combinations
        if not obj.has_size and not obj.has_color:
            current_qty = self.get_current_stock(obj)
            return [{
                'size_id': None,
                'size_name': None,
                'color_id': None,
                'color_name': None,
                'available_stock': current_qty,
            }]

        req = self.context.get('request')
        # Cache school-wide active sizes and colors in request context so we do NOT query DB 50 times in a loop
        if req:
            if not hasattr(req, '_cached_sizes'):
                req._cached_sizes = list(ItemSize.objects.filter(school=obj.school, is_active=True))
            if not hasattr(req, '_cached_colors'):
                req._cached_colors = list(ItemColor.objects.filter(school=obj.school, is_active=True))
            all_sizes = req._cached_sizes
            all_colors = req._cached_colors
        else:
            all_sizes = list(ItemSize.objects.filter(school=obj.school, is_active=True))
            all_colors = list(ItemColor.objects.filter(school=obj.school, is_active=True))

        stock_map = {}
        txns = (
            obj.stock_transactions.values('size_id', 'color_id')
            .annotate(total_qty=Sum('quantity'))
        )
        for t in txns:
            stock_map[(t['size_id'], t['color_id'])] = t['total_qty'] or 0

        sizes = all_sizes if obj.has_size else [None]
        colors = all_colors if obj.has_color else [None]

        matrix = []
        for s in sizes:
            for c in colors:
                s_id = s.id if s else None
                c_id = c.id if c else None
                qty = max(0, stock_map.get((s_id, c_id), 0))
                matrix.append({
                    'size_id': s_id,
                    'size_name': s.name if s else None,
                    'color_id': c_id,
                    'color_name': c.name if c else None,
                    'available_stock': qty,
                })
        return matrix

    def get_last_purchase_cost(self, obj):
        # Check cached prefetched pricing first
        if hasattr(obj, '_prefetched_objects_cache') and 'pricings' in obj._prefetched_objects_cache:
            active_pricings = [p for p in obj.pricings.all() if p.is_active]
            pricing = active_pricings[0] if active_pricings else None
            if pricing and pricing.purchase_cost is not None:
                return str(pricing.purchase_cost)

        last_txn = obj.stock_transactions.filter(
            transaction_type__in=['PURCHASE', 'OPENING'],
            unit_purchase_cost__isnull=False
        ).order_by('-transaction_date', '-id').first()
        if last_txn and last_txn.unit_purchase_cost is not None:
            return str(last_txn.unit_purchase_cost)

        pricing = obj.pricings.filter(is_active=True).order_by('-academic_year__id').first()
        if pricing and pricing.purchase_cost is not None:
            return str(pricing.purchase_cost)
        return "0.00"


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
        extra_kwargs = {
            'supplier_name': {
                'validators': [],
                'error_messages': {'unique': "A supplier with this name already exists."}
            },
            'phone': {
                'validators': [],
                'error_messages': {'unique': "This phone number is already registered to another supplier."}
            },
            'email': {
                'validators': [],
                'error_messages': {'unique': "This email is already registered to another supplier."}
            },
            'gst_number': {
                'validators': [],
                'error_messages': {'unique': "This GST number is already registered to another supplier."}
            },
        }

    def validate_supplier_name(self, value):
        name = (value or "").strip()
        if not name:
            raise ValidationError("Supplier name is required and cannot be blank.")
        qs = Supplier.objects.filter(supplier_name__iexact=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A supplier with this name already exists.")
        return name

    def validate_phone(self, value):
        phone = (value or "").strip()
        if not phone:
            return None

        if not re.fullmatch(r"[6-9][0-9]{9}", phone):
            raise ValidationError(
                "Enter exactly 10 digits for an Indian mobile number, starting with 6–9."
            )
        qs = Supplier.objects.filter(phone__iexact=phone)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("This phone number is already registered to another supplier.")
        return phone

    def validate_email(self, value):
        email = (value or "").strip()
        if not email:
            return None
        qs = Supplier.objects.filter(email__iexact=email)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("This email is already registered to another supplier.")
        return email

    def validate_gst_number(self, value):
        gst = (value or "").strip()
        if not gst:
            return None
        qs = Supplier.objects.filter(gst_number__iexact=gst)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("This GST number is already registered to another supplier.")
        return gst

    def validate(self, attrs):
        for field in ['phone', 'email', 'gst_number']:
            if field in attrs:
                v = (attrs[field] or '').strip()
                attrs[field] = v if v else None

        phone = attrs.get('phone')
        if phone:
            qs = Supplier.objects.filter(phone__iexact=phone)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError({'phone': "This phone number is already registered to another supplier."})

        email = attrs.get('email')
        if email:
            qs = Supplier.objects.filter(email__iexact=email)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError({'email': "This email is already registered to another supplier."})

        gst = attrs.get('gst_number')
        if gst:
            qs = Supplier.objects.filter(gst_number__iexact=gst)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError({'gst_number': "This GST number is already registered to another supplier."})

        name = attrs.get('supplier_name')
        if name:
            qs = Supplier.objects.filter(supplier_name__iexact=name.strip())
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError({'supplier_name': "A supplier with this name already exists."})

        return attrs

    def get_total_purchases_count(self, obj):
        if hasattr(obj, 'annotated_purchases_count'):
            return obj.annotated_purchases_count
        return obj.purchases.count()

    def get_total_purchases_amount(self, obj):
        if hasattr(obj, 'annotated_purchases_amount'):
            return obj.annotated_purchases_amount or Decimal('0.00')
        return obj.purchases.filter(status='CONFIRMED').aggregate(total=Sum('grand_total'))['total'] or Decimal('0.00')


class PurchaseItemSerializer(serializers.ModelSerializer):
    item = serializers.PrimaryKeyRelatedField(
        queryset=Item.objects.all(),
        required=True,
        error_messages={
            'required': 'Please select an item for each line.',
            'null': 'Please select an item for each line.',
            'does_not_exist': 'Selected item was not found.'
        }
    )
    quantity = serializers.IntegerField(
        required=True,
        min_value=1,
        error_messages={
            'required': 'Quantity is required.',
            'null': 'Quantity cannot be blank.',
            'invalid': 'Quantity must be a valid integer.',
            'min_value': 'Quantity must be at least 1.'
        }
    )
    unit_cost = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        min_value=Decimal('0.00'),
        error_messages={
            'required': 'Unit cost is required.',
            'null': 'Unit cost cannot be blank.',
            'invalid': 'Unit cost must be a valid number.',
            'min_value': 'Unit cost cannot be negative.'
        }
    )
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
        quantity = attrs.get('quantity')
        unit_cost = attrs.get('unit_cost')

        if not item:
            raise ValidationError({'item': 'Please select an item for each line.'})
        if school and item and item.school_id != school.id:
            raise ValidationError({'item': 'Item must belong to the purchase school.'})
        if item and item.has_size and not size:
            raise ValidationError({'size': f"Please select a size for '{item.item_name}'."})
        if item and item.has_color and not color:
            raise ValidationError({'color': f"Please select a color for '{item.item_name}'."})
        if school and size and size.school_id != school.id:
            raise ValidationError({'size': 'Size must belong to the purchase school.'})
        if school and color and color.school_id != school.id:
            raise ValidationError({'color': 'Color must belong to the purchase school.'})

        if quantity is not None and quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if unit_cost is not None and unit_cost < 0:
            raise ValidationError({'unit_cost': 'Unit cost cannot be negative.'})
        for field in ('tax', 'discount', 'total_amount'):
            if attrs.get(field, 0) < 0:
                raise ValidationError({field: 'Amount cannot be negative.'})
        return attrs


class PurchaseSerializer(serializers.ModelSerializer):
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(),
        required=True,
        error_messages={
            'required': 'Please select a supplier.',
            'null': 'Please select a supplier.',
            'does_not_exist': 'Selected supplier was not found.'
        }
    )
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(),
        required=True,
        error_messages={
            'required': 'Please select an academic year.',
            'null': 'Please select an academic year.',
            'does_not_exist': 'Selected academic year was not found.'
        }
    )
    invoice_number = serializers.CharField(
        required=True,
        allow_blank=False,
        error_messages={
            'required': 'Invoice number is required.',
            'blank': 'Invoice number cannot be blank.'
        }
    )
    items = PurchaseItemSerializer(
        many=True,
        required=True,
        allow_empty=False,
        error_messages={
            'required': 'Add at least one purchase line item.',
            'empty': 'Add at least one purchase line item.'
        }
    )
    supplier_name = serializers.CharField(source='supplier.supplier_name', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    tax_amount = serializers.DecimalField(source='tax', max_digits=12, decimal_places=2, read_only=True)
    discount_amount = serializers.DecimalField(source='discount', max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Purchase
        fields = [
            'id', 'school', 'supplier', 'supplier_name', 'academic_year', 'academic_year_name',
            'invoice_number', 'purchase_date', 'subtotal', 'discount', 'discount_amount', 'tax', 'tax_amount',
            'grand_total', 'payment_status', 'status', 'notes', 'items',
            'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'created_by', 'created_at', 'updated_at']

    def validate(self, attrs):
        school = self.context.get('school')
        supplier = attrs.get('supplier', getattr(self.instance, 'supplier', None))
        academic_year = attrs.get('academic_year', getattr(self.instance, 'academic_year', None))
        if not supplier:
            raise ValidationError({'supplier': 'Please select a supplier.'})
        if not academic_year:
            raise ValidationError({'academic_year': 'Please select an academic year.'})
        if school and supplier and supplier.school_id != school.id:
            raise ValidationError({'supplier': 'Supplier must belong to this school.'})
        if school and academic_year and academic_year.school_id != school.id:
            raise ValidationError({'academic_year': 'Academic year must belong to this school.'})

        invoice_number = (attrs.get('invoice_number', getattr(self.instance, 'invoice_number', None)) or "").strip()
        if not invoice_number:
            raise ValidationError({'invoice_number': 'Invoice number is required.'})

        if school and invoice_number:
            duplicate = Purchase.objects.filter(school=school, invoice_number=invoice_number)
            if self.instance:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise ValidationError({'invoice_number': f"Invoice number '{invoice_number}' already exists for this school."})

        line_items = attrs.get('items')
        if line_items is not None and not line_items:
            raise ValidationError({'items': 'Add at least one purchase line item.'})
        if line_items is not None and school:
            item_quantities = {}
            for index, line in enumerate(line_items):
                item = line.get('item')
                if item and item.school_id != school.id:
                    raise ValidationError({'items': {index: {'item': 'Item must belong to this school.'}}})
                if item and item.has_size and not line.get('size'):
                    raise ValidationError({'items': {index: {'size': f"Select a size for '{item.item_name}'."}}})
                if item and item.has_color and not line.get('color'):
                    raise ValidationError({'items': {index: {'color': f"Select a color for '{item.item_name}'."}}})
                for field in ('size', 'color'):
                    variant = line.get(field)
                    if variant and variant.school_id != school.id:
                        raise ValidationError({'items': {index: {field: f'{field.title()} must belong to this school.'}}})
                if item:
                    item_quantities[item] = item_quantities.get(item, 0) + (line.get('quantity') or 0)

            # Maximum Stock Capacity Validation (Row 53)
            for item, purchase_qty in item_quantities.items():
                if item.maximum_stock_level is not None:
                    curr_stock = item.stock_transactions.aggregate(total=Sum('quantity'))['total'] or 0
                    if (curr_stock + purchase_qty) > item.maximum_stock_level:
                        err_msg = f"Purchase exceeds maximum stock capacity of {item.maximum_stock_level} for {item.item_name}."
                        raise ValidationError({'items': err_msg, 'non_field_errors': [err_msg]})
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


class PurchaseListSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.supplier_name', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Purchase
        fields = [
            'id', 'invoice_number', 'supplier', 'supplier_name',
            'academic_year', 'academic_year_name', 'purchase_date',
            'subtotal', 'discount', 'tax', 'grand_total',
            'payment_status', 'status', 'notes', 'items_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_items_count(self, obj):
        if hasattr(obj, 'annotated_items_count'):
            return obj.annotated_items_count
        return obj.items.count()


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
    status = serializers.SerializerMethodField()

    class Meta:
        model = StudentItemIssue
        fields = [
            'id', 'school', 'academic_year', 'academic_year_name', 'student',
            'student_name', 'student_roll', 'student_class', 'student_division',
            'item', 'item_name', 'item_code', 'size', 'size_name', 'color', 'color_name',
            'quantity', 'unit_purchase_cost', 'unit_selling_price', 'charging_type',
            'charged_amount', 'profit', 'status', 'issue_date', 'issue_reason', 'remarks',
            'issued_by', 'created_at'
        ]
        read_only_fields = ['id', 'school', 'issued_by', 'created_at']

    def get_status(self, obj):
        return getattr(obj, "status", None) or "ISSUED"

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
        qty = attrs.get('quantity', 1)
        if qty <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if school and student and item:
            from .inventory_models import StudentItemIssue
            issued_total = StudentItemIssue.objects.filter(
                school=school,
                student=student,
                item=item
            ).aggregate(total=Sum('quantity'))['total'] or 0
            if issued_total <= 0:
                raise ValidationError({'item': f"No issuance records found for '{item.item_name}' for this student."})
            if qty > issued_total:
                raise ValidationError({'quantity': f"Requested quantity ({qty}) cannot exceed the previously issued quantity ({issued_total}) for '{item.item_name}'."})
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
    adjustment_date = serializers.DateField(required=False, default=timezone.localdate)

    class Meta:
        model = StockAdjustment
        fields = [
            'id', 'school', 'item', 'item_name', 'item_code', 'size', 'size_name',
            'color', 'color_name', 'adjustment_type', 'quantity', 'reason',
            'remarks', 'adjustment_date', 'created_by', 'created_at'
        ]
        read_only_fields = ['id', 'school', 'created_by', 'created_at']

    def to_internal_value(self, data):
        if isinstance(data, dict):
            data = data.copy()
            if 'adjustment_date' in data and data['adjustment_date']:
                val = data.get('adjustment_date')
                if isinstance(val, str) and 'T' in val:
                    data['adjustment_date'] = val.split('T')[0]
                elif hasattr(val, 'date'):
                    data['adjustment_date'] = val.date()
            else:
                data['adjustment_date'] = timezone.localdate().isoformat()
        return super().to_internal_value(data)

    def validate_quantity(self, value):
        if value is None or int(value) <= 0:
            raise ValidationError("Adjustment quantity must be greater than zero.")
        return int(value)

    def validate_reason(self, value):
        reason = (value or "").strip()
        if not reason:
            raise ValidationError("Reason is required and cannot be blank.")
        return reason

    def validate(self, attrs):
        school = self.context.get('school')
        item = attrs.get('item', getattr(self.instance, 'item', None))
        size = attrs.get('size', getattr(self.instance, 'size', None))
        color = attrs.get('color', getattr(self.instance, 'color', None))
        adjustment_type = attrs.get('adjustment_type', getattr(self.instance, 'adjustment_type', None))
        quantity = attrs.get('quantity', getattr(self.instance, 'quantity', 0))

        if not item:
            raise ValidationError({'item': 'Item is required.'})
        if school and item.school_id != school.id:
            raise ValidationError({'item': 'Item must belong to this school.'})
        if school and size and size.school_id != school.id:
            raise ValidationError({'size': 'Selected size must belong to this school.'})
        if school and color and color.school_id != school.id:
            raise ValidationError({'color': 'Selected color must belong to this school.'})

        if item.has_size and not size:
            raise ValidationError({'size': f"Size is required for item '{item.item_name}'."})
        if item.has_color and not color:
            raise ValidationError({'color': f"Color is required for item '{item.item_name}'."})

        valid_types = ['ADJUSTMENT_IN', 'ADJUSTMENT_OUT', 'DAMAGE', 'LOST']
        if adjustment_type not in valid_types:
            raise ValidationError({'adjustment_type': f"Invalid adjustment type. Must be one of: {', '.join(valid_types)}."})

        # Check available stock if reduction
        if adjustment_type in ['ADJUSTMENT_OUT', 'DAMAGE', 'LOST']:
            from .inventory_services import InventoryService
            current_stock = InventoryService.get_item_stock(
                item.id,
                size.id if size else None,
                color.id if color else None
            )
            if current_stock < quantity:
                raise ValidationError({
                    'quantity': f"Adjustment quantity ({quantity}) exceeds available stock ({current_stock})."
                })

        return attrs


class InventoryAuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = InventoryAuditLog
        fields = ['id', 'school', 'user', 'user_name', 'action', 'entity_type', 'entity_id', 'old_values', 'new_values', 'created_at']
        read_only_fields = ['id', 'school', 'created_at']


class RequisitionSerializer(serializers.ModelSerializer):
    requester_name = serializers.SerializerMethodField()
    requester_role = serializers.SerializerMethodField()
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    unit = serializers.CharField(source='item.unit', read_only=True)
    available_stock = serializers.SerializerMethodField()
    action_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Requisition
        fields = [
            'id',
            'school',
            'requester',
            'requester_name',
            'requester_role',
            'item',
            'item_name',
            'item_code',
            'unit',
            'available_stock',
            'quantity_requested',
            'purpose',
            'status',
            'requested_at',
            'action_date',
            'action_by',
            'action_by_name',
            'remarks',
        ]
        read_only_fields = [
            'id',
            'school',
            'requester',
            'status',
            'requested_at',
            'action_date',
            'action_by',
        ]

    def get_requester_name(self, obj):
        if not obj.requester:
            return "N/A"
        full_name = f"{obj.requester.first_name or ''} {obj.requester.last_name or ''}".strip()
        if not full_name or full_name.lower() == 'none':
            staff = getattr(obj.requester, 'staff', None) or getattr(obj.requester, 'staff_profile', None)
            if staff and getattr(staff, 'name', None) and staff.name.lower() != 'none':
                full_name = staff.name
        return full_name or obj.requester.username

    def get_requester_role(self, obj):
        if not obj.requester:
            return ""
        return getattr(obj.requester, 'role', '') or getattr(obj.requester, 'user_type', '') or 'STAFF'

    def get_available_stock(self, obj):
        from .inventory_services import InventoryService
        return InventoryService.get_item_stock(obj.item_id)

    def get_action_by_name(self, obj):
        if not obj.action_by:
            return None
        full_name = f"{obj.action_by.first_name or ''} {obj.action_by.last_name or ''}".strip()
        if not full_name or full_name.lower() == 'none':
            staff = getattr(obj.action_by, 'staff', None) or getattr(obj.action_by, 'staff_profile', None)
            if staff and getattr(staff, 'name', None) and staff.name.lower() != 'none':
                full_name = staff.name
        return full_name or obj.action_by.username

    def validate_quantity_requested(self, value):
        if value is None or int(value) <= 0:
            raise serializers.ValidationError("Quantity requested must be greater than 0.")
        return int(value)

    def validate_purpose(self, value):
        purpose = (value or "").strip()
        if not purpose:
            raise serializers.ValidationError("Purpose is required and cannot be blank.")
        return purpose

    def validate(self, attrs):
        school = self.context.get('school')
        item = attrs.get('item', getattr(self.instance, 'item', None))
        if item and school and item.school_id != school.id:
            raise serializers.ValidationError({"item": "The selected item does not belong to your school."})
        return attrs

