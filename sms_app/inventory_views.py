from rest_framework import viewsets, status
from rest_framework.exceptions import PermissionDenied, ValidationError as DRFValidationError, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, SAFE_METHODS
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Sum, Count, Q, F, DecimalField, ExpressionWrapper
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.http import HttpResponse
from decimal import Decimal
import json
from .inventory_reports import export_inventory_report_excel, export_inventory_report_pdf



def extract_clean_error_message(data, parent_key=None):
    if isinstance(data, str):
        cleaned = data.strip()
        if parent_key and parent_key.lower() not in ('error', 'detail', 'non_field_errors', 'items'):
            clean_parent = parent_key.replace('_', ' ').strip().capitalize()
            if clean_parent.lower() in cleaned.lower() or cleaned.endswith('.') or len(cleaned.split()) >= 4:
                return cleaned
            return f"{clean_parent}: {cleaned}"
        return cleaned
    if isinstance(data, (list, tuple)):
        for item in data:
            msg = extract_clean_error_message(item, parent_key)
            if msg:
                return msg
    if isinstance(data, dict):
        for k, v in data.items():
            key_name = parent_key if str(k).isdigit() else str(k)
            msg = extract_clean_error_message(v, key_name)
            if msg:
                return msg
    return str(data) if data is not None else "Validation error occurred."


def format_error_response(exc):
    """
    Standardized error response formatter for the Inventory module.
    Prevents 500 crashes and returns structured 400/403 JSON responses with exact error messages:
    {"error": "<specific message>", "detail": "<specific message>", "field_errors": {...}}
    """
    if isinstance(exc, PermissionDenied):
        msg = str(getattr(exc, 'detail', exc))
        return Response({
            "error": msg,
            "detail": msg,
            "field_errors": {"detail": [msg]}
        }, status=status.HTTP_403_FORBIDDEN)

    field_errors = {}
    main_error = "Validation error occurred."

    if isinstance(exc, DRFValidationError):
        main_error = extract_clean_error_message(exc.detail)
        field_errors = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": [str(exc.detail)]}

    elif isinstance(exc, DjangoValidationError):
        if hasattr(exc, 'message_dict'):
            field_errors = exc.message_dict
            main_error = extract_clean_error_message(exc.message_dict)
        elif hasattr(exc, 'messages'):
            main_error = exc.messages[0] if exc.messages else str(exc)
            field_errors["non_field_errors"] = list(exc.messages)
        else:
            main_error = str(exc)
            field_errors["non_field_errors"] = [main_error]

    elif isinstance(exc, IntegrityError):
        err_str = str(exc)
        err_lower = err_str.lower()
        if "item_code" in err_lower:
            main_error = "An item with this Item Code already exists."
            field_errors["item_code"] = [main_error]
        elif "item_name" in err_lower:
            main_error = "An item with this Item Name already exists."
            field_errors["item_name"] = [main_error]
        elif "gst_number" in err_lower:
            main_error = "This GST number is already registered to another supplier."
            field_errors["gst_number"] = [main_error]
        elif "phone" in err_lower:
            main_error = "This phone number is already registered to another supplier."
            field_errors["phone"] = [main_error]
        elif "email" in err_lower:
            main_error = "This email is already registered to another supplier."
            field_errors["email"] = [main_error]
        elif "supplier_name" in err_lower or "inventory_supplier" in err_lower:
            main_error = "A supplier with this name already exists."
            field_errors["supplier_name"] = [main_error]
        elif "hex_code" in err_lower:
            main_error = "A color variant with this hex code already exists."
            field_errors["hex_code"] = [main_error]
        elif "item_color" in err_lower or "itemcolor" in err_lower:
            main_error = "A color variant with this name already exists."
            field_errors["name"] = [main_error]
        elif "item_size" in err_lower or "itemsize" in err_lower:
            main_error = "A size variant with this name already exists."
            field_errors["name"] = [main_error]
        elif "item_category" in err_lower or "itemcategory" in err_lower:
            main_error = "A category with this name already exists."
            field_errors["name"] = [main_error]
        elif "foreign key" in err_lower or "foreign key constraint failed" in err_lower:
            main_error = "Referenced record does not exist or is currently linked to other transactions."
            field_errors["foreign_key"] = [main_error]
        else:
            main_error = f"Database constraint violation: {err_str.splitlines()[0] if err_str else 'Conflict detected.'}"
            field_errors["integrity"] = [main_error]

    else:
        main_error = str(exc) or "An unexpected error occurred."
        field_errors["non_field_errors"] = [main_error]

    if main_error.startswith("{") and ("error" in main_error or "detail" in main_error):
        try:
            parsed = json.loads(main_error.replace("'", '"'))
            if isinstance(parsed, dict):
                main_error = parsed.get("error") or parsed.get("detail") or str(next(iter(parsed.values())))
        except Exception:
            pass

    return Response({
        "error": main_error,
        "detail": main_error,
        "field_errors": field_errors
    }, status=status.HTTP_400_BAD_REQUEST)

from .inventory_models import (
    ItemCategory, ItemSize, ItemColor, Item, ItemPricing,
    Supplier, Purchase, PurchaseItem, StockTransaction,
    StudentItemEntitlement, StudentItemIssue, ReplacementRequest,
    StudentItemReturn, StockAdjustment, InventoryAuditLog, Requisition
)
from .inventory_serializers import (
    ItemCategorySerializer, ItemSizeSerializer, ItemColorSerializer,
    ItemPricingSerializer, ItemSerializer, SupplierSerializer,
    PurchaseSerializer, PurchaseItemSerializer, StockTransactionSerializer,
    StudentItemEntitlementSerializer, StudentItemIssueSerializer,
    ReplacementRequestSerializer, StudentItemReturnSerializer,
    StockAdjustmentSerializer, InventoryAuditLogSerializer, RequisitionSerializer
)
from .inventory_services import InventoryService
from .inventory_pdf_service import generate_purchase_invoice_pdf
from .models import School, AcademicYear, SchoolClass, Student, FeeType
from .permissions import Isinventory


def resolve_school_from_request(request):
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        if hasattr(user, 'school') and user.school:
            return user.school
        
        # Check if user is the school owner / admin
        school_owner = School.objects.filter(login_id=user.id).first()
        if school_owner:
            return school_owner

        # Check staff / clerk / teacher profile
        staff = getattr(user, 'staff_profile', None) or getattr(user, 'staff', None)
        if staff and getattr(staff, 'school', None):
            return staff.school

        # Check student profile
        student = getattr(user, 'student', None)
        if student and getattr(student, 'school', None):
            return student.school

    # A client supplied school id is only an explicit selector for superusers.
    # Ordinary users must resolve through their authenticated school/profile.
    school_id = (
        request.headers.get('X-School-ID') or
        request.headers.get('x-school-id') or
        request.query_params.get('school_id') or
        (request.data.get('school') if hasattr(request, 'data') and isinstance(request.data, dict) else None)
    )
    if school_id:
        if user and user.is_authenticated and user.is_superuser:
            return School.objects.filter(id=school_id).first()
    return None


class BaseSchoolViewSet(viewsets.ModelViewSet):
    """Base ViewSet ensuring multi-tenant isolation by school and robust error handling"""
    permission_classes = [Isinventory]

    def get_school(self):
        school = resolve_school_from_request(self.request)
        if not school:
            raise PermissionDenied("Your account is not linked to a school.")
        return school

    def get_queryset(self):
        school = self.get_school()
        return self.queryset.filter(school=school)

    def perform_create(self, serializer):
        school = self.get_school()
        if not school:
            raise PermissionDenied("Your account is not linked to a school.")
        serializer.save(school=school)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['school'] = self.get_school()
        return context

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except Exception as exc:
            return format_error_response(exc)

    def update(self, request, *args, **kwargs):
        try:
            return super().update(request, *args, **kwargs)
        except Exception as exc:
            return format_error_response(exc)

    def partial_update(self, request, *args, **kwargs):
        try:
            return super().partial_update(request, *args, **kwargs)
        except Exception as exc:
            return format_error_response(exc)

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as exc:
            return format_error_response(exc)


class ItemCategoryViewSet(BaseSchoolViewSet):
    queryset = ItemCategory.objects.all().prefetch_related('items')
    serializer_class = ItemCategorySerializer

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [Isinventory()]

    def create(self, request, *args, **kwargs):
        try:
            school = self.get_school()
            name = (request.data.get('name') or '').strip()
            if not name:
                return Response(
                    {
                        "error": "Category name is required.",
                        "detail": "Category name is required.",
                        "field_errors": {"name": ["Category name is required."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            existing = ItemCategory.objects.filter(name__iexact=name).first()
            if existing:
                return Response(
                    {
                        "error": "A category with this name already exists.",
                        "detail": "A category with this name already exists.",
                        "field_errors": {"name": ["A category with this name already exists."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            return super().create(request, *args, **kwargs)
        except Exception as exc:
            return format_error_response(exc)

    def destroy(self, request, *args, **kwargs):
        try:
            category = self.get_object()
            if category.items.exists():
                return Response(
                    {
                        "error": "Cannot delete category with associated items. Reassign or remove items first.",
                        "detail": "Cannot delete category with associated items. Reassign or remove items first."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            return super().destroy(request, *args, **kwargs)
        except Exception as exc:
            return format_error_response(exc)


class ItemSizeViewSet(BaseSchoolViewSet):
    queryset = ItemSize.objects.all().prefetch_related('allowed_items')
    serializer_class = ItemSizeSerializer

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [Isinventory()]

    def create(self, request, *args, **kwargs):
        try:
            school = self.get_school()
            name = (request.data.get('name') or '').strip()
            if not name:
                return Response(
                    {
                        "error": "Size name is required.",
                        "detail": "Size name is required.",
                        "field_errors": {"name": ["Size name is required."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            existing = ItemSize.objects.filter(name__iexact=name).first()
            if existing:
                return Response(
                    {
                        "error": "A size variant with this name already exists.",
                        "detail": "A size variant with this name already exists.",
                        "field_errors": {"name": ["A size variant with this name already exists."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            return super().create(request, *args, **kwargs)
        except Exception as exc:
            return format_error_response(exc)

    def destroy(self, request, *args, **kwargs):
        try:
            size = self.get_object()
            has_txns = StockTransaction.objects.filter(size=size).exists()
            has_purchases = PurchaseItem.objects.filter(size=size).exists()
            has_issues = StudentItemIssue.objects.filter(size=size).exists()
            has_items = size.allowed_items.exists()
            if has_txns or has_purchases or has_issues or has_items:
                return Response(
                    {
                        "error": "Cannot delete size variant with associated items or transaction history.",
                        "detail": "Cannot delete size variant with associated items or transaction history."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            return super().destroy(request, *args, **kwargs)
        except Exception as exc:
            return format_error_response(exc)


class ItemColorViewSet(BaseSchoolViewSet):
    queryset = ItemColor.objects.all().prefetch_related('allowed_items')
    serializer_class = ItemColorSerializer

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [Isinventory()]

    def create(self, request, *args, **kwargs):
        try:
            school = self.get_school()
            name = (request.data.get('name') or '').strip()
            if not name:
                return Response(
                    {
                        "error": "Color name is required.",
                        "detail": "Color name is required.",
                        "field_errors": {"name": ["Color name is required."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            existing = ItemColor.objects.filter(name__iexact=name).first()
            if existing:
                return Response(
                    {
                        "error": "A color variant with this name already exists.",
                        "detail": "A color variant with this name already exists.",
                        "field_errors": {"name": ["A color variant with this name already exists."]}
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            hex_code = (request.data.get('hex_code') or '').strip()
            if hex_code:
                existing_hex = ItemColor.objects.filter(hex_code__iexact=hex_code).first()
                if existing_hex:
                    return Response(
                        {
                            "error": "A color variant with this hex code already exists.",
                            "detail": "A color variant with this hex code already exists.",
                            "field_errors": {"hex_code": ["A color variant with this hex code already exists."]}
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
            return super().create(request, *args, **kwargs)
        except Exception as exc:
            return format_error_response(exc)

    def destroy(self, request, *args, **kwargs):
        try:
            color = self.get_object()
            has_txns = StockTransaction.objects.filter(color=color).exists()
            has_purchases = PurchaseItem.objects.filter(color=color).exists()
            has_issues = StudentItemIssue.objects.filter(color=color).exists()
            has_items = color.allowed_items.exists()
            if has_txns or has_purchases or has_issues or has_items:
                return Response(
                    {
                        "error": "Cannot delete color variant with associated items or transaction history.",
                        "detail": "Cannot delete color variant with associated items or transaction history."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            return super().destroy(request, *args, **kwargs)
        except Exception as exc:
            return format_error_response(exc)


class ItemPricingViewSet(BaseSchoolViewSet):
    queryset = ItemPricing.objects.all()
    serializer_class = ItemPricingSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        item_id = self.request.query_params.get('item')
        academic_year_id = self.request.query_params.get('academic_year')
        if item_id:
            qs = qs.filter(item_id=item_id)
        if academic_year_id:
            qs = qs.filter(academic_year_id=academic_year_id)
        return qs

    def create(self, request, *args, **kwargs):
        try:
            school = self.get_school()
            data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
            if 'charging_policy' in data and 'charging_type' not in data:
                data['charging_type'] = data['charging_policy']
            if 'applicable_class' in data and 'school_class' not in data:
                data['school_class'] = data['applicable_class']

            item_id = data.get('item')
            academic_year_id = data.get('academic_year')
            school_class_id = data.get('school_class') or None

            # Upsert logic: check for existing pricing record for the same item, academic_year, and applicable_class
            existing = ItemPricing.objects.filter(
                school=school,
                item_id=item_id,
                academic_year_id=academic_year_id,
                school_class_id=school_class_id
            ).first()

            if existing:
                # Update existing record instead of creating duplicate row
                serializer = self.get_serializer(existing, data=data, partial=True)
                serializer.is_valid(raise_exception=True)
                serializer.save(school=school)
                return Response(serializer.data, status=status.HTTP_200_OK)

            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save(school=school)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return format_error_response(exc)


class ItemViewSet(BaseSchoolViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [Isinventory()]

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('allowed_sizes', 'allowed_colors')
        category_id = self.request.query_params.get('category')
        is_active = self.request.query_params.get('is_active')
        search = self.request.query_params.get('search')

        if category_id:
            qs = qs.filter(category_id=category_id)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        if search:
            qs = qs.filter(Q(item_name__icontains=search) | Q(item_code__icontains=search))
        return qs

    def perform_create(self, serializer):
        school = self.get_school()
        serializer.save(school=school, created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        try:
            item = self.get_object()

            total_stock = item.stock_transactions.aggregate(total=Sum('quantity'))['total'] or 0
            has_stock = total_stock > 0
            has_txns = item.stock_transactions.exists()
            has_purchases = item.purchase_items.exists()
            has_issues = item.item_issues.exists()
            has_adjustments = item.stock_adjustments.exists()
            has_entitlements = item.student_entitlements.exists()
            has_returns = item.item_returns.exists()
            has_replacements = item.replacement_requests.exists()

            if (has_stock or has_txns or has_purchases or has_issues or
                has_adjustments or has_entitlements or has_returns or has_replacements):
                return Response(
                    {
                        "error": "Cannot delete item with active stock/history.",
                        "detail": "Cannot delete item with active stock/history."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            item.delete()
            return Response({"message": "Item deleted successfully."}, status=status.HTTP_200_OK)
        except Exception as exc:
            return format_error_response(exc)

    @action(detail=False, methods=['get'], url_path='low-stock')
    def low_stock_items(self, request):
        """Return items where current stock <= minimum_stock_level"""
        school = self.get_school()
        items = Item.objects.filter(school=school, is_active=True)
        low_stock = []
        for item in items:
            total_stock = item.stock_transactions.aggregate(total=Sum('quantity'))['total'] or 0
            if total_stock <= item.minimum_stock_level:
                data = ItemSerializer(item).data
                data['current_stock'] = total_stock
                low_stock.append(data)
        return Response(low_stock)

    @action(detail=True, methods=['get'], url_path='variant-stock')
    def variant_stock(self, request, pk=None):
        """Return the variant-wise available stock matrix for an item"""
        item = self.get_object()
        school = self.get_school()

        stock_map = {}
        txns = (
            StockTransaction.objects.filter(school=school, item=item)
            .values('size_id', 'color_id')
            .annotate(total_qty=Sum('quantity'))
        )
        for t in txns:
            stock_map[(t['size_id'], t['color_id'])] = t['total_qty'] or 0

        # Resolve sizes
        if item.has_size:
            sizes = list(ItemSize.objects.filter(school=school, is_active=True))
            existing_size_ids = {s.id for s in sizes}
            historical_size_ids = {t['size_id'] for t in txns if t['size_id'] and t['size_id'] not in existing_size_ids}
            if historical_size_ids:
                sizes.extend(list(ItemSize.objects.filter(id__in=historical_size_ids)))
        else:
            sizes = [None]

        # Resolve colors
        if item.has_color:
            colors = list(ItemColor.objects.filter(school=school, is_active=True))
            existing_color_ids = {c.id for c in colors}
            historical_color_ids = {t['color_id'] for t in txns if t['color_id'] and t['color_id'] not in existing_color_ids}
            if historical_color_ids:
                colors.extend(list(ItemColor.objects.filter(id__in=historical_color_ids)))
        else:
            colors = [None]

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

        total_stock = max(0, item.stock_transactions.aggregate(total=Sum('quantity'))['total'] or 0)

        return Response({
            'item_id': item.id,
            'item_name': item.item_name,
            'has_size': item.has_size,
            'has_color': item.has_color,
            'unit': item.unit,
            'total_stock': total_stock,
            'variant_stock_matrix': matrix,
        })

    @action(detail=True, methods=['get'], url_path='variant_stock')
    def variant_stock_underscore(self, request, pk=None):
        return self.variant_stock(request, pk)


class SupplierViewSet(BaseSchoolViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer


class PurchaseViewSet(BaseSchoolViewSet):
    queryset = Purchase.objects.all()
    serializer_class = PurchaseSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset().select_related('supplier', 'academic_year').prefetch_related('items')
        from_date = self.request.query_params.get('from_date')
        to_date = self.request.query_params.get('to_date')
        status_filter = self.request.query_params.get('status')
        if from_date:
            qs = qs.filter(purchase_date__gte=from_date)
        if to_date:
            qs = qs.filter(purchase_date__lte=to_date)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @transaction.atomic
    def perform_create(self, serializer):
        school = self.get_school()
        if not school:
            raise PermissionDenied("Your account is not linked to a school.")
        purchase = serializer.save(school=school, created_by=self.request.user)
        if purchase.status == 'CONFIRMED':
            InventoryService.process_purchase_confirmation(purchase, self.request.user)

    @action(detail=True, methods=['post'], url_path='confirm')
    def confirm_purchase(self, request, pk=None):
        try:
            purchase = self.get_object()
            InventoryService.process_purchase_confirmation(purchase, request.user)
            return Response({'message': 'Purchase confirmed and stock updated successfully.'})
        except Exception as exc:
            return format_error_response(exc)

    @action(detail=True, methods=['get'], url_path='invoice-pdf')
    def download_invoice_pdf(self, request, pk=None):
        try:
            purchase = self.get_object()
            pdf_bytes = generate_purchase_invoice_pdf(purchase)
            filename = f"Purchase_Invoice_{purchase.invoice_number or purchase.id}.pdf"
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Access-Control-Expose-Headers'] = 'Content-Disposition'
            return response
        except Exception as exc:
            return format_error_response(exc)


class StockTransactionViewSet(BaseSchoolViewSet):
    queryset = StockTransaction.objects.all()
    serializer_class = StockTransactionSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def create(self, request, *args, **kwargs):
        return Response({
            'error': 'Use the opening-stock action or a purchase, issue, return, or adjustment workflow.',
            'detail': 'Use the opening-stock action or a purchase, issue, return, or adjustment workflow.'
        }, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def get_queryset(self):
        qs = super().get_queryset()
        item_id = self.request.query_params.get('item')
        transaction_type = self.request.query_params.get('transaction_type')
        from_date = self.request.query_params.get('from_date')
        to_date = self.request.query_params.get('to_date')

        if item_id:
            qs = qs.filter(item_id=item_id)
        if transaction_type:
            qs = qs.filter(transaction_type=transaction_type)
        if from_date:
            qs = qs.filter(transaction_date__gte=from_date)
        if to_date:
            qs = qs.filter(transaction_date__lte=to_date)
        return qs

    @action(detail=False, methods=['post'], url_path='opening-stock')
    @transaction.atomic
    def create_opening_stock(self, request):
        try:
            school = self.get_school()
            if not school:
                raise PermissionDenied("Your account is not linked to a school.")

            qty_raw = request.data.get('quantity')
            if qty_raw is None or str(qty_raw).strip() == '':
                raise DRFValidationError({'quantity': "Opening quantity is required."})
            try:
                quantity = int(qty_raw)
            except (ValueError, TypeError):
                raise DRFValidationError({'quantity': "Opening quantity must be a valid integer."})
            if quantity <= 0:
                raise DRFValidationError({'quantity': "Opening quantity must be greater than zero."})

            cost_raw = request.data.get('unit_cost')
            if cost_raw is None or str(cost_raw).strip() == '':
                raise DRFValidationError({'unit_cost': "Unit cost is required."})
            try:
                unit_cost = Decimal(str(cost_raw))
            except Exception:
                raise DRFValidationError({'unit_cost': "Unit cost must be a valid number."})
            if unit_cost < 0:
                raise DRFValidationError({'unit_cost': "Unit cost cannot be negative."})

            item_id = request.data.get('item')
            if not item_id:
                raise DRFValidationError({'item': "Please select an item."})
            item = Item.objects.filter(id=item_id, school=school).first()
            if not item:
                raise DRFValidationError({'item': "Selected item was not found in this school."})

            size_id = request.data.get('size') or None
            color_id = request.data.get('color') or None
            size = ItemSize.objects.filter(id=size_id, school=school).first() if size_id else None
            color = ItemColor.objects.filter(id=color_id, school=school).first() if color_id else None

            if item.has_size and not size:
                raise DRFValidationError({'size': f"Select a size for '{item.item_name}'."})
            if item.has_color and not color:
                raise DRFValidationError({'color': f"Select a color for '{item.item_name}'."})

            academic_year_id = request.data.get('academic_year')
            if not academic_year_id:
                raise DRFValidationError({'academic_year': "Please select an academic year."})
            acad_year = AcademicYear.objects.filter(id=academic_year_id, school=school).first()
            if not acad_year:
                raise DRFValidationError({'academic_year': "Selected academic year was not found in this school."})
            txn = StockTransaction.objects.create(
                school=school, item=item, academic_year=acad_year, size=size, color=color,
                transaction_type='OPENING', quantity=quantity, unit_purchase_cost=unit_cost,
                reference_type='OpeningStock', transaction_date=request.data.get('entry_date') or timezone.now().date(),
                remarks=request.data.get('remarks', 'Opening Stock Entry'), created_by=request.user
            )
            InventoryService.log_stock_transaction(txn, request.user)
            return Response(StockTransactionSerializer(txn).data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return format_error_response(exc)


class StudentItemEntitlementViewSet(BaseSchoolViewSet):
    queryset = StudentItemEntitlement.objects.all()
    serializer_class = StudentItemEntitlementSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        student_id = self.request.query_params.get('student')
        academic_year_id = self.request.query_params.get('academic_year')
        status_filter = self.request.query_params.get('status')
        if student_id:
            qs = qs.filter(student_id=student_id)
        if academic_year_id:
            qs = qs.filter(academic_year_id=academic_year_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    @action(detail=False, methods=['post'], url_path='generate-bulk')
    def generate_bulk(self, request):
        """Generate entitlement records for students by class and academic year"""
        try:
            school = self.get_school()
            academic_year_id = request.data.get('academic_year')
            class_id = request.data.get('school_class')
            division = request.data.get('division')
            item_id = request.data.get('item')
            try:
                quantity = int(request.data.get('quantity', 1))
                if quantity <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return Response({
                    'error': 'Quantity must be a positive whole number.',
                    'detail': 'Quantity must be a positive whole number.',
                    'field_errors': {'quantity': ['Quantity must be a positive whole number.']}
                }, status=status.HTTP_400_BAD_REQUEST)
            charging_type = request.data.get('charging_type', 'INCLUDED_IN_FEE')
            fee_type_id = request.data.get('fee_type')
            size_id = request.data.get('size')
            color_id = request.data.get('color')

            students_qs = Student.objects.filter(school=school, is_active=True)
            if class_id:
                students_qs = students_qs.filter(school_class_id=class_id)
            if division:
                students_qs = students_qs.filter(division=division)

            item = Item.objects.filter(id=item_id, school=school).first()
            if not item:
                raise DRFValidationError({'item': 'Selected item was not found in this school.'})
            acad_year = AcademicYear.objects.filter(id=academic_year_id, school=school).first()
            if not acad_year:
                raise DRFValidationError({'academic_year': 'Selected academic year was not found in this school.'})
            size = ItemSize.objects.filter(id=size_id, school=school).first() if size_id else None
            color = ItemColor.objects.filter(id=color_id, school=school).first() if color_id else None
            fee_type = FeeType.objects.filter(id=fee_type_id, school=school).first() if fee_type_id else None

            if item.has_size and not size:
                raise DRFValidationError({'size': f"Select a size for item '{item.item_name}'."})
            if item.has_color and not color:
                raise DRFValidationError({'color': f"Select a color for item '{item.item_name}'."})
            if charging_type not in {'INCLUDED_IN_FEE', 'SEPARATE_CHARGE', 'FREE'}:
                raise DRFValidationError({'charging_type': 'Invalid charging type.'})

            created_count = 0
            for student in students_qs:
                ent, created = StudentItemEntitlement.objects.get_or_create(
                    school=school,
                    academic_year=acad_year,
                    student=student,
                    item=item,
                    size=size,
                    color=color,
                    defaults={
                        'entitled_quantity': quantity,
                        'charging_type': charging_type,
                        'fee_type': fee_type,
                        'status': 'PENDING'
                    }
                )
                if created:
                    created_count += 1

            return Response({
                'message': f'Generated entitlements for {created_count} students.',
                'total_students_processed': students_qs.count()
            })
        except Exception as exc:
            return format_error_response(exc)


class StudentItemIssueViewSet(BaseSchoolViewSet):
    queryset = StudentItemIssue.objects.all()
    serializer_class = StudentItemIssueSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            'student', 'student__school_class', 'item', 'size', 'color', 'academic_year'
        )
        student_id = self.request.query_params.get('student')
        item_id = self.request.query_params.get('item')
        from_date = self.request.query_params.get('from_date')
        to_date = self.request.query_params.get('to_date')
        search = self.request.query_params.get('search')

        if student_id:
            qs = qs.filter(student_id=student_id)
        if item_id:
            qs = qs.filter(item_id=item_id)
        if from_date:
            qs = qs.filter(issue_date__gte=from_date)
        if to_date:
            qs = qs.filter(issue_date__lte=to_date)
        if search:
            qs = qs.filter(
                Q(student__name__icontains=search) |
                Q(student__surname__icontains=search) |
                Q(item__item_name__icontains=search) |
                Q(item__item_code__icontains=search)
            )
        return qs


    def create(self, request, *args, **kwargs):
        try:
            school = self.get_school()
            academic_year_id = request.data.get('academic_year')
            student_id = request.data.get('student')
            item_id = request.data.get('item')
            try:
                quantity = int(request.data.get('quantity', 1))
                charged_amount = Decimal(str(request.data['charged_amount'])) if 'charged_amount' in request.data else None
            except (TypeError, ValueError, ArithmeticError):
                return Response({
                    'error': 'Quantity and charged amount must be valid numbers.',
                    'detail': 'Quantity and charged amount must be valid numbers.',
                    'field_errors': {'quantity': ['Quantity and charged amount must be valid numbers.']}
                }, status=status.HTTP_400_BAD_REQUEST)
            size_id = request.data.get('size')
            color_id = request.data.get('color')
            charging_type = request.data.get('charging_type')
            issue_reason = request.data.get('issue_reason', 'INITIAL_ISSUE')
            remarks = request.data.get('remarks', '')

            student = Student.objects.filter(id=student_id, school=school).first()
            if not student:
                raise DRFValidationError({'student': 'Selected student was not found in this school.'})
            item = Item.objects.filter(id=item_id, school=school).first()
            if not item:
                raise DRFValidationError({'item': 'Selected item was not found in this school.'})
            acad_year = AcademicYear.objects.filter(id=academic_year_id, school=school).first()
            if not acad_year:
                raise DRFValidationError({'academic_year': 'Selected academic year was not found in this school.'})
            size = ItemSize.objects.filter(id=size_id, school=school).first() if size_id else None
            color = ItemColor.objects.filter(id=color_id, school=school).first() if color_id else None

            record = InventoryService.issue_item_single(
                school=school,
                academic_year=acad_year,
                student=student,
                item=item,
                quantity=quantity,
                size=size,
                color=color,
                charging_type=charging_type,
                charged_amount=charged_amount,
                issue_reason=issue_reason,
                remarks=remarks,
                user=request.user
            )
            return Response(StudentItemIssueSerializer(record).data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return format_error_response(exc)

    @action(detail=False, methods=['post'], url_path='bulk-issue')
    def bulk_issue(self, request):
        try:
            school = self.get_school()
            academic_year_id = request.data.get('academic_year')
            item_id = request.data.get('item')
            student_ids = request.data.get('student_ids', [])
            try:
                quantity_per_student = int(request.data.get('quantity_per_student', 1))
            except (TypeError, ValueError):
                return Response({
                    'error': 'Quantity per student must be a positive whole number.',
                    'detail': 'Quantity per student must be a positive whole number.',
                    'field_errors': {'quantity_per_student': ['Quantity per student must be a positive whole number.']}
                }, status=status.HTTP_400_BAD_REQUEST)
            size_id = request.data.get('size')
            color_id = request.data.get('color')

            item = Item.objects.filter(id=item_id, school=school).first()
            if not item:
                raise DRFValidationError({'item': 'Selected item was not found in this school.'})
            acad_year = AcademicYear.objects.filter(id=academic_year_id, school=school).first()
            if not acad_year:
                raise DRFValidationError({'academic_year': 'Selected academic year was not found in this school.'})
            size = ItemSize.objects.filter(id=size_id, school=school).first() if size_id else None
            color = ItemColor.objects.filter(id=color_id, school=school).first() if color_id else None

            issued_records = InventoryService.issue_item_bulk(
                school=school,
                academic_year=acad_year,
                item=item,
                student_ids=student_ids,
                quantity_per_student=quantity_per_student,
                size=size,
                color=color,
                user=request.user
            )
            return Response({
                'message': f'Successfully issued {len(issued_records) * quantity_per_student} items to {len(issued_records)} students.',
                'records_count': len(issued_records)
            })
        except Exception as exc:
            return format_error_response(exc)


class ReplacementRequestViewSet(BaseSchoolViewSet):
    queryset = ReplacementRequest.objects.all()
    serializer_class = ReplacementRequestSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    @action(detail=True, methods=['post'], url_path='approve')
    def approve_request(self, request, pk=None):
        try:
            replacement = self.get_object()
            if replacement.status != 'PENDING':
                raise DRFValidationError({'status': 'Only pending requests can be approved.'})
            replacement.status = 'APPROVED'
            replacement.reviewed_at = timezone.now()
            replacement.reviewed_by = request.user
            replacement.admin_remarks = request.data.get('admin_remarks', '')
            replacement.save()
            return Response({'message': 'Replacement request approved.'})
        except Exception as exc:
            return format_error_response(exc)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject_request(self, request, pk=None):
        try:
            replacement = self.get_object()
            if replacement.status != 'PENDING':
                raise DRFValidationError({'status': 'Only pending requests can be rejected.'})
            replacement.status = 'REJECTED'
            replacement.reviewed_at = timezone.now()
            replacement.reviewed_by = request.user
            replacement.admin_remarks = request.data.get('admin_remarks', '')
            replacement.save()
            return Response({'message': 'Replacement request rejected.'})
        except Exception as exc:
            return format_error_response(exc)

    @action(detail=True, methods=['post'], url_path='issue')
    def issue_replacement(self, request, pk=None):
        try:
            replacement = self.get_object()
            charging_type = request.data.get('charging_type', 'FREE')
            charged_amount = Decimal(str(request.data.get('charged_amount', '0.00')))
            record = InventoryService.process_replacement_issue(
                replacement=replacement,
                charging_type=charging_type,
                charged_amount=charged_amount,
                user=request.user
            )
            return Response({'message': 'Replacement item issued and stock updated.', 'issue_id': record.id})
        except Exception as exc:
            return format_error_response(exc)


class StudentItemReturnViewSet(BaseSchoolViewSet):
    queryset = StudentItemReturn.objects.all()
    serializer_class = StudentItemReturnSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    @transaction.atomic
    def perform_create(self, serializer):
        school = self.get_school()
        if not school:
            raise PermissionDenied("Your account is not linked to a school.")
        return_obj = serializer.save(school=school, received_by=self.request.user)
        InventoryService.process_return(return_obj, self.request.user)


class StockAdjustmentViewSet(BaseSchoolViewSet):
    queryset = StockAdjustment.objects.all()
    serializer_class = StockAdjustmentSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    @transaction.atomic
    def perform_create(self, serializer):
        school = self.get_school()
        if not school:
            raise PermissionDenied("Your account is not linked to a school.")
        adj = serializer.save(school=school, created_by=self.request.user)
        InventoryService.process_adjustment(adj, self.request.user)


class InventoryAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InventoryAuditLogSerializer
    permission_classes = [Isinventory]

    def get_queryset(self):
        school = resolve_school_from_request(self.request)
        if not school:
            raise PermissionDenied("Your account is not linked to a school.")
        qs = InventoryAuditLog.objects.filter(school=school)
        entity_type = self.request.query_params.get('entity_type')
        action_name = self.request.query_params.get('action')
        if entity_type:
            qs = qs.filter(entity_type=entity_type)
        if action_name:
            qs = qs.filter(action=action_name)
        return qs


def get_effective_issue_cost(issue):
    """
    Returns the unit purchase cost for a StudentItemIssue.
    If the issue has a recorded unit_purchase_cost > 0, returns it.
    Otherwise, retrieves the purchase cost from:
    1) ItemPricing for the issue's item, academic year, and student class
    2) Any active ItemPricing with purchase_cost > 0 for the item
    3) The latest PurchaseItem for the item
    4) The latest StockTransaction (PURCHASE or OPENING) for the item
    """
    if issue.unit_purchase_cost and issue.unit_purchase_cost > Decimal('0.00'):
        return issue.unit_purchase_cost
    item = getattr(issue, 'item', None)
    if item:
        pricing = None
        if getattr(issue, 'academic_year', None):
            class_id = issue.student.school_class_id if getattr(issue, 'student', None) and issue.student else None
            pricing_qs = item.pricings.filter(academic_year=issue.academic_year, is_active=True)
            if class_id:
                pricing = pricing_qs.filter(Q(school_class_id=class_id) | Q(school_class__isnull=True)).order_by('-school_class_id').first()
            else:
                pricing = pricing_qs.first()
        if pricing and pricing.purchase_cost and pricing.purchase_cost > Decimal('0.00'):
            return pricing.purchase_cost

        alt_pricing = item.pricings.filter(is_active=True, purchase_cost__gt=0).order_by('-academic_year__id').first()
        if alt_pricing and alt_pricing.purchase_cost and alt_pricing.purchase_cost > Decimal('0.00'):
            return alt_pricing.purchase_cost

        last_pi = item.purchase_items.filter(unit_cost__gt=0).order_by('-purchase__purchase_date', '-id').first()
        if last_pi and last_pi.unit_cost and last_pi.unit_cost > Decimal('0.00'):
            return last_pi.unit_cost

        last_tx = item.stock_transactions.filter(
            transaction_type__in=['PURCHASE', 'OPENING'],
            unit_purchase_cost__gt=0
        ).order_by('-transaction_date', '-id').first()
        if last_tx and last_tx.unit_purchase_cost and last_tx.unit_purchase_cost > Decimal('0.00'):
            return last_tx.unit_purchase_cost

    return Decimal('0.00')


class InventoryReportViewSet(viewsets.ViewSet):
    """Aggregated reporting endpoints for Purchase, Sales, P&L, Free Items, Replacements & Dashboard"""
    permission_classes = [Isinventory]

    def get_school(self):
        school = resolve_school_from_request(self.request)
        if not school:
            raise PermissionDenied("Your account is not linked to a school.")
        return school

    @action(detail=False, methods=['get'], url_path='dashboard-summary')
    def dashboard_summary(self, request):
        school = self.get_school()
        today = timezone.now().date()
        start_of_month = today.replace(day=1)

        total_items = Item.objects.filter(school=school, is_active=True).count()
        # Low stock and out of stock counts
        all_items = Item.objects.filter(school=school, is_active=True)
        low_stock_count = 0
        out_of_stock_count = 0
        total_stock_units = 0
        for it in all_items:
            stock = it.stock_transactions.aggregate(total=Sum('quantity'))['total'] or 0
            total_stock_units += max(0, stock)
            if stock <= 0:
                out_of_stock_count += 1
            elif stock <= it.minimum_stock_level:
                low_stock_count += 1

        # Today stats
        today_purchases = Purchase.objects.filter(school=school, purchase_date=today, status='CONFIRMED').aggregate(total=Sum('grand_total'))['total'] or Decimal('0.00')
        today_issues = StudentItemIssue.objects.filter(school=school, issue_date=today).aggregate(
            qty=Sum('quantity'),
            rev=Sum('charged_amount')
        )

        # Monthly stats
        month_purchases = Purchase.objects.filter(school=school, purchase_date__gte=start_of_month, status='CONFIRMED').aggregate(total=Sum('grand_total'))['total'] or Decimal('0.00')
        month_revenue = StudentItemIssue.objects.filter(school=school, issue_date__gte=start_of_month).aggregate(total=Sum('charged_amount'))['total'] or Decimal('0.00')

        pending_replacements = ReplacementRequest.objects.filter(school=school, status='PENDING').count()

        return Response({
            'total_items': total_items,
            'total_stock_units': total_stock_units,
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
            'today_purchases_amount': today_purchases,
            'today_issues_count': today_issues['qty'] or 0,
            'today_revenue': today_issues['rev'] or Decimal('0.00'),
            'month_purchases_amount': month_purchases,
            'month_revenue': month_revenue,
            'pending_replacements_count': pending_replacements,
        })

    @action(detail=False, methods=['get'], url_path='profit-loss')
    def profit_loss_report(self, request):
        school = self.get_school()
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        issues_qs = StudentItemIssue.objects.filter(school=school)
        purchases_qs = Purchase.objects.filter(school=school, status='CONFIRMED')
        adjustments_qs = StockAdjustment.objects.filter(school=school)

        if from_date:
            issues_qs = issues_qs.filter(issue_date__gte=from_date)
            purchases_qs = purchases_qs.filter(purchase_date__gte=from_date)
            adjustments_qs = adjustments_qs.filter(adjustment_date__gte=from_date)
        if to_date:
            issues_qs = issues_qs.filter(issue_date__lte=to_date)
            purchases_qs = purchases_qs.filter(purchase_date__lte=to_date)
            adjustments_qs = adjustments_qs.filter(adjustment_date__lte=to_date)

        total_purchase_cost = purchases_qs.aggregate(total=Sum('grand_total'))['total'] or Decimal('0.00')
        total_charged_revenue = issues_qs.aggregate(total=Sum('charged_amount'))['total'] or Decimal('0.00')

        # Cost of items issued
        total_issued_cost = Decimal('0.00')
        free_items_cost = Decimal('0.00')
        for issue in issues_qs:
            unit_c = get_effective_issue_cost(issue)
            cost = unit_c * issue.quantity
            total_issued_cost += cost
            if issue.charging_type == 'FREE':
                free_items_cost += cost

        gross_profit = total_charged_revenue - total_issued_cost

        total_items_sold = issues_qs.aggregate(total=Sum('quantity'))['total'] or 0

        return Response({
            'total_purchases': total_purchase_cost,
            'total_revenue': total_charged_revenue,
            'total_issued_cost': total_issued_cost,
            'free_items_cost': free_items_cost,
            'gross_profit': gross_profit,
            'issues_count': total_items_sold,
            'total_items_sold': total_items_sold,
            'total_transactions': issues_qs.count()
        })


    @action(detail=False, methods=['get'], url_path='sales-summary')
    def sales_summary(self, request):
        school = self.get_school()
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        issues_qs = StudentItemIssue.objects.filter(school=school).select_related('item', 'student', 'student__school_class', 'size', 'color')
        if from_date:
            issues_qs = issues_qs.filter(issue_date__gte=from_date)
        if to_date:
            issues_qs = issues_qs.filter(issue_date__lte=to_date)

        rows = []
        for iss in issues_qs:
            unit_cost = get_effective_issue_cost(iss)
            total_cost = unit_cost * iss.quantity
            rev = iss.charged_amount or Decimal('0.00')
            profit = rev - total_cost
            margin = ((profit / rev) * 100) if rev > 0 else Decimal('0.00')

            rows.append({
                'id': iss.id,
                'issue_date': iss.issue_date,
                'student_name': f"{iss.student.name or ''} {iss.student.surname or ''}".strip() if iss.student else "N/A",
                'admission_number': iss.student.gr_no if iss.student else "N/A",
                'class_name': str(iss.student.school_class) if iss.student and iss.student.school_class else "N/A",
                'item_name': iss.item.item_name if iss.item else "N/A",
                'item_code': iss.item.item_code if iss.item else "N/A",
                'size': iss.size.name if iss.size else None,
                'color': iss.color.name if iss.color else None,
                'quantity': iss.quantity,
                'charging_type': iss.charging_type,
                'unit_cost': str(unit_cost),
                'total_cost': str(total_cost),
                'charged_amount': str(rev),
                'gross_profit': str(profit),
                'profit_margin_pct': round(float(margin), 2)
            })

        return Response(rows)

    @action(detail=False, methods=['get'], url_path='replacements-summary')
    def replacements_summary(self, request):
        school = self.get_school()
        raw_from_date = request.query_params.get('from_date')
        raw_to_date = request.query_params.get('to_date')

        from_date = parse_date(raw_from_date) if raw_from_date else None
        to_date = parse_date(raw_to_date) if raw_to_date else None
        if raw_from_date and from_date is None:
            raise DRFValidationError({'from_date': 'Use a valid date in YYYY-MM-DD format.'})
        if raw_to_date and to_date is None:
            raise DRFValidationError({'to_date': 'Use a valid date in YYYY-MM-DD format.'})
        if from_date and to_date and from_date > to_date:
            raise DRFValidationError({'to_date': 'Must be on or after from_date.'})

        repl_qs = ReplacementRequest.objects.filter(school=school).select_related(
            'student', 'item', 'current_size', 'requested_size', 'current_color', 'requested_color'
        )
        if from_date:
            repl_qs = repl_qs.filter(requested_at__date__gte=from_date)
        if to_date:
            repl_qs = repl_qs.filter(requested_at__date__lte=to_date)

        rows = []
        for r in repl_qs:
            rows.append({
                'id': r.id,
                'date': r.requested_at.date(),
                'student_name': f"{r.student.name or ''} {r.student.surname or ''}".strip() if r.student else "N/A",
                'item_name': r.item.item_name if r.item else "N/A",
                'quantity': r.quantity,
                'reason': r.reason,
                'reason_display': r.get_reason_display(),
                'status': r.status,
                'admin_remarks': r.admin_remarks
            })
        return Response(rows)

    def _get_export_rows(self, request, report_type, school):
        raw_from_date = request.query_params.get('from_date')
        raw_to_date = request.query_params.get('to_date')
        from_date = parse_date(raw_from_date) if raw_from_date else None
        to_date = parse_date(raw_to_date) if raw_to_date else None

        if report_type in ('sales', 'issues_ledger'):
            qs = StudentItemIssue.objects.filter(school=school).select_related(
                'student', 'student__school_class', 'item', 'size', 'color'
            )
            if from_date:
                qs = qs.filter(issue_date__gte=from_date)
            if to_date:
                qs = qs.filter(issue_date__lte=to_date)

            rows = []
            for iss in qs:
                unit_cost = get_effective_issue_cost(iss)
                total_cost = unit_cost * iss.quantity
                rev = iss.charged_amount or Decimal('0.00')
                profit = rev - total_cost
                rows.append({
                    'id': iss.id,
                    'issue_date': iss.issue_date,
                    'student_name': f"{iss.student.name or ''} {iss.student.surname or ''}".strip() if iss.student else "N/A",
                    'student_class': str(iss.student.school_class) if iss.student and iss.student.school_class else "N/A",
                    'student_division': iss.student.division if iss.student else "",
                    'item_name': iss.item.item_name if iss.item else "N/A",
                    'item_code': iss.item.item_code if iss.item else "N/A",
                    'size_name': iss.size.name if iss.size else "",
                    'color_name': iss.color.name if iss.color else "",
                    'quantity': iss.quantity,
                    'charging_type': iss.charging_type,
                    'unit_cost': str(unit_cost),
                    'total_cost': str(total_cost),
                    'charged_amount': str(rev),
                    'profit': str(profit),
                    'status': 'ISSUED',
                })
            return rows

        elif report_type == 'purchases':
            qs = Purchase.objects.filter(school=school, status='CONFIRMED').select_related('supplier', 'academic_year')
            if from_date:
                qs = qs.filter(purchase_date__gte=from_date)
            if to_date:
                qs = qs.filter(purchase_date__lte=to_date)

            rows = []
            for p in qs:
                rows.append({
                    'purchase_date': p.purchase_date,
                    'invoice_number': p.invoice_number,
                    'supplier_name': p.supplier.name if p.supplier else "Direct / Internal",
                    'academic_year_name': p.academic_year.name if p.academic_year else "-",
                    'items_count': p.items.count() if hasattr(p, 'items') else 1,
                    'subtotal': str(p.subtotal),
                    'tax_amount': str(p.tax_amount),
                    'discount_amount': str(p.discount_amount),
                    'grand_total': str(p.grand_total),
                    'status': p.status,
                })
            return rows

        elif report_type == 'replacements':
            qs = ReplacementRequest.objects.filter(school=school).select_related('student', 'item')
            if from_date:
                qs = qs.filter(requested_at__date__gte=from_date)
            if to_date:
                qs = qs.filter(requested_at__date__lte=to_date)

            rows = []
            for r in qs:
                rows.append({
                    'date': r.requested_at.date(),
                    'student_name': f"{r.student.name or ''} {r.student.surname or ''}".strip() if r.student else "N/A",
                    'item_name': r.item.item_name if r.item else "N/A",
                    'quantity': r.quantity,
                    'reason': r.reason,
                    'reason_display': r.get_reason_display(),
                    'status': r.status,
                    'admin_remarks': r.admin_remarks or "-",
                })
            return rows

        return []

    @action(detail=False, methods=['get'], url_path='export-excel')
    def export_excel(self, request):
        report_type = request.query_params.get('type', 'sales')
        school = self.get_school()
        rows = self._get_export_rows(request, report_type, school)
        excel_bytes = export_inventory_report_excel(report_type, rows, school=school)
        response = HttpResponse(
            excel_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"Inventory_{report_type}_{timezone.now().strftime('%Y%m%d')}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return response

    @action(detail=False, methods=['get'], url_path='export-pdf')
    def export_pdf(self, request):
        report_type = request.query_params.get('type', 'sales')
        school = self.get_school()
        rows = self._get_export_rows(request, report_type, school)
        pdf_bytes = export_inventory_report_pdf(report_type, rows, school=school)
        response = HttpResponse(
            pdf_bytes,
            content_type='application/pdf'
        )
        filename = f"Inventory_{report_type}_{timezone.now().strftime('%Y%m%d')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return response



def is_inventory_approver(user):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    role = str(getattr(user, 'role', '') or '').strip().upper()
    if role in ['INVENTORY', 'PRINCIPAL', 'ADMIN', 'SUPERADMIN']:
        return True
    if user.groups.filter(name__iregex=r'^(inventory|principal|super_admin|superadmin|admin|trustee)').exists():
        return True
    staff = getattr(user, 'staff', None) or getattr(user, 'staff_profile', None)
    if staff and str(getattr(staff, 'category', '') or '').strip().upper() in ['INVENTORY', 'PRINCIPAL', 'ADMIN']:
        return True
    return False


class RequisitionViewSet(viewsets.ModelViewSet):
    """
    Staff / Teacher inventory requisition endpoint:
    - Teachers / Staff: Create requests and view only their own (requester=request.user).
    - Inventory Managers / Approvers: View all requests for their school, approve or reject.
    - Approval automatically deducts stock via StockTransaction ledger (type='REQUISITION', quantity=-quantity_requested).
    """
    queryset = Requisition.objects.all()
    serializer_class = RequisitionSerializer
    permission_classes = [IsAuthenticated]

    def get_school(self):
        school = resolve_school_from_request(self.request)
        if not school:
            raise PermissionDenied("Your account is not linked to a school.")
        return school

    def get_queryset(self):
        school = self.get_school()
        user = self.request.user
        qs = Requisition.objects.filter(school=school).select_related('requester', 'item', 'action_by')

        # If not an inventory manager/approver, restrict to requester's own requests
        if not is_inventory_approver(user):
            qs = qs.filter(requester=user)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status__iexact=status_param.strip())

        item_param = self.request.query_params.get('item')
        if item_param:
            qs = qs.filter(item_id=item_param)

        return qs

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except Exception as exc:
            return format_error_response(exc)

    def perform_create(self, serializer):
        school = self.get_school()
        serializer.save(
            school=school,
            requester=self.request.user,
            status='Pending',
            action_date=None,
            action_by=None
        )

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as exc:
            return format_error_response(exc)

    def perform_destroy(self, instance):
        user = self.request.user
        if not is_inventory_approver(user):
            if instance.requester_id != user.id:
                raise PermissionDenied("You can only delete your own requisitions.")
            if instance.status != 'Pending':
                raise DRFValidationError({"error": "Cannot delete a requisition that has already been reviewed."})
        elif instance.status == 'Approved':
            raise DRFValidationError({"error": "Cannot delete an approved requisition as stock has already been deducted."})
        instance.delete()

    @transaction.atomic
    def _apply_status_change(self, requisition, new_status, user, remarks=None):
        req = Requisition.objects.select_for_update().get(id=requisition.id)
        if req.status != 'Pending':
            raise DRFValidationError({'status': f"Cannot change status of requisition #{req.id}. It is already '{req.status}'."})

        if new_status == 'Approved':
            # Check stock availability
            current_stock = InventoryService.get_item_stock(req.item_id)
            if current_stock < req.quantity_requested:
                raise DRFValidationError({
                    'error': f"Insufficient stock for '{req.item.item_name}'. Current available stock: {current_stock}, Requested: {req.quantity_requested}."
                })

            academic_year = AcademicYear.objects.filter(school=req.school, is_active=True).first()
            tx = StockTransaction.objects.create(
                school=req.school,
                item=req.item,
                academic_year=academic_year,
                transaction_type='REQUISITION',
                quantity=-abs(req.quantity_requested),
                reference_type='Requisition',
                reference_id=str(req.id),
                transaction_date=timezone.now().date(),
                remarks=f"Requisition #{req.id} approved for {req.requester.username}: {req.purpose}",
                created_by=user
            )
            InventoryService.log_stock_transaction(tx, user)

            req.status = 'Approved'
            req.action_date = timezone.now()
            req.action_by = user
            if remarks is not None and str(remarks).strip():
                req.remarks = str(remarks).strip()
            elif not req.remarks:
                date_str = timezone.now().strftime("%d %b %Y")
                approver_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                if not approver_name or approver_name.lower() == 'none':
                    staff = getattr(user, 'staff', None) or getattr(user, 'staff_profile', None)
                    if staff and getattr(staff, 'name', None):
                        approver_name = staff.name
                approver_name = approver_name or user.username
                req.remarks = f"Acted on {date_str} by {approver_name}"
            req.save(update_fields=['status', 'action_date', 'action_by', 'remarks'])
            return req

        elif new_status == 'Rejected':
            req.status = 'Rejected'
            req.action_date = timezone.now()
            req.action_by = user
            if remarks is not None and str(remarks).strip():
                req.remarks = str(remarks).strip()
            elif not req.remarks:
                date_str = timezone.now().strftime("%d %b %Y")
                approver_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
                if not approver_name or approver_name.lower() == 'none':
                    staff = getattr(user, 'staff', None) or getattr(user, 'staff_profile', None)
                    if staff and getattr(staff, 'name', None):
                        approver_name = staff.name
                approver_name = approver_name or user.username
                req.remarks = f"Acted on {date_str} by {approver_name}"
            req.save(update_fields=['status', 'action_date', 'action_by', 'remarks'])
            return req
        else:
            raise DRFValidationError({'status': f"Invalid status: '{new_status}'. Allowed values: 'Approved', 'Rejected'."})

    def update(self, request, *args, **kwargs):
        try:
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            user = request.user
            new_status = request.data.get('status')

            # If status change is being attempted:
            if new_status and new_status != instance.status:
                if not is_inventory_approver(user):
                    raise PermissionDenied("Only inventory managers or administrators can approve or reject requisitions.")
                remarks = request.data.get('remarks', instance.remarks)
                req = self._apply_status_change(instance, new_status, user, remarks)
                serializer = self.get_serializer(req)
                return Response(serializer.data)

            # Non-status updates (e.g. requester editing purpose/quantity before approval)
            if not is_inventory_approver(user):
                if instance.requester_id != user.id:
                    raise PermissionDenied("You can only edit your own requisitions.")
                if instance.status != 'Pending':
                    raise DRFValidationError({"error": "Cannot modify a requisition after it has been reviewed."})

            return super().update(request, *args, partial=partial, **kwargs)
        except Exception as exc:
            return format_error_response(exc)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        try:
            if not is_inventory_approver(request.user):
                raise PermissionDenied("Only inventory managers or administrators can approve requisitions.")
            requisition = self.get_object()
            remarks = request.data.get('remarks', requisition.remarks)
            req = self._apply_status_change(requisition, 'Approved', request.user, remarks)
            serializer = self.get_serializer(req)
            return Response({
                'message': f"Requisition #{req.id} approved successfully and {req.quantity_requested} {req.item.unit} deducted from stock.",
                'requisition': serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as exc:
            return format_error_response(exc)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        try:
            if not is_inventory_approver(request.user):
                raise PermissionDenied("Only inventory managers or administrators can reject requisitions.")
            requisition = self.get_object()
            remarks = request.data.get('remarks', requisition.remarks)
            req = self._apply_status_change(requisition, 'Rejected', request.user, remarks)
            serializer = self.get_serializer(req)
            return Response({
                'message': f"Requisition #{req.id} rejected.",
                'requisition': serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as exc:
            return format_error_response(exc)

