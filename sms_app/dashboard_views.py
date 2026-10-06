"""Live dashboard counts and searchable records, sharing the same role scope."""

from django.db.models import Q, Count
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AssignClass, Perents, School, SchoolClass, Staff, Student, StudentFieldValue,
)


MANAGEMENT = {"principal", "clerk", "fees_clerk", "fees management", "fee management", "fees", "trustee", "admin(trustee)", "admin"}
OPERATIONS = {"librarian", "inventory", "teacher"}
PLATFORM = {"superadmin", "super_admin", "super admin"}


def dashboard_scope(user):
    roles = {str(role).strip().lower() for role in user.groups.values_list("name", flat=True)}
    roles.add((getattr(user, "role", "") or "").strip().lower())
    platform = user.is_superuser or bool(roles & PLATFORM)
    students = Student.objects.all()
    staff = Staff.objects.all()
    schools = School.objects.all()
    classes = SchoolClass.objects.all()
    directory = platform or bool(roles & MANAGEMENT)
    if platform:
        label = "All schools"
    elif roles & (MANAGEMENT | OPERATIONS):
        if not user.school_id:
            raise PermissionDenied("A school must be assigned to view this dashboard.")
        schools = schools.filter(pk=user.school_id)
        students = students.filter(school_id=user.school_id)
        staff = staff.filter(school_id=user.school_id)
        classes = classes.filter(school_id=user.school_id)
        label = "Your school"
        if "teacher" in roles and not roles & MANAGEMENT:
            assignments = AssignClass.objects.filter(teacher__user=user, school_id=user.school_id, division__isnull=False)
            placement = Q(pk__in=[])
            for assignment in assignments.select_related("division"):
                placement |= Q(school_class_id=assignment.division.SchoolClass_id, division=assignment.division.division)
            students = students.filter(placement)
            classes = classes.filter(pk__in=assignments.values("division__SchoolClass_id"))
            label = "Your assigned classes"
    elif roles & {"student", "parent", "parents"}:
        linked = Perents.objects.filter(user=user).values("perents_of_id")
        students = students.filter(Q(user=user) | Q(pk__in=linked))
        schools = schools.filter(pk__in=students.values("school_id"))
        classes = classes.filter(pk__in=students.values("school_class_id"))
        staff = staff.none()
        label = "Your linked student records"
    else:
        raise PermissionDenied("This account has no dashboard access.")
    return {"students": students, "staff": staff, "schools": schools, "classes": classes, "directory": directory, "scope": label}


def gender_ids(students):
    """Latest recognized gender value wins; missing values remain unrecorded."""
    values = StudentFieldValue.objects.filter(student_id__in=students.values("pk")).filter(
        Q(field__label__icontains="gender") | Q(field__map_to_student_field__icontains="gender")
        | Q(field__label__iexact="sex")
    ).order_by("student_id", "-created_at", "-id").values_list("student_id", "value")
    genders = {}
    for student_id, value in values:
        if student_id in genders:
            continue
        normalized = (value or "").strip().lower()
        genders[student_id] = "boys" if normalized in {"male", "boy", "boys", "m"} else "girls" if normalized in {"female", "girl", "girls", "f"} else "unrecorded"
    return {key: {pk for pk, value in genders.items() if value == key} for key in ("boys", "girls")}


class WorkspaceDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        scope = dashboard_scope(request.user)
        students, staff = scope["students"], scope["staff"]
        genders = gender_ids(students)
        total = students.count()
        metrics = [
            {"key": "schools", "label": "Schools", "value": scope["schools"].count()},
            {"key": "students", "label": "Students", "value": total},
            {"key": "boys", "label": "Boys", "value": len(genders["boys"])},
            {"key": "girls", "label": "Girls", "value": len(genders["girls"])},
            {"key": "unrecorded", "label": "Gender not recorded / other", "value": total - len(genders["boys"] | genders["girls"])},
            {"key": "classes", "label": "Classes", "value": scope["classes"].count()},
        ]
        if scope["directory"] or staff.exists():
            metrics.extend([
                {"key": "staff", "label": "Staff", "value": staff.count()},
                {"key": "teachers", "label": "Teachers", "value": staff.filter(category__iexact="teacher").count()},
                {"key": "active_staff", "label": "Active staff", "value": staff.filter(is_active=True).count()},
            ])
        for metric in metrics:
            metric["can_view"] = scope["directory"] or metric["key"] in {"students", "boys", "girls", "unrecorded", "classes"}
        return Response({
            "scope": scope["scope"], "metrics": metrics,
            "schools": list(scope["schools"].values("id", "name")),
            "class_distribution": list(students.values("school_class__school_class").annotate(count=Count("id")).order_by("school_class__school_class")),
        })


class WorkspaceDashboardRecordsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        scope = dashboard_scope(request.user)
        kind = request.query_params.get("kind", "students")
        if kind not in {"students", "boys", "girls", "unrecorded", "staff", "teachers", "active_staff", "schools", "classes"}:
            raise ValidationError("Unknown dashboard record type.")
        if not scope["directory"] and kind in {"staff", "teachers", "active_staff", "schools"}:
            raise PermissionDenied("Your role cannot open this directory.")
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError:
            raise ValidationError("Page must be a number.")
        search = request.query_params.get("search", "").strip()
        record_id = request.query_params.get("id")
        school_id = request.query_params.get("school")
        student_kind = kind in {"students", "boys", "girls", "unrecorded"}
        if student_kind:
            queryset = scope["students"].select_related("school", "school_class", "academic_year")
            genders = gender_ids(scope["students"])
            if kind in {"boys", "girls"}:
                queryset = queryset.filter(pk__in=genders[kind])
            elif kind == "unrecorded":
                queryset = queryset.exclude(pk__in=genders["boys"] | genders["girls"])
            if search:
                queryset = queryset.filter(Q(name__icontains=search) | Q(surname__icontains=search) | Q(gr_no__icontains=search) | Q(school_class__school_class__icontains=search))
        elif kind in {"staff", "teachers", "active_staff"}:
            queryset = scope["staff"].select_related("school", "department")
            if kind == "teachers":
                queryset = queryset.filter(category__iexact="teacher")
            if kind == "active_staff":
                queryset = queryset.filter(is_active=True)
            if search:
                queryset = queryset.filter(Q(name__icontains=search) | Q(category__icontains=search) | Q(email__icontains=search))
        elif kind == "schools":
            queryset = scope["schools"]
            if search:
                queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search) | Q(city__icontains=search))
        else:
            queryset = scope["classes"].select_related("school")
            if search:
                queryset = queryset.filter(school_class__icontains=search)
        if school_id:
            if not school_id.isdigit():
                raise ValidationError("School must be a numeric ID.")
            queryset = queryset.filter(pk=school_id) if kind == "schools" else queryset.filter(school_id=school_id)
        if record_id:
            if not record_id.isdigit():
                raise ValidationError("Record ID must be numeric.")
            queryset = queryset.filter(pk=record_id)
        count = queryset.count()
        records = []
        for obj in queryset.order_by("id")[(page - 1) * 12:page * 12]:
            if student_kind:
                gender = "Boy" if obj.id in genders["boys"] else "Girl" if obj.id in genders["girls"] else "Not recorded / other"
                details = {
                    "Name": " ".join(filter(None, [obj.name, obj.surname])), "GR number": obj.gr_no,
                    "School": obj.school.name, "Class": obj.school_class.school_class if obj.school_class else None,
                    "Division": obj.division, "Roll number": obj.roll_no, "Gender": gender,
                    "Academic year": obj.academic_year.name if obj.academic_year else None,
                    "Status": "Active" if obj.is_active else "Inactive", "RTE": "Yes" if obj.is_rte else "No",
                }
                if scope["directory"] or scope["scope"] == "Your linked student records":
                    details.update({"Father": obj.father_name, "Mother": obj.mother_name, "Mobile": obj.mobile, "Date of birth": obj.date_of_birth, "Admission date": obj.admission_date})
                name, secondary = details["Name"], obj.gr_no or f"Student #{obj.id}"
            elif kind in {"staff", "teachers", "active_staff"}:
                name, secondary = obj.name, obj.category
                details = {"Name": obj.name, "School": obj.school.name if obj.school else None, "Role": obj.category, "Department": obj.department.name if obj.department else None, "Email": obj.email, "Mobile": obj.mobile, "Address": obj.address, "Joining date": obj.joining_date, "Status": "Active" if obj.is_active else "Inactive"}
            elif kind == "schools":
                name, secondary = obj.name, obj.code
                details = {"School": obj.name, "Code": obj.code, "Index number": obj.index_no, "Email": obj.email, "Phone": obj.phone, "Address": obj.address, "City": obj.city, "State": obj.state, "Country": obj.country, "Pincode": obj.pincode, "Status": "Inactive" if obj.is_active is False else "Active"}
            else:
                name, secondary = obj.school_class, obj.school.name if obj.school else None
                details = {"Class": obj.school_class, "School": secondary, "Students": scope["students"].filter(school_class=obj).count()}
            records.append({"id": obj.id, "name": name or f"Record #{obj.id}", "secondary": secondary, "details": details})
        return Response({"count": count, "page": page, "page_size": 12, "results": records})
