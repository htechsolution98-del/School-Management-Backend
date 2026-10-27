import json
from decimal import Decimal
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError as DRFValidationError, PermissionDenied

from .models import School, Student, Staff, SchoolClass, AcademicYear
from .id_card_models import IDCardTemplate, IDCardRecord, IDCardLog
from .id_card_serializers import (
    IDCardTemplateSerializer,
    IDCardRecordSerializer,
    IDCardLogSerializer
)
from .id_card_pdf_service import (
    resolve_card_data,
    generate_single_card_pdf,
    generate_a4_grid_pdf,
    get_default_layout
)
from .inventory_views import format_error_response


class BaseIDCardViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_school(self):
        user = self.request.user
        school_id = self.request.headers.get('X-School-ID') or self.request.query_params.get('school_id')
        if school_id:
            return School.objects.filter(id=school_id).first()
        if hasattr(user, 'school') and user.school:
            return user.school
        if hasattr(user, 'userprofile') and user.userprofile.school:
            return user.userprofile.school
        return School.objects.first()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['school'] = self.get_school()
        return ctx


class IDCardTemplateViewSet(BaseIDCardViewSet):
    queryset = IDCardTemplate.objects.all()
    serializer_class = IDCardTemplateSerializer

    def get_queryset(self):
        school = self.get_school()
        if not school:
            return IDCardTemplate.objects.none()
        qs = IDCardTemplate.objects.filter(school=school)
        user_type = self.request.query_params.get('user_type')
        if user_type:
            qs = qs.filter(user_type=user_type)
        return qs

    def perform_create(self, serializer):
        school = self.get_school()
        if not school:
            raise PermissionDenied("Your account is not linked to any school.")
        # If this is the first template for user_type, make it default
        user_type = serializer.validated_data.get('user_type', 'STUDENT')
        is_first = not IDCardTemplate.objects.filter(school=school, user_type=user_type).exists()
        is_default = serializer.validated_data.get('is_default', False) or is_first

        # Ensure layout_config has default fields if not provided
        layout = serializer.validated_data.get('layout_config')
        if not layout or not layout.get('fields'):
            orientation = serializer.validated_data.get('orientation', 'PORTRAIT')
            layout = get_default_layout(orientation, user_type)

        if is_default:
            IDCardTemplate.objects.filter(school=school, user_type=user_type).update(is_default=False)

        serializer.save(
            school=school,
            created_by=self.request.user,
            is_default=is_default,
            layout_config=layout
        )

    def perform_update(self, serializer):
        school = self.get_school()
        is_default = serializer.validated_data.get('is_default', False)
        if is_default:
            user_type = serializer.instance.user_type
            IDCardTemplate.objects.filter(school=school, user_type=user_type).exclude(pk=serializer.instance.pk).update(is_default=False)
        serializer.save()

    def perform_destroy(self, instance):
        school = self.get_school()
        user_type = instance.user_type
        was_default = instance.is_default
        instance.delete()
        if was_default and school:
            next_tmpl = IDCardTemplate.objects.filter(school=school, user_type=user_type).first()
            if next_tmpl:
                next_tmpl.is_default = True
                next_tmpl.save(update_fields=['is_default', 'updated_at'])

    @action(detail=True, methods=['post'], url_path='set-default')
    def set_default(self, request, pk=None):
        try:
            template = self.get_object()
            school = self.get_school()
            IDCardTemplate.objects.filter(school=school, user_type=template.user_type).update(is_default=False)
            template.is_default = True
            template.save(update_fields=['is_default', 'updated_at'])
            return Response({'message': f"Template '{template.name}' is now the default {template.get_user_type_display()} template."})
        except Exception as exc:
            return format_error_response(exc)

    @action(detail=True, methods=['post'], url_path='duplicate')
    def duplicate_template(self, request, pk=None):
        try:
            source = self.get_object()
            school = self.get_school()
            copy_name = f"{source.name} (Copy)"
            counter = 1
            while IDCardTemplate.objects.filter(school=school, name=copy_name).exists():
                counter += 1
                copy_name = f"{source.name} (Copy {counter})"

            cloned = IDCardTemplate.objects.create(
                school=school,
                name=copy_name,
                user_type=source.user_type,
                orientation=source.orientation,
                front_background=source.front_background,
                back_background=source.back_background,
                layout_config=source.layout_config,
                is_active=True,
                is_default=False,
                created_by=request.user
            )
            return Response(IDCardTemplateSerializer(cloned, context={'school': school}).data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return format_error_response(exc)


class IDCardRecordViewSet(BaseIDCardViewSet):
    queryset = IDCardRecord.objects.all()
    serializer_class = IDCardRecordSerializer

    def get_queryset(self):
        school = self.get_school()
        if not school:
            return IDCardRecord.objects.none()
        qs = IDCardRecord.objects.filter(school=school).select_related('template', 'student', 'staff', 'student__school_class')

        user_type = self.request.query_params.get('user_type')
        card_status = self.request.query_params.get('status')
        class_id = self.request.query_params.get('school_class')
        division = self.request.query_params.get('division')
        academic_year_id = self.request.query_params.get('academic_year')
        search = self.request.query_params.get('search')

        if user_type:
            qs = qs.filter(user_type=user_type)
        if card_status:
            qs = qs.filter(card_status=card_status)
        if class_id:
            qs = qs.filter(student__school_class_id=class_id)
        if division:
            qs = qs.filter(student__division=division)
        if academic_year_id:
            qs = qs.filter(student__academic_year_id=academic_year_id)
        if search:
            q = search.strip()
            qs = qs.filter(
                Q(card_number__icontains=q) |
                Q(student__name__icontains=q) |
                Q(student__surname__icontains=q) |
                Q(student__gr_no__icontains=q) |
                Q(staff__name__icontains=q)
            )
        return qs

    @action(detail=False, methods=['post'], url_path='check-readiness')
    def check_readiness(self, request):
        """
        Pre-generation validation: Check for missing critical fields (photo, blood group, roll no, etc.)
        before initiating bulk card printing.
        """
        try:
            school = self.get_school()
            if not school:
                raise PermissionDenied("Your account is not linked to any school.")

            user_type = request.data.get('user_type', 'STUDENT')
            user_ids = request.data.get('user_ids', [])
            template_id = request.data.get('template_id')

            template = None
            if template_id:
                template = IDCardTemplate.objects.filter(id=template_id, school=school).first()
            if not template:
                template = IDCardTemplate.objects.filter(school=school, user_type=user_type, is_default=True).first() or \
                           IDCardTemplate.objects.filter(school=school, user_type=user_type).first()

            required_checks = request.data.get('required_fields', ['name', 'photo', 'blood_group'])
            results = []
            ready_count = 0
            missing_count = 0

            if user_type == 'STUDENT':
                users = Student.objects.filter(school=school, id__in=user_ids) if user_ids else Student.objects.filter(school=school, is_active=True)
                for s in users:
                    udata = resolve_card_data('STUDENT', s, school)
                    missing = []
                    if 'photo' in required_checks and not udata.get('photo_path'):
                        missing.append('Photograph')
                    if 'blood_group' in required_checks and (not udata.get('blood_group') or udata.get('blood_group') == 'N/A'):
                        missing.append('Blood Group')
                    if 'roll_no' in required_checks and (not udata.get('roll_no') or udata.get('roll_no') == 'N/A'):
                        missing.append('Roll No')
                    if 'emergency_contact' in required_checks and (not udata.get('emergency_contact') or udata.get('emergency_contact') == 'N/A'):
                        missing.append('Emergency Contact')

                    is_ready = len(missing) == 0
                    if is_ready:
                        ready_count += 1
                    else:
                        missing_count += 1

                    results.append({
                        'id': s.id,
                        'name': udata.get('name'),
                        'gr_no': udata.get('gr_no'),
                        'class_div': udata.get('class_div'),
                        'is_ready': is_ready,
                        'missing_fields': missing,
                        'has_existing_card': s.id_card_records.filter(card_status__in=['ISSUED', 'REISSUED']).exists()
                    })
            else:
                users = Staff.objects.filter(school=school, id__in=user_ids) if user_ids else Staff.objects.filter(school=school, is_active=True)
                for st in users:
                    udata = resolve_card_data('STAFF', st, school)
                    missing = []
                    if 'photo' in required_checks and not udata.get('photo_path'):
                        missing.append('Photograph')
                    if 'blood_group' in required_checks and (not udata.get('blood_group') or udata.get('blood_group') == 'N/A'):
                        missing.append('Blood Group')
                    if 'emergency_contact' in required_checks and (not udata.get('emergency_contact') or udata.get('emergency_contact') == 'N/A'):
                        missing.append('Emergency Contact')

                    is_ready = len(missing) == 0
                    if is_ready:
                        ready_count += 1
                    else:
                        missing_count += 1

                    results.append({
                        'id': st.id,
                        'name': udata.get('name'),
                        'department': udata.get('department'),
                        'designation': udata.get('designation'),
                        'is_ready': is_ready,
                        'missing_fields': missing,
                        'has_existing_card': st.id_card_records.filter(card_status__in=['ISSUED', 'REISSUED']).exists()
                    })

            return Response({
                'total_count': len(results),
                'ready_count': ready_count,
                'missing_count': missing_count,
                'users': results,
                'template_selected': template.name if template else None
            })
        except Exception as exc:
            return format_error_response(exc)

    @action(detail=False, methods=['post'], url_path='generate-cards')
    @transaction.atomic
    def generate_cards(self, request):
        """
        Card generation & Issuance engine:
        - Mode: Single Card PVC Print or A4 Sheet Grid Print
        - Action: PREVIEW (returns PDF without issuing) or ISSUE / REISSUE (persists IDCardRecord & history)
        """
        try:
            school = self.get_school()
            if not school:
                raise PermissionDenied("Your account is not linked to any school.")

            template_id = request.data.get('template_id')
            user_type = request.data.get('user_type', 'STUDENT')
            user_ids = request.data.get('user_ids', [])
            print_mode = request.data.get('print_mode', 'PVC')  # PVC or A4_GRID
            include_back = request.data.get('include_back', True)
            action_type = request.data.get('action_type', 'PREVIEW')  # PREVIEW, ISSUE, REISSUE
            reissue_reason = request.data.get('reissue_reason', '')
            valid_upto_str = request.data.get('valid_upto')

            if not template_id:
                template = IDCardTemplate.objects.filter(school=school, user_type=user_type, is_default=True).first() or \
                           IDCardTemplate.objects.filter(school=school, user_type=user_type).first()
            else:
                template = IDCardTemplate.objects.filter(id=template_id, school=school).first()

            if not template:
                raise DRFValidationError({"template": "Please create or select an ID card template first."})

            if not user_ids:
                raise DRFValidationError({"user_ids": "Please select at least one person to generate an ID card."})

            # Fetch targeted users
            if user_type == 'STUDENT':
                users = list(Student.objects.filter(school=school, id__in=user_ids).select_related('school_class'))
            else:
                users = list(Staff.objects.filter(school=school, id__in=user_ids).select_related('department'))

            if not users:
                raise DRFValidationError({"users": "No matching user records found."})

            valid_upto = None
            if valid_upto_str:
                try:
                    from django.utils.dateparse import parse_date
                    valid_upto = parse_date(valid_upto_str)
                except Exception:
                    pass

            records_and_data = []

            for u in users:
                # Find existing card
                existing_card = None
                if user_type == 'STUDENT':
                    existing_card = IDCardRecord.objects.filter(school=school, student=u, card_status__in=['ISSUED', 'REISSUED']).order_by('-version').first()
                else:
                    existing_card = IDCardRecord.objects.filter(school=school, staff=u, card_status__in=['ISSUED', 'REISSUED']).order_by('-version').first()

                card_rec = existing_card

                if action_type in ['ISSUE', 'REISSUE']:
                    card_num = f"IDC-{user_type[:3]}-{school.id}-{u.id}-{int(timezone.now().timestamp()) % 100000}"
                    version = 1
                    if action_type == 'REISSUE' and existing_card:
                        version = existing_card.version + 1
                        existing_card.card_status = 'REISSUED'
                        existing_card.save(update_fields=['card_status', 'updated_at'])

                    card_rec = IDCardRecord.objects.create(
                        school=school,
                        template=template,
                        user_type=user_type,
                        student=u if user_type == 'STUDENT' else None,
                        staff=u if user_type == 'STAFF' else None,
                        card_number=card_num,
                        card_status='ISSUED',
                        issue_date=timezone.now().date(),
                        valid_upto=valid_upto,
                        blood_group=request.data.get('blood_group') or getattr(u, 'blood_group', ''),
                        emergency_contact=request.data.get('emergency_contact') or getattr(u, 'emergency_contact', ''),
                        custom_field_1_value=request.data.get('custom_1') or '',
                        custom_field_2_value=request.data.get('custom_2') or '',
                        custom_field_3_value=request.data.get('custom_3') or '',
                        version=version,
                        reissue_reason=reissue_reason if action_type == 'REISSUE' else '',
                        previous_card=existing_card if action_type == 'REISSUE' else None,
                        issued_by=request.user
                    )

                    # Log audit history
                    IDCardLog.objects.create(
                        school=school,
                        card_record=card_rec,
                        action='REISSUED' if action_type == 'REISSUE' else 'ISSUED',
                        remarks=reissue_reason if action_type == 'REISSUE' else f"Card issued with template '{template.name}'",
                        performed_by=request.user
                    )

                # Prepare dynamic data
                udata = resolve_card_data(user_type, u, school, card_rec, template)
                if card_rec and action_type in ['ISSUE', 'REISSUE']:
                    card_rec.snapshot_data = udata
                    card_rec.save(update_fields=['snapshot_data', 'updated_at'])

                records_and_data.append((card_rec, udata))

            # Generate PDF based on print mode
            if print_mode == 'A4_GRID' or len(records_and_data) > 1:
                pdf_bytes = generate_a4_grid_pdf(template, records_and_data, include_back=include_back)
                filename = f"ID_Cards_A4_Batch_{user_type}.pdf"
            else:
                rec, udata = records_and_data[0]
                pdf_bytes = generate_single_card_pdf(template, rec, udata, include_back=include_back)
                filename = f"ID_Card_PVC_{rec.card_number if rec else 'Preview'}.pdf"

            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            response['X-Generated-Count'] = str(len(records_and_data))
            return response
        except Exception as exc:
            return format_error_response(exc)

    @action(detail=True, methods=['get'], url_path='download-pdf')
    def download_card_pdf(self, request, pk=None):
        """Download high quality printable PDF for a single card."""
        try:
            card = self.get_object()
            school = self.get_school()
            template = card.template
            user_obj = card.student if card.user_type == 'STUDENT' else card.staff
            udata = resolve_card_data(card.user_type, user_obj, school, card, template)

            pdf_bytes = generate_single_card_pdf(template, card, udata, include_back=True)

            # Audit log
            IDCardLog.objects.create(
                school=school,
                card_record=card,
                action='DOWNLOADED',
                remarks='Single card PVC PDF downloaded',
                performed_by=request.user
            )

            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="ID_Card_{card.card_number}.pdf"'
            return response
        except Exception as exc:
            return format_error_response(exc)

    @action(detail=True, methods=['post'], url_path='reissue')
    @transaction.atomic
    def reissue_card(self, request, pk=None):
        """Reissue a card with version tracking without overwriting previous card history."""
        try:
            previous_card = self.get_object()
            school = self.get_school()
            reason = request.data.get('reissue_reason', 'Reissuance request')
            template_id = request.data.get('template_id')
            template = IDCardTemplate.objects.filter(id=template_id, school=school).first() if template_id else previous_card.template

            previous_card.card_status = 'REISSUED'
            previous_card.save(update_fields=['card_status', 'updated_at'])

            new_card_num = f"IDC-{previous_card.user_type[:3]}-{school.id}-{previous_card.student_id or previous_card.staff_id}-{int(timezone.now().timestamp()) % 100000}"
            new_card = IDCardRecord.objects.create(
                school=school,
                template=template,
                user_type=previous_card.user_type,
                student=previous_card.student,
                staff=previous_card.staff,
                card_number=new_card_num,
                card_status='ISSUED',
                issue_date=timezone.now().date(),
                valid_upto=previous_card.valid_upto,
                blood_group=request.data.get('blood_group') or previous_card.blood_group,
                emergency_contact=request.data.get('emergency_contact') or previous_card.emergency_contact,
                custom_field_1_value=request.data.get('custom_1') or previous_card.custom_field_1_value,
                custom_field_2_value=request.data.get('custom_2') or previous_card.custom_field_2_value,
                custom_field_3_value=request.data.get('custom_3') or previous_card.custom_field_3_value,
                version=previous_card.version + 1,
                reissue_reason=reason,
                previous_card=previous_card,
                issued_by=request.user
            )

            IDCardLog.objects.create(
                school=school,
                card_record=new_card,
                action='REISSUED',
                remarks=f"Reissued (v{new_card.version}) replacing {previous_card.card_number}. Reason: {reason}",
                performed_by=request.user
            )

            return Response(IDCardRecordSerializer(new_card, context={'school': school}).data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return format_error_response(exc)

    @action(detail=True, methods=['post'], url_path='update-status')
    def update_card_status(self, request, pk=None):
        """Update lifecycle status: ISSUED, EXPIRED, LOST_DAMAGED."""
        try:
            card = self.get_object()
            new_status = request.data.get('status')
            remarks = request.data.get('remarks', '')

            valid_statuses = ['ISSUED', 'REISSUED', 'EXPIRED', 'LOST_DAMAGED']
            if new_status not in valid_statuses:
                raise DRFValidationError({"status": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"})

            old_status = card.card_status
            card.card_status = new_status
            card.save(update_fields=['card_status', 'updated_at'])

            IDCardLog.objects.create(
                school=self.get_school(),
                card_record=card,
                action='STATUS_CHANGED',
                remarks=f"Status changed from {old_status} to {new_status}. {remarks}".strip(),
                performed_by=request.user
            )

            return Response(IDCardRecordSerializer(card, context={'school': self.get_school()}).data)
        except Exception as exc:
            return format_error_response(exc)


class IDCardLogViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IDCardLogSerializer
    queryset = IDCardLog.objects.all()

    def get_queryset(self):
        user = self.request.user
        school_id = self.request.headers.get('X-School-ID') or self.request.query_params.get('school_id')
        school = School.objects.filter(id=school_id).first() if school_id else (getattr(user, 'school', None) or School.objects.first())
        if not school:
            return IDCardLog.objects.none()
        qs = IDCardLog.objects.filter(school=school).select_related('card_record', 'performed_by')
        card_id = self.request.query_params.get('card_record')
        if card_id:
            qs = qs.filter(card_record_id=card_id)
        return qs
