from rest_framework import serializers
from .models import *

class ClassCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassCategory
        fields = "__all__"
        read_only_fields = ["school"]

class SchoolClassSerializer(serializers.ModelSerializer):

    class Meta:
        model = SchoolClass
        fields = ["id", "school_class", "category"]

    def validate(self, data):
        request = self.context.get("request")
        school = request.user.school
        school_class = data.get("school_class")

        # Prevent duplicate in DB
        if school_class and SchoolClass.objects.filter(
            school=school, school_class__iexact=school_class
        ).exists():
            raise serializers.ValidationError(
                {"message": f"{school_class} already exists"}
            )

        return data

    def create(self, validated_data):
        request = self.context.get("request")
        school = request.user.school

        return SchoolClass.objects.create(
            school=school,
            school_class=validated_data["school_class"],
            category=validated_data.get("category"),
        )


# # ================================================ modified serializers for admission form 23/04/26


# ===================== FORMFIELD =====================
# 1
ALLOWED_STUDENT_FIELD_MAPPINGS = {
    "surname",
    "name",
    "father_name",
    "mother_name",
    "date_of_birth",
    "mobile",
    "school_class",
    "division",
    "admission_date",
    "academic_year",
    "aadhar_number",
}




class SetDivisionSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(
        source="SchoolClass.school_class", read_only=True
    )

    class Meta:
        model = Division
        fields = ["id", "SchoolClass", "class_name", "division", "capacity"]




class SetDivisionListSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(
        source="SchoolClass.school_class", read_only=True
    )

    class Meta:
        model = Division
        fields = ["id", "SchoolClass", "class_name", "division", "capacity"]


# =========serializers for set division by clerk========
# NOT IN USE
import string




class DivisionSetSerilaizer(serializers.ModelSerializer):
    capacity = serializers.IntegerField(write_only=True)

    class Meta:
        model = Student
        fields = ["division", "capacity"]

    def create(self, validated_data):
        total_division = int(validated_data.pop("division"))
        capacity = validated_data.pop("capacity")

        alphabet = string.ascii_uppercase[:total_division]

        alphabet_len = len(alphabet)

        alphabet = list(string.ascii_uppercase[:alphabet_len])

        students = Student.objects.all().order_by("created_at")

        for index, student in enumerate(students):
            division = alphabet[index % alphabet_len]  # round-robin assignment
            student.division = division
            student.save()

        return students


# ==========CLERK UPDATE AND VERIFY DATA===============GET,PUT
# clerk side verify serializerfrom django.db import transaction


# =======================
# Field Value Serializer
# =======================




class SetSubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = "__all__"
        read_only_fields = ["school"]




class SyllabusSerializer(serializers.ModelSerializer):

    class Meta:
        model = Syllabus
        fields = "__all__"
        read_only_fields = ["school"]


# NEED VALIDATION OF SAME SUBJECT AS SAME DIVISION
# --------ASSIGN CLASS-------

from rest_framework import serializers




class AssignClassSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.name", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    class_name = serializers.CharField(
        source="division.SchoolClass.school_class", read_only=True
    )
    division_name = serializers.CharField(source="division.division", read_only=True)

    class Meta:
        model = AssignClass
        fields = [
            "id",
            "teacher",
            "teacher_name",
            "subject",
            "subject_name",
            "division",
            "division_name",
            "class_name",
            "is_class_teacher",
        ]

        read_only_fields = ["teacher_name", "subject_name", "division_name", "class_name"]

    def validate(self, data):
        request = self.context.get("request")
        school = request.user.school if request else None

        division = data.get("division")
        teacher = data.get("teacher")
        subject = data.get("subject")
        is_class_teacher = data.get("is_class_teacher", False)

        instance_id = self.instance.id if self.instance else None

        if is_class_teacher:
            # Rule 1: A division can only have ONE class teacher
            existing_div_class_teacher = (
                AssignClass.objects.filter(
                    school=school, division=division, is_class_teacher=True
                )
                .exclude(id=instance_id)
                .first()
            )
            if existing_div_class_teacher:
                teacher_name = (
                    existing_div_class_teacher.teacher.name
                    if existing_div_class_teacher.teacher
                    else "another teacher"
                )
                raise serializers.ValidationError(
                    f"This division already has a Class Teacher ({teacher_name})."
                )

            # Rule 2: A teacher can be Class Teacher of ONLY ONE division across the school
            existing_teacher_class_teacher = (
                AssignClass.objects.filter(
                    school=school, teacher=teacher, is_class_teacher=True
                )
                .exclude(id=instance_id)
                .first()
            )
            if existing_teacher_class_teacher:
                div = existing_teacher_class_teacher.division
                div_name = (
                    f"{div.SchoolClass.school_class} - Div {div.division}"
                    if div and div.SchoolClass
                    else "another division"
                )
                t_name = teacher.name if teacher else "This teacher"
                raise serializers.ValidationError(
                    f"Teacher '{t_name}' is already the Class Teacher for {div_name}. A teacher can only be Class Teacher for one division."
                )

        # Rule 3: Avoid duplicate exact teacher+division+subject assignment
        filter_kwargs = {"teacher": teacher, "division": division, "subject": subject}
        if school:
            filter_kwargs["school"] = school

        if (
            AssignClass.objects.filter(**filter_kwargs)
            .exclude(id=instance_id)
            .exists()
        ):
            raise serializers.ValidationError(
                "This teacher is already assigned to this subject for this division."
            )

        return data

    def create(self, validated_data):
        request = self.context.get("request")
        if request and hasattr(request.user, "school") and request.user.school:
            validated_data["school"] = request.user.school
        return super().create(validated_data)


# ----------TO GET ADMISSION DATA TO TRUSTEE----------------
# class AdmissionDocumentReadSerializer(serializers.ModelSerializer):
#     document_label = serializers.CharField(
#         source="document_field.label", read_only=True
#     )

#     class Meta:
#         model = AdmissionDocument
#         fields = ["id", "document_field", "document_label", "file"]




class Tt_day_timeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tt_day_time
        fields = "__all__"
        read_only_fields = ["day"]




class Tt_breaksSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tt_breaks
        fields = "__all__"
        read_only_fields = ["day"]




class Tt_slotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tt_slot
        fields = ["id", "lecture", "slot"]
        read_only_fields = ["id", "lecture"]




class SetTimeTableSerializer(serializers.ModelSerializer):
    year_value = serializers.CharField(source="year.year", read_only=True)
    division_name = serializers.CharField(source="class_div.division", read_only=True)
    class_name = serializers.CharField(
        source="class_div.SchoolClass.school_class", read_only=True
    )
    teacher_name = serializers.CharField(source="teacher.name", read_only=True)

    class Meta:
        model = Time_table
        fields = [
            "id",
            "year",
            "year_value",
            "day",
            "class_div",
            "division_name",
            "class_name",
            "teacher",
            "teacher_name",
            "slot",
            "start",
            "end",
        ]


from django.db import transaction




class Tt_yearSerializer(serializers.ModelSerializer):
    start_year = serializers.IntegerField(write_only=True)
    end_year = serializers.IntegerField(write_only=True)

    class Meta:
        model = Tt_year
        fields = ["year", "start_year", "end_year"]

        read_only_fields = ["year"]

    def validate(self, data):
        start = data.get("start_year")
        end = data.get("end_year")

        if len(str(start)) != 4 or len(str(end)) != 4:
            raise serializers.ValidationError("Year must be 4 digits")

        if not (1900 <= start <= 2100):
            raise serializers.ValidationError(
                "Start year must be between 1900 and 2100"
            )

        if not (1900 <= end <= 2100):
            raise serializers.ValidationError("End year must be between 1900 and 2100")

        if end != start + 1:
            raise serializers.ValidationError("End year must be start_year + 1")

        return data

    def create(self, validated_data):
        start = validated_data.get("start_year")
        end = validated_data.get("end_year")

        year_str = f"{start}-{str(end)[-2:]}"

        request = self.context.get("request")
        school = getattr(getattr(request, "user", None), "school", None)

        if Tt_year.objects.filter(year=year_str).exists():
            raise serializers.ValidationError("This academic year already exists")

        with transaction.atomic():
            tt_year = Tt_year.objects.create(year=year_str, school=school)

        return tt_year




class Time_tableSerializer(serializers.ModelSerializer):
    year = serializers.PrimaryKeyRelatedField(
        queryset=Tt_year.objects.all(), write_only=True
    )

    day = serializers.CharField(write_only=True)
    lecture = serializers.CharField(write_only=True)

    class_div = serializers.PrimaryKeyRelatedField(
        queryset=Division.objects.all(), write_only=True, required=False
    )
    division = serializers.PrimaryKeyRelatedField(
        queryset=Division.objects.all(), write_only=True, required=False
    )

    day_time = Tt_day_timeSerializer(write_only=True)
    breaks = Tt_breaksSerializer(write_only=True, many=True)
    slot = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False
    )

    class Meta:
        model = Tt_year
        fields = [
            "id",
            "year",
            "day",
            "lecture",
            "class_div",
            "division",
            "day_time",
            "breaks",
            "slot",
        ]
        # read_only_fields = ["year"]

    def validate(self, data):
        slot_data = data.get("slot", [])
        class_div = data.get("class_div") or data.get("division")
        year = data.get("year")
        day = data.get("day")

        if not class_div:
            raise serializers.ValidationError({"class_div": "This field is required."})

        if year and day and class_div:
            if Tt_day.objects.filter(
                year=year,
                day=day,
                class_div=class_div,
            ).exists():
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "This timetable already exists for the selected year, day and class division."
                        ]
                    }
                )

        for item in slot_data:
            if "slot" not in item or "start" not in item or "end" not in item:
                raise serializers.ValidationError(
                    "Each slot must have slot, start and end"
                )

        return data

    def create(self, validated_data):

        request = self.context.get("request")
        school = getattr(getattr(request, "user", None), "school", None)

        year = validated_data.pop("year")
        day = validated_data.pop("day")
        lecture = validated_data.pop("lecture")
        class_div = validated_data.pop("class_div", None) or validated_data.pop(
            "division", None
        )

        day_time_data = validated_data.pop("day_time")

        breaks_data = validated_data.pop("breaks")
        slot_data = validated_data.pop("slot", [])

        with transaction.atomic():

            tt_day = Tt_day.objects.create(
                school=school,
                year=year,
                day=day,
                class_div=class_div,
                lecture=lecture,
            )

            Tt_day_time.objects.create(
                school=school,
                day=tt_day,
                start=day_time_data.get("start"),
                end=day_time_data.get("end"),
            )

            for b in breaks_data:
                Tt_breaks.objects.create(
                    day=tt_day,
                    total_breaks=b.get("total_breaks"),
                    breaks=b.get("breaks"),
                    time=b.get("time"),
                    description=b.get("description"),
                )

            for item in slot_data:
                Tt_slot.objects.create(
                    school=school,
                    day=tt_day,
                    lecture=str(item.get("slot")),
                    slot={
                        "slot": item.get("slot"),
                        "start": item.get("start"),
                        "end": item.get("end"),
                    },
                )

        self._created_day_id = tt_day.id
        return year

    def to_representation(self, instance):
        request = self.context.get("request")
        days = instance.tt_day_set.all()

        class_div = request.query_params.get("class_div") if request else None
        class_id = request.query_params.get("class_id") if request else None

        if class_div:
            days = days.filter(class_div_id=class_div)

        if class_id:
            days = days.filter(class_div__SchoolClass_id=class_id)

        if request and request.method == "POST":
            created_day_id = getattr(self, "_created_day_id", None)
            if created_day_id:
                days = days.filter(id=created_day_id)

        data = {
            "id": instance.id,
            "year": instance.year,
            "days": [
                {
                    "id": d.id,
                    "day": d.day,
                    "lecture": d.lecture,
                    "class_div": (
                        {
                            "id": d.class_div.id,
                            "division": d.class_div.division,
                            "class_id": (
                                d.class_div.SchoolClass.id
                                if d.class_div and d.class_div.SchoolClass
                                else None
                            ),
                            "class_name": (
                                d.class_div.SchoolClass.school_class
                                if d.class_div and d.class_div.SchoolClass
                                else None
                            ),
                        }
                        if d.class_div
                        else None
                    ),
                    "day_time": (
                        {
                            "id": d.tt_day_time_set.first().id,
                            "start": str(d.tt_day_time_set.first().start),
                            "end": str(d.tt_day_time_set.first().end),
                        }
                        if d.tt_day_time_set.exists()
                        else None
                    ),
                    "breaks": [
                        {
                            "id": b.id,
                            "total_breaks": b.total_breaks,
                            "breaks": b.breaks,
                            "time": b.time,
                            "description": b.description,
                        }
                        for b in d.tt_breaks_set.all()
                    ],
                    "slot": [
                        {
                            "id": s.id,
                            "lecture": s.lecture,
                            "slot": s.slot,
                        }
                        for s in d.tt_slot_set.all()
                    ],
                }
                for d in days
            ],
        }

        if request and request.method == "POST":
            return {
                "message": "Table created successfully",
                "data": data,
            }

        return data




class AttendanceLocationSerializer(serializers.ModelSerializer):
    start_time = serializers.TimeField(source='time_rule.start_time',required=False, allow_null=True)
    end_time = serializers.TimeField(source='time_rule.end_time',required=False, allow_null=True)
    half_day_time = serializers.TimeField(source='time_rule.half_day_time',required=False, allow_null=True)

    class Meta:
        model = AttendanceLocation
        fields = [
            "id",
            "latitude",
            "longitude",
            "radius",
            "school",
            "start_time",
            "end_time",
            "half_day_time",
        ]
        read_only_fields = ["school"]

    def validate(self, attrs):
        return super().validate(attrs)

    def create(self, validated_data):
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            raise serializers.ValidationError("Request user is required.")

        school = getattr(request.user, "school", None)
        if not school:
            raise serializers.ValidationError("User school is not configured.")

        time_rule_data = validated_data.pop("time_rule", None)

        existing_location = AttendanceLocation.objects.filter(school=school).first()

        if existing_location:
            existing_location.latitude = validated_data.get("latitude", existing_location.latitude)
            existing_location.longitude = validated_data.get("longitude", existing_location.longitude)
            existing_location.radius = validated_data.get("radius", existing_location.radius)

            if time_rule_data:
                if existing_location.time_rule:
                    time_rule = existing_location.time_rule
                    time_rule.start_time = time_rule_data.get("start_time", time_rule.start_time)
                    time_rule.end_time = time_rule_data.get("end_time", time_rule.end_time)
                    time_rule.half_day_time = time_rule_data.get("half_day_time", time_rule.half_day_time)
                    time_rule.save()
                else:
                    time_rule = AttendanceTimeRule.objects.create(
                        school=school,
                        start_time=time_rule_data.get("start_time"),
                        end_time=time_rule_data.get("end_time"),
                        half_day_time=time_rule_data.get("half_day_time"),
                    )
                    existing_location.time_rule = time_rule

            existing_location.save()
            return existing_location

        time_rule = None
        if time_rule_data:
            time_rule = AttendanceTimeRule.objects.create(
                school=school,
                start_time=time_rule_data.get("start_time"),
                end_time=time_rule_data.get("end_time"),
                half_day_time=time_rule_data.get("half_day_time"),
            )

        return AttendanceLocation.objects.create(
            school=school, time_rule=time_rule, **validated_data
        )

    def update(self, instance, validated_data):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None

        time_rule_data = validated_data.pop("time_rule", None)

        instance.latitude = validated_data.get("latitude", instance.latitude)
        instance.longitude = validated_data.get("longitude", instance.longitude)
        instance.radius = validated_data.get("radius", instance.radius)

        if time_rule_data:
            if instance.time_rule:
                time_rule = instance.time_rule
                time_rule.start_time = time_rule_data.get("start_time", time_rule.start_time)
                time_rule.end_time = time_rule_data.get("end_time", time_rule.end_time)
                time_rule.half_day_time = time_rule_data.get("half_day_time", time_rule.half_day_time)
                time_rule.save()
            else:
                time_rule = AttendanceTimeRule.objects.create(
                    school=school,
                    start_time=time_rule_data.get("start_time"),
                    end_time=time_rule_data.get("end_time"),
                    half_day_time=time_rule_data.get("half_day_time"),
                )
                instance.time_rule = time_rule

        instance.save()
        return instance




class AttendanceSerializer(serializers.ModelSerializer):

    latitude = serializers.CharField(write_only=True)
    longitude = serializers.CharField(write_only=True)
    # radius = serializers.CharField(write_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id",
            "latitude",
            "longitude",
            "school",
            "staff",
            "attendance_date",
            "date_time",
            "name",
            "category",
            "is_present",
            "is_half_day",
            "check_in",
            "check_out",
        ]

        read_only_fields = [
            "id",
            "school",
            "staff",
            "attendance_date",
            "date_time",
            "name",
            "category",
            "is_present",
            "is_half_day",
            "check_in",
            "check_out",
        ]

    def validate_latitude(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError("Latitude must be a valid number.")
        if value < -90 or value > 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError("Longitude must be a valid number.")
        if value < -180 or value > 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            raise serializers.ValidationError(
                "Request user is required for attendance validation."
            )

        school = getattr(request.user, "school", None)
        if not school:
            raise serializers.ValidationError("User school is not configured.")

        attendance_location = AttendanceLocation.objects.filter(
            school=school.id
        ).first()
        if not attendance_location:
            raise serializers.ValidationError(
                "Attendance location is not configured for this school."
            )

        staff = Staff.objects.filter(user=request.user).first()
        if not staff:
            raise serializers.ValidationError(
                "Staff profile not found for current user."
            )

        today = timezone.localdate()
        attendance = Attendance.objects.filter(
            staff=staff, attendance_date=today
        ).first()
        if attendance and attendance.check_out:
            raise serializers.ValidationError(
                "Check-out has already been recorded for today."
            )

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        school = request.user.school
        user = request.user

        latitude = validated_data.pop("latitude", None)
        longitude = validated_data.pop("longitude", None)

        attendance_location = AttendanceLocation.objects.filter(
            school=school.id
        ).first()

        loc_latitude = attendance_location.latitude
        loc_longitude = attendance_location.longitude
        loc_radius = attendance_location.radius

        is_inside = is_inside_radius(
            float(latitude),
            float(longitude),
            float(loc_latitude),
            float(loc_longitude),
            float(loc_radius),
        )

        if not is_inside:
            raise serializers.ValidationError(
                "You are not within the attendance radius."
            )

        staff = Staff.objects.filter(user=user).first()
        attendance_rule = AttendanceTimeRule.objects.filter(school=school).first()
        now = timezone.localtime()
        current_time = now.time()

        with transaction.atomic():
            today = timezone.localdate()
            rule_start_time = attendance_rule.start_time if attendance_rule else None
            attendance, created = Attendance.objects.select_for_update().get_or_create(
                staff=staff,
                attendance_date=today,
                defaults={
                    "school": school,
                    "category": staff.category,
                    "name": staff.name,
                    "is_present": True,
                    "date_time": now,
                    "check_in": now,
                    "is_half_day": is_after_time(current_time, rule_start_time),
                },
            )

            if not created:
                if attendance.check_out:
                    raise serializers.ValidationError(
                        "Check-out has already been recorded for today."
                    )

                attendance.check_out = now
                update_fields = ["check_out"]

                rule_end_time = attendance_rule.end_time if attendance_rule else None
                if is_before_time(current_time, rule_end_time):
                    attendance.is_half_day = True
                    update_fields.append("is_half_day")

                attendance.save(update_fields=update_fields)
                return attendance

            return attendance




class AcademicYearSerializer(serializers.ModelSerializer):
    start_year = serializers.IntegerField(write_only=True, required=False)
    end_year = serializers.IntegerField(write_only=True, required=False)

    month_numbers = serializers.SerializerMethodField()
    billing_periods = serializers.SerializerMethodField()

    class Meta:
        model = AcademicYear
        fields = [
            "id",
            "school",
            "name",
            "start_month",
            "end_month",
            "start_year",
            "end_year",
            "month_numbers",
            "billing_periods",
            "is_active",
        ]
        read_only_fields = ["school", "name"]

    def get_month_numbers(self, obj):
        return obj.get_month_numbers()

    def get_billing_periods(self, obj):
        return obj.get_billing_periods()

    def validate(self, attrs):
        start_month = attrs.get(
            "start_month", getattr(self.instance, "start_month", None)
        )
        end_month = attrs.get(
            "end_month", getattr(self.instance, "end_month", None)
        )

        if not self.instance and (start_month is None or end_month is None):
            raise serializers.ValidationError(
                {
                    "start_month": "Start month is required.",
                    "end_month": "End month is required.",
                }
            )

        for field_name, month in [
            ("start_month", start_month),
            ("end_month", end_month),
        ]:
            if month is not None and (month < 1 or month > 12):
                raise serializers.ValidationError(
                    {field_name: "Month must be between 1 and 12."}
                )

        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None

        start_year = attrs.get("start_year")
        end_year = attrs.get("end_year")

        if start_year is not None or end_year is not None:

            if start_year is None or end_year is None:
                raise serializers.ValidationError(
                    {
                        "start_year": "Both start_year and end_year are required.",
                        "end_year": "Both start_year and end_year are required.",
                    }
                )

            if len(str(start_year)) != 4 or len(str(end_year)) != 4:
                raise serializers.ValidationError(
                    "Year values must be 4 digits."
                )

            if end_year != start_year + 1:
                raise serializers.ValidationError(
                    "End year must be start_year + 1."
                )

            attrs["name"] = f"{start_year}-{str(end_year)[-2:]}"

        name = attrs.get("name", getattr(self.instance, "name", None))

        if school and name:
            queryset = AcademicYear.objects.filter(school=school, name=name)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError(
                    {"name": "This academic year already exists for this school."}
                )

        return attrs

    def create(self, validated_data):
        validated_data.pop("start_year", None)
        validated_data.pop("end_year", None)

        is_active = validated_data.get("is_active", False)
        school = validated_data.get("school")
        if is_active and school:
            AcademicYear.objects.filter(school=school).update(is_active=False)

        return AcademicYear.objects.create(**validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("start_year", None)
        validated_data.pop("end_year", None)

        is_active = validated_data.get("is_active", None)
        if is_active is True and instance.school:
            AcademicYear.objects.filter(school=instance.school).exclude(pk=instance.pk).update(is_active=False)

        return super().update(instance, validated_data)




class ClassDivSerializer(serializers.ModelSerializer):
    class Meta:
        model = Division
        fields = "__all__"

    # class SubjectSerializer(serializers.ModelSerializer):
    #     class Meta:
    #         model = Subject
    #         fields = "__all__"

    # class TeacherStaffSerializer(serializers.ModelSerializer):
    #     class Meta:
    #         model = Staff
    #         fields = "__all__"

    # class LectureSlotSerializer(serializers.ModelSerializer):
    #     class Meta:
    #         model = LectureSlot
    #         fields = "__all__"

    # class BreakSlotSerializer(serializers.ModelSerializer):
    #     class Meta:
    #         model = BreakSlot
    #         fields = "__all__"

    # class TimetableEntrySerializer(serializers.ModelSerializer):
    #     class Meta:
    #         model = TimetableEntry
    #         fields = "__all__"

    #     def validate(self, attrs):
    #         request = self.context.get("request")
    #         school = getattr(getattr(request, "user", None), "school", None)

    #         timetable = attrs.get("timetable", getattr(self.instance, "timetable", None))
    #         lecture_slot = attrs.get(
    #             "lecture_slot", getattr(self.instance, "lecture_slot", None)
    #         )
    #         subject = attrs.get("subject", getattr(self.instance, "subject", None))
    #         teacher_staff = attrs.get(
    #             "teacher_staff", getattr(self.instance, "teacher_staff", None)
    #         )

    #         if not timetable or not lecture_slot or not subject or not teacher_staff:
    #             return attrs

    #         if school and timetable.school_id != school.id:
    #             raise serializers.ValidationError(
    #                 {"timetable": "Invalid timetable for this school."}
    #             )

    #         if school and lecture_slot.school_id != school.id:
    #             raise serializers.ValidationError(
    #                 {"lecture_slot": "Invalid lecture slot for this school."}
    #             )

    #         if lecture_slot.timetable_id != timetable.id:
    #             raise serializers.ValidationError(
    #                 {"lecture_slot": "Lecture slot does not belong to this timetable."}
    #             )

    #         assigned_teacher = AssignClass.objects.filter(
    #             school=school,
    #             division=timetable.class_div,
    #             subject=subject,
    #             teacher=teacher_staff,
    #         )

    #         if not assigned_teacher.exists():
    #             raise serializers.ValidationError(
    #                 {
    #                     "teacher_staff": (
    #                         "This teacher is not assigned to this subject and division."
    #                     )
    #                 }
    #             )

    #         if lecture_slot.lecture_number == 1 and not assigned_teacher.filter(
    #             is_class_teacher=True
    #         ).exists():
    #             raise serializers.ValidationError(
    #                 {"teacher_staff": "First lecture must be assigned to class teacher."}
    #             )

    #         return attrs

    # class TimetableSerializer(serializers.ModelSerializer):

    #     lecture_slots = LectureSlotSerializer(many=True, required=False)
    #     break_slots = BreakSlotSerializer(many=True, required=False)
    #     working_days = serializers.ListField(
    #         child=serializers.ChoiceField(choices=WorkingDay.DAY_CHOICES),
    #         write_only=True,
    #         required=False,
    #     )

    #     class Meta:
    #         model = Timetable
    #         fields = "__all__"

    #     def create(self, validated_data):

    #         request = self.context["request"]
    #         school = request.user.school

    #         lectures = validated_data.pop("lecture_slots", [])
    #         breaks = validated_data.pop("break_slots", [])
    #         working_days = validated_data.pop("working_days", [])
    #         validated_data.pop("school", None)

    #         for day in working_days:
    #             WorkingDay.objects.get_or_create(school=school, day=day)

    #         timetable = Timetable.objects.create(
    #             school=school,
    #             **validated_data
    #         )

    #         for l in lectures:
    #             LectureSlot.objects.create(
    #                 school=school,
    #                 timetable=timetable,
    #                 **l
    #             )

    #         for b in breaks:
    #             BreakSlot.objects.create(
    #                 school=school,
    #                 timetable=timetable,
    #                 **b
    #             )

    #         return timetable

    def update(self, instance, validated_data):

        lectures = validated_data.pop("lecture_slots", None)
        breaks = validated_data.pop("break_slots", None)
        working_days = validated_data.pop("working_days", None)
        validated_data.pop("school", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        school = instance.school

        if working_days is not None:
            for day in working_days:
                WorkingDay.objects.get_or_create(school=school, day=day)

        if lectures is not None:
            instance.lecture_slots.all().delete()
            for l in lectures:
                LectureSlot.objects.create(school=school, timetable=instance, **l)

        if breaks is not None:
            instance.break_slots.all().delete()
            for b in breaks:
                BreakSlot.objects.create(school=school, timetable=instance, **b)

        return instance




class SlotSerializer(serializers.ModelSerializer):

    class Meta:
        model = Slot
        exclude = ["timetable", "school"]

    def validate(self, attrs):

        is_lecture = attrs.get("is_lecture")
        is_break = attrs.get("is_break")

        subject = attrs.get("subject")
        teacher = attrs.get("teacher")

        slot_start_time = attrs.get("slot_start_time")
        slot_end_time = attrs.get("slot_end_time")

        # both true or both false
        if is_lecture == is_break:
            raise serializers.ValidationError("Slot must be either lecture or break")

        # time validation
        if slot_start_time >= slot_end_time:
            raise serializers.ValidationError(
                "End time must be greater than start time"
            )

        # lecture validation
        if is_lecture:

            if not subject:
                raise serializers.ValidationError("Lecture slot requires subject")

            if not teacher:
                raise serializers.ValidationError("Lecture slot requires teacher")

        # break validation
        if is_break:

            if subject or teacher:
                raise serializers.ValidationError(
                    "Break slot cannot have subject or teacher"
                )

        return attrs




class TimeTableSerializer(serializers.ModelSerializer):

    # slots = SlotSerializer(many=True)
    slots = SlotSerializer(many=True)

    class Meta:
        model = Time_Table_tb
        fields = "__all__"
        read_only_fields = ["school"]

    # def validate(self, attrs):

    #     start_time = attrs.get("start_time")
    #     end_time = attrs.get("end_time")

    #     if start_time >= end_time:
    #         raise serializers.ValidationError(
    #             "End time must be greater than start time"
    #         )

    #     return
    def validate(self, attrs):

        start_time = attrs.get("start_time") or getattr(
            self.instance, "start_time", None
        )
        end_time = attrs.get("end_time") or getattr(self.instance, "end_time", None)
        slots = self.initial_data.get("slots", [])

        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError(
                "End time must be greater than start time"
            )

        lecture_count = 0
        previous_end = None

        for slot in slots:

            slot_start = slot.get("slot_start_time")
            slot_end = slot.get("slot_end_time")

            if previous_end and previous_end != slot_start:
                raise serializers.ValidationError("Slot timings are not continuous")

            previous_end = slot_end

            if slot.get("is_lecture"):
                lecture_count += 1

        if lecture_count != attrs.get("total_lecture"):
            raise serializers.ValidationError("Total lecture count mismatch")

        request = self.context.get("request")
        school = getattr(getattr(request, "user", None), "school", None)
        class_division = attrs.get("class_division") or getattr(
            self.instance, "class_division", None
        )
        day = attrs.get("day") or getattr(self.instance, "day", None)

        if school and class_division and class_division.school_id != school.id:
            raise serializers.ValidationError(
                {"class_division": "Invalid division for this school."}
            )

        if school and class_division and day:
            existing = Time_Table_tb.objects.filter(
                school=school,
                class_division=class_division,
                day=day,
            )
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            conflicting_timetable = existing.first()
            if conflicting_timetable:
                raise serializers.ValidationError(
                    {
                        "day": (
                            "A timetable for this class division and day "
                            "already exists."
                        ),
                        "existing_timetable_id": conflicting_timetable.id,
                    }
                )

        return attrs

    @transaction.atomic
    def create(self, validated_data):

        slots_data = validated_data.pop("slots")

        timetable = Time_Table_tb.objects.create(**validated_data)

        for slot_data in slots_data:

            teacher = slot_data.get("teacher")

            # CHECK CLASS TEACHER LOGIC
            if teacher and slot_data.get("slot_number") == 1:

                is_class_teacher = AssignClass.objects.filter(
                    school=timetable.school,
                    division=timetable.class_division,
                    teacher=teacher,
                    is_class_teacher=True,
                ).exists()

                if not is_class_teacher:
                    raise serializers.ValidationError(
                        {"slot_1": ("First slot teacher must " "be class teacher")}
                    )

            Slot.objects.create(
                timetable=timetable, school=timetable.school, **slot_data
            )

        return timetable

    @transaction.atomic
    def update(self, instance, validated_data):

        slots_data = validated_data.pop("slots", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if slots_data is not None:

            instance.slots.all().delete()

            for slot_data in slots_data:

                teacher = slot_data.get("teacher")

                if teacher and slot_data.get("slot_number") == 1:

                    is_class_teacher = AssignClass.objects.filter(
                        school=instance.school,
                        division=instance.class_division,
                        teacher=teacher,
                        is_class_teacher=True,
                    ).exists()

                    if not is_class_teacher:
                        raise serializers.ValidationError(
                            {"slot_1": ("First slot teacher " "must be class teacher")}
                        )

                Slot.objects.create(
                    timetable=instance, school=instance.school, **slot_data
                )

        return instance


# -------------------------
# Student attendance




class StudentAttendanceSerializer(serializers.ModelSerializer):

    class Meta:
        model = StudentAttendance
        fields = [
            "id",
            "student",
            "is_present",
            "is_absent",
            "attendance_date",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "school",
            "attendance_by",
            "attendance_date",
            "created_at",
        ]

    def validate(self, attrs):

        is_present = attrs.get("is_present", False)
        is_absent = attrs.get("is_absent", False)

        if is_present and is_absent:
            raise serializers.ValidationError(
                "Student cannot be both present and absent."
            )

        if not is_present and not is_absent:
            raise serializers.ValidationError(
                "Either present or absent must be selected."
            )

        return attrs

    def create(self, validated_data):

        request = self.context["request"]

        validated_data["school"] = request.user.school
        validated_data["attendance_by"] = request.user.staff

        attendance = super().create(validated_data)

        StudentNotification.objects.create(
            school=attendance.school,
            student=attendance.student,
            created_by=request.user.staff,
            notification_type="ATTENDANCE",
            title="Attendance Updated",
            message=(
                f"{attendance.student.name} marked "
                f"{'Present' if attendance.is_present else 'Absent'} "
                f"on {attendance.attendance_date}"
            )
        )

        return attendance

    def update(self, instance, validated_data):
        request = self.context.get("request")
        if request and hasattr(request.user, "staff"):
            validated_data["attendance_by"] = request.user.staff
        attendance = super().update(instance, validated_data)
        return attendance


from rest_framework import serializers
from .models import Homework, HomeworkSubmissions

# ======================== HOMEWORK SERIALIZERS ========================




class HomeworkSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and listing homework.
    Teachers create homework for a division.
    """

    due_date = serializers.DateField(input_formats=["%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"])
    division_name = serializers.CharField(source="division.division", read_only=True)
    school_class_name = serializers.CharField(
        source="division.SchoolClass.school_class", read_only=True
    )
    teacher_name = serializers.CharField(source="teacher.name", read_only=True)
    submission_count = serializers.SerializerMethodField()

    class Meta:
        model = Homework
        fields = [
            "id",
            "school",
            "division",
            "division_name",
            "school_class_name",
            "teacher",
            "teacher_name",
            "title",
            "description",
            "assigned_date",
            "due_date",
            "attachment",
            "is_active",
            "submission_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "school",
            "teacher",
            "teacher_name",
            "division_name",
            "school_class_name",
            "submission_count",
            "assigned_date",
            "created_at",
            "updated_at",
        ]

    def get_submission_count(self, obj):
        """Return count of total submissions for this homework"""
        # return obj.submissions.count()
        return HomeworkSubmissions.objects.all().count()

    def validate(self, attrs):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        division = attrs.get("division", getattr(self.instance, "division", None))

        if not division:
            raise serializers.ValidationError({"division": "Division is required."})

        if school and division.school_id != school.id:
            raise serializers.ValidationError(
                {"division": "Invalid division for this school."}
            )

        return attrs
    
    def validate_due_date(self, value):
        if value < date.today():
            raise serializers.ValidationError("Due date cannot be in the past.")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        # Automatically set school and teacher from request
        validated_data["school"] = user.school
        validated_data["teacher"] = user.staff if hasattr(user, "staff") else None

        return super().create(validated_data)


# class GetHomeworkSerializer(serializers.ModelSerializer):
#     """
#     Serializer for students to view homework for their division.
#     Shows homework details and submission status for the logged-in student.
#     """

#     division_name = serializers.CharField(source="division.division", read_only=True)
#     school_class_name = serializers.CharField(
#         source="division.SchoolClass.school_class", read_only=True
#     )
#     teacher_name = serializers.CharField(source="teacher.name", read_only=True)

#     # Student's submission for this homework
#     student_submission = serializers.SerializerMethodField()
#     is_submitted = serializers.SerializerMethodField()
#     submission_status = serializers.SerializerMethodField()
#     is_late = serializers.SerializerMethodField()

#     class Meta:
#         model = Homework
#         fields = [
#             "id",
#             "division",
#             "division_name",
#             "school_class_name",
#             "teacher_name",
#             "title",
#             "description",
#             "assigned_date",
#             "due_date",
#             "attachment",
#             "is_active",
#             "is_submitted",
#             "submission_status",
#             "student_submission",
#             "is_late",
#         ]
#         read_only_fields = fields

#     def get_student_submission(self, obj):
#         """Get the logged-in student's submission for this homework"""
#         request = self.context.get("request")
#         if not request or not hasattr(request.user, "student"):
#             return None

#         submission = obj.submissions.filter(student__user=request.user).first()

#         if submission:
#             return HomeworkSubmissionDetailSerializer(submission).data
#         return None

#     def get_is_submitted(self, obj):
#         """Check if the logged-in student has submitted this homework"""
#         request = self.context.get("request")
#         if not request or not hasattr(request.user, "student"):
#             return False

#         return obj.submissions.filter(student__user=request.user).exists()

#     def get_submission_status(self, obj):
#         """Get the logged-in student's submission status"""
#         request = self.context.get("request")
#         if not request or not hasattr(request.user, "student"):
#             return None

#         submission = obj.submissions.filter(student__user=request.user).first()

#         return submission.status if submission else None

#     def get_is_late(self, obj):
#         """Check if due date has passed"""
#         from django.utils import timezone

#         return timezone.now().date() > obj.due_date


# class HomeworkSubmissionSerializer(serializers.ModelSerializer):
#     """
#     Serializer for students to submit homework and teachers to check submissions.
#     """

#     student_name = serializers.SerializerMethodField()
#     homework_title = serializers.CharField(source="homework.title", read_only=True)
#     submission_date = serializers.SerializerMethodField()

#     class Meta:
#         model = HomeworkSubmission
#         fields = [
#             "id",
#             "school",
#             "homework",
#             "homework_title",
#             "student",
#             "student_name",
#             "attachment",
#             "submitted_at",
#             "submission_date",
#             "status",
#             "marks",
#             "teacher_remark",
#             "checked_by",
#             "checked_at",
#             "created_at",
#             "updated_at",
#         ]
#         read_only_fields = [
#             "id",
#             "school",
#             "student",
#             "student_name",
#             "homework_title",
#             "submitted_at",
#             "submission_date",
#             "checked_by",
#             "checked_at",
#             "created_at",
#             "updated_at",
#         ]

#     def get_student_name(self, obj):
#         """Return formatted student name"""
#         return " ".join(
#             filter(
#                 None,
#                 [
#                     obj.student.surname,
#                     obj.student.name,
#                     obj.student.father_name,
#                 ],
#             )
#         )

#     def get_submission_date(self, obj):
#         """Format submission date"""
#         return obj.submitted_at.date() if obj.submitted_at else None

#     def validate(self, attrs):
#         request = self.context.get("request")
#         school = getattr(request.user, "school", None) if request else None
#         homework = attrs.get("homework", getattr(self.instance, "homework", None))
#         student = attrs.get("student", getattr(self.instance, "student", None))

#         if not homework:
#             raise serializers.ValidationError({"homework": "Homework is required."})

#         if not student:
#             raise serializers.ValidationError({"student": "Student is required."})

#         if school and homework.school_id != school.id:
#             raise serializers.ValidationError(
#                 {"homework": "Invalid homework for this school."}
#             )

#         if school and student.school_id != school.id:
#             raise serializers.ValidationError(
#                 {"student": "Invalid student for this school."}
#             )

#         # Check if student belongs to the class/division this homework is for
#         # homework_division = (homework.division.division or "").strip().lower()
#         # student_division = (student.division or "").strip()

#         # if "(" in student_division and ")" in student_division:
#         #     student_division = (
#         #         student_division.rsplit("(", 1)[-1].split(")", 1)[0].strip()
#         #     )

#         # student_division = student_division.lower()
        
#         homework_division = (homework.division.division or "").strip().lower()
#         student_division = (student.division.division or "").strip().lower()

#         if (
#             homework.division_id != student.division_id
#             or homework.division.SchoolClass_id != student.school_class_id
#         ):
#             raise serializers.ValidationError(
#                 {
#                     "student": "This student is not in the class/division assigned for this homework."
#                 }
#             )

#         if (
#             homework.division.SchoolClass_id != student.school_class_id
#             or homework_division != student_division
#         ):
#             raise serializers.ValidationError(
#                 {
#                     "student": "This student is not in the class/division assigned for this homework."
#                 }
#             )

#         # Check for duplicate submission (on create only)
#         if not self.instance:
#             if HomeworkSubmission.objects.filter(
#                 homework=homework, student=student
#             ).exists():
#                 raise serializers.ValidationError(
#                     "This student has already submitted this homework."
#                 )

#         return attrs

#     def create(self, validated_data):
#         request = self.context.get("request")
#         user = request.user if request and request.user.is_authenticated else None

#         validated_data["school"] = user.school
#         validated_data["submitted_at"] = timezone.now()

#         return super().create(validated_data)


# class HomeworkSubmissionDetailSerializer(serializers.ModelSerializer):
#     """
#     Detailed serializer for viewing a single submission with all details.
#     """

#     student_name = serializers.SerializerMethodField()
#     homework_title = serializers.CharField(source="homework.title", read_only=True)
#     teacher_name = serializers.CharField(source="checked_by.staff.name", read_only=True)

#     class Meta:
#         model = HomeworkSubmission
#         fields = [
#             "id",
#             "homework",
#             "homework_title",
#             "student",
#             "student_name",
#             "attachment",
#             "submitted_at",
#             "status",
#             "marks",
#             "teacher_remark",
#             "checked_by",
#             "teacher_name",
#             "checked_at",
#         ]
#         read_only_fields = fields

#     def get_student_name(self, obj):
#         return " ".join(
#             filter(
#                 None,
#                 [
#                     obj.student.surname,
#                     obj.student.name,
#                     obj.student.father_name,
#                 ],
#             )
#         )


# class CheckHomeworkSubmissionSerializer(serializers.ModelSerializer):
#     """
#     Serializer for teachers to check and grade homework submissions.
#     """

#     student_name = serializers.CharField(source="student.name", read_only=True)

#     class Meta:
#         model = HomeworkSubmission
#         fields = [
#             "id",
#             "student_name",
#             "status",
#             "marks",
#             "teacher_remark",
#             "checked_at",
#         ]
#         read_only_fields = [
#             "id",
#             "student_name",
#             "checked_at",
#         ]

#     def validate_marks(self, value):
#         """Validate marks are between 0 and 100"""
#         if value is not None:
#             if value < 0 or value > 100:
#                 raise serializers.ValidationError("Marks must be between 0 and 100.")
#         return value

#     def validate(self, attrs):
#         status = attrs.get("status", getattr(self.instance, "status", None))

#         if status == "checked" and not attrs.get("marks"):
#             raise serializers.ValidationError(
#                 {"marks": "Marks are required when status is marked as 'checked'."}
#             )

#         return attrs

#     def update(self, instance, validated_data):
#         request = self.context.get("request")
#         user = request.user if request and request.user.is_authenticated else None

#         if validated_data.get("status") == "checked" and not instance.checked_by:
#             validated_data["checked_by"] = user
#             validated_data["checked_at"] = timezone.now()

#         return super().update(instance, validated_data)




class StudentHomeworkListSerializer(serializers.ModelSerializer):
    """
    Serializer for students to view all homework for their division.
    Shows division-wise homework with submission status.
    """

    class Meta:
        model = Homework
        fields = [
            "id",
            "title",
            "description",
            "assigned_date",
            "due_date",
            "attachment",
            "is_active",
        ]
        read_only_fields = fields


# --------------------------------GET STUDENT DATA----------------------------




class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model=Exam
        fields=["id","title","description","exam_date","start_time","end_time","class_group"]



class ExamNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model=ExamNotification
        fields=["id","exam","title","message"]



class HomeworkSubmissionSerializer(serializers.ModelSerializer):
    class Meta():
        model=HomeworkSubmissions
        fields=["id","homework","file","submitted_at"]
        read_only_fields=["student","submitted_at"]

    def validate(self, attrs):
        homework = attrs.get("homework")

        if homework and homework.due_date:
            submission_date = now().date() 
            due_date = homework.due_date

            if submission_date > due_date:
                raise serializers.ValidationError(
                    "You cannot submit homework after the due date."
                )

        return attrs
    



class MonthlyProgressReportSerializer(serializers.ModelSerializer):
    grade = serializers.SerializerMethodField()
    class Meta:
        model=MonthlyProgressReport
        fields='__all__'
        read_only_fields=["school","attendance_percentage","created_by","overall_score"]

    def create(self,validated_data):
            student=validated_data["student"]
            month=validated_data["month"]
            year=validated_data["year"]
            
            attendance_records=StudentAttendance.objects.filter(
                student=student,
                attendance_date__month=month,
                attendance_date__year=year
            )
            10*5/100
            total_days=attendance_records.count()
            present_days=attendance_records.filter(is_present=True).count()
            attendance_percentage=(
                (present_days/total_days)*100
                if total_days > 0 else 0)
            validated_data["attendance_percentage"]=attendance_percentage

            overall_score = round(
                (attendance_percentage+
                 validated_data["discipline"]+
                 validated_data["communication_skills"]+
                 validated_data["emotional_development"]+
                 validated_data["social_development"]+
                 validated_data["freindly_with_others"]
                 )/6,2)
            validated_data["overall_score"]=overall_score
            return MonthlyProgressReport.objects.create(**validated_data)
    
    def get_grade(self,obj):
            score=obj.overall_score
            if score >=90:
                return "A+"
            elif score >=80 and score<90:
                return "B"
            elif score>=70 and score<80:
                return "C"
            elif score>=60 and score<70:
                return "D"
            



class StudyMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model=StudyMaterial
        fields=["subject","student_class","material_type","title","description","file"]
        



