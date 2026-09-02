from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Sum, Count, F, Q, DecimalField
from django.utils import timezone
from decimal import Decimal

from .models import *
from .serializer import *
from .permissions import Isinventory, Isteacher
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
from .inventory_serializers import (
    InventoryCategorySerializer,
    InventorySubCategorySerializer,
    InventoryUnitSerializer,
    InventoryItemSerializer,
    InventoryItemVariantSerializer,
    InventoryWarehouseSerializer,
    InventorySupplierSerializer,
    InventoryStockBalanceSerializer,
    InventoryTransactionSerializer,
    InventoryOpeningStockSerializer,
    InventoryPurchaseSerializer,
    PurchaseRequestSerializer,
    StudentInventoryIssueSerializer,
    StudentIDCardSerializer,
    InventoryBundleSerializer,
    InventoryReturnSerializer,
    InventoryStockAdjustmentSerializer,
    InventoryBudgetSerializer,
)
from .inventory_services import (
    record_stock_transaction,
    process_opening_stock,
    process_purchase_grn,
    process_student_issue,
    process_id_card_issue,
    process_id_card_replacement,
    process_stock_adjustment,
    process_return,
    process_warehouse_transfer,
)


class InventoryCategoryViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventoryCategorySerializer
    queryset = InventoryCategory.objects.all()

    def get_queryset(self):
        return InventoryCategory.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class InventorySubCategoryViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventorySubCategorySerializer
    queryset = InventorySubCategory.objects.all()

    def get_queryset(self):
        return InventorySubCategory.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class InventoryUnitViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventoryUnitSerializer
    queryset = InventoryUnit.objects.all()

    def get_queryset(self):
        return InventoryUnit.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class InventoryWarehouseViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventoryWarehouseSerializer
    queryset = InventoryWarehouse.objects.all()

    def get_queryset(self):
        return InventoryWarehouse.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class InventorySupplierViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventorySupplierSerializer
    queryset = InventorySupplier.objects.all()

    def get_queryset(self):
        return InventorySupplier.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class InventoryItemViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventoryItemSerializer
    queryset = InventoryItem.objects.all()

    def get_queryset(self):
        qs = InventoryItem.objects.filter(school=self.request.user.school).select_related('category', 'sub_category').prefetch_related('variants')
        category_id = self.request.query_params.get('category')
        item_type = self.request.query_params.get('item_type')
        search = self.request.query_params.get('search')
        if category_id:
            qs = qs.filter(category_id=category_id)
        if item_type:
            qs = qs.filter(item_type=item_type)
        if search:
            qs = qs.filter(Q(item_name__icontains=search) | Q(item_code__icontains=search) | Q(barcode__icontains=search))
        return qs

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)

    @action(detail=True, methods=['post'], url_path='add-variant')
    def add_variant(self, request, pk=None):
        item = self.get_object()
        serializer = InventoryItemVariantSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(item=item)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class InventoryItemVariantViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventoryItemVariantSerializer
    queryset = InventoryItemVariant.objects.all()

    def get_queryset(self):
        return InventoryItemVariant.objects.filter(item__school=self.request.user.school)


class InventoryStockBalanceViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventoryStockBalanceSerializer
    queryset = InventoryStockBalance.objects.all()

    def get_queryset(self):
        qs = InventoryStockBalance.objects.filter(school=self.request.user.school).select_related('item', 'variant', 'warehouse', 'item__category')
        warehouse_id = self.request.query_params.get('warehouse')
        low_stock = self.request.query_params.get('low_stock')
        category_id = self.request.query_params.get('category')
        search = self.request.query_params.get('search')

        if warehouse_id:
            qs = qs.filter(warehouse_id=warehouse_id)
        if category_id:
            qs = qs.filter(item__category_id=category_id)
        if search:
            qs = qs.filter(Q(item__item_name__icontains=search) | Q(item__item_code__icontains=search))
        if low_stock == 'true':
            qs = qs.filter(available_quantity__lte=F('item__minimum_stock'))
        return qs


class InventoryTransactionViewSet(ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventoryTransactionSerializer
    queryset = InventoryTransaction.objects.all()

    def get_queryset(self):
        qs = InventoryTransaction.objects.filter(school=self.request.user.school).select_related('item', 'variant', 'warehouse', 'to_warehouse', 'created_by')
        item_id = self.request.query_params.get('item')
        warehouse_id = self.request.query_params.get('warehouse')
        tx_type = self.request.query_params.get('transaction_type')
        direction = self.request.query_params.get('direction')
        search = self.request.query_params.get('search')

        if item_id:
            qs = qs.filter(item_id=item_id)
        if warehouse_id:
            qs = qs.filter(Q(warehouse_id=warehouse_id) | Q(to_warehouse_id=warehouse_id))
        if tx_type:
            qs = qs.filter(transaction_type=tx_type)
        if direction:
            qs = qs.filter(direction=direction)
        if search:
            qs = qs.filter(Q(transaction_number__icontains=search) | Q(item__item_name__icontains=search) | Q(remarks__icontains=search))
        return qs


class InventoryOpeningStockViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventoryOpeningStockSerializer
    queryset = InventoryOpeningStock.objects.all()

    def get_queryset(self):
        return InventoryOpeningStock.objects.filter(school=self.request.user.school)

    def create(self, request, *args, **kwargs):
        school = request.user.school
        item_id = request.data.get('item')
        variant_id = request.data.get('variant')
        warehouse_id = request.data.get('warehouse')
        quantity = int(request.data.get('quantity', 0))
        unit_cost = Decimal(str(request.data.get('unit_cost', 0.00)))
        remarks = request.data.get('remarks', 'Initial Opening Stock Entry')

        if quantity <= 0:
            return Response({"error": "Quantity must be greater than 0."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = InventoryItem.objects.get(id=item_id, school=school)
            warehouse = InventoryWarehouse.objects.get(id=warehouse_id, school=school)
            variant = InventoryItemVariant.objects.get(id=variant_id, item=item) if variant_id else None

            opening, txn = process_opening_stock(
                school=school,
                item=item,
                warehouse=warehouse,
                quantity=quantity,
                unit_cost=unit_cost,
                variant=variant,
                remarks=remarks,
                created_by=request.user,
            )
            serializer = self.get_serializer(opening)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InventoryPurchaseViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventoryPurchaseSerializer
    queryset = InventoryPurchase.objects.all()

    def get_queryset(self):
        return InventoryPurchase.objects.filter(school=self.request.user.school).prefetch_related('items')

    def create(self, request, *args, **kwargs):
        school = request.user.school
        supplier_id = request.data.get('supplier')
        warehouse_id = request.data.get('warehouse')
        invoice_number = request.data.get('invoice_number', '')
        invoice_date = request.data.get('invoice_date') or None
        purchase_date = request.data.get('purchase_date') or timezone.now().date()
        payment_status = request.data.get('payment_status', 'PENDING')
        remarks = request.data.get('remarks', '')
        items_data = request.data.get('items', [])

        if not warehouse_id:
            return Response({"error": "Warehouse is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not items_data:
            return Response({"error": "At least one item is required in the purchase order."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            supplier = InventorySupplier.objects.get(id=supplier_id, school=school) if supplier_id else None
            warehouse = InventoryWarehouse.objects.get(id=warehouse_id, school=school)

            subtotal = Decimal('0.00')
            for it in items_data:
                q = int(it.get('quantity', 1))
                p = Decimal(str(it.get('unit_price', 0.00)))
                subtotal += q * p

            tax_amount = Decimal(str(request.data.get('tax_amount', 0.00)))
            discount_amount = Decimal(str(request.data.get('discount_amount', 0.00)))
            total_amount = subtotal + tax_amount - discount_amount

            purchase_number = f"PO-{timezone.now().strftime('%Y%m%d')}-{InventoryPurchase.objects.count() + 1:04d}"

            purchase = InventoryPurchase.objects.create(
                school=school,
                purchase_number=purchase_number,
                supplier=supplier,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                purchase_date=purchase_date,
                warehouse=warehouse,
                subtotal=subtotal,
                tax_amount=tax_amount,
                discount_amount=discount_amount,
                total_amount=total_amount,
                payment_status=payment_status,
                status='RECEIVED',
                remarks=remarks,
                created_by=request.user,
            )

            for it in items_data:
                item_obj = InventoryItem.objects.get(id=it['item_id'], school=school)
                variant_obj = InventoryItemVariant.objects.get(id=it['variant_id'], item=item_obj) if it.get('variant_id') else None
                qty = int(it.get('quantity', 1))
                unit_price = Decimal(str(it.get('unit_price', 0.00)))
                total_price = qty * unit_price

                InventoryPurchaseItem.objects.create(
                    purchase=purchase,
                    item=item_obj,
                    variant=variant_obj,
                    quantity=qty,
                    received_quantity=qty,
                    unit_price=unit_price,
                    total_price=total_price,
                    batch_number=it.get('batch_number', ''),
                )

            # Auto-stock into warehouse
            process_purchase_grn(purchase, user=request.user)

            serializer = self.get_serializer(purchase)
            return Response(serializer.data, status=status.HTTP_201_CREATED)


class PurchaseRequestViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PurchaseRequestSerializer
    queryset = PurchaseRequest.objects.all()

    def get_queryset(self):
        return PurchaseRequest.objects.filter(school=self.request.user.school)

    def create(self, request, *args, **kwargs):
        school = request.user.school
        request_number = f"PR-{timezone.now().strftime('%Y%m%d')}-{PurchaseRequest.objects.count() + 1:04d}"
        items_data = request.data.get('items', [])

        with transaction.atomic():
            pr = PurchaseRequest.objects.create(
                school=school,
                request_number=request_number,
                requested_by=getattr(request.user, 'staff', None),
                department=request.data.get('department', ''),
                priority=request.data.get('priority', 'MEDIUM'),
                status='PENDING',
                remarks=request.data.get('remarks', ''),
            )

            for it in items_data:
                item = InventoryItem.objects.get(id=it['item_id'], school=school)
                variant = InventoryItemVariant.objects.get(id=it['variant_id'], item=item) if it.get('variant_id') else None
                qty = int(it.get('requested_quantity', 1))
                cost = Decimal(str(it.get('estimated_cost', item.purchase_price * qty)))

                PurchaseRequestItem.objects.create(
                    purchase_request=pr,
                    item=item,
                    variant=variant,
                    requested_quantity=qty,
                    approved_quantity=qty,
                    estimated_cost=cost,
                    remarks=it.get('remarks', ''),
                )

            serializer = self.get_serializer(pr)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='review')
    def review(self, request, pk=None):
        pr = self.get_object()
        new_status = request.data.get('status')
        if new_status not in ['APPROVED', 'REJECTED']:
            return Response({"error": "Status must be APPROVED or REJECTED."}, status=status.HTTP_400_BAD_REQUEST)
        pr.status = new_status
        pr.remarks = request.data.get('remarks', pr.remarks)
        pr.save()
        return Response(self.get_serializer(pr).data)


class StudentInventoryIssueViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = StudentInventoryIssueSerializer
    queryset = StudentInventoryIssue.objects.all()

    def get_queryset(self):
        qs = StudentInventoryIssue.objects.filter(school=self.request.user.school).select_related('student', 'warehouse', 'issued_by').prefetch_related('items')
        student_id = self.request.query_params.get('student')
        payment_status = self.request.query_params.get('payment_status')
        search = self.request.query_params.get('search')
        if student_id:
            qs = qs.filter(student_id=student_id)
        if payment_status:
            qs = qs.filter(payment_status=payment_status)
        if search:
            qs = qs.filter(Q(issue_number__icontains=search) | Q(student__name__icontains=search))
        return qs

    def create(self, request, *args, **kwargs):
        school = request.user.school
        student_id = request.data.get('student')
        warehouse_id = request.data.get('warehouse')
        items_data = request.data.get('items', [])
        bundle_id = request.data.get('bundle_id')
        paid_amount = Decimal(str(request.data.get('paid_amount', 0.00)))
        payment_status = request.data.get('payment_status', 'PAID')
        remarks = request.data.get('remarks', '')

        if not student_id:
            return Response({"error": "Student is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not warehouse_id:
            return Response({"error": "Warehouse is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(id=student_id, school=school)
            warehouse = InventoryWarehouse.objects.get(id=warehouse_id, school=school)

            # If bundle is selected and items_data is empty, resolve bundle items
            if bundle_id and not items_data:
                bundle = InventoryBundle.objects.get(id=bundle_id, school=school)
                for b_item in bundle.items.all():
                    items_data.append({
                        'item_id': b_item.item_id,
                        'variant_id': b_item.variant_id,
                        'quantity': b_item.quantity,
                        'unit_price': b_item.item.issue_price or b_item.item.selling_price or 0.00,
                        'is_returnable': False,
                    })

            if not items_data:
                return Response({"error": "Please select at least one item or kit to issue."}, status=status.HTTP_400_BAD_REQUEST)

            issue = process_student_issue(
                school=school,
                student=student,
                warehouse=warehouse,
                items_data=items_data,
                academic_year=getattr(student, 'academic_year', None),
                paid_amount=paid_amount,
                payment_status=payment_status,
                remarks=remarks,
                issued_by=request.user,
            )

            serializer = self.get_serializer(issue)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StudentIDCardViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = StudentIDCardSerializer
    queryset = StudentIDCard.objects.all()

    def get_queryset(self):
        qs = StudentIDCard.objects.filter(school=self.request.user.school).select_related('student', 'previous_card')
        status_filter = self.request.query_params.get('status')
        student_id = self.request.query_params.get('student')
        search = self.request.query_params.get('search')
        if status_filter:
            qs = qs.filter(issue_status=status_filter)
        if student_id:
            qs = qs.filter(student_id=student_id)
        if search:
            qs = qs.filter(Q(card_number__icontains=search) | Q(student__name__icontains=search))
        return qs

    def create(self, request, *args, **kwargs):
        school = request.user.school
        student_id = request.data.get('student')
        card_number = request.data.get('card_number') or f"ID-{timezone.now().strftime('%Y%m')}-{student_id}"
        card_serial_number = request.data.get('card_serial_number', '')
        expiry_date = request.data.get('expiry_date') or None
        remarks = request.data.get('remarks', 'Standard Student ID Card Issuance')

        # Optional blank ID card stock deduction
        item_id = request.data.get('deduct_stock_item')
        warehouse_id = request.data.get('warehouse')
        stock_item = InventoryItem.objects.filter(id=item_id, school=school).first() if item_id else None
        warehouse = InventoryWarehouse.objects.filter(id=warehouse_id, school=school).first() if warehouse_id else None

        try:
            student = Student.objects.get(id=student_id, school=school)
            card = process_id_card_issue(
                school=school,
                student=student,
                card_number=card_number,
                card_serial_number=card_serial_number,
                expiry_date=expiry_date,
                issued_by=request.user,
                remarks=remarks,
                deduct_stock_item=stock_item,
                warehouse=warehouse,
            )
            serializer = self.get_serializer(card)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='replace')
    def replace(self, request, pk=None):
        old_card = self.get_object()
        new_card_number = request.data.get('new_card_number') or f"{old_card.card_number}-R{old_card.replacement_cards.count() + 1}"
        reason = request.data.get('reason', 'LOST')
        item_id = request.data.get('deduct_stock_item')
        warehouse_id = request.data.get('warehouse')
        stock_item = InventoryItem.objects.filter(id=item_id, school=request.user.school).first() if item_id else None
        warehouse = InventoryWarehouse.objects.filter(id=warehouse_id, school=request.user.school).first() if warehouse_id else None

        try:
            new_card = process_id_card_replacement(
                school=request.user.school,
                old_card=old_card,
                new_card_number=new_card_number,
                card_serial_number=request.data.get('card_serial_number', ''),
                reason=reason,
                issued_by=request.user,
                deduct_stock_item=stock_item,
                warehouse=warehouse,
            )
            serializer = self.get_serializer(new_card)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InventoryBundleViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventoryBundleSerializer
    queryset = InventoryBundle.objects.all()

    def get_queryset(self):
        return InventoryBundle.objects.filter(school=self.request.user.school).prefetch_related('items')

    def create(self, request, *args, **kwargs):
        school = request.user.school
        bundle_code = request.data.get('bundle_code') or f"KIT-{InventoryBundle.objects.count() + 1:03d}"
        bundle_name = request.data.get('bundle_name')
        description = request.data.get('description', '')
        class_id = request.data.get('applicable_class')
        gender = request.data.get('applicable_gender', 'UNISEX')
        total_price = Decimal(str(request.data.get('total_price', 0.00)))
        items_data = request.data.get('items', [])

        with transaction.atomic():
            school_class = SchoolClass.objects.get(id=class_id, school=school) if class_id else None
            bundle = InventoryBundle.objects.create(
                school=school,
                bundle_code=bundle_code,
                bundle_name=bundle_name,
                description=description,
                applicable_class=school_class,
                applicable_gender=gender,
                total_price=total_price,
            )

            for row in items_data:
                item = InventoryItem.objects.get(id=row['item_id'], school=school)
                variant = InventoryItemVariant.objects.get(id=row['variant_id'], item=item) if row.get('variant_id') else None
                InventoryBundleItem.objects.create(
                    bundle=bundle,
                    item=item,
                    variant=variant,
                    quantity=int(row.get('quantity', 1)),
                )

            serializer = self.get_serializer(bundle)
            return Response(serializer.data, status=status.HTTP_201_CREATED)


class InventoryReturnViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventoryReturnSerializer
    queryset = InventoryReturn.objects.all()

    def get_queryset(self):
        return InventoryReturn.objects.filter(school=self.request.user.school).prefetch_related('items')

    def create(self, request, *args, **kwargs):
        school = request.user.school
        warehouse_id = request.data.get('warehouse')
        return_type = request.data.get('return_type', 'STUDENT')
        student_id = request.data.get('student')
        staff_id = request.data.get('staff')
        condition = request.data.get('condition', 'GOOD')
        remarks = request.data.get('remarks', '')
        items_data = request.data.get('items', [])

        if not warehouse_id:
            return Response({"error": "Warehouse is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not items_data:
            return Response({"error": "Items list is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            warehouse = InventoryWarehouse.objects.get(id=warehouse_id, school=school)
            student = Student.objects.get(id=student_id, school=school) if student_id else None
            staff = Staff.objects.get(id=staff_id, school=school) if staff_id else None

            ret_record = process_return(
                school=school,
                warehouse=warehouse,
                return_type=return_type,
                items_data=items_data,
                student=student,
                staff=staff,
                condition=condition,
                remarks=remarks,
                received_by=request.user,
            )
            serializer = self.get_serializer(ret_record)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InventoryStockAdjustmentViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = InventoryStockAdjustmentSerializer
    queryset = InventoryStockAdjustment.objects.all()

    def get_queryset(self):
        return InventoryStockAdjustment.objects.filter(school=self.request.user.school).prefetch_related('items')

    def create(self, request, *args, **kwargs):
        school = request.user.school
        warehouse_id = request.data.get('warehouse')
        reason = request.data.get('reason', 'PHYSICAL_COUNT')
        remarks = request.data.get('remarks', '')
        items_data = request.data.get('items', [])

        if not warehouse_id:
            return Response({"error": "Warehouse is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not items_data:
            return Response({"error": "At least one item is required for stock adjustment."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            warehouse = InventoryWarehouse.objects.get(id=warehouse_id, school=school)
            adjustment = process_stock_adjustment(
                school=school,
                warehouse=warehouse,
                reason=reason,
                items_data=items_data,
                remarks=remarks,
                created_by=request.user,
            )
            serializer = self.get_serializer(adjustment)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InventoryWarehouseTransferAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        school = request.user.school
        from_wh_id = request.data.get('from_warehouse')
        to_wh_id = request.data.get('to_warehouse')
        item_id = request.data.get('item')
        variant_id = request.data.get('variant')
        quantity = int(request.data.get('quantity', 0))
        remarks = request.data.get('remarks', '')

        if quantity <= 0:
            return Response({"error": "Transfer quantity must be > 0."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from_wh = InventoryWarehouse.objects.get(id=from_wh_id, school=school)
            to_wh = InventoryWarehouse.objects.get(id=to_wh_id, school=school)
            item = InventoryItem.objects.get(id=item_id, school=school)
            variant = InventoryItemVariant.objects.get(id=variant_id, item=item) if variant_id else None

            # Verify available balance at source
            bal = InventoryStockBalance.objects.filter(school=school, item=item, variant=variant, warehouse=from_wh).first()
            if not bal or bal.available_quantity < quantity:
                return Response({"error": f"Insufficient stock available at {from_wh.warehouse_name}. Available: {bal.available_quantity if bal else 0}"}, status=status.HTTP_400_BAD_REQUEST)

            txn_out, txn_in = process_warehouse_transfer(
                school=school,
                item=item,
                from_warehouse=from_wh,
                to_warehouse=to_wh,
                quantity=quantity,
                variant=variant,
                remarks=remarks,
                user=request.user,
            )

            return Response({
                "message": "Stock transferred successfully.",
                "out_transaction": txn_out.transaction_number,
                "in_transaction": txn_in.transaction_number,
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InventoryDashboardSummaryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school = request.user.school
        today = timezone.now().date()

        # Item & Stock calculations
        total_items = InventoryItem.objects.filter(school=school, is_active=True).count()
        balances = InventoryStockBalance.objects.filter(school=school).select_related('item', 'variant')

        total_units = sum(b.available_quantity for b in balances)
        total_damaged = sum(b.damaged_quantity for b in balances)

        total_valuation = sum(
            (b.available_quantity * (b.variant.purchase_price if b.variant and b.variant.purchase_price > 0 else b.item.purchase_price))
            for b in balances if b.available_quantity > 0
        )

        low_stock_items = balances.filter(available_quantity__lte=F('item__minimum_stock')).count()
        out_of_stock_items = balances.filter(available_quantity__lte=0).count()

        # Student Distributions
        today_issues_count = StudentInventoryIssue.objects.filter(school=school, issue_date=today).count()
        total_uniforms_issued = StudentInventoryIssueItem.objects.filter(student_issue__school=school, item__item_type='STUDENT_ITEM').aggregate(total=Sum('quantity'))['total'] or 0
        total_id_cards_active = StudentIDCard.objects.filter(school=school, issue_status='ACTIVE').count()
        total_id_cards_lost = StudentIDCard.objects.filter(school=school, issue_status__in=['LOST', 'DAMAGED', 'REPLACED']).count()

        # Procurement & Budget
        pending_purchase_requests = PurchaseRequest.objects.filter(school=school, status='PENDING').count()
        pending_purchase_orders = InventoryPurchase.objects.filter(school=school, payment_status='PENDING').count()

        # Recent transactions
        recent_txns = InventoryTransaction.objects.filter(school=school).select_related('item', 'warehouse', 'variant').order_by('-id')[:10]
        recent_txns_data = InventoryTransactionSerializer(recent_txns, many=True).data

        # Category distribution
        categories = InventoryCategory.objects.filter(school=school).annotate(item_count=Count('items'))
        category_breakdown = [{'name': c.name, 'count': c.item_count} for c in categories]

        return Response({
            "overview": {
                "total_items": total_items,
                "total_stock_units": total_units,
                "total_valuation": float(total_valuation),
                "low_stock_count": low_stock_items,
                "out_of_stock_count": out_of_stock_items,
                "damaged_units": total_damaged,
                "today_issues_count": today_issues_count,
                "uniforms_distributed": total_uniforms_issued,
                "active_id_cards": total_id_cards_active,
                "replaced_id_cards": total_id_cards_lost,
                "pending_purchase_requests": pending_purchase_requests,
                "pending_purchase_orders": pending_purchase_orders,
            },
            "category_breakdown": category_breakdown,
            "recent_transactions": recent_txns_data,
        })


# ==========================================================
# Legacy Models & Viewsets (Retained for full backward compatibility)
# ==========================================================

class StockItemsViewset(ModelViewSet):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        else:
            return [IsAuthenticated(), Isinventory()]

    queryset = StockItems.objects.all()
    serializer_class = StockItemsSerializer

    def get_queryset(self):
        return StockItems.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class StockRequestViewset(ModelViewSet):
    permission_classes = [IsAuthenticated, Isteacher]
    queryset = StockRequest.objects.all()
    serializer_class = StockRequestSerializer

    def get_queryset(self):
        if self.request.user.groups.filter(name="INVENTORY").exists():
            return StockRequest.objects.filter(school=self.request.user.school)
        return StockRequest.objects.filter(teacher=self.request.user.staff)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school, teacher=self.request.user.staff)


class InventoryStockRequestViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, Isinventory]
    serializer_class = StockRequestSerializer
    queryset = StockRequest.objects.all()

    def get_queryset(self):
        return StockRequest.objects.filter(school=self.request.user.school)

    def partial_update(self, request, *args, **kwargs):
        stock_request = self.get_object()
        if stock_request.status != "pending":
            return Response({"error": "Request has already been processed."}, status=status.HTTP_400_BAD_REQUEST)

        status_value = request.data.get("status")
        if status_value not in ["approved", "rejected"]:
            return Response({"error": "Status must be 'approved' or 'rejected'."}, status=status.HTTP_400_BAD_REQUEST)

        if status_value == "approved":
            item = stock_request.stock_item
            if item.quantity < stock_request.quantity:
                return Response({"error": "Insufficient stock available."}, status=status.HTTP_400_BAD_REQUEST)
            item.quantity -= stock_request.quantity
            item.save()

        stock_request.status = status_value
        stock_request.save()
        serializer = self.get_serializer(stock_request)
        return Response(serializer.data)


class AssetViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Asset.objects.all()
    serializer_class = AssetSerializer

    def get_queryset(self):
        return Asset.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class AssetMaintenanceViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = AssetMaintenance.objects.all()
    serializer_class = AssetMaintenanceSerializer

    def get_queryset(self):
        return AssetMaintenance.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class ProcurementViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Procurement.objects.all()
    serializer_class = ProcurementSerializer

    def get_queryset(self):
        return Procurement.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)

    def perform_update(self, serializer):
        procurement = serializer.save()
        if procurement.status == "received":
            procurement.restock()


class ProcurementItemViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = ProcurementItem.objects.all()
    serializer_class = ProcurementItemSerializer

    def get_queryset(self):
        return ProcurementItem.objects.filter(procurement__school=self.request.user.school)


class LossPreventionViewset(ModelViewSet):
    queryset = LossPrevention.objects.all()
    serializer_class = LosspreventionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return LossPrevention.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class BudgetViewset(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Budget.objects.all()
    serializer_class = BudgetSerializer

    def get_queryset(self):
        return Budget.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class BudgetExpenseViewset(ModelViewSet):
    permission_classes = [IsAuthenticated]
    queryset = BudgetExpense.objects.all()
    serializer_class = BudgetExpenseSerializer

    def get_queryset(self):
        return BudgetExpense.objects.filter(budget__school=self.request.user.school)


class PostTrackingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostTracking
        fields = "__all__"
        read_only_fields = ["school"]


class PostTrackingViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PostTrackingSerializer
    queryset = PostTracking.objects.all()

    def get_queryset(self):
        return PostTracking.objects.filter(school=self.request.user.school).order_by("-post_date", "-id")

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)
