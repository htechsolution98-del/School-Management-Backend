from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Book, BookCopy, BookIssued, BookReservation, LibrarySetting, LateBookFees, School, Staff
from .trustee_inventory_report import IsTrustee, money


class LibraryReportFilters(serializers.Serializer):
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    book = serializers.IntegerField(required=False, min_value=1)
    category = serializers.CharField(required=False, max_length=100)
    search = serializers.CharField(required=False, max_length=200, allow_blank=True)
    borrower_type = serializers.ChoiceField(required=False, choices=['student', 'staff'])
    borrower = serializers.IntegerField(required=False, min_value=1)
    loan_status = serializers.ChoiceField(required=False, choices=['ISSUED', 'RETURNED', 'LOST', 'DAMAGED', 'OVERDUE'])
    page = serializers.IntegerField(default=1, min_value=1)
    page_size = serializers.IntegerField(default=25, min_value=1, max_value=100)

    def validate(self, attrs):
        today = timezone.localdate()
        attrs.setdefault('to_date', today)
        if attrs['to_date'] > today or attrs.get('from_date', today) > today:
            raise serializers.ValidationError('Dates cannot be in the future.')
        if attrs.get('from_date') and attrs['from_date'] > attrs['to_date']:
            raise serializers.ValidationError('From date must be on or before to date.')
        if attrs.get('borrower') and not attrs.get('borrower_type'):
            raise serializers.ValidationError('Select a borrower type when filtering a borrower ID.')
        return attrs


class TrusteeLibraryReport(APIView):
    permission_classes = [IsAuthenticated, IsTrustee]

    def get(self, request):
        serializer = LibraryReportFilters(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data
        school = getattr(request.user, 'school', None)
        if not school:
            member = Staff.objects.filter(user=request.user).select_related('school').first()
            school = member.school if member else None
        if not school:
            school = School.objects.filter(login_id=request.user).first()
        if not school:
            raise PermissionDenied('No school is assigned to your account.')
        now = timezone.now()
        settings = LibrarySetting.objects.filter(school=school).first()
        legacy_policy = LateBookFees.objects.filter(school=school).first() if not settings else None
        grace = settings.grace_period_days if settings else legacy_policy.grace_period_days if legacy_policy else 0
        daily_fine = Decimal(str(settings.fine_per_day if settings else legacy_policy.fees if legacy_policy else 0))

        catalogue = list(Book.objects.filter(school=school).select_related('category_ref', 'author_ref', 'publisher_ref', 'rack', 'shelf').order_by('title', 'id'))
        def category(book):
            return book.category_ref.name if book.category_ref else book.category or 'Unassigned'
        options = {'books': [{'id': book.pk, 'title': book.title} for book in catalogue], 'categories': sorted({category(book) for book in catalogue})}
        books = [book for book in catalogue if
                 (not params.get('book') or book.pk == params['book']) and
                 (not params.get('category') or category(book) == params['category']) and
                 (not params.get('search') or params['search'].lower() in f'{book.title} {book.isbn or ""} {book.author} {book.author_ref.name if book.author_ref else ""}'.lower())]
        book_ids = [book.pk for book in books]
        copies = list(BookCopy.objects.filter(school=school, book_id__in=book_ids).select_related('book', 'rack', 'shelf').order_by('book__title', 'accession_no'))
        copy_by_book = {}
        copy_rows = []
        for copy in copies:
            copy_by_book.setdefault(copy.book_id, []).append(copy)
            value = copy.purchase_price if copy.purchase_price > 0 else copy.book.price
            copy_rows.append({
                'id': copy.pk, 'book_id': copy.book_id, 'title': copy.book.title, 'accession_no': copy.accession_no,
                'barcode': copy.barcode, 'status': copy.status, 'condition': copy.condition, 'is_active': copy.is_active,
                'purchase_date': copy.purchase_date, 'value': money(value),
                'rack': copy.rack.rack_code if copy.rack else None, 'shelf': copy.shelf.shelf_code if copy.shelf else None,
            })

        current_loans = list(BookIssued.objects.filter(school=school, book_id__in=book_ids, book_issued_date__lte=now).filter(
            Q(student__school=school, staff__isnull=True) | Q(staff__school=school, student__isnull=True)
        ).select_related('book', 'book_copy', 'student__school_class', 'staff__department').order_by('-book_issued_date', '-id'))
        loan_rows = []
        current_counts = Counter()
        current_by_book = Counter()
        overdue_by_book = Counter()
        for loan in current_loans:
            borrower = loan.student or loan.staff
            kind = 'student' if loan.student_id else 'staff'
            active = loan.status == 'ISSUED' and loan.actual_return_date is None
            overdue = active and loan.due_date < now
            after_grace = active and loan.due_date + timedelta(days=grace) < now
            days = max(0, (timezone.localdate(now) - timezone.localdate(loan.due_date)).days) if overdue else 0
            charge_days = max(0, (timezone.localdate(now) - timezone.localdate(loan.due_date + timedelta(days=grace))).days) if after_grace else 0
            if active:
                current_counts['issued'] += 1
                current_counts[f'{kind}_issued'] += 1
                current_by_book[loan.book_id] += 1
            if overdue:
                current_counts['overdue'] += 1
                overdue_by_book[loan.book_id] += 1
            if after_grace:
                current_counts['past_grace'] += 1
            issued_day = timezone.localdate(loan.book_issued_date)
            if issued_day > params['to_date'] or (params.get('from_date') and issued_day < params['from_date']):
                continue
            if params.get('borrower_type') and kind != params['borrower_type']:
                continue
            if params.get('borrower') and borrower.pk != params['borrower']:
                continue
            if params.get('loan_status') == 'OVERDUE' and not overdue:
                continue
            if params.get('loan_status') and params['loan_status'] != 'OVERDUE' and loan.status != params['loan_status']:
                continue
            loan_rows.append({
                'id': loan.pk, 'book_id': loan.book_id, 'title': loan.book.title,
                'accession_no': loan.book_copy.accession_no if loan.book_copy and loan.book_copy.school_id == school.pk else None,
                'borrower_type': kind, 'borrower_id': borrower.pk,
                'borrower_name': f'{borrower.name or ""} {borrower.surname or ""}'.strip() if kind == 'student' else borrower.name,
                'identifier': borrower.gr_no if kind == 'student' else str(borrower.pk),
                'class_or_role': str(borrower.school_class) if kind == 'student' and borrower.school_class else borrower.category if kind == 'staff' else None,
                'division_or_department': borrower.division if kind == 'student' else borrower.department.name if borrower.department else None,
                'issued_date': loan.book_issued_date, 'due_date': loan.due_date, 'returned_date': loan.actual_return_date,
                'status': loan.status, 'overdue': overdue, 'days_overdue': days, 'past_grace': after_grace,
                'estimated_late_fine': money(charge_days * daily_fine), 'renewals': loan.renewal_count,
                'late_fees': money(loan.late_fees), 'damage_fees': money(loan.damage_fees), 'lost_fees': money(loan.lost_fees),
                'total_fine': money(loan.total_fine), 'condition_on_return': loan.condition_on_return, 'remarks': loan.remarks,
            })

        stock_rows = []
        for book in books:
            tracked = copy_by_book.get(book.pk, [])
            statuses = Counter(copy.status for copy in tracked)
            untracked = max(0, book.total_copies - len(tracked))
            retained_value = sum((copy.purchase_price if copy.purchase_price > 0 else book.price for copy in tracked if copy.is_active and copy.status not in ['LOST', 'DISPOSED']), Decimal('0')) + untracked * book.price
            stock_rows.append({
                'id': book.pk, 'title': book.title, 'isbn': book.isbn, 'author': book.author_ref.name if book.author_ref else book.author,
                'category': category(book), 'publisher': book.publisher_ref.name if book.publisher_ref else None,
                'rack': book.rack.rack_code if book.rack else None, 'shelf': book.shelf.shelf_code if book.shelf else None,
                'catalogue_copies': book.total_copies, 'catalogue_available': book.available_copies,
                'registered_copies': len(tracked), 'untracked_copies': untracked,
                'available': sum(copy.status == 'AVAILABLE' and copy.is_active for copy in tracked),
                'issued': current_by_book[book.pk], 'overdue': overdue_by_book[book.pk],
                'lost': statuses['LOST'], 'damaged': statuses['DAMAGED'], 'under_repair': statuses['UNDER_REPAIR'],
                'reserved': statuses['RESERVED'], 'disposed': statuses['DISPOSED'],
                'damaged_condition': sum(copy.condition != 'GOOD' for copy in tracked),
                'stock_value': money(retained_value), 'catalogue_value': money(book.total_copies * book.price),
                'count_mismatch': len(tracked) != book.total_copies,
                'times_issued_in_period': sum(row['book_id'] == book.pk for row in loan_rows),
            })

        borrowers = {}
        daily = {}
        for row in loan_rows:
            key = (row['borrower_type'], row['borrower_id'])
            if key not in borrowers:
                borrowers[key] = {field: row[field] for field in ['borrower_type', 'borrower_id', 'borrower_name', 'identifier', 'class_or_role', 'division_or_department']}
                borrowers[key].update({'id': f'{key[0]}:{key[1]}', 'total_loans': 0, 'active': 0, 'overdue': 0, 'returned': 0, 'lost': 0, 'damaged': 0, '_fine': Decimal('0')})
            entry = borrowers[key]
            entry['total_loans'] += 1
            entry['active'] += row['status'] == 'ISSUED' and row['returned_date'] is None
            entry['overdue'] += row['overdue']
            for status in ['returned', 'lost', 'damaged']:
                entry[status] += row['status'] == status.upper()
            entry['_fine'] += Decimal(row['total_fine'])
            day = str(timezone.localdate(row['issued_date']))
            daily.setdefault(day, {'date': day, 'student_issues': 0, 'staff_issues': 0, 'total_issues': 0})
            daily[day][f'{row["borrower_type"]}_issues'] += 1
            daily[day]['total_issues'] += 1
        borrower_rows = []
        for entry in borrowers.values():
            entry['assessed_fines'] = money(entry.pop('_fine'))
            borrower_rows.append(entry)
        borrower_rows.sort(key=lambda row: (-row['total_loans'], row['borrower_name'] or ''))
        offset = (params['page'] - 1) * params['page_size']
        reservations = BookReservation.objects.filter(school=school, book_id__in=book_ids).values_list('status', flat=True)
        reservation_counts = Counter(reservations)
        current = {
            'total_titles': len(books), 'total_copies': sum(book.total_copies for book in books),
            'catalogue_available': sum(book.available_copies for book in books), 'registered_copies': len(copies),
            'issued': current_counts['issued'], 'overdue': current_counts['overdue'], 'past_grace': current_counts['past_grace'],
            'student_issued': current_counts['student_issued'], 'staff_issued': current_counts['staff_issued'],
            'lost_copies': sum(copy.status == 'LOST' for copy in copies), 'damaged_copies': sum(copy.status == 'DAMAGED' for copy in copies),
            'under_repair': sum(copy.status == 'UNDER_REPAIR' for copy in copies),
            'stock_value': money(sum((Decimal(row['stock_value']) for row in stock_rows), Decimal('0'))),
            'catalogue_value': money(sum((Decimal(row['catalogue_value']) for row in stock_rows), Decimal('0'))),
            'count_mismatches': sum(row['count_mismatch'] for row in stock_rows),
            'waiting_reservations': reservation_counts['WAITING'], 'ready_reservations': reservation_counts['AVAILABLE'],
        }
        period = {'total_loans': len(loan_rows), 'students': sum(row['borrower_type'] == 'student' for row in borrower_rows), 'staff': sum(row['borrower_type'] == 'staff' for row in borrower_rows),
                  'lost_loans': sum(row['status'] == 'LOST' for row in loan_rows), 'damaged_loans': sum(row['status'] == 'DAMAGED' for row in loan_rows),
                  'assessed_fines': money(sum((Decimal(row['total_fine']) for row in loan_rows), Decimal('0'))),
                  'estimated_late_fines': money(sum((Decimal(row['estimated_late_fine']) for row in loan_rows), Decimal('0')))}
        return Response({
            'school': school.name, 'current_as_of': now, 'from_date': params.get('from_date'), 'to_date': params['to_date'],
            'current': current, 'period': period, 'stocks': stock_rows, 'copies': copy_rows,
            'borrowers': borrower_rows, 'daily': sorted(daily.values(), key=lambda row: row['date']),
            'loans': {'count': len(loan_rows), 'page': params['page'], 'page_size': params['page_size'], 'results': loan_rows[offset:offset + params['page_size']]},
            'options': options, 'grace_period_days': grace,
            'valuation_note': 'Current retained stock uses recorded copy purchase cost, falling back to book price. Lost, disposed and inactive registered copies are excluded. Catalogue copies without accession records use book price. Damaged/repair stock remains included at recorded cost; no depreciation is recorded.',
        })
