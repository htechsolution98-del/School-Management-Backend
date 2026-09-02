from rest_framework import serializers
from .models import *
from .inventory_models import (
    InventoryCategory,
    InventorySubCategory,
    InventoryUnit,
    InventoryItem,
    InventoryItemVariant,
    InventoryWarehouse,
    InventorySupplier,
    InventoryPurchase,
    InventoryPurchaseItem,
    PurchaseRequest,
    PurchaseRequestItem,
    InventoryOpeningStock,
    InventoryTransaction,
    InventoryStockBalance,
    StudentInventoryIssue,
    StudentInventoryIssueItem,
    StudentIDCard,
    InventoryBundle,
    InventoryBundleItem,
    InventoryReturn,
    InventoryReturnItem,
    InventoryStockAdjustment,
    InventoryStockAdjustmentItem,
    InventoryBudget,
)


class InventorySubCategorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = InventorySubCategory
        fields = '__all__'
        read_only_fields = ['school', 'created_at']


class InventoryCategorySerializer(serializers.ModelSerializer):
    subcategories = InventorySubCategorySerializer(many=True, read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = InventoryCategory
        fields = '__all__'
        read_only_fields = ['school', 'created_at']

    def get_item_count(self, obj):
        return obj.items.count()


class InventoryUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryUnit
        fields = '__all__'
        read_only_fields = ['school']


class InventoryItemVariantSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    total_stock = serializers.ReadOnlyField()
    class_name = serializers.CharField(source='applicable_class.name', read_only=True)

    class Meta:
        model = InventoryItemVariant
        fields = '__all__'


class InventoryItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    sub_category_name = serializers.CharField(source='sub_category.name', read_only=True)
    variants = InventoryItemVariantSerializer(many=True, read_only=True)
    total_stock = serializers.ReadOnlyField()

    class Meta:
        model = InventoryItem
        fields = '__all__'
        read_only_fields = ['school', 'created_at', 'updated_at']


class InventoryWarehouseSerializer(serializers.ModelSerializer):
    incharge_username = serializers.CharField(source='incharge_user.username', read_only=True)

    class Meta:
        model = InventoryWarehouse
        fields = '__all__'
        read_only_fields = ['school', 'created_at']


class InventorySupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventorySupplier
        fields = '__all__'
        read_only_fields = ['school', 'created_at']


class InventoryStockBalanceSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    item_type = serializers.CharField(source='item.item_type', read_only=True)
    category_name = serializers.CharField(source='item.category.name', read_only=True)
    unit = serializers.CharField(source='item.unit', read_only=True)
    minimum_stock = serializers.IntegerField(source='item.minimum_stock', read_only=True)
    purchase_price = serializers.DecimalField(source='item.purchase_price', max_digits=12, decimal_places=2, read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.warehouse_name', read_only=True)
    variant_code = serializers.CharField(source='variant.variant_code', read_only=True)
    variant_size = serializers.CharField(source='variant.size', read_only=True)
    variant_color = serializers.CharField(source='variant.color', read_only=True)
    is_low_stock = serializers.SerializerMethodField()
    stock_value = serializers.SerializerMethodField()

    class Meta:
        model = InventoryStockBalance
        fields = '__all__'
        read_only_fields = ['school', 'updated_at']

    def get_is_low_stock(self, obj):
        threshold = obj.variant.minimum_stock if obj.variant else obj.item.minimum_stock
        return obj.available_quantity <= threshold

    def get_stock_value(self, obj):
        price = (obj.variant.purchase_price if obj.variant and obj.variant.purchase_price > 0 else obj.item.purchase_price) or 0
        return float(obj.available_quantity * price)


class InventoryTransactionSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.warehouse_name', read_only=True)
    to_warehouse_name = serializers.CharField(source='to_warehouse.warehouse_name', read_only=True)
    variant_code = serializers.CharField(source='variant.variant_code', read_only=True)
    variant_size = serializers.CharField(source='variant.size', read_only=True)
    variant_color = serializers.CharField(source='variant.color', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = InventoryTransaction
        fields = '__all__'
        read_only_fields = ['school', 'created_at']


class InventoryOpeningStockSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.warehouse_name', read_only=True)
    variant_code = serializers.CharField(source='variant.variant_code', read_only=True)

    class Meta:
        model = InventoryOpeningStock
        fields = '__all__'
        read_only_fields = ['school', 'total_cost', 'created_at']


class InventoryPurchaseItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    variant_size = serializers.CharField(source='variant.size', read_only=True)

    class Meta:
        model = InventoryPurchaseItem
        fields = '__all__'


class InventoryPurchaseSerializer(serializers.ModelSerializer):
    items = InventoryPurchaseItemSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.warehouse_name', read_only=True)

    class Meta:
        model = InventoryPurchase
        fields = '__all__'
        read_only_fields = ['school', 'created_at']


class PurchaseRequestItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    variant_size = serializers.CharField(source='variant.size', read_only=True)

    class Meta:
        model = PurchaseRequestItem
        fields = '__all__'


class PurchaseRequestSerializer(serializers.ModelSerializer):
    items = PurchaseRequestItemSerializer(many=True, read_only=True)
    requested_by_name = serializers.CharField(source='requested_by.name', read_only=True)

    class Meta:
        model = PurchaseRequest
        fields = '__all__'
        read_only_fields = ['school', 'created_at']


class StudentInventoryIssueItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    variant_size = serializers.CharField(source='variant.size', read_only=True)
    variant_color = serializers.CharField(source='variant.color', read_only=True)

    class Meta:
        model = StudentInventoryIssueItem
        fields = '__all__'


class StudentInventoryIssueSerializer(serializers.ModelSerializer):
    items = StudentInventoryIssueItemSerializer(many=True, read_only=True)
    student_name = serializers.CharField(source='student.name', read_only=True)
    student_roll = serializers.CharField(source='student.roll_number', read_only=True)
    student_class = serializers.CharField(source='student.student_class.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.warehouse_name', read_only=True)
    issued_by_name = serializers.CharField(source='issued_by.username', read_only=True)

    class Meta:
        model = StudentInventoryIssue
        fields = '__all__'
        read_only_fields = ['school', 'issue_number', 'created_at']


class StudentIDCardSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    student_roll = serializers.CharField(source='student.roll_number', read_only=True)
    student_class = serializers.CharField(source='student.student_class.name', read_only=True)
    previous_card_number = serializers.CharField(source='previous_card.card_number', read_only=True)

    class Meta:
        model = StudentIDCard
        fields = '__all__'
        read_only_fields = ['school', 'created_at']


class InventoryBundleItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    variant_size = serializers.CharField(source='variant.size', read_only=True)

    class Meta:
        model = InventoryBundleItem
        fields = '__all__'


class InventoryBundleSerializer(serializers.ModelSerializer):
    items = InventoryBundleItemSerializer(many=True, read_only=True)
    class_name = serializers.CharField(source='applicable_class.name', read_only=True)

    class Meta:
        model = InventoryBundle
        fields = '__all__'
        read_only_fields = ['school', 'created_at']


class InventoryReturnItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    variant_size = serializers.CharField(source='variant.size', read_only=True)

    class Meta:
        model = InventoryReturnItem
        fields = '__all__'


class InventoryReturnSerializer(serializers.ModelSerializer):
    items = InventoryReturnItemSerializer(many=True, read_only=True)
    student_name = serializers.CharField(source='student.name', read_only=True)
    staff_name = serializers.CharField(source='staff.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.warehouse_name', read_only=True)

    class Meta:
        model = InventoryReturn
        fields = '__all__'
        read_only_fields = ['school', 'return_number', 'created_at']


class InventoryStockAdjustmentItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.item_name', read_only=True)
    variant_size = serializers.CharField(source='variant.size', read_only=True)

    class Meta:
        model = InventoryStockAdjustmentItem
        fields = '__all__'


class InventoryStockAdjustmentSerializer(serializers.ModelSerializer):
    items = InventoryStockAdjustmentItemSerializer(many=True, read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.warehouse_name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = InventoryStockAdjustment
        fields = '__all__'
        read_only_fields = ['school', 'adjustment_number', 'created_at']


class InventoryBudgetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = InventoryBudget
        fields = '__all__'
        read_only_fields = ['school', 'created_at']
