from django.utils import timezone
from .models import StaffRemainingLeave
from .models import *
from .serializer import *
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView;
from rest_framework.response import Response
from rest_framework.permissions import BasePermission
from .harsh_serializer import *
from rest_framework.generics import GenericAPIView, ListCreateAPIView, ListAPIView
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from uuid import uuid4



class IsCLerk(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="CLERK").exists()
        )
        
class Isstudent(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="student").exists()
        )
        
class Isteacher(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="TEACHER").exists()
        )
   
   
class IsLibrarian(BasePermission):     
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="LIBRARIAN").exists()
        )


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
            print("already current", lt.id)
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
        
        
        
        
class CertificateTypeSerializer(ModelViewSet): #for create, read, update, delete  certificate type - Bonafide
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
def get_clerk_school(request):
    user = request.user
    if not hasattr(user, "role") or user.role != "CLERK":
        raise PermissionDenied("Only clerks can perform this action.")
    school = getattr(user, "school", None)
    if school is None:
        raise PermissionDenied("Clerk is not associated with any school.")
    return school
 
 

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
    
    
    
    
class GetStaffLeaveRequest(APIView): # perticular staff leave request to staff see there leave request
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # leave_template = request.data.get("leave_template")
        user = request.user

        staff = Staff.objects.filter(user=user).first()
        queryset = LeaveRequest.objects.filter(
            staff=staff, school=user.school
            # , leave_template=leave_template
        )

        serializer = GetLeaveRequestSerializer(queryset, many=True)
        return Response(serializer.data)
        
        
        
        
class GetLeaveRequestView(ModelViewSet): #for all the leaves to clerk can see and approve
    queryset = LeaveRequest.objects.all()
    serializer_class = GetLeaveRequestSerializer
    permission_classes = [IsAuthenticated, IsCLerk]
    http_method_names = ["get"]

    def get_queryset(self):

        queryset = LeaveRequest.objects.filter(school=self.request.user.school)

        return queryset
    
    
    
    
class ChangeLeaveView(ModelViewSet): # for approving day wise APPROVAL
    queryset = LeavePerDay.objects.all()
    serializer_class = ChangeLeavePerDaySerializer
    permission_classes = [IsAuthenticated, IsCLerk]
    http_method_names = ["patch"]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.leave.school != request.user.school:
            return Response(
                {"error": "You are not allowed to modify this record"}, status=403
            )

        return super().update(request, *args, **kwargs)
    
    


class ChangeAllLeaveView(APIView): # for APPROVE all day leave
    permission_classes = [IsAuthenticated, IsCLerk]

    def patch(self, request, pk):
        
        status_value = request.data.get("status")

        leave_request = LeaveRequest.objects.filter(
            id=pk,
            school=request.user.school
        ).first()

        if not leave_request:
            return Response(
                {"error": "Leave request not found"},
                status=404
            )

        leave_days = leave_request.leave_days.filter(
            status="PENDING"
        )

        for leave_day in leave_days:

            serializer = ChangeLeavePerDaySerializer(
                leave_day,  
                data={"status": status_value},
                partial=True,
                context={"request": request}
            )

            serializer.is_valid(raise_exception=True)
            serializer.save()

        return Response(
            {"message": "All leave days approved"}
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
    
    def get_queryset(self):
        
        user = self.request.user
        
        student = Student.objects.filter(user=user).first()
        
        qs = StudentAttendance.objects.filter(student = student)
        
        
        return qs
    
    
class SyllabusListView(ListAPIView):
    serializer_class = SyllabusListSerializer
    permission_classes=[IsAuthenticated, Isstudent]
    
    def get_queryset(self):
        
        user = self.request.user
        
        student = Student.objects.filter(user=user).first()
        
        
        qs = Syllabus.objects.filter(division = student.division, school=student.school)
        # qs = Syllabus.objects.filter(school=student.school)
        
        
        return qs


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
        
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            title = serializer.validated_data['title']
            description = serializer.validated_data['description']
            subject = serializer.validated_data['subject']
            exam_date = serializer.validated_data['exam_date']
            start_time = serializer.validated_data['start_time']
            end_time = serializer.validated_data['end_time']
            class_group = serializer.validated_data['class_group']


            exam = Exam.objects.create(
                school = staff.school,
                created_by = staff,
                title = title,
                description = description,
                subject = subject,
                exam_date= exam_date,
                start_time = start_time,
                end_time = end_time,
                class_group = class_group
            )
            
            exam.save()
            
            return Response({
                "detail":"exam scheduled"
            })
        
        return Response(serializer.errors)
    
    
    
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
    
    def get_queryset(self):
        
        staff = Staff.objects.filter(user=self.request.user).first()
        
        
        return SchoolClass.objects.filter(school = staff.school)
    
    
    
class BookManageView(ModelViewSet):
    serializer_class = BookManageSerializer

    permission_classes = [IsAuthenticated, IsLibrarian]
    
    def get_queryset(self):
        
        staff = Staff.objects.filter(user=self.request.user).first()
        
        return Book.objects.filter(school=staff.school)
    
    
    
    def perform_create(self, serializer):
        
        staff = Staff.objects.filter(user=self.request.user).first()
        # school = School.objects.filter(login_id = self.request.user).first()
        

        title = serializer.validated_data.get("title")
        author = serializer.validated_data.get("author")
        category = serializer.validated_data.get("category")
        total_copies = serializer.validated_data.get("total_copies")
        
        book_already= Book.objects.filter(school=staff.school, title=title, author=author).first()
        
        
        if book_already is not None:
            raise ValidationError(f"Book Already exists id = {book_already.pk}")
        
        
        serializer.save(school = staff.school,available_copies=total_copies)
        
    
    
    def perform_destroy(self, instance):
        
        if not instance.total_copies == instance.available_copies:
            raise ValidationError("Can't Delete Beacause Book Issued To Someone First Take That Back")
        
        return super().perform_destroy(instance)
    
    
    
    def perform_update(self, serializer):
        
        read_only_value = self.request.data.get('available_copies')
        
        if read_only_value is not None:
            serializer.save(available_copies = read_only_value)
        
        else:
            serializer.save()
            
            
            
            
class LateBookFeesViews(ModelViewSet):
    serializer_class = LateBookFeesSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        
        staff = Staff.objects.filter(user=self.request.user).first()
        
        latebookfees = LateBookFees.objects.filter(school=staff.school)
        
        return latebookfees
    
    def perform_create(self, serializer):
        
        staff = Staff.objects.filter(user=self.request.user).first()
        
        latefee_already = LateBookFees.objects.filter(school=staff.school).exists()
        
        if latefee_already:
            raise ValidationError("Already Fees Decided if you want to change edit it")
                
        serializer.save(school=staff.school)
        
        
        

class BookIssuedView(ModelViewSet):
    serializer_class = BookIssuedSerializer

    def get_queryset(self):
        
        staff = Staff.objects.filter(user=self.request.user).first()
        
        book_issued = BookIssued.objects.filter(school=staff.school)
        
        return book_issued
    
    
    def perform_create(self, serializer):
        
        staff = Staff.objects.filter(user=self.request.user).first()
        
        
        
        return super().perform_create(serializer)