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



class IsCLerk(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="CLERK").exists()
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


class LeaveTypeView(ModelViewSet): #for creating leave type - casual leave, sick leave
    queryset = LeaveType.objects.all()
    serializer_class = LeaveTypeSerializer
    permission_classes = [IsAuthenticated, IsCLerk]


class LeaveTemplateView(ModelViewSet): #for giving perticular staff hoe many days of leave given
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