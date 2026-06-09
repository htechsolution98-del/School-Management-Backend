from django.utils import timezone
from .models import StaffRemainingLeave
from .models import *
from .serializer import *
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import BasePermission
from .harsh_serializer import *
from rest_framework.generics import GenericAPIView, ListCreateAPIView, ListAPIView
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action



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




def carry_forward_leave(staff): # when login staff check month and year and carry forward pending leaves
    current_month = timezone.now().month
    current_year = timezone.now().year

    leaves = StaffRemainingLeave.objects.filter(staff=staff)

    for leave in leaves:

        if (leave.month != current_month or leave.year != current_year):
            carry = leave.remaining_leaves

            monthly_quota = leave.leave_template.leave_num

            leave.total_levaes = monthly_quota + carry
            leave.remaining_leaves = monthly_quota + carry

            leave.month = current_month
            leave.year = current_year

            leave.save()


# class LeaveTypeView(ModelViewSet): #for creating leave type - casual leave, sick leave
#     queryset = LeaveType.objects.all()
#     serializer_class = LeaveTypeSerializer
#     permission_classes = [IsAuthenticated, IsCLerk]



class LeaveTypeView(ModelViewSet): #for create, read, update, delete  leave type - casual leave, sick leave
    serializer_class = LeaveTypeSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        staff = Staff.objects.filter(
            user=self.request.user,
            category="CLERK"
        ).first()

        if not staff:
            return LeaveType.objects.none()

        return LeaveType.objects.filter(
            school=staff.school
        )

    def perform_create(self, serializer):
        staff = Staff.objects.filter(
            user=self.request.user,
            category="CLERK"
        ).first()

        if not staff:
            raise ValidationError("Clerk profile not found.")

        name = serializer.validated_data.get("name")

        if LeaveType.objects.filter(
            school=staff.school,
            name__iexact=name
        ).exists():
            raise ValidationError(
                {"name": "This leave type already exists."}
            )

        serializer.save(school=staff.school)




class LeaveTemplateView(ModelViewSet): #for giving perticular staff how many days of leave given
    queryset = LeaveTemplate.objects.all()
    serializer_class = LeaveTemplateSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_parsers(self):

        return super().get_parsers()


class LeaveRequestView(ModelViewSet): #for requesting leave
    queryset = LeaveRequest.objects.all()
    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticated]
    


class GetLeaveRequestView(ModelViewSet): #for all the leaves to clerk
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
    
    
class GetStaffRemainingleave(ListAPIView):
    permission_classes = [IsAuthenticated]

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
    
    
    

class GetRemainingLeaveView(APIView): # perticular staff leave request
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
    serializer_class = CertificateRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        student = Student.objects.filter(user=self.request.user).first()
        if not student:
            return CertificateRequest.objects.none()

        return CertificateRequest.objects.filter(student=student, school=student.school)

    def perform_create(self, serializer):
        student = Student.objects.filter(user=self.request.user).first()

        if not student:
            raise ValidationError("Student profile not found.")
        
        if CertificateRequest.objects.filter(
                student=student,
                school=student.school,
                certificate_type=serializer.validated_data["certificate_type"],
                status="PENDING"
            ).exists():
            
            raise ValidationError("Request already pending.")

        serializer.save(student=student)
      
        


class ClerkCertificateRequestViewSet(ModelViewSet):
    serializer_class = ClerkCertificateRequestSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        staff = Staff.objects.filter(
            user=self.request.user,
            category="CLERK"
        ).first()

        if not staff:
            return CertificateRequest.objects.none()

        queryset = CertificateRequest.objects.filter(
            certificate_type__school=staff.school
        ).select_related("certificate_type")

        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status.upper())

        return queryset

    def perform_update(self, serializer):
        staff = Staff.objects.filter(
            user=self.request.user,
            category="CLERK"
        ).first()

        if not staff:
            raise ValidationError("Clerk profile not found.")

        instance = self.get_object()

        # Only allow status change if PENDING
        if instance.status != "PENDING":
            raise ValidationError("Request already processed.")

        new_status = serializer.validated_data.get("status")

        if new_status not in ["APPROVED", "REJECTED"]:
            raise ValidationError("Invalid status value.")

        serializer.save()