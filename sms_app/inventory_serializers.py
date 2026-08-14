from rest_framework import serializers
from .models import *

class StockItemsSerializer(serializers.ModelSerializer):
    class Meta:
        model=StockItems
        fields=["id","name","category","quantity","min_quantity"]



class StockRequestSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = StockRequest
        fields = [
            "id",
            "stock_item",
            "quantity",
            "status",
            "teacher",
            "teacher_name",
        ]
        read_only_fields = ["teacher", "teacher_name"]

    def get_teacher_name(self, obj):
        return " ".join(
            filter(
                None,
                [
                    
                    obj.teacher.name
                    
                ],
            )
        )
        


class AssetSerializer(serializers.ModelSerializer):
    class Meta:
        model=Asset
        fields=["id","asset_name","category","asset_code","quantity","unit_price","purchase_date","total_value"]
    


class AssetMaintenanceSerializer(serializers.ModelSerializer):
    class Meta:
        model=AssetMaintenance
        fields=["id","asset","issue","maintance_date","status"]

        


class ProcurementSerializer(serializers.ModelSerializer):
    class Meta:
        model=Procurement
        fields=["id","supplier","purchase_date","status"]



class ProcurementItemSerializer(serializers.ModelSerializer):
    class Meta:
        model=ProcurementItem
        fields=["id","procurement","stock_item","quantity","unit_price"]



class LosspreventionSerializer(serializers.ModelSerializer):
    class Meta:
        model=LossPrevention
        fields=["id","maintenance","remark","replacement_cost","repair_cost","amount_saved"]



