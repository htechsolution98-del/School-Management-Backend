from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sms_app.inventory_views import (
    ItemCategoryViewSet,
    ItemSizeViewSet,
    ItemColorViewSet,
    ItemPricingViewSet,
    ItemViewSet,
    SupplierViewSet,
    PurchaseViewSet,
    StockTransactionViewSet,
    StockAdjustmentViewSet,
    StudentItemEntitlementViewSet,
    StudentItemIssueViewSet,
    ReplacementRequestViewSet,
    StudentItemReturnViewSet,
    InventoryReportViewSet,
)

router = DefaultRouter()
router.register(r"item-categories", ItemCategoryViewSet, basename="item-categories")
router.register(r"item-sizes", ItemSizeViewSet, basename="item-sizes")
router.register(r"item-colors", ItemColorViewSet, basename="item-colors")
router.register(r"item-pricing", ItemPricingViewSet, basename="item-pricing")
router.register(r"items", ItemViewSet, basename="items")
router.register(r"suppliers", SupplierViewSet, basename="suppliers")
router.register(r"purchases", PurchaseViewSet, basename="purchases")
router.register(r"stock-transactions", StockTransactionViewSet, basename="stock-transactions")
router.register(r"stock-adjustments", StockAdjustmentViewSet, basename="stock-adjustments")
router.register(r"student-entitlements", StudentItemEntitlementViewSet, basename="student-entitlements")
router.register(r"student-issues", StudentItemIssueViewSet, basename="student-issues")
router.register(r"replacements", ReplacementRequestViewSet, basename="replacements")
router.register(r"student-returns", StudentItemReturnViewSet, basename="student-returns")
router.register(r"reports", InventoryReportViewSet, basename="inventory-reports")

urlpatterns = [
    path("api/v1/inventory/", include(router.urls)),
]
