from rest_framework import viewsets, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Sum, Count, Q, F, DecimalField, ExpressionWrapper
from django.utils import timezone
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta
from decimal import Decimal

from .inventory_models import (
    ItemCategory, ItemSize, ItemColor, Item, ItemPricing,
    Supplier, Purchase, PurchaseItem, StockTransaction,
    StudentItemEntitlement, StudentItemIssue, ReplacementRequest,
    StudentItemReturn, StockAdjustment, InventoryAuditLog
)
from .inventory_serializers import (
    ItemCategorySerializer, ItemSizeSerializer, ItemColorSerializer,
    ItemPricingSerializer, ItemSerializer, SupplierSerializer,
    PurchaseSerializer, PurchaseItemSerializer, StockTransactionSerializer,
    StudentItemEntitlementSerializer, StudentItemIssueSerializer,
    ReplacementRequestSerializer, StudentItemReturnSerializer,
    StockAdjustmentSerializer, InventoryAuditLogSerializer
)
from .inventory_services import InventoryService
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
    """Base ViewSet ensuring multi-tenant isolation by school"""
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



class ItemCategoryViewSet(BaseSchoolViewSet):
    queryset = ItemCategory.objects.all()
    serializer_class = ItemCategorySerializer

    def create(self, request, *args, **kwargs):
        school = self.get_school()
        name = (request.data.get('name') or '').strip()
        existing = ItemCategory.objects.filter(school=school, name__iexact=name).first()
        if existing:
            return Response(
                {"name": ["A category with this name already exists in your school."]},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().create(request, *args, **kwargs)


class ItemSizeViewSet(BaseSchoolViewSet):
    queryset = ItemSize.objects.all()
    serializer_class = ItemSizeSerializer

    def create(self, request, *args, **kwargs):
        school = self.get_school()
        name = (request.data.get('name') or '').strip()
        size_type = request.data.get('size_type') or 'ALPHA'
        existing = ItemSize.objects.filter(school=school, name__iexact=name, size_type=size_type).first()
        if existing:
            return Response(
                {"name": ["A size variant with this name and type already exists."]},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().create(request, *args, **kwargs)


class ItemColorViewSet(BaseSchoolViewSet):
    queryset = ItemColor.objects.all()
    serializer_class = ItemColorSerializer

    def create(self, request, *args, **kwargs):
        school = self.get_school()
        name = (request.data.get('name') or '').strip()
        existing = ItemColor.objects.filter(school=school, name__iexact=name).first()
        if existing:
            return Response(
                {"name": ["A color variant with this name already exists."]},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().create(request, *args, **kwargs)


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
        school = self.get_school()
        item_id = request.data.get('item')
        academic_year_id = request.data.get('academic_year')
        school_class_id = request.data.get('school_class') or None

        # Check if pricing already exists for this (school, item, academic_year, school_class)
        existing = ItemPricing.objects.filter(
            school=school,
            item_id=item_id,
            academic_year_id=academic_year_id,
            school_class_id=school_class_id
        ).first()

        if existing:
            # Update existing record instead of creating duplicate
            serializer = self.get_serializer(existing, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save(school=school)
            return Response(serializer.data, status=status.HTTP_200_OK)

        return super().create(request, *args, **kwargs)



class ItemViewSet(BaseSchoolViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
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
        purchase = self.get_object()
        InventoryService.process_purchase_confirmation(purchase, request.user)
        return Response({'message': 'Purchase confirmed and stock updated successfully.'})


class StockTransactionViewSet(BaseSchoolViewSet):
    queryset = StockTransaction.objects.all()
    serializer_class = StockTransactionSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def create(self, request, *args, **kwargs):
        return Response({'detail': 'Use the opening-stock action or a purchase, issue, return, or adjustment workflow.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

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
        school = self.get_school()
        if not school:
            raise PermissionDenied("Your account is not linked to a school.")
        try:
            quantity = int(request.data.get('quantity', 0))
            unit_cost = Decimal(str(request.data.get('unit_cost', '0.00')))
            if quantity <= 0 or unit_cost < 0:
                raise ValidationError("Quantity must be positive and unit cost cannot be negative.")
            size_id = request.data.get('size') or None
            color_id = request.data.get('color') or None
            item = Item.objects.get(id=request.data.get('item'), school=school)
            size = ItemSize.objects.get(id=size_id, school=school) if size_id else None
            color = ItemColor.objects.get(id=color_id, school=school) if color_id else None
            if item.has_size and not size:
                raise ValidationError({'size': 'Select a size for this item.'})
            if item.has_color and not color:
                raise ValidationError({'color': 'Select a color for this item.'})
            academic_year_id = request.data.get('academic_year')
            acad_year = AcademicYear.objects.get(id=academic_year_id, school=school) if academic_year_id else None
            txn = StockTransaction.objects.create(
                school=school, item=item, academic_year=acad_year, size=size, color=color,
                transaction_type='OPENING', quantity=quantity, unit_purchase_cost=unit_cost,
                reference_type='OpeningStock', transaction_date=request.data.get('entry_date') or timezone.now().date(),
                remarks=request.data.get('remarks', 'Opening Stock Entry'), created_by=request.user
            )
            InventoryService.log_stock_transaction(txn, request.user)
            return Response(StockTransactionSerializer(txn).data, status=status.HTTP_201_CREATED)
        except (Item.DoesNotExist, ItemSize.DoesNotExist, ItemColor.DoesNotExist, AcademicYear.DoesNotExist):
            return Response({'error': 'Item or academic year was not found in this school.'}, status=status.HTTP_400_BAD_REQUEST)


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
            return Response({'error': 'Quantity must be a positive whole number.'}, status=status.HTTP_400_BAD_REQUEST)
        charging_type = request.data.get('charging_type', 'INCLUDED_IN_FEE')
        fee_type_id = request.data.get('fee_type')
        size_id = request.data.get('size')
        color_id = request.data.get('color')

        students_qs = Student.objects.filter(school=school, is_active=True)
        if class_id:
            students_qs = students_qs.filter(school_class_id=class_id)
        if division:
            students_qs = students_qs.filter(division=division)

        try:
            item = Item.objects.get(id=item_id, school=school)
            acad_year = AcademicYear.objects.get(id=academic_year_id, school=school)
            size = ItemSize.objects.get(id=size_id, school=school) if size_id else None
            color = ItemColor.objects.get(id=color_id, school=school) if color_id else None
            fee_type = FeeType.objects.filter(id=fee_type_id, school=school).first() if fee_type_id else None
        except (Item.DoesNotExist, AcademicYear.DoesNotExist, ItemSize.DoesNotExist, ItemColor.DoesNotExist):
            return Response({'error': 'Item, academic year, or variant was not found in this school.'}, status=status.HTTP_400_BAD_REQUEST)
        if item.has_size and not size or item.has_color and not color:
            return Response({'error': 'Select all required item variants.'}, status=status.HTTP_400_BAD_REQUEST)
        if charging_type not in {'INCLUDED_IN_FEE', 'SEPARATE_CHARGE', 'FREE'}:
            return Response({'error': 'Invalid charging type.'}, status=status.HTTP_400_BAD_REQUEST)

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


class StudentItemIssueViewSet(BaseSchoolViewSet):
    queryset = StudentItemIssue.objects.all()
    serializer_class = StudentItemIssueSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        student_id = self.request.query_params.get('student')
        item_id = self.request.query_params.get('item')
        from_date = self.request.query_params.get('from_date')
        to_date = self.request.query_params.get('to_date')

        if student_id:
            qs = qs.filter(student_id=student_id)
        if item_id:
            qs = qs.filter(item_id=item_id)
        if from_date:
            qs = qs.filter(issue_date__gte=from_date)
        if to_date:
            qs = qs.filter(issue_date__lte=to_date)
        return qs

    def create(self, request, *args, **kwargs):
        school = self.get_school()
        academic_year_id = request.data.get('academic_year')
        student_id = request.data.get('student')
        item_id = request.data.get('item')
        try:
            quantity = int(request.data.get('quantity', 1))
            charged_amount = Decimal(str(request.data['charged_amount'])) if 'charged_amount' in request.data else None
        except (TypeError, ValueError, ArithmeticError):
            return Response({'error': 'Quantity and charged amount must be valid numbers.'}, status=status.HTTP_400_BAD_REQUEST)
        size_id = request.data.get('size')
        color_id = request.data.get('color')
        charging_type = request.data.get('charging_type')
        issue_reason = request.data.get('issue_reason', 'INITIAL_ISSUE')
        remarks = request.data.get('remarks', '')

        try:
            student = Student.objects.get(id=student_id, school=school)
            item = Item.objects.get(id=item_id, school=school)
            acad_year = AcademicYear.objects.get(id=academic_year_id, school=school)
            size = ItemSize.objects.get(id=size_id, school=school) if size_id else None
            color = ItemColor.objects.get(id=color_id, school=school) if color_id else None

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
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='bulk-issue')
    def bulk_issue(self, request):
        school = self.get_school()
        academic_year_id = request.data.get('academic_year')
        item_id = request.data.get('item')
        student_ids = request.data.get('student_ids', [])
        try:
            quantity_per_student = int(request.data.get('quantity_per_student', 1))
        except (TypeError, ValueError):
            return Response({'error': 'Quantity per student must be a positive whole number.'}, status=status.HTTP_400_BAD_REQUEST)
        size_id = request.data.get('size')
        color_id = request.data.get('color')

        try:
            item = Item.objects.get(id=item_id, school=school)
            acad_year = AcademicYear.objects.get(id=academic_year_id, school=school)
            size = ItemSize.objects.get(id=size_id, school=school) if size_id else None
            color = ItemColor.objects.get(id=color_id, school=school) if color_id else None

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
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ReplacementRequestViewSet(BaseSchoolViewSet):
    queryset = ReplacementRequest.objects.all()
    serializer_class = ReplacementRequestSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    @action(detail=True, methods=['post'], url_path='approve')
    def approve_request(self, request, pk=None):
        replacement = self.get_object()
        if replacement.status != 'PENDING':
            return Response({'error': 'Only pending requests can be approved.'}, status=status.HTTP_400_BAD_REQUEST)
        replacement.status = 'APPROVED'
        replacement.reviewed_at = timezone.now()
        replacement.reviewed_by = request.user
        replacement.admin_remarks = request.data.get('admin_remarks', '')
        replacement.save()
        return Response({'message': 'Replacement request approved.'})

    @action(detail=True, methods=['post'], url_path='reject')
    def reject_request(self, request, pk=None):
        replacement = self.get_object()
        if replacement.status != 'PENDING':
            return Response({'error': 'Only pending requests can be rejected.'}, status=status.HTTP_400_BAD_REQUEST)
        replacement.status = 'REJECTED'
        replacement.reviewed_at = timezone.now()
        replacement.reviewed_by = request.user
        replacement.admin_remarks = request.data.get('admin_remarks', '')
        replacement.save()
        return Response({'message': 'Replacement request rejected.'})

    @action(detail=True, methods=['post'], url_path='issue')
    def issue_replacement(self, request, pk=None):
        replacement = self.get_object()
        charging_type = request.data.get('charging_type', 'FREE')
        charged_amount = Decimal(str(request.data.get('charged_amount', '0.00')))
        try:
            record = InventoryService.process_replacement_issue(
                replacement=replacement,
                charging_type=charging_type,
                charged_amount=charged_amount,
                user=request.user
            )
            return Response({'message': 'Replacement item issued and stock updated.', 'issue_id': record.id})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


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
            cost = (issue.unit_purchase_cost or Decimal('0.00')) * issue.quantity
            total_issued_cost += cost
            if issue.charging_type == 'FREE':
                free_items_cost += cost

        gross_profit = total_charged_revenue - total_issued_cost

        return Response({
            'total_purchases': total_purchase_cost,
            'total_revenue': total_charged_revenue,
            'total_issued_cost': total_issued_cost,
            'free_items_cost': free_items_cost,
            'gross_profit': gross_profit,
            'issues_count': issues_qs.count()
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
            unit_cost = iss.unit_purchase_cost or Decimal('0.00')
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
            raise ValidationError({'from_date': 'Use a valid date in YYYY-MM-DD format.'})
        if raw_to_date and to_date is None:
            raise ValidationError({'to_date': 'Use a valid date in YYYY-MM-DD format.'})
        if from_date and to_date and from_date > to_date:
            raise ValidationError({'to_date': 'Must be on or after from_date.'})

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
