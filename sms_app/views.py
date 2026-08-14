from .inventory_views import *
from .academic_views import *
from .finance_views import *
from .staff_views import *
from .student_views import *
from .school_views import *
from .auth_views import *
from .utils import *
from .permissions import *
from django.shortcuts import redirect, render
from django.urls import reverse
from django.db.models import Q
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Q
from .models import *
from django.db import models

from rest_framework.permissions import BasePermission
from .models import UserModuleAccess

from sms_app.razorpay_client import client
from rest_framework.views import APIView

from os import link
from urllib import request, response
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.shortcuts import render
from requests import get
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from django.core.cache import cache
from rest_framework.permissions import IsAuthenticated

from sms_app.models import *
from sms_app.serializer import *
from rest_framework.permissions import BasePermission, IsAuthenticated
import random
import string
from django.contrib.auth.models import Group

from django.conf import settings
from django.db import transaction
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework.views import APIView
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.db.models import Q

from rest_framework_simplejwt.views import TokenObtainPairView

from django.contrib.auth import get_user_model

User = get_user_model()


from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from sms_app.models import DocumentFile

from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from sms_app.models import DocumentFile

import hmac
import hashlib
from rest_framework import status
from django.conf import settings

import hmac
import hashlib

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

# from .serializers import DocumentS

from django.core.cache import cache
from rest_framework import generics

import pandas as pd
from datetime import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from sms_app.harsh_views import carry_forward_leave
# from yourapp.models import Student, SchoolClass, School

User = get_user_model()

# from django.http import JsonRespons

# from .views import Isprincipal


def health_check(request):
    return JsonResponse({"status": "ok"})


def health_check(request):
    return JsonResponse({"status": "ok"})


# Create your views here.
# set access and refresh token in cookie
class RazarDataView(ModelViewSet):
    queryset = RazorPayData.objects.all()
    serializer_class = RazarDataSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ShareFormLink(request):
    user = getattr(request, "user", None)
    school = getattr(user, "school", None) if user else None
    if not school:
        return Response(
            {"detail": "User is not associated with any school.", "form_link": ""},
            status=status.HTTP_400_BAD_REQUEST,
        )

    form = AdmissionForm.objects.filter(
        school=school, is_active=True
    ).first()

    if not form:
        return Response(
            {"detail": "No active admission form found for this school.", "form_link": ""},
            status=status.HTTP_404_NOT_FOUND,
        )

    form_link = f"/api/admission/{form.unique_link}/"

    return Response({"form_link": form_link, "unique_link": str(form.unique_link)})


FRONTEND_LOGIN_URL = "https://edunet-one.vercel.app/login"


def get_receipt(request, student_id, form_id):

    student = Student.objects.filter(id=student_id).first()

    message = None
    field_values = None
    if student.details_done:
        field_values = StudentFieldValue.objects.select_related("field").filter(
            student_id=student_id, form_id=form_id
        )

    else:
        message = "Some Think error admission process are not done yet"
    # Example: Payment (if you have model)
    # payment = Payment.objects.filter(student_id=student_id).last()

    context = {
        "fields": field_values,
        # "payment": payment,
        "message": message,
    }

    return render(request, "receipt.html", context)


from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from itertools import cycle


def assign_student_divisions():

    # Get all classes
    classes = SchoolClass.objects.all()

    for school_class in classes:
        # Get divisions for this class
        divisions = list(
            Division.objects.filter(SchoolClass=school_class).order_by("id")
        )

        # Skip if no divisions exist
        if not divisions:
            print(f"Skipping {school_class} (no divisions found)")
            continue

        division_len = len(divisions)

        # Get students of this class
        students = list(
            Student.objects.filter(school_class=school_class).order_by("created_at")
        )

        if not students:
            print(f"No students in {school_class}")
            continue

        # Optional: shuffle students for random distribution
        # random.shuffle(students)

        # Assign divisions (round-robin)
        for index, student in enumerate(students):
            student.division = divisions[index % division_len].division

        # Bulk update for performance
        Student.objects.bulk_update(students, ["division"])



# ==================================================================


def SetSlotView(request):
    class_div_id = request.data.get("class_div")
    school = getattr(request.user, "school", None)

    if not class_div_id:
        return Response(
            {"error": "class_div is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    tt_days = Tt_day.objects.filter(class_div=class_div_id).select_related(
        "year", "class_div", "class_div__SchoolClass"
    )

    # if school:
    #     tt_days = tt_days.filter(school=school)

    if not tt_days.exists():
        return Response(
            {"error": "No timetable day found for the selected filters"},
            status=status.HTTP_404_NOT_FOUND,
        )

    assignments = list(
        AssignClass.objects.filter(division=class_div_id)
        .exclude(teacher__isnull=True)
        .select_related("teacher", "division")
    )

    print(class_div_id)
    print(assignments)
    # if school:
    #     assignments = [a for a in assignments if a.school_id == school.id]

    if not assignments:
        return Response(
            {"error": "No assigned teachers found for this class division"},
            status=status.HTTP_404_NOT_FOUND,
        )

    class_teacher_assignment = next(
        (item for item in assignments if item.is_class_teacher), None
    )
    other_assignments = [item for item in assignments if not item.is_class_teacher]
    random.shuffle(other_assignments)

    teacher_pool = other_assignments[:]
    if not teacher_pool and class_teacher_assignment:
        teacher_pool = [class_teacher_assignment]

    if not teacher_pool and not class_teacher_assignment:
        return Response(
            {"error": "No teachers available to set timetable"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    created_rows = []

    with transaction.atomic():
        for tt_day in tt_days:
            day_time = tt_day.tt_day_time_set.first()
            slots = list(tt_day.tt_slot_set.all().order_by("id"))

            if not day_time:
                return Response(
                    {"error": f"Day time is missing for {tt_day.day}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not slots:
                return Response(
                    {"error": f"Slots are missing for {tt_day.day}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            rotating_teachers = cycle(teacher_pool)

            for index, slot_obj in enumerate(slots):
                slot_data = slot_obj.slot or {}
                slot_label = str(slot_data.get("slot") or slot_obj.lecture)
                start_time = slot_data.get("start") or day_time.start
                end_time = slot_data.get("end") or day_time.end

                if index == 0 and class_teacher_assignment:
                    teacher = class_teacher_assignment.teacher
                else:
                    teacher = next(rotating_teachers).teacher

                timetable_obj, _ = Time_table.objects.update_or_create(
                    year=tt_day.year,
                    day=tt_day.day,
                    class_div=tt_day.class_div,
                    slot=slot_label,
                    defaults={
                        "school": school or tt_day.school,
                        "teacher": teacher,
                        "start": start_time,
                        "end": end_time,
                    },
                )
                created_rows.append(timetable_obj)

    serializer = SetTimeTableSerializer(created_rows, many=True)
    return Response(
        {
            "message": "Time table set successfully",
            "data": serializer.data,
        },
        status=status.HTTP_201_CREATED,
    )


# for get student for principle with filter     [school filter add remainig]
def get_student_fee_for_online_payment(user, student_fee_id):
    student = Student.objects.filter(user=user).select_related("school").first()

    if student:
        student_fee = StudentFee.objects.select_related(
            "student", "feetype", "school"
        ).get(id=student_fee_id, student=student, school=student.school)
        return student_fee, student.school

    school = getattr(user, "school", None)
    if not school:
        raise StudentFee.DoesNotExist

    student_fee = StudentFee.objects.select_related("student", "feetype", "school").get(
        id=student_fee_id, school=school
    )
    return student_fee, school


def get_student_fee_payment_for_online_verify(user, order_id):
    student = Student.objects.filter(user=user).select_related("school").first()
    queryset = StudentFeePayment.objects.select_related(
        "student_fee",
        "student_fee__student",
        "student_fee__feetype",
        "student",
        "feetype",
    ).filter(razorpay_order_id=order_id)

    if student:
        return queryset.get(student=student, school=student.school)

    school = getattr(user, "school", None)
    if not school:
        raise StudentFeePayment.DoesNotExist

    return queryset.get(school=school)


class SchoolQuerySetMixin:
    def get_queryset(self):
        return self.queryset.filter(school=self.request.user.school)


class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get('refresh_token')
        if refresh_token:
            if hasattr(request.data, '_mutable'):
                request.data._mutable = True
                request.data['refresh'] = refresh_token
                request.data._mutable = False
            else:
                request.data['refresh'] = refresh_token
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200 and 'access' in response.data:
            access_token = response.data['access']
            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure=True,
                samesite='None',
                max_age=60 * 60,
                path='/',
            )
        return response
