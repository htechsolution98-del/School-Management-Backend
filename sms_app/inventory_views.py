from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Sum, Count, Q, F, DecimalField, ExpressionWrapper
from django.utils import timezone
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


class BaseSchoolViewSet(viewsets.ModelViewSet):
    """Base ViewSet ensuring multi-tenant isolation by school"""
    permission_classes = [permissions.IsAuthenticated]

    def get_school(self):
        user = self.request.user
        if hasattr(user, 'school') and user.school:
            return user.school
        # Fallback for school query param or user's first school
        school_id = self.request.query_params.get('school_id') or self.request.data.get('school')
        if school_id:
            return School.objects.filter(id=school_id).first()
        return School.objects.first()

    def get_queryset(self):
        school = self.get_school()
        if school:
            return self.queryset.filter(school=school)
        return self.queryset.all()

    def perform_create(self, serializer):
        school = self.get_school()
        serializer.save(school=school)


class ItemCategoryViewSet(BaseSchoolViewSet):
    queryset = ItemCategory.objects.all()
    serializer_class = ItemCategorySerializer


class ItemSizeViewSet(BaseSchoolViewSet):
    queryset = ItemSize.objects.all()
    serializer_class = ItemSizeSerializer


class ItemColorViewSet(BaseSchoolViewSet):
    queryset = ItemColor.objects.all()
    serializer_class = ItemColorSerializer


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


class ItemViewSet(BaseSchoolViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer

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


class SupplierViewSet(BaseSchoolViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer


class PurchaseViewSet(BaseSchoolViewSet):
    queryset = Purchase.objects.all()
    serializer_class = PurchaseSerializer

    def perform_create(self, serializer):
        school = self.get_school()
        purchase = serializer.save(school=school, created_by=self.request.user)

        # Handle items payload if passed
        items_data = self.request.data.get('items', [])
        for it in items_data:
            PurchaseItem.objects.create(
                purchase=purchase,
                item_id=it['item'],
                size_id=it.get('size'),
                color_id=it.get('color'),
                quantity=it['quantity'],
                unit_cost=Decimal(str(it['unit_cost'])),
                tax=Decimal(str(it.get('tax', '0.00'))),
                discount=Decimal(str(it.get('discount', '0.00'))),
                total_amount=Decimal(str(it['total_amount']))
            )

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
    def create_opening_stock(self, request):
        school = self.get_school()
        item_id = request.data.get('item')
        academic_year_id = request.data.get('academic_year')
        quantity = int(request.data.get('quantity', 0))
        unit_cost = Decimal(str(request.data.get('unit_cost', '0.00')))
        size_id = request.data.get('size')
        color_id = request.data.get('color')
        entry_date = request.data.get('entry_date') or timezone.now().date()
        remarks = request.data.get('remarks', 'Opening Stock Entry')

        item = Item.objects.get(id=item_id, school=school)
        acad_year = AcademicYear.objects.filter(id=academic_year_id).first()

        txn = StockTransaction.objects.create(
            school=school,
            item=item,
            academic_year=acad_year,
            size_id=size_id,
            color_id=color_id,
            transaction_type='OPENING',
            quantity=quantity,
            unit_purchase_cost=unit_cost,
            reference_type='OpeningStock',
            transaction_date=entry_date,
            remarks=remarks,
            created_by=request.user
        )
        return Response(StockTransactionSerializer(txn).data, status=status.HTTP_201_CREATED)


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
        quantity = int(request.data.get('quantity', 1))
        charging_type = request.data.get('charging_type', 'INCLUDED_IN_FEE')
        fee_type_id = request.data.get('fee_type')
        size_id = request.data.get('size')
        color_id = request.data.get('color')

        students_qs = Student.objects.filter(school=school, is_active=True)
        if class_id:
            students_qs = students_qs.filter(school_class_id=class_id)
        if division:
            students_qs = students_qs.filter(division=division)

        item = Item.objects.get(id=item_id, school=school)
        acad_year = AcademicYear.objects.get(id=academic_year_id)
        fee_type = FeeType.objects.filter(id=fee_type_id).first() if fee_type_id else None

        created_count = 0
        for student in students_qs:
            ent, created = StudentItemEntitlement.objects.get_or_create(
                school=school,
                academic_year=acad_year,
                student=student,
                item=item,
                size_id=size_id,
                color_id=color_id,
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
        quantity = int(request.data.get('quantity', 1))
        size_id = request.data.get('size')
        color_id = request.data.get('color')
        charging_type = request.data.get('charging_type')
        charged_amount = Decimal(str(request.data['charged_amount'])) if 'charged_amount' in request.data else None
        issue_reason = request.data.get('issue_reason', 'INITIAL_ISSUE')
        remarks = request.data.get('remarks', '')

        try:
            student = Student.objects.get(id=student_id, school=school)
            item = Item.objects.get(id=item_id, school=school)
            acad_year = AcademicYear.objects.get(id=academic_year_id)
            size = ItemSize.objects.filter(id=size_id).first() if size_id else None
            color = ItemColor.objects.filter(id=color_id).first() if color_id else None

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
        quantity_per_student = int(request.data.get('quantity_per_student', 1))
        size_id = request.data.get('size')
        color_id = request.data.get('color')

        try:
            item = Item.objects.get(id=item_id, school=school)
            acad_year = AcademicYear.objects.get(id=academic_year_id)
            size = ItemSize.objects.filter(id=size_id).first() if size_id else None
            color = ItemColor.objects.filter(id=color_id).first() if color_id else None

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

    @action(detail=True, methods=['post'], url_path='approve')
    def approve_request(self, request, pk=None):
        replacement = self.get_object()
        replacement.status = 'APPROVED'
        replacement.reviewed_at = timezone.now()
        replacement.reviewed_by = request.user
        replacement.admin_remarks = request.data.get('admin_remarks', '')
        replacement.save()
        return Response({'message': 'Replacement request approved.'})

    @action(detail=True, methods=['post'], url_path='reject')
    def reject_request(self, request, pk=None):
        replacement = self.get_object()
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

    def perform_create(self, serializer):
        school = self.get_school()
        return_obj = serializer.save(school=school, received_by=self.request.user)
        InventoryService.process_return(return_obj, self.request.user)


class StockAdjustmentViewSet(BaseSchoolViewSet):
    queryset = StockAdjustment.objects.all()
    serializer_class = StockAdjustmentSerializer

    def perform_create(self, serializer):
        school = self.get_school()
        adj = serializer.save(school=school, created_by=self.request.user)
        InventoryService.process_adjustment(adj, self.request.user)


class InventoryReportViewSet(viewsets.ViewSet):
    """Aggregated reporting endpoints for Purchase, Sales, P&L, Free Items, Replacements & Dashboard"""
    permission_classes = [permissions.IsAuthenticated]

    def get_school(self):
        user = self.request.user
        if hasattr(user, 'school') and user.school:
            return user.school
        school_id = self.request.query_params.get('school_id')
        if school_id:
            return School.objects.filter(id=school_id).first()
        return School.objects.first()

    @action(detail=False, methods=['get'], url_path='dashboard-summary')
    def dashboard_summary(self, request):
        school = self.get_school()
        today = timezone.now().date()
        start_of_month = today.replace(day=1)

        total_items = Item.objects.filter(school=school, is_active=True).count()
        total_stock_units = StockTransaction.objects.filter(school=school).aggregate(total=Sum('quantity'))['total'] or 0

        # Low stock and out of stock counts
        all_items = Item.objects.filter(school=school, is_active=True)
        low_stock_count = 0
        out_of_stock_count = 0
        for it in all_items:
            stock = it.stock_transactions.aggregate(total=Sum('quantity'))['total'] or 0
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
            'total_stock_units': max(0, total_stock_units),
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
                'student_name': f"{iss.student.first_name} {iss.student.last_name}" if iss.student else "N/A",
                'admission_number': iss.student.admission_number if iss.student else "N/A",
                'class_name': str(iss.student.school_class) if iss.student and iss.student.school_class else "N/A",
                'item_name': iss.item.item_name if iss.item else "N/A",
                'item_code': iss.item.item_code if iss.item else "N/A",
                'size': iss.size.size_name if iss.size else None,
                'color': iss.color.color_name if iss.color else None,
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
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        repl_qs = ReplacementRequest.objects.filter(school=school).select_related('student', 'item', 'size')
        if from_date:
            repl_qs = repl_qs.filter(created_at__date__gte=from_date)
        if to_date:
            repl_qs = repl_qs.filter(created_at__date__lte=to_date)

        rows = []
        for r in repl_qs:
            rows.append({
                'id': r.id,
                'date': r.created_at.date(),
                'student_name': f"{r.student.first_name} {r.student.last_name}" if r.student else "N/A",
                'item_name': r.item.item_name if r.item else "N/A",
                'quantity': r.quantity,
                'reason': r.reason,
                'reason_display': r.get_reason_display(),
                'status': r.status,
                'admin_remarks': r.admin_remarks
            })
        return Response(rows)
