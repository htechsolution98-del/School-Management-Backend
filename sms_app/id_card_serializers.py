from rest_framework import serializers
from .id_card_models import IDCardTemplate, IDCardRecord, IDCardLog
from .models import Student, Staff, SchoolClass, AcademicYear


class IDCardTemplateSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    records_count = serializers.SerializerMethodField()

    class Meta:
        model = IDCardTemplate
        fields = [
            'id', 'school', 'name', 'user_type', 'orientation',
            'front_background', 'back_background', 'layout_config',
            'is_active', 'is_default', 'created_by', 'created_by_name',
            'records_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'created_by', 'created_at', 'updated_at']

    def get_records_count(self, obj):
        return obj.records.count()

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Template name is required and cannot be blank.")
        school = self.context.get('school')
        if school:
            qs = IDCardTemplate.objects.filter(school=school, name__iexact=name)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(f"A template named '{name}' already exists in your school.")
        return name

    def validate(self, attrs):
        school = self.context.get('school')
        if not school:
            raise serializers.ValidationError("School context is required.")
        return attrs


class IDCardRecordSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.name', read_only=True)
    template_orientation = serializers.CharField(source='template.orientation', read_only=True)
    student_name = serializers.SerializerMethodField()
    student_gr_no = serializers.CharField(source='student.gr_no', read_only=True)
    student_roll = serializers.CharField(source='student.roll_no', read_only=True)
    student_class = serializers.CharField(source='student.school_class.school_class', read_only=True)
    student_division = serializers.CharField(source='student.division', read_only=True)
    staff_name = serializers.CharField(source='staff.name', read_only=True)
    staff_department = serializers.CharField(source='staff.department.name', read_only=True)
    staff_designation = serializers.CharField(source='staff.designation', read_only=True)
    issued_by_name = serializers.CharField(source='issued_by.username', read_only=True)

    class Meta:
        model = IDCardRecord
        fields = [
            'id', 'school', 'template', 'template_name', 'template_orientation',
            'user_type', 'student', 'student_name', 'student_gr_no', 'student_roll',
            'student_class', 'student_division', 'staff', 'staff_name',
            'staff_department', 'staff_designation', 'card_number', 'card_status',
            'issue_date', 'valid_upto', 'blood_group', 'emergency_contact',
            'custom_field_1_value', 'custom_field_2_value', 'custom_field_3_value',
            'version', 'reissue_reason', 'previous_card', 'snapshot_data',
            'front_image', 'back_image', 'pdf_file', 'issued_by', 'issued_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'card_number', 'version', 'issued_by', 'created_at', 'updated_at']

    def get_student_name(self, obj):
        if not obj.student:
            return None
        return f"{obj.student.name or ''} {obj.student.surname or ''}".strip()


class IDCardLogSerializer(serializers.ModelSerializer):
    card_number = serializers.CharField(source='card_record.card_number', read_only=True)
    target_name = serializers.SerializerMethodField()
    performed_by_name = serializers.CharField(source='performed_by.username', read_only=True)

    class Meta:
        model = IDCardLog
        fields = [
            'id', 'school', 'card_record', 'card_number', 'target_name',
            'action', 'remarks', 'performed_by', 'performed_by_name', 'timestamp'
        ]
        read_only_fields = ['id', 'school', 'performed_by', 'timestamp']

    def get_target_name(self, obj):
        rec = obj.card_record
        if rec.student:
            return f"{rec.student.name or ''} {rec.student.surname or ''}".strip()
        if rec.staff:
            return rec.staff.name or ""
        return "N/A"
