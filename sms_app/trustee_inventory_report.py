"""Read-only, school-scoped trustee reporting over the physical stock ledger."""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import School, Staff
from .inventory_models import Item, StockTransaction, Purchase, StudentItemIssue, StudentItemReturn


class IsTrustee(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.is_active:
            return False
        roles = {str(getattr(user, 'role', '') or '').strip().lower()}
        roles.update(str(role).strip().lower() for role in user.groups.values_list('name', flat=True))
        roles.update(str(role or '').strip().lower() for role in Staff.objects.filter(user=user).values_list('category', flat=True))
        return bool(roles & {'trustee', 'admin(trustee)'})


class ReportFilters(serializers.Serializer):
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    item = serializers.IntegerField(required=False, min_value=1)
    category = serializers.IntegerField(required=False, min_value=1)
    search = serializers.CharField(required=False, max_length=200, allow_blank=True)
    transaction_type = serializers.ChoiceField(required=False, choices=StockTransaction.TRANSACTION_TYPE_CHOICES)
    stock_status = serializers.ChoiceField(required=False, choices=['low', 'out', 'healthy', 'negative'])
    page = serializers.IntegerField(default=1, min_value=1)
    page_size = serializers.IntegerField(default=25, min_value=1, max_value=100)

    def validate(self, attrs):
        today = timezone.localdate()
        attrs.setdefault('to_date', today)
        if attrs['to_date'] > today or attrs.get('from_date', today) > today:
            raise serializers.ValidationError('Report dates cannot be in the future.')
        if attrs.get('from_date') and attrs['from_date'] > attrs['to_date']:
            raise serializers.ValidationError('From date must be on or before to date.')
        return attrs


def money(value):
    return str(value.quantize(Decimal('0.01')))


class TrusteeInventoryReport(APIView):
    permission_classes = [IsAuthenticated, IsTrustee]

    def get(self, request):
        filters = ReportFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        params = filters.validated_data
        user = request.user
        school = getattr(user, 'school', None)
        if not school:
            member = Staff.objects.filter(user=user).select_related('school').first()
            school = member.school if member else None
        if not school:
            school = School.objects.filter(login_id=user).first()
        if not school:
            raise PermissionDenied('No school is assigned to your account.')

        all_items = Item.objects.filter(school=school).select_related('category')
        options = [{'id': item.id, 'name': item.item_name, 'code': item.item_code} for item in all_items]
        categories = list(school.inventory_categories.order_by('name').values('id', 'name'))
        items = all_items
        if params.get('item'):
            items = items.filter(pk=params['item'])
        if params.get('category'):
            items = items.filter(category_id=params['category'])
        if params.get('search'):
            items = items.filter(Q(item_name__icontains=params['search']) | Q(item_code__icontains=params['search']))
        items = list(items)
        item_map = {item.pk: item for item in items}
        today = timezone.localdate()
        start, end = params.get('from_date'), params['to_date']
        ledger = list(StockTransaction.objects.filter(
            school=school, item_id__in=item_map, transaction_date__lte=today,
        ).select_related('size', 'color', 'created_by', 'academic_year').order_by('transaction_date', 'id'))

        # Moving-average acquisition valuation per physical variant. Uncosted returns
        # and adjustments inherit the current average; never invent a catalogue price.
        states = {}
        period = []
        for txn in ledger:
            key = (txn.item_id, txn.size_id, txn.color_id)
            item = item_map[txn.item_id]
            if key not in states:
                states[key] = {
                    'id': ':'.join(str(part or 0) for part in key), 'item_id': item.pk,
                    'item_name': item.item_name, 'item_code': item.item_code,
                    'category': item.category.name if item.category else 'Unassigned',
                    'unit': item.unit, 'size': txn.size.name if txn.size else '—',
                    'color': txn.color.name if txn.color else '—', 'is_active': item.is_active,
                    'minimum_stock': item.minimum_stock_level, 'opening_balance': 0,
                    'received': 0, 'issued': 0, 'returned': 0, 'other_in': 0, 'other_out': 0,
                    'closing_balance': 0, 'current_balance': 0,
                    '_value': Decimal('0'), '_closing_value': Decimal('0'), '_average': Decimal('0'),
                }
            row = states[key]
            qty = txn.quantity
            before = row['current_balance']
            average = row['_value'] / before if before > 0 else row['_average']
            if qty > 0:
                cost = txn.unit_purchase_cost if txn.unit_purchase_cost > 0 else average
                row['_value'] += qty * cost
                if before + qty > 0:
                    row['_average'] = max(Decimal('0'), row['_value'] / (before + qty))
            elif qty < 0:
                row['_value'] += qty * average
            row['current_balance'] += qty
            if row['current_balance'] <= 0:
                row['_value'] = Decimal('0')
            if start and txn.transaction_date < start:
                row['opening_balance'] += qty
            if txn.transaction_date <= end:
                row['closing_balance'] += qty
                row['_closing_value'] = row['_value']
            if (not start or txn.transaction_date >= start) and txn.transaction_date <= end:
                field = ('received' if txn.transaction_type == 'PURCHASE' and qty > 0 else
                         'issued' if txn.transaction_type == 'ISSUE' and qty < 0 else
                         'returned' if txn.transaction_type == 'RETURN' and qty > 0 else
                         'other_in' if qty > 0 else 'other_out')
                row[field] += abs(qty)
                period.append((txn, key, row['current_balance']))

        # Include never-stocked catalogue items, so zero-stock alerts are visible.
        represented = {key[0] for key in states}
        for item in items:
            if item.pk not in represented:
                states[(item.pk, None, None)] = {
                    'id': f'{item.pk}:0:0', 'item_id': item.pk, 'item_name': item.item_name,
                    'item_code': item.item_code, 'category': item.category.name if item.category else 'Unassigned',
                    'unit': item.unit, 'size': '—', 'color': '—', 'is_active': item.is_active,
                    'minimum_stock': item.minimum_stock_level,
                    **{field: 0 for field in ['opening_balance', 'received', 'issued', 'returned', 'other_in', 'other_out', 'closing_balance', 'current_balance']},
                    '_value': Decimal('0'), '_closing_value': Decimal('0'), '_average': Decimal('0'),
                }
        for row in states.values():
            balance = row['current_balance']
            row['stock_status'] = 'negative' if balance < 0 else 'out' if balance == 0 else 'low' if balance <= row['minimum_stock'] else 'healthy'
            row['current_stock_value'] = money(row.pop('_value'))
            row['closing_stock_value'] = money(row.pop('_closing_value'))
            row.pop('_average')
        selected = {key: row for key, row in states.items() if not params.get('stock_status') or row['stock_status'] == params['stock_status']}
        rows = sorted(selected.values(), key=lambda row: (row['item_name'], row['size'], row['color']))
        # Movement type is a ledger-only filter; balances always include all movements.
        movements = [(txn, key, balance) for txn, key, balance in period if key in selected and (not params.get('transaction_type') or txn.transaction_type == params['transaction_type'])]
        movements.reverse()
        offset = (params['page'] - 1) * params['page_size']
        page = movements[offset:offset + params['page_size']]
        purchase_ids = [txn.reference_id for txn, _, _ in page if txn.reference_type == 'Purchase' and str(txn.reference_id).isdigit()]
        issue_ids = [txn.reference_id for txn, _, _ in page if txn.reference_type == 'StudentItemIssue' and str(txn.reference_id).isdigit()]
        return_ids = [txn.reference_id for txn, _, _ in page if txn.reference_type == 'StudentItemReturn' and str(txn.reference_id).isdigit()]
        purchases = {str(p.pk): p for p in Purchase.objects.filter(school=school, pk__in=purchase_ids).select_related('supplier')}
        issues = {str(i.pk): i for i in StudentItemIssue.objects.filter(school=school, pk__in=issue_ids).select_related('student')}
        returns = {str(r.pk): r for r in StudentItemReturn.objects.filter(school=school, pk__in=return_ids).select_related('student')}
        records = []
        for txn, key, balance in page:
            purchase = purchases.get(txn.reference_id) if txn.reference_type == 'Purchase' else None
            issue = issues.get(txn.reference_id) if txn.reference_type == 'StudentItemIssue' else None
            returned = returns.get(txn.reference_id) if txn.reference_type == 'StudentItemReturn' else None
            student = issue.student if issue else returned.student if returned else None
            records.append({
                'id': txn.pk, 'date': txn.transaction_date, 'type': txn.transaction_type,
                'item_name': selected[key]['item_name'], 'item_code': selected[key]['item_code'],
                'size': selected[key]['size'], 'color': selected[key]['color'], 'unit': selected[key]['unit'],
                'quantity': txn.quantity, 'balance_after': balance, 'unit_cost': money(txn.unit_purchase_cost),
                'recorded_value': money(abs(txn.quantity) * txn.unit_purchase_cost),
                'reference': f'{txn.reference_type or ""} #{txn.reference_id or ""}'.strip(),
                'invoice': purchase.invoice_number if purchase else None,
                'supplier': purchase.supplier.supplier_name if purchase and purchase.supplier else None,
                'recipient': f'{student.name or ""} {student.surname or ""}'.strip() if student else None,
                'charging_type': issue.charging_type if issue else None,
                'charged_amount': money(issue.charged_amount) if issue else None,
                'condition': returned.condition if returned else None,
                'academic_year': str(txn.academic_year) if txn.academic_year else None,
                'recorded_by': txn.created_by.get_username() if txn.created_by else None,
                'remarks': txn.remarks,
            })
        summary = {field: sum(row[field] for row in rows) for field in ['opening_balance', 'received', 'issued', 'returned', 'other_in', 'other_out', 'closing_balance', 'current_balance']}
        summary.update({
            'total_items': len({row['item_id'] for row in rows}), 'total_variants': len(rows),
            'current_stock_value': money(sum((Decimal(row['current_stock_value']) for row in rows), Decimal('0'))),
            'closing_stock_value': money(sum((Decimal(row['closing_stock_value']) for row in rows), Decimal('0'))),
            'low_stock_count': sum(row['stock_status'] == 'low' and row['is_active'] for row in rows),
            'out_of_stock_count': sum(row['stock_status'] == 'out' and row['is_active'] for row in rows),
            'negative_stock_count': sum(row['stock_status'] == 'negative' for row in rows),
        })
        # Daily rows use the same stock filters as the balance table.
        daily = defaultdict(lambda: {'received': 0, 'issued': 0, 'returned': 0, 'other_in': 0, 'other_out': 0, 'net_change': 0})
        for txn, key, _ in period:
            if key in selected:
                field = 'received' if txn.transaction_type == 'PURCHASE' and txn.quantity > 0 else 'issued' if txn.transaction_type == 'ISSUE' and txn.quantity < 0 else 'returned' if txn.transaction_type == 'RETURN' and txn.quantity > 0 else 'other_in' if txn.quantity > 0 else 'other_out'
                daily[str(txn.transaction_date)][field] += abs(txn.quantity)
                daily[str(txn.transaction_date)]['net_change'] += txn.quantity
        running = summary['opening_balance']
        daily_rows = []
        for date, values in sorted(daily.items()):
            daily_rows.append({'date': date, 'opening_balance': running, **values, 'closing_balance': running + values['net_change']})
            running += values['net_change']
        return Response({
            'school': school.name, 'from_date': start, 'to_date': end, 'current_as_of': today,
            'valuation_method': 'Moving-average acquisition cost per size/color. Uncosted inflows inherit the existing average; stock with no recorded cost is valued at zero. This is an estimate, not an audited accounting valuation.',
            'summary': summary, 'stocks': rows, 'daily': daily_rows,
            'alerts': [row for row in rows if (row['is_active'] and row['stock_status'] in ['low', 'out']) or row['stock_status'] == 'negative'],
            'transactions': {'count': len(movements), 'page': params['page'], 'page_size': params['page_size'], 'results': records},
            'options': {'items': options, 'categories': categories, 'transaction_types': [{'value': value, 'label': label} for value, label in StockTransaction.TRANSACTION_TYPE_CHOICES]},
        })
