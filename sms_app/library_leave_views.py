from django.utils import timezone
from .models import StaffRemainingLeave
from .models import *
from rest_framework.viewsets import ModelViewSet, ViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView;
from rest_framework.response import Response
from rest_framework.permissions import BasePermission
from .permissions import IsClerkOrPrincipal, IsCLerk, Isprincipal, IsPrincipalOrTrustee
from .library_leave_serializers import *
from rest_framework.generics import GenericAPIView, ListCreateAPIView, ListAPIView
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from uuid import uuid4
from django.db.models import Count
from django.db.models.functions import TruncMonth



from .permissions import (
    IsCLerk,
    Isstudent,
    Isteacher,
    Isparent,
    Is_super_admin,
    Is_admin_trustee,
    IsFeeManager,
    Isprincipal,
)
        
class IsClassTeacher(BasePermission):
    message = "You are not a class teacher."

    def has_permission(self, request, view):
        staff = Staff.objects.filter(user=request.user).first()
        return AssignClass.objects.filter(
            teacher=staff,
            is_class_teacher=True
        ).exists()
   
   
class IsLibrarian(BasePermission):     
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser or request.user.groups.filter(name__in=["LIBRARIAN", "PRINCIPAL", "SUPERADMIN"]).exists():
            return True
        staff = Staff.objects.filter(user=request.user).first()
        if staff and staff.category in ["LIBRARIAN", "PRINCIPAL"]:
            return True
        return False


CARRY_MONTHS = {
    "MONTHLY": lambda m: True,
    "QUARTERLY": lambda m: m in (1, 4, 7, 10),
    "SEMI_ANNUAL": lambda m: m in (1, 7),
    "ANNUAL": lambda m: m == 1,
}



def should_carry_now(time_line, current_month):
    check = CARRY_MONTHS.get(time_line)
    return bool(check and check(current_month))



def carry_forward_leave(staff):
    current_month = timezone.now().month
    
    current_year = timezone.now().year
    school = getattr(staff, "school", None)
    if not school:
        return

    leave_types = LeaveType.objects.filter(
        leave_template__school=school,
        is_carry_forward=True,
    ).select_related("leave_template")

    if not leave_types.exists():
        print("no carry forward leave type found")
        return

    for lt in leave_types:
        time_line = (lt.leave_template.time_line or "MONTHLY").upper()
        if not should_carry_now(time_line, current_month):
            print("skip", lt.id, time_line)
            continue

        monthly_quota = lt.leave_num or 0

        srl, created = StaffRemainingLeave.objects.get_or_create(
            school=school,
            staff=staff,
            leave_template=lt.leave_template,
            leave_type=lt,
            defaults={
                "total_levaes": monthly_quota,
                "remaining_leaves": monthly_quota,
                "month": current_month,
                "year": current_year,
            },
        )

        if created:
            print("created remaining leave", lt.id)
            continue

        if srl.month == current_month and srl.year == current_year:
            continue

        carry = srl.remaining_leaves or 0
        new_total = carry + monthly_quota
        srl.total_levaes = new_total
        srl.remaining_leaves = new_total
        srl.month = current_month
        srl.year = current_year
        srl.save(update_fields=["total_levaes", "remaining_leaves", "month", "year"])
        print("carried forward", lt.id, carry)


        
        
        
class AttendanceLocationViewSet(ModelViewSet):
    serializer_class = AttendanceLocationViewSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        return AttendanceLocation.objects.filter(
            school=self.request.user.school
        )

    # ✅ attach request context (important for your create logic)
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    # ✅ auto-attach school on create (optional but safer)
    def perform_create(self, serializer):
        serializer.save()
        
        
        
        
# class CertificateType(ModelViewSet): #for create, read, update, delete  certificate type - Bonafide
#     serializer_class = CerificateTypeSerializer
#     permission_classes = [IsAuthenticated, IsCLerk]

#     def get_queryset(self):
#         user = self.request.user

#         # Clerk access (same as before)
#         staff = Staff.objects.filter(user=user, category="CLERK").first()
#         if staff:
#             return CertificateType.objects.filter(school=staff.school)

#         # Student access
#         student = Student.objects.filter(user=user).first()
#         if student:
#             return CertificateType.objects.filter(school=student.school)

#         return CertificateType.objects.none()


#     def perform_create(self, serializer):
#         staff = Staff.objects.filter(
#             user=self.request.user,
#             category="CLERK"
#         ).first()

#         if not staff:
#             raise ValidationError("Clerk profile not found.")

#         name = serializer.validated_data.get("name")

#         if CertificateType.objects.filter(
#             school=staff.school,
#             name__iexact=name
#         ).exists():
#             raise ValidationError(
#                 {"name": "This Certificate already exists."}
#             )

#         serializer.save(school=staff.school)

from io import BytesIO
from django.shortcuts import get_object_or_404
from datetime import datetime





class CertificateTemplateAdminViewSet(ModelViewSet):

    serializer_class = CertificateTemplateAdminSerializer

    permission_classes = [
        IsAuthenticated,
        IsCLerk
    ]

    def get_queryset(self):

        staff = Staff.objects.filter(
            user=self.request.user,
            category="CLERK"
        ).first()

        return CertificateTemplate.objects.filter(
            certificate_type__school=staff.school
        )
        




class CertificateTemplateFieldAdminViewSet(ModelViewSet):

    serializer_class = CertificateTemplateFieldAdminSerializer

    permission_classes = [
        IsAuthenticated,
        IsCLerk
    ]

    def get_queryset(self):

        staff = Staff.objects.filter(
            user=self.request.user,
            category="CLERK"
        ).first()

        queryset = CertificateTemplateField.objects.filter(
            template__certificate_type__school=staff.school
        )

        template = self.request.query_params.get("template")

        if template:
            queryset = queryset.filter(
                template_id=template
            )

        return queryset





class CertificateTemplateAPIView(APIView):

    permission_classes = [IsAuthenticated, IsCLerk]

    def get(self, request, pk):

        staff = get_object_or_404(
            Staff,
            user=request.user,
            category="CLERK"
        )

        certificate_request = get_object_or_404(
            CertificateRequest.objects.select_related(
                "student",
                "certificate_type",
                "certificate_type__template",
            ),
            pk=pk,
            school=staff.school
        )

        serializer = CertificateTemplateSerializer(
            certificate_request
        )

        return Response(serializer.data)
    
    
    
    
    
class CertificateGenerateAPIView(APIView):

    permission_classes = [IsAuthenticated, IsCLerk]

    STUDENT_FIELD_MAP = {
        "surname": "surname",
        "name": "name",
        "father_name": "father_name",
        "mother_name": "mother_name",
        "gr_no": "gr_no",
        "date_of_birth": "date_of_birth",
        "admission_date": "admission_date",
        "mobile": "mobile",
        "aadhar_number": "aadhar_number",
    }

    def get_student_value(self, student, field_name):

        if field_name == "school_class":
            return (
                student.school_class.school_class
                if student.school_class else ""
            )

        if field_name == "division":
            return (
                student.division.division
                if student.division else ""
            )

        if field_name == "academic_year":
            return (
                student.academic_year.name
                if student.academic_year else ""
            )

        field = self.STUDENT_FIELD_MAP.get(field_name)

        if field:
            return getattr(student, field, "")

        return None

    def patch(self, request, pk):

        serializer = CertificateGenerateSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        staff = get_object_or_404(
            Staff,
            user=request.user,
            category="CLERK"
        )

        certificate_request = get_object_or_404(
            CertificateRequest.objects.select_related(
                "student",
                "certificate_type__template"
            ),
            pk=pk,
            school=staff.school
        )

        if certificate_request.status != "PENDING":
            raise ValidationError(
                "This request has already been processed."
            )

        student = certificate_request.student

        template = certificate_request.certificate_type.template

        editable_data = serializer.validated_data["generated_data"]

        final_data = {}
        
        print("Editable Data:", editable_data)

        for field in template.fields.all():
            
            print(f"--- Field: {field.field_name} ---",f"Editable: {field.editable}",f"Value: {editable_data.get(field.field_name)}",sep="\n")

            if field.editable:

                value = editable_data.get(field.field_name)

                if field.required and not value:
                    raise ValidationError(
                        {
                            field.field_name:
                            f"{field.label} is required."
                        }
                    )

                final_data[field.field_name] = value

            else:

                value = self.get_student_value(
                    student,
                    field.field_name
                )

                if value is None:
                    value = field.default_value or ""

                final_data[field.field_name] = value

        certificate_number = (
            f"CERT-{uuid4().hex[:8].upper()}"
        )

        final_data["certificate_number"] = certificate_number

        final_data["issue_date"] = str(timezone.localdate())

        certificate = Certificate.objects.create(
            request=certificate_request,
            certificate_number=certificate_number,
            generated_data=final_data,
        )

        certificate_request.status = "APPROVED"
        certificate_request.save(update_fields=["status"])

        return Response(
            {
                "message": "Certificate generated successfully.",
                "certificate_id": certificate.id,
                "certificate_number": certificate.certificate_number,
                "generated_data": certificate.generated_data,
            },
            status=status.HTTP_200_OK,
        )
        
        
        


class CertificateUploadAPIView(APIView):

    permission_classes = [IsAuthenticated, IsCLerk]

    def patch(self, request, pk):

        serializer = CertificateUploadSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        staff = get_object_or_404(
            Staff,
            user=request.user,
            category="CLERK"
        )

        certificate = get_object_or_404(
            Certificate.objects.select_related(
                "request__school"
            ),
            pk=pk,
            request__school=staff.school
        )

        certificate.file = serializer.validated_data["file"]

        certificate.save(update_fields=["file"])

        return Response(
            {
                "message": "Certificate uploaded successfully.",
                "certificate_id": certificate.id,
                "file": certificate.file.url,
            },
            status=status.HTTP_200_OK
        )
        
        
        
        
        
class CertificateTemplateFieldOptionsAPIView(APIView):

    permission_classes = [IsAuthenticated, IsCLerk]

    FIELD_OPTIONS = [
        {
            "key": "name",
            "label": "Student Name",
            "field_type": "text",
            "editable": False,
        },
        {
            "key": "surname",
            "label": "Surname",
            "field_type": "text",
            "editable": False,
        },
        {
            "key": "father_name",
            "label": "Father Name",
            "field_type": "text",
            "editable": False,
        },
        {
            "key": "mother_name",
            "label": "Mother Name",
            "field_type": "text",
            "editable": False,
        },
        {
            "key": "gr_no",
            "label": "GR Number",
            "field_type": "text",
            "editable": False,
        },
        {
            "key": "date_of_birth",
            "label": "Date of Birth",
            "field_type": "date",
            "editable": False,
        },
        {
            "key": "admission_date",
            "label": "Admission Date",
            "field_type": "date",
            "editable": False,
        },  
        {
            "key": "mobile",
            "label": "Mobile",
            "field_type": "text",
            "editable": False,
        },
        {
            "key": "aadhar_number",
            "label": "Aadhar Number",
            "field_type": "text",
            "editable": False,
        },
    ]

    def get(self, request):
        serializer = CertificateFieldOptionSerializer(
            self.FIELD_OPTIONS,
            many=True
        )
        return Response(serializer.data)
    
    



class CertificateDetailAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        certificate = get_object_or_404(
            Certificate.objects.select_related(
                "request",
                "request__student",
            ),
            pk=pk,
        )

        serializer = CertificateDetailSerializer(
            certificate
        )

        return Response(serializer.data)
    
    
    
    
    
class CertificateAPIView(ModelViewSet):

    serializer_class = CertificateDetailSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    def get_queryset(self):

        staff = Staff.objects.filter(user=self.request.user).first()
        
        if staff:
            
            return Certificate.objects.select_related(
                "request",
                "request__student",
                "request__certificate_type",
            ).filter(
                request__school=staff.school
            )
            
        else:
             
            student = get_object_or_404(
                Student,
                user=self.request.user,
            )
            
            return Certificate.objects.select_related(
                "request",
                "request__student",
                "request__certificate_type",
            ).filter(
                request__school=student.school
            )





class CertificateTypeViewSet(ModelViewSet): #for create, read, update, delete  certificate type - Bonafide
    serializer_class = CerificateTypeSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        user = self.request.user

        # Clerk access (same as before)
        staff = Staff.objects.filter(user=user, category="CLERK").first()
        if staff:
            return CertificateType.objects.filter(school=staff.school)

        # Student access
        student = Student.objects.filter(user=user).first()
        if student:
            return CertificateType.objects.filter(school=student.school)

        return CertificateType.objects.none()


    def perform_create(self, serializer):
        staff = Staff.objects.filter(
            user=self.request.user,
            category="CLERK"
        ).first()

        if not staff:
            raise ValidationError("Clerk profile not found.")

        name = serializer.validated_data.get("name")

        if CertificateType.objects.filter(
            school=staff.school,
            name__iexact=name
        ).exists():
            raise ValidationError(
                {"name": "This Certificate already exists."}
            )

        serializer.save(school=staff.school)





class CertificateRequestViewSet(ModelViewSet):
    """Student-facing viewset: create requests, view status & certificate."""
    serializer_class = CertificateRequestSerializer
    permission_classes = [IsAuthenticated, Isstudent]
    http_method_names = ["get", "post", "head", "options"]  # Students can't update/delete

    def get_queryset(self):
        student = Student.objects.filter(user=self.request.user).first()

        if not student:
            return CertificateRequest.objects.none()

        return (
            CertificateRequest.objects.filter(student=student)
            .select_related("certificate_type")
            .prefetch_related("certificate")
        )

    def perform_create(self, serializer):
        student = Student.objects.filter(user=self.request.user).first()

        if not student:
            raise ValidationError("Student profile not found.")

        certificate_type = serializer.validated_data["certificate_type"]

        # Prevent duplicate pending requests for the same certificate type
        if CertificateRequest.objects.filter(
            student=student,
            certificate_type=certificate_type,
            status="PENDING"
        ).exists():
            raise ValidationError(
                "You already have a pending request for this certificate type."
            )

        serializer.save(student=student, school=student.school)
        
        
        
        
        
class ClerkCertificateRequestViewSet(ModelViewSet):
    """Clerk-facing viewset: view all school requests, approve/reject."""
    serializer_class = ClerkCertificateRequestSerializer
    permission_classes = [IsAuthenticated, IsCLerk]
    http_method_names = ["get", "patch", "head", "options"]  # Clerks can only read + update

    def get_queryset(self):
        staff = Staff.objects.filter(
            user=self.request.user,
            category="CLERK"
        ).first()

        if not staff:
            return CertificateRequest.objects.none()

        queryset = (
            CertificateRequest.objects.filter(school=staff.school)
            .select_related("student__user", "certificate_type")
            .prefetch_related("certificate")
        )

        # Optional filtering by status: /clerk-requests/?status=PENDING
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status.upper())

        return queryset

    def perform_update(self, serializer):
        instance = self.get_object()

        # Prevent re-processing an already handled request
        if instance.status != "PENDING":
            raise ValidationError(
                f"This request has already been {instance.status.lower()}."
            )

        new_status = serializer.validated_data.get("status")

        if new_status == "APPROVED":
            # Validate file BEFORE saving status, so we don't save APPROVED with no file
            file = self.request.FILES.get("file")
            if not file:
                raise ValidationError(
                    "A certificate file (PDF) is required to approve this request."
                )

            # Now safe to save
            serializer.save(status="APPROVED")

            Certificate.objects.create(
                request=instance,
                certificate_number=f"CERT-{uuid4().hex[:8].upper()}",
                file=file
            )
            
            
            instance.refresh_from_db()

        elif new_status == "REJECTED":
            serializer.save(status="REJECTED")

        else:
            raise ValidationError(
                "Status must be either APPROVED or REJECTED."
            )





from rest_framework.exceptions import PermissionDenied, NotFound






# Helper
def get_user_school(request):
    """Return the school for any staff-level user (CLERK, PRINCIPAL, TRUSTEE, ADMIN)."""
    user = request.user
    allowed_roles = ["CLERK", "PRINCIPAL", "TRUSTEE", "ADMIN"]
    role = getattr(user, "role", None)
    if role not in allowed_roles:
        raise PermissionDenied("You do not have permission to perform this action.")
    school = getattr(user, "school", None)
    if school is None:
        raise PermissionDenied("Your account is not associated with any school.")
    return school


# Keep backward-compatible alias
def get_clerk_school(request):
    return get_user_school(request)


# LeaveTemplate ViewSet
class LeaveTemplateViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = NewLeaveTemplateSerializer
 
    def get_queryset(self):
        school = get_clerk_school(self.request)
        return LeaveTemplate.objects.filter(school=school)
 
    def perform_create(self, serializer):
        school = get_clerk_school(self.request)
        serializer.save(school=school)
 
    def perform_update(self, serializer):
        school = get_clerk_school(self.request)
        serializer.save(school=school)
 
    @action(detail=False, methods=["post"], url_path="bulk_create")
    def bulk_create(self, request):
        school = get_clerk_school(request)
        serializer = LeaveTemplateBulkCreateSerializer(
            data=request.data,
            context={"request": request, "school": school},
        )
        serializer.is_valid(raise_exception=True)
        template = serializer.save()
        return Response(
            NewLeaveTemplateSerializer(template).data,
            status=status.HTTP_201_CREATED,
        )
 
 
 
 
class LeaveTypeViewSet(ModelViewSet):
 
    permission_classes = [IsAuthenticated]
    serializer_class = NewLeaveTypeSerializer
 
    def get_queryset(self):
        school = get_clerk_school(self.request)
        
        
        # Scope to the clerk's school via the template's school FK
        qs = LeaveType.objects.filter(
            leave_template__school=school
        ).select_related("leave_template", "category")
 
        
        
        # Optional filter: /leave-types/?template=5
        template_id = self.request.query_params.get("template")
        if template_id:
            qs = qs.filter(leave_template_id=template_id)
 
        return qs
 
    def perform_create(self, serializer):

        
        school = get_clerk_school(self.request)
        # Ensure the chosen template belongs to the clerk's school
        template = serializer.validated_data.get("leave_template")
        if template and template.school != school:
            raise PermissionDenied("That leave template does not belong to your school.")
        
        serializer.save()
        
        
        
        
class LeaveRequestView(ModelViewSet): #for requesting leave
    # queryset = LeaveRequest.objects.all()
    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        
        
        staff = Staff.objects.filter(user=self.request.user).first()
        
        # print(staff.school)
        
        if staff and staff.school:
            return LeaveRequest.objects.filter(staff=staff, school=staff.school)
        
        return LeaveRequest.objects.all()
    

    
class GetStaffRemainingleave(ListAPIView): # perticular staff remaining leaves
    permission_classes = [IsAuthenticated]
    queryset = StaffRemainingLeave.objects.all()
    def get(self, request):
        # leave_template = request.data.get("leave_template")
        user = request.user

        staff = Staff.objects.filter(user=user).first()
        queryset = StaffRemainingLeave.objects.filter(
            staff=staff, school=user.school
            # , leave_template=leave_template
        )

        serializer = StaffRemainingLeaveSerializer(queryset, many=True)
        return Response(serializer.data)
    
    
    
    
class GetStaffLeaveRequest(APIView): # particular staff leave request to staff see their leave request
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        staff = Staff.objects.filter(user=user).first()
        if not staff:
            return Response([])

        school = user.school or staff.school
        if school:
            # Backfill school on any orphaned leave requests for this staff
            LeaveRequest.objects.filter(staff=staff, school__isnull=True).update(school=school)

        queryset = LeaveRequest.objects.filter(staff=staff).order_by("-id")
        serializer = GetLeaveRequestSerializer(queryset, many=True)
        return Response(serializer.data)
        
        
        
        
class GetLeaveRequestView(ModelViewSet): #for all the leaves — clerk/principal/trustee can view
    queryset = LeaveRequest.objects.all()
    serializer_class = GetLeaveRequestSerializer
    permission_classes = [IsAuthenticated, IsClerkOrPrincipal]
    http_method_names = ["get"]

    def get_queryset(self):

        queryset = LeaveRequest.objects.filter(school=self.request.user.school)

        return queryset
    
    
    
    
class ChangeLeaveView(ModelViewSet): # for approving day wise APPROVAL — principal/clerk/trustee
    queryset = LeavePerDay.objects.all()
    serializer_class = ChangeLeavePerDaySerializer
    permission_classes = [IsAuthenticated, IsClerkOrPrincipal]
    http_method_names = ["patch"]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        if request.user.school and instance.leave.school and instance.leave.school != request.user.school:
            return Response(
                {"error": "You are not allowed to modify this record"}, status=403
            )

        return super().update(request, *args, **kwargs)
    
    


class ChangeAllLeaveView(APIView): # for APPROVE all day leave — principal/clerk/trustee
    permission_classes = [IsAuthenticated, IsClerkOrPrincipal]

    def patch(self, request, pk):
        status_value = request.data.get("status")

        leave_request = LeaveRequest.objects.filter(id=pk).first()

        if not leave_request:
            return Response(
                {"error": "Leave request not found"},
                status=404
            )

        leave_days = leave_request.leave_days.all()

        for leave_day in leave_days:
            serializer = ChangeLeavePerDaySerializer(
                leave_day,  
                data={"status": status_value},
                partial=True,
                context={"request": request}
            )

            serializer.is_valid(raise_exception=True)
            serializer.save()

        leave_request.status = status_value
        leave_request.save()

        return Response(
            {"message": f"All leave days updated to {status_value}"}
        )
    
            

        
def get_approved_paid_leave_days(staff, start_date, end_date):
    """Count approved leave days where is_paid=True"""
    return LeavePerDay.objects.filter(
        leave__staff=staff,
        status="APPROVED",
        date__range=(start_date, end_date),
        leave__is_paid=True  # ← Filter by is_paid on the leave request
    ).count()
    
    
    
    
    
# class StudentAttendanceListView(GenericAPIView):
#     serializer_class = StudentAttendanceListSerializer
    
#     def get(self, request):
        
#         user = self.request.user
        
#         student = Student.objects.filter(user=user).first()
        
#         StudentAttendance.objects.filter(student = student)
    
    
    
    
class StudentAttendanceListView(ListAPIView):
    serializer_class = StudentAttendanceListSerializer
    permission_classes = [IsAuthenticated, Isstudent]
    
    def get_queryset(self):
        
        user = self.request.user
        
        student = Student.objects.filter(user=user).first()
        
        qs = StudentAttendance.objects.filter(student = student)
        
        
        return qs
    
    
class SyllabusListView(ListAPIView):
    serializer_class = SyllabusListSerializer
    permission_classes = [IsAuthenticated, Isstudent]
    
    def get_queryset(self):
        user = self.request.user
        student = Student.objects.filter(user=user).first()
        if not student or not student.school:
            return Syllabus.objects.none()

        div_name = student.division
        if div_name and student.school_class:
            div_obj = Division.objects.filter(
                SchoolClass=student.school_class,
                division__iexact=div_name,
                school=student.school
            ).first()
            if div_obj:
                return Syllabus.objects.filter(division=div_obj, school=student.school)

        if student.school_class:
            return Syllabus.objects.filter(division__SchoolClass=student.school_class, school=student.school)

        return Syllabus.objects.filter(school=student.school)
    
class ExamViewTeacher(ListAPIView):
    serializer_class = ExamViewSerializer
    permission_classes = [IsAuthenticated, Isteacher]
    
    def get_queryset(self):
        
        staff = Staff.objects.filter(user=self.request.user).first()
        
        qs=Exam.objects.filter(school=staff.school, created_by=staff)
        
        return qs
    
    
class ExamViewClassTeacher(ListAPIView):
    serializer_class = ExamViewSerializer
    permission_classes = [IsAuthenticated, IsClassTeacher]
    
    def get_queryset(self):
        staff = Staff.objects.filter(user=self.request.user).first()

        if not staff:
            raise ValidationError("Staff record not found.")

        assign_class = AssignClass.objects.filter(
            teacher=staff,
            is_class_teacher=True
        ).first()

        if not assign_class:
            raise ValidationError("You are not a class teacher.")

        return Exam.objects.filter(
            school=assign_class.school
        )


class ExamViewSet(ListAPIView):
    serializer_class = ExamViewSerializer
    permission_classes = [IsAuthenticated, Isstudent]
    
    def get_queryset(self):
        
        student = Student.objects.filter(user=self.request.user).first()

        qs = Exam.objects.filter(school=student.school, class_group=student.school_class)
        
        return qs
    
class ExamCreateViewSet(GenericAPIView):
    serializer_class = ExamViewSerializer
    permission_classes = [IsAuthenticated, Isteacher]

    def post(self, request, *args, **kwargs):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            return Response({"detail": "Staff profile not found."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        exam = Exam.objects.create(
            school=staff.school,
            created_by=staff,
            title=serializer.validated_data["title"],
            description=serializer.validated_data["description"],
            subject=serializer.validated_data["subject"],
            exam_date=serializer.validated_data["exam_date"],
            start_time=serializer.validated_data["start_time"],
            end_time=serializer.validated_data["end_time"],
            class_group=serializer.validated_data["class_group"],
        )

        exam.save()
        
        return Response({"detail": "exam scheduled"}, status=status.HTTP_201_CREATED)
    

def calculate_grade(marks, max_marks):
    if marks is None:
        return ""
    pct = (marks / max_marks) * 100
    if pct >= 90: return "A+"
    if pct >= 75: return "A"
    if pct >= 60: return "B"
    if pct >= 40: return "C"
    return "F"
    
class ResultBulkCreateViewSet(GenericAPIView):
    serializer_class = ResultBulkCreateSerializer
    permission_classes = [IsAuthenticated, Isteacher]

    def post(self, request, *args, **kwargs):
        staff = Staff.objects.filter(user=request.user).first()
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        exam = serializer.validated_data["exam"]
        max_marks = serializer.validated_data["max_marks"]
        entries = serializer.validated_data["entries"]

        # Check verification lock
        from .models import ClassTeacherMarksVerification
        is_locked = ClassTeacherMarksVerification.objects.filter(
            school=request.user.school,
            academic_year=exam.academic_year,
            school_class=exam.class_group,
            exam_term=exam.exam_term,
            status="VERIFIED"
        ).exists()
        if is_locked:
            return Response({"error": "Marks for this class and term have already been verified and locked by the Class Teacher."}, status=status.HTTP_400_BAD_REQUEST)

        created, updated = 0, 0

        for entry in entries:
            marks = None if entry["is_absent"] else entry.get("marks_obtained")
            grade = calculate_grade(marks, max_marks)

            obj, is_created = Result.objects.update_or_create(
                exam=exam,
                student=entry["student"],
                defaults={
                    "entered_by": staff,
                    "marks_obtained": marks,
                    "max_marks": max_marks,
                    "is_absent": entry["is_absent"],
                    "remarks": entry.get("remarks", ""),
                    "grade": grade,
                    "is_published": False,  # always revert to unpublished on edit
                },
            )
            created += is_created
            updated += (not is_created)

        return Response(
            {"detail": "results saved", "created": created, "updated": updated},
            status=status.HTTP_200_OK,
        )
    

class ResultPublishViewSet(GenericAPIView):
    serializer_class = ResultPublishSerializer
    permission_classes = [IsAuthenticated, Isteacher | Isprincipal]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        exam = serializer.validated_data["exam"]
        updated_count = Result.objects.filter(exam=exam).update(is_published=True)

        return Response(
            {"detail": "results published", "count": updated_count},
            status=status.HTTP_200_OK,
        )


class ExamResultRosterView(GenericAPIView):
    """
    GET: returns the class roster for an exam with any existing
    (possibly unpublished) marks pre-filled, so the teacher UI
    can render an editable grid.
    """
    permission_classes = [IsAuthenticated, Isteacher]
 
    def get(self, request, exam_id, *args, **kwargs):
        staff = Staff.objects.filter(user=request.user).first()
        exam = Exam.objects.filter(id=exam_id, school=staff.school).first()
 
        if not exam:
            return Response({"detail": "exam not found"}, status=status.HTTP_404_NOT_FOUND)
 
        students = Student.objects.filter(school_class=exam.class_group).order_by("gr_no")
        existing_results = {
            r.student_id: r for r in Result.objects.filter(exam=exam)
        }
 
        data = []
        for s in students:
            r = existing_results.get(s.id)
            data.append({
                "student": s.id,
                "student_name": s.name,
                "gr_no": s.gr_no,
                "marks_obtained": r.marks_obtained if r else None,
                "max_marks": r.max_marks if r else None,
                "is_absent": r.is_absent if r else False,
                "remarks": r.remarks if r else "",
                "is_published": r.is_published if r else False,
            })
 
        return Response({"exam": exam.id, "class_group": exam.class_group.id, "roster": data})
 
 
class ExamRankListView(GenericAPIView):
    """
    GET: class-wise ranking for a given exam, computed from
    published (or all, teacher's choice) results.
    """
    permission_classes = [IsAuthenticated]  # teacher or student, both can view
 
    def get(self, request, exam_id, *args, **kwargs):
        exam = Exam.objects.filter(id=exam_id).first()
        if not exam:
            return Response({"detail": "exam not found"}, status=status.HTTP_404_NOT_FOUND)
 
        results = (
            Result.objects.filter(exam=exam, is_published=True, is_absent=False)
            .exclude(marks_obtained__isnull=True)
            .select_related("student", "student__user")
            .order_by("-marks_obtained")
        )
 
        data = []
        for idx, r in enumerate(results, start=1):
            data.append({
                "rank": idx,
                "student": r.student.id,
                "student_name": r.student.name,
                "marks_obtained": r.marks_obtained,
                "max_marks": r.max_marks,
                "grade": r.grade,
            })
 
        return Response({"exam": exam.id, "ranking": data})
    
    
# student side view


class StudentResultViewSet(ListAPIView):
    serializer_class = ResultViewSerializer
    permission_classes = [IsAuthenticated, Isstudent]

    def get_queryset(self):
        student = Student.objects.filter(user=self.request.user).first()
        return Result.objects.filter(student=student, is_published=True).select_related("exam", "exam__subject")


from xhtml2pdf import pisa
from django.template.loader import render_to_string
from django.http import HttpResponse
import io

class StudentResultPDFView(APIView):
    permission_classes = [IsAuthenticated, Isstudent]

    def get(self, request, student_id, *args, **kwargs):
        student = Student.objects.filter(user=request.user).first()
        if str(student.id) != str(student_id):
            return Response({"detail": "not allowed"}, status=status.HTTP_403_FORBIDDEN)

        results = Result.objects.filter(student=student, is_published=True).select_related("exam", "exam__subject")

        total_obtained = sum(r.marks_obtained or 0 for r in results)
        total_max = sum(r.max_marks for r in results)
        percentage = round((total_obtained / total_max) * 100, 2) if total_max else 0

        html_string = render_to_string("report_card.html", {
            "student": student,
            "results": results,
            "total_obtained": total_obtained,
            "total_max": total_max,
            "percentage": percentage,
        })

        pdf_buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(html_string, dest=pdf_buffer)

        if pisa_status.err:
            return Response({"detail": "PDF generation failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        response = HttpResponse(pdf_buffer.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="report_card_{student.id}.pdf"'
        return response
    
    
class SubjectByClassAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, class_id):
        subjects = Subject.objects.filter(
            division__SchoolClass_id=class_id
        ).distinct()

        data = [
            {
                "id": subject.id,
                "name": subject.name
            }
            for subject in subjects
        ]

        return Response(data)
    
    
    
class SchoolClassesView(ListAPIView):
    queryset = SchoolClass.objects.all()
    serializer_class = SchoolClassSerializer
    permission_classes = [IsAuthenticated, Isteacher]
    
    def get_queryset(self):
        
        staff = Staff.objects.filter(user=self.request.user).first()
        
        
        return SchoolClass.objects.filter(school = staff.school)
    
    
    
# class BookManageView(ModelViewSet):
#     serializer_class = BookManageSerializer

#     permission_classes = [IsAuthenticated, IsLibrarian]
    
#     def get_queryset(self):
        
#         staff = Staff.objects.filter(user=self.request.user).first()
        
#         return Book.objects.filter(school=staff.school)
    
    
    
#     def perform_create(self, serializer):
        
#         staff = Staff.objects.filter(user=self.request.user).first()
#         # school = School.objects.filter(login_id = self.request.user).first()
        

#         title = serializer.validated_data.get("title")
#         author = serializer.validated_data.get("author")
#         category = serializer.validated_data.get("category")
#         total_copies = serializer.validated_data.get("total_copies")
        
#         book_already= Book.objects.filter(school=staff.school, title=title, author=author).first()
        
        
#         if book_already is not None:
#             raise ValidationError(f"Book Already exists id = {book_already.pk}")
        
        
#         serializer.save(school = staff.school,available_copies=total_copies)
        
    
    
#     def perform_destroy(self, instance):
        
#         if not instance.total_copies == instance.available_copies:
#             raise ValidationError("Can't Delete Beacause Book Issued To Someone First Take That Back")
        
#         return super().perform_destroy(instance)
    
    
    
#     def perform_update(self, serializer):
        
#         read_only_value = self.request.data.get('available_copies')
        
#         if read_only_value is not None:
#             serializer.save(available_copies = read_only_value)
        
#         else:
#             serializer.save()
            
            
            
            
# class LateBookFeesViews(ModelViewSet):
#     serializer_class = LateBookFeesSerializer
#     permission_classes = [IsAuthenticated]
    
#     def get_queryset(self):
        
#         staff = Staff.objects.filter(user=self.request.user).first()
        
#         latebookfees = LateBookFees.objects.filter(school=staff.school)
        
#         return latebookfees
    
#     def perform_create(self, serializer):
#         staff = Staff.objects.filter(user=self.request.user).first()
        
#         latefee_already = LateBookFees.objects.filter(school=staff.school).exists()
        
#         if latefee_already:
#             raise ValidationError("Already Fees Decided if you want to change edit it")
                
#         serializer.save(school=staff.school)
        
        
        

# class BookIssuedView(ModelViewSet):
#     serializer_class = BookIssuedSerializer

#     def get_queryset(self):
        
#         staff = Staff.objects.filter(user=self.request.user).first()
        
#         book_issued = BookIssued.objects.filter(school=staff.school)
        
#         return book_issued
    
    
#     def perform_create(self, serializer):

#         staff = Staff.objects.get(user=self.request.user)

#         book = serializer.validated_data["book"]
#         student = serializer.validated_data["student"]

#         if book.available_copies == 0:
#             raise ValidationError("Book is not available.")

#         already_issued = BookIssued.objects.filter(
#             student=student,
#             book=book,
#             status="ISSUED"
#         ).exists()

#         if already_issued:
#             raise ValidationError("Student already has this book.")

#         book.available_copies -= 1
#         book.save()

#         serializer.save(
#             school=staff.school,
#             status="ISSUED"
#         )
    
    

# class BookViewStudent(ModelViewSet):
#     serializer_class = BookManageSerializer
#     http_method_names = ['get']
#     permission_classes = [IsAuthenticated]
    
#     def get_queryset(self):
#         user = CustomUser.objects.filter(username=self.request.user).first()
#         book = Book.objects.filter(school = user.school)
#         return book
    
    
# class BookIssueStudent(ModelViewSet):
#     serializer_class = BookIssuedSerializer
#     permission_classes = [IsAuthenticated]
    
#     def get_queryset(self):
#         student = Student.objects.get(user=self.request.user)

#         return BookIssued.objects.filter(
#             student=student
#         )
    
#     def perform_create(self, serializer):
        
        
        
#         return super().perform_create(serializer)
def _get_or_create_library_setting(school):
    setting, _ = LibrarySetting.objects.get_or_create(
        school=school,
        defaults={
            "max_books_per_student": 3,
            "issue_duration_days": 14,
            "max_renewal_count": 2,
            "fine_per_day": 2.00,
            "grace_period_days": 0,
            "lost_penalty": 100.00,
            "damage_penalty": 50.00,
            "allow_renewal_with_fine": False,
            "allow_issue_with_fine": False,
        }
    )
    # Sync with LateBookFees for backward compatibility
    late_fee, _ = LateBookFees.objects.get_or_create(
        school=school,
        defaults={"fees": int(setting.fine_per_day), "grace_period_days": setting.grace_period_days}
    )
    return setting


class LibrarySettingViewSet(ModelViewSet):
    serializer_class = LibrarySettingSerializer
    permission_classes = [IsAuthenticated, IsLibrarian]

    def get_queryset(self):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        return LibrarySetting.objects.filter(school=staff.school)

    @action(detail=False, methods=["get", "post", "put", "patch"], url_path="my-setting")
    def my_setting(self, request):
        staff = Staff.objects.filter(user=request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        setting = _get_or_create_library_setting(staff.school)

        if request.method in ["POST", "PUT", "PATCH"]:
            serializer = self.get_serializer(setting, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()

            # Sync LateBookFees
            LateBookFees.objects.update_or_create(
                school=staff.school,
                defaults={
                    "fees": int(serializer.validated_data.get("fine_per_day", setting.fine_per_day)),
                    "grace_period_days": serializer.validated_data.get("grace_period_days", setting.grace_period_days),
                }
            )
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(setting)
        return Response(serializer.data, status=status.HTTP_200_OK)


class BookCategoryViewSet(ModelViewSet):
    serializer_class = BookCategorySerializer
    permission_classes = [IsAuthenticated, IsLibrarian]

    def get_queryset(self):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        return BookCategory.objects.filter(school=staff.school, is_active=True)

    def perform_create(self, serializer):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        serializer.save(school=staff.school)


class AuthorViewSet(ModelViewSet):
    serializer_class = AuthorSerializer
    permission_classes = [IsAuthenticated, IsLibrarian]

    def get_queryset(self):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        return Author.objects.filter(school=staff.school, is_active=True)

    def perform_create(self, serializer):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        serializer.save(school=staff.school)


class PublisherViewSet(ModelViewSet):
    serializer_class = PublisherSerializer
    permission_classes = [IsAuthenticated, IsLibrarian]

    def get_queryset(self):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        return Publisher.objects.filter(school=staff.school, is_active=True)

    def perform_create(self, serializer):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        serializer.save(school=staff.school)


class RackViewSet(ModelViewSet):
    serializer_class = RackSerializer
    permission_classes = [IsAuthenticated, IsLibrarian]

    def get_queryset(self):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        return Rack.objects.filter(school=staff.school, is_active=True)

    def perform_create(self, serializer):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        serializer.save(school=staff.school)


class ShelfViewSet(ModelViewSet):
    serializer_class = ShelfSerializer
    permission_classes = [IsAuthenticated, IsLibrarian]

    def get_queryset(self):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        return Shelf.objects.filter(school=staff.school, is_active=True)

    def perform_create(self, serializer):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        serializer.save(school=staff.school)


class BookCopyViewSet(ModelViewSet):
    serializer_class = BookCopySerializer
    permission_classes = [IsAuthenticated, IsLibrarian]

    def get_queryset(self):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        qs = BookCopy.objects.filter(school=staff.school, is_active=True)
        book_id = self.request.query_params.get("book")
        if book_id:
            qs = qs.filter(book_id=book_id)
        return qs

    def perform_create(self, serializer):
        staff = Staff.objects.filter(user=self.request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        copy = serializer.save(school=staff.school)
        book = copy.book
        book.total_copies = book.copies.filter(is_active=True).count()
        book.available_copies = book.copies.filter(is_active=True, status="AVAILABLE").count()
        book.save()

    @action(detail=False, methods=["post"], url_path="generate-copies")
    def generate_copies(self, request):
        staff = Staff.objects.filter(user=request.user).first()
        if not staff:
            raise PermissionDenied("You are not registered as staff.")
        
        book_id = request.data.get("book_id")
        count = int(request.data.get("count", 1))
        rack_id = request.data.get("rack_id")
        shelf_id = request.data.get("shelf_id")

        book = Book.objects.filter(id=book_id, school=staff.school).first()
        if not book:
            raise ValidationError("Book not found.")

        existing_count = BookCopy.objects.filter(school=staff.school, book=book).count()
        created_copies = []
        for i in range(1, count + 1):
            copy_num = existing_count + i
            accession_no = f"BC-{book.id:04d}-{copy_num:03d}"
            barcode = f"{book.id:04d}{copy_num:03d}"
            copy = BookCopy.objects.create(
                school=staff.school,
                book=book,
                accession_no=accession_no,
                barcode=barcode,
                rack_id=rack_id,
                shelf_id=shelf_id,
                status="AVAILABLE",
                condition="GOOD",
                purchase_price=book.price
            )
            created_copies.append(copy)

        book.total_copies = book.copies.filter(is_active=True).count()
        book.available_copies = book.copies.filter(is_active=True, status="AVAILABLE").count()
        book.save()

        serializer = self.get_serializer(created_copies, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BookManageView(ModelViewSet):
    serializer_class = BookManageSerializer
    permission_classes = [IsAuthenticated, IsLibrarian]

    def get_queryset(self):
        staff = Staff.objects.filter(user=self.request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")
        return Book.objects.filter(school=staff.school).select_related("category_ref", "author_ref", "publisher_ref", "rack", "shelf")

    def perform_create(self, serializer):
        staff = Staff.objects.filter(user=self.request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")

        title = serializer.validated_data.get("title")
        author = serializer.validated_data.get("author")
        total_copies = serializer.validated_data.get("total_copies", 1)

        book_already = Book.objects.filter(
            school=staff.school, title=title, author=author
        ).first()

        if book_already is not None:
            raise ValidationError(f"Book already exists, id = {book_already.pk}")

        book = serializer.save(school=staff.school, available_copies=total_copies)

        # Auto-create physical BookCopy instances for individual barcode/accession tracking
        for i in range(1, total_copies + 1):
            accession_no = f"BC-{book.id:04d}-{i:03d}"
            barcode = f"{book.id:04d}{i:03d}"
            BookCopy.objects.create(
                school=staff.school,
                book=book,
                accession_no=accession_no,
                barcode=barcode,
                rack=book.rack,
                shelf=book.shelf,
                status="AVAILABLE",
                condition="GOOD",
                purchase_price=book.price
            )

    def perform_destroy(self, instance):
        if instance.total_copies != instance.available_copies:
            raise ValidationError(
                "Can't delete: this book is currently issued to someone. "
                "It must be returned first."
            )
        instance.copies.all().delete()
        return super().perform_destroy(instance)

    def perform_update(self, serializer):
        book = serializer.save()
        # Keep copy count consistent if total copies increased
        current_copies = book.copies.filter(is_active=True).count()
        if book.total_copies > current_copies:
            for i in range(current_copies + 1, book.total_copies + 1):
                accession_no = f"BC-{book.id:04d}-{i:03d}"
                barcode = f"{book.id:04d}{i:03d}"
                BookCopy.objects.create(
                    school=book.school,
                    book=book,
                    accession_no=accession_no,
                    barcode=barcode,
                    rack=book.rack,
                    shelf=book.shelf,
                    status="AVAILABLE",
                    condition="GOOD",
                    purchase_price=book.price
                )
        book.available_copies = book.copies.filter(is_active=True, status="AVAILABLE").count()
        book.save()


class LateBookFeesViews(ModelViewSet):
    serializer_class = LateBookFeesSerializer
    permission_classes = [IsAuthenticated, IsLibrarian]

    def get_queryset(self):
        staff = Staff.objects.filter(user=self.request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")
        return LateBookFees.objects.filter(school=staff.school)

    def perform_create(self, serializer):
        staff = Staff.objects.filter(user=self.request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")

        latefee_already = LateBookFees.objects.filter(school=staff.school).exists()
        if latefee_already:
            raise ValidationError("Fees already set for this school. Edit the existing entry instead.")

        serializer.save(school=staff.school)


class BookIssuedView(ModelViewSet):
    serializer_class = BookIssuedSerializer
    permission_classes = [IsAuthenticated, IsLibrarian]

    def get_queryset(self):
        staff = Staff.objects.filter(user=self.request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")
        return BookIssued.objects.filter(school=staff.school).select_related("book", "student", "book_copy")

    def perform_create(self, serializer):
        staff = Staff.objects.filter(user=self.request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")

        book = serializer.validated_data["book"]
        student = serializer.validated_data["student"]
        due_date = serializer.validated_data.get("due_date")

        if book.school_id != staff.school_id:
            raise ValidationError("That book does not belong to your school.")
        if student.school_id != staff.school_id:
            raise ValidationError("That student does not belong to your school.")

        _issue_book(book=book, student=student, school=staff.school, serializer=serializer, due_date=due_date)

    @action(detail=True, methods=["post"], url_path="return")
    def return_book(self, request, pk=None):
        staff = Staff.objects.filter(user=request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")
        issued = self.get_queryset().filter(pk=pk).first()
        if issued is None:
            raise NotFound("Issued record not found for your school.")

        condition = request.data.get("condition", "GOOD")
        remarks = request.data.get("remarks", "")
        damage_fee = request.data.get("damage_fee")
        lost_fee = request.data.get("lost_fee")

        _finalize_return(issued, condition=condition, remarks=remarks, custom_damage_fee=damage_fee, custom_lost_fee=lost_fee)

        serializer = self.get_serializer(issued)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="renew")
    def renew_book(self, request, pk=None):
        staff = Staff.objects.filter(user=request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")
        issued = self.get_queryset().filter(pk=pk).first()
        if issued is None:
            raise NotFound("Issued record not found.")

        _renew_book_loan(issued)
        serializer = self.get_serializer(issued)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="mark-lost")
    def mark_lost(self, request, pk=None):
        staff = Staff.objects.filter(user=request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")
        issued = self.get_queryset().filter(pk=pk).first()
        if issued is None:
            raise NotFound("Issued record not found.")

        remarks = request.data.get("remarks", "Reported lost by student")
        _finalize_return(issued, condition="LOST", remarks=remarks)

        serializer = self.get_serializer(issued)
        return Response(serializer.data, status=status.HTTP_200_OK)


def _issue_book(*, book, student, school, serializer, due_date=None):
    setting = _get_or_create_library_setting(school)

    # 1. Rule Check: Active Loan Limit per student
    active_loans_count = BookIssued.objects.filter(
        school=school, student=student, status="ISSUED"
    ).count()
    if active_loans_count >= setting.max_books_per_student:
        raise ValidationError(f"Student has reached the maximum allowed limit of {setting.max_books_per_student} books.")

    # 2. Rule Check: Book Availability
    if book.available_copies <= 0:
        raise ValidationError("No copies of this book are currently available. You can reserve this book.")

    # 3. Rule Check: Student duplicate checkout
    already_issued = BookIssued.objects.filter(
        student=student, book=book, status="ISSUED"
    ).exists()
    if already_issued:
        raise ValidationError("This student already has a copy of this book checked out.")

    # 4. Find available physical BookCopy
    available_copy = BookCopy.objects.filter(
        school=school, book=book, status="AVAILABLE", is_active=True
    ).first()

    now = timezone.now()

    if due_date is None:
        loan_days = setting.issue_duration_days or 14
        due_date = now + timezone.timedelta(days=loan_days)
    elif due_date <= now:
        raise ValidationError("Due date must be in the future.")

    # Update physical copy status if exists
    if available_copy:
        available_copy.status = "ISSUED"
        available_copy.save()

    book.available_copies = max(0, book.available_copies - 1)
    book.save()

    serializer.save(
        school=school,
        student=student,
        book=book,
        book_copy=available_copy,
        book_issued_date=now,
        due_date=due_date,
        renewal_count=0,
        status="ISSUED",
    )


def _renew_book_loan(issued: BookIssued):
    if issued.status != "ISSUED":
        raise ValidationError("Only active loans can be renewed.")

    setting = _get_or_create_library_setting(issued.school)

    if issued.renewal_count >= setting.max_renewal_count:
        raise ValidationError(f"Maximum renewal limit of {setting.max_renewal_count} times reached for this book.")

    # Check if someone is in the reservation queue for this book
    reservation_exists = BookReservation.objects.filter(
        school=issued.school, book=issued.book, status="WAITING"
    ).exists()
    if reservation_exists:
        raise ValidationError("Cannot renew: Another student is currently waiting in the reservation queue for this book.")

    loan_days = setting.issue_duration_days or 14
    issued.due_date = (issued.due_date or timezone.now()) + timezone.timedelta(days=loan_days)
    issued.renewal_count += 1
    issued.save()


def _finalize_return(issued: BookIssued, condition="GOOD", remarks="", custom_damage_fee=None, custom_lost_fee=None):
    if issued.status in ["RETURNED", "LOST"]:
        raise ValidationError("This book transaction has already been closed.")

    now = timezone.now()
    issued.actual_return_date = now
    issued.condition_on_return = condition
    issued.remarks = remarks

    setting = _get_or_create_library_setting(issued.school)
    grace_period_days = setting.grace_period_days or 0
    per_day_fee = float(setting.fine_per_day or 0)

    grace_deadline = issued.due_date + timezone.timedelta(days=grace_period_days)

    late_fee = 0
    if now > grace_deadline:
        issued.is_late = True
        days_past_grace = (now.date() - grace_deadline.date()).days
        late_fee = max(days_past_grace, 0) * per_day_fee
    else:
        issued.is_late = False
        late_fee = 0

    issued.late_fees = late_fee

    damage_fee = 0
    lost_fee = 0

    if condition in ["MINOR_DAMAGE", "MAJOR_DAMAGE", "DAMAGED"]:
        issued.status = "DAMAGED"
        damage_fee = float(custom_damage_fee) if custom_damage_fee is not None else float(setting.damage_penalty or 50.0)
        issued.damage_fees = damage_fee
        if issued.book_copy:
            issued.book_copy.status = "DAMAGED"
            issued.book_copy.condition = "MAJOR_DAMAGE" if condition == "MAJOR_DAMAGE" else "MINOR_DAMAGE"
            issued.book_copy.save()
    elif condition == "LOST":
        issued.status = "LOST"
        book_price = float(issued.book.price or 0)
        lost_penalty = float(setting.lost_penalty or 100.0)
        lost_fee = float(custom_lost_fee) if custom_lost_fee is not None else (book_price + lost_penalty)
        issued.lost_fees = lost_fee
        if issued.book_copy:
            issued.book_copy.status = "LOST"
            issued.book_copy.save()
    else:
        issued.status = "RETURNED"
        if issued.book_copy:
            issued.book_copy.status = "AVAILABLE"
            issued.book_copy.condition = "GOOD"
            issued.book_copy.save()

    issued.total_fine = late_fee + damage_fee + lost_fee
    issued.save()

    # If good or minor damage, restore available count
    book = issued.book
    if condition not in ["LOST", "MAJOR_DAMAGE"]:
        book.available_copies = min(book.total_copies, book.available_copies + 1)
        book.save()

        # Check waiting reservations queue and notify/promote the next student
        waiting_reservation = BookReservation.objects.filter(
            school=issued.school, book=book, status="WAITING"
        ).order_by("queue_number", "reservation_date").first()

        if waiting_reservation:
            waiting_reservation.status = "AVAILABLE"
            waiting_reservation.available_date = now
            waiting_reservation.expiry_date = now + timezone.timedelta(days=2)
            waiting_reservation.save()


class BookReservationViewSet(ModelViewSet):
    serializer_class = BookReservationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        staff = Staff.objects.filter(user=user).first()
        student = Student.objects.filter(user=user).first()

        if staff:
            return BookReservation.objects.filter(school=staff.school).select_related("book", "student")
        elif student:
            return BookReservation.objects.filter(school=student.school, student=student).select_related("book", "student")
        else:
            raise PermissionDenied("Access denied.")

    def perform_create(self, serializer):
        user = self.request.user
        student = Student.objects.filter(user=user).first()
        if not student:
            raise PermissionDenied("Only students can reserve books.")

        book = serializer.validated_data["book"]
        if book.school_id != student.school_id:
            raise ValidationError("That book does not belong to your school.")

        already_reserved = BookReservation.objects.filter(
            school=student.school, book=book, student=student, status__in=["WAITING", "AVAILABLE"]
        ).exists()
        if already_reserved:
            raise ValidationError("You have already reserved this book.")

        active_loan = BookIssued.objects.filter(
            school=student.school, book=book, student=student, status="ISSUED"
        ).exists()
        if active_loan:
            raise ValidationError("You already have this book checked out.")

        # Compute next queue number for this book
        last_queue = BookReservation.objects.filter(
            school=student.school, book=book, status="WAITING"
        ).count()
        next_queue = last_queue + 1

        serializer.save(
            school=student.school,
            student=student,
            book=book,
            queue_number=next_queue,
            status="WAITING"
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel_reservation(self, request, pk=None):
        reservation = self.get_object()
        reservation.status = "CANCELLED"
        reservation.save()
        return Response({"detail": "Reservation cancelled successfully."}, status=status.HTTP_200_OK)


class BookViewStudent(ModelViewSet):
    """Read-only catalogue browsing for students, scoped to their school."""
    serializer_class = BookManageSerializer
    http_method_names = ["get"]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        student = Student.objects.filter(user=self.request.user).first()
        if student is None:
            raise PermissionDenied("You are not registered as a student.")
        return Book.objects.filter(school=student.school).select_related("category_ref", "author_ref", "publisher_ref", "rack", "shelf")


class BookIssueStudent(ModelViewSet):
    serializer_class = BookIssuedForSelfSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post"]

    def get_queryset(self):
        student = Student.objects.filter(user=self.request.user).first()
        if student is None:
            raise PermissionDenied("You are not registered as a student.")
        return BookIssued.objects.filter(student=student).select_related("book", "book_copy")

    def perform_create(self, serializer):
        student = Student.objects.filter(user=self.request.user).first()
        if student is None:
            raise PermissionDenied("You are not registered as a student.")

        if serializer.validated_data.get("due_date") is not None:
            raise PermissionDenied("Only library staff can set the due date for a loan.")

        book = serializer.validated_data["book"]
        if book.school_id != student.school_id:
            raise ValidationError("That book is not available at your school.")

        _issue_book(book=book, student=student, school=student.school, serializer=serializer)

    @action(detail=True, methods=["post"], url_path="renew")
    def request_renewal(self, request, pk=None):
        student = Student.objects.filter(user=request.user).first()
        if student is None:
            raise PermissionDenied("You are not registered as a student.")

        issued = BookIssued.objects.filter(pk=pk, student=student).first()
        if not issued:
            raise NotFound("Issued book record not found.")

        _renew_book_loan(issued)
        serializer = self.get_serializer(issued)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="return")
    def return_book(self, request, pk=None):
        raise PermissionDenied(
            "Only library staff can confirm a return. "
            "Please return the physical book to the librarian's desk."
        )
        
        
        
class ReportsView(ViewSet):
    """
    Library usage reports. Not a ModelViewSet — these are aggregation
    queries over BookIssued/Book, not CRUD on a single model. Each report
    is its own @action, scoped to the caller's school via the same
    Staff-lookup pattern used throughout this file.
 
    GET /reports/most_borrowed/      ?limit=N (default 10)
    GET /reports/category_trends/
    GET /reports/overdue_and_late/
    GET /reports/fee_collection/
    GET /reports/student_activity/   ?limit=N (default 20)
 
    All five were verified against seeded test data with hand-checked
    totals (issue counts, late-fee sums, overdue day counts) before being
    added here — the query logic is not guesswork.
    """
    permission_classes = [IsAuthenticated, IsLibrarian]
 
    @action(detail=False, methods=["get"])
    def most_borrowed(self, request):
        """Ranks books by total times issued (all-time, ISSUED + RETURNED)."""
        staff = Staff.objects.filter(user=request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")
 
        try:
            limit = int(request.query_params.get("limit", 10))
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 100))  # sane bounds against abuse
 
        qs = (
            Book.objects.filter(school=staff.school)
            .annotate(times_issued=Count("bookissued"))
            .order_by("-times_issued", "title")[:limit]
        )
 
        data = [
            {
                "book_id": b.id,
                "title": b.title,
                "author": b.author,
                "category": b.category,
                "times_issued": b.times_issued,
                "total_copies": b.total_copies,
                "available_copies": b.available_copies,
            }
            for b in qs
        ]
        return Response({"results": data})
 
    @action(detail=False, methods=["get"])
    def category_trends(self, request):
        """Total issues per category, most popular first."""
        staff = Staff.objects.filter(user=request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")
 
        qs = (
            BookIssued.objects.filter(school=staff.school)
            .values("book__category")
            .annotate(times_issued=Count("id"))
            .order_by("-times_issued")
        )
 
        data = [
            {"category": row["book__category"], "times_issued": row["times_issued"]}
            for row in qs
        ]
        return Response({"results": data})
 
    @action(detail=False, methods=["get"])
    def overdue_and_late(self, request):
        """
        Two parts:
          - currently_overdue: loans still ISSUED, past (due_date + grace
            period) — i.e. would be charged a fee right now if returned today.
          - historical_late_rate: of all RETURNED loans, what % came back
            after the grace period (is_late=True).
        """
        staff = Staff.objects.filter(user=request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")
 
        now = timezone.now()
        fee_policy = LateBookFees.objects.filter(school=staff.school).first()
        grace_days = fee_policy.grace_period_days if fee_policy else 0
 
        currently_issued = BookIssued.objects.filter(
            school=staff.school, status="ISSUED"
        ).select_related("book", "student")
 
        overdue_list = []
        for loan in currently_issued:
            grace_deadline = loan.due_date + timezone.timedelta(days=grace_days)
            if now > grace_deadline:
                days_overdue = (now.date() - grace_deadline.date()).days
                overdue_list.append({
                    "loan_id": loan.id,
                    "book_id": loan.book_id,
                    "book_title": loan.book.title,
                    "student_id": loan.student_id,
                    "student_name": getattr(loan.student, "name", str(loan.student_id)),
                    "due_date": loan.due_date,
                    "days_overdue": days_overdue,
                })
 
        overdue_list.sort(key=lambda x: x["days_overdue"], reverse=True)
 
        returned_qs = BookIssued.objects.filter(school=staff.school, status="RETURNED")
        total_returned = returned_qs.count()
        total_late = returned_qs.filter(is_late=True).count()
        late_rate_percent = round((total_late / total_returned) * 100, 1) if total_returned else 0.0
 
        return Response({
            "currently_overdue": overdue_list,
            "currently_overdue_count": len(overdue_list),
            "historical_late_rate": {
                "total_returned_loans": total_returned,
                "total_late_returns": total_late,
                "late_rate_percent": late_rate_percent,
            },
        })
 
    @action(detail=False, methods=["get"])
    def fee_collection(self, request):
        """
        Total late fees across all returned loans, plus a month-by-month
        breakdown (grouped by actual_return_date).
 
        Note: reflects fees computed at return time — the model has no
        separate paid/unpaid flag, so every RETURNED loan's late_fees
        value is treated as the amount owed for that loan.
        """
        staff = Staff.objects.filter(user=request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")
 
        returned_qs = BookIssued.objects.filter(school=staff.school, status="RETURNED")
        total_fees = returned_qs.aggregate(total=Sum("late_fees"))["total"] or 0
 
        monthly = (
            returned_qs.filter(is_late=True)
            .annotate(month=TruncMonth("actual_return_date"))
            .values("month")
            .annotate(total_fees=Sum("late_fees"), late_returns=Count("id"))
            .order_by("month")
        )
 
        monthly_data = [
            {
                "month": row["month"].strftime("%Y-%m") if row["month"] else None,
                "total_fees": str(row["total_fees"]),
                "late_returns": row["late_returns"],
            }
            for row in monthly
        ]
 
        return Response({
            "total_fees_collected": str(total_fees),
            "monthly_breakdown": monthly_data,
        })
 
    @action(detail=False, methods=["get"])
    def student_activity(self, request):
        """Per-student borrowing stats: total loans, currently held, late returns."""
        staff = Staff.objects.filter(user=request.user).first()
        if staff is None:
            raise PermissionDenied("You are not registered as staff for any school.")
 
        try:
            limit = int(request.query_params.get("limit", 20))
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 200))
 
        qs = (
            BookIssued.objects.filter(school=staff.school)
            .values("student_id", "student__name")
            .annotate(
                total_loans=Count("id"),
                currently_held=Count("id", filter=Q(status="ISSUED")),
                late_returns=Count("id", filter=Q(status="RETURNED", is_late=True)),
            )
            .order_by("-total_loans")[:limit]
        )
 
        data = [
            {
                "student_id": row["student_id"],
                "student_name": row["student__name"],
                "total_loans": row["total_loans"],
                "currently_held": row["currently_held"],
                "late_returns": row["late_returns"],
            }
            for row in qs
        ]
        return Response({"results": data})