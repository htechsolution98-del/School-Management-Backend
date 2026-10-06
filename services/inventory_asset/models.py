from django.db import models


class ItemCategory(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "service_inventory_item_category"

    def __str__(self):
        return self.name


class ItemSize(models.Model):
    size = models.CharField(max_length=50)

    class Meta:
        db_table = "service_inventory_item_size"


class ItemColor(models.Model):
    color = models.CharField(max_length=50)

    class Meta:
        db_table = "service_inventory_item_color"


class Item(models.Model):
    name = models.CharField(max_length=255)
    category = models.ForeignKey(ItemCategory, on_delete=models.CASCADE)
    code = models.CharField(max_length=100, unique=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_in_stock = models.IntegerField(default=0)

    class Meta:
        db_table = "service_inventory_item"

    def __str__(self):
        return self.name


class Supplier(models.Model):
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)

    class Meta:
        db_table = "service_inventory_supplier"


class StockTransaction(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="transactions")
    transaction_type = models.CharField(max_length=50)  # IN / OUT
    quantity = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "service_inventory_stock_transaction"


class Asset(models.Model):
    asset_name = models.CharField(max_length=255)
    asset_code = models.CharField(max_length=100, unique=True)
    purchase_date = models.DateField()
    cost = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "inventory_asset"
