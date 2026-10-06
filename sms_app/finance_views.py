import hmac
import hashlib
import json
import razorpay
from django.conf import settings
from sms_app.razorpay_client import client, get_school_razorpay
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.utils import timezone
from .models import *
from .serializer import *
from .permissions import *
from .utils import *
import datetime
import re
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes, action

class FeeVerifyView(ModelViewSet):
    queryset = Admission.objects.all()
    serializer_class = FeesVerifySerializer
    permission_classes = [IsAuthenticated, IsFeeManager | IsClerkOrPrincipal]
    lookup_field = "admission_number"

    def get_queryset(self):
        user = self.request.user
        school = getattr(user, "school", None)
        if not school:
            staff = getattr(user, "staff", None)
            if staff and staff.school:
                school = staff.school
        return Admission.objects.filter(
            pay_process=True, school=school
        )

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response(
            {
                "message": "Fee verified successfully",
                "admission_number": response.data.get("admission_number"),
            },
            status=response.status_code,
        )


# ========================================


# =====serializer for School class=====
# this for only get its public use on Admission fprosecc


class RazorpayOrderView(APIView):

    def post(self, request):

        admission_number = request.data.get("admission_number")
        amount = request.data.get("amount")

        if not admission_number:
            return Response(
                {"error": "Admission number is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get admission
        admission = (
            Admission.objects.select_related("form")
            .filter(admission_number=admission_number)
            .first()
        )

        if not admission:
            return Response(
                {"error": "Admission not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if admission.pay_process or AdmissionFee.objects.filter(admission_number=admission_number, paid_at__isnull=False).exists():
            raise serializers.ValidationError({"message": "You already paid"})

        try:
            with transaction.atomic():
                # print(admission.form.fee_type)
                if admission.is_rte:
                    fee_amount = 0.0
                elif admission.form.fee_type == "general":
                    fee_amount = admission.form.fees
                    fee_amount = float(fee_amount)

                else:
                    # Get class field value
                    value_obj = AdmissionFieldValue.objects.filter(
                        admission=admission,
                        field__section__form=admission.form,
                        field__map_to_student_field="school_class",
                    ).first()

                    fee_structure = None
                    val = str(value_obj.value).strip() if value_obj and value_obj.value else ""

                    if val.isdigit():
                        fee_structure = AdmissionFeeStructure.objects.filter(
                            admission_form=admission.form,
                            class_name_id=int(val),
                        ).first()

                    if not fee_structure and val:
                        fee_structure = AdmissionFeeStructure.objects.filter(
                            admission_form=admission.form,
                            class_name__school_class__iexact=val,
                        ).first()

                    if not fee_structure and val and getattr(admission, "school", None):
                        matched_class = SchoolClass.objects.filter(
                            school=admission.school,
                            school_class__iexact=val,
                        ).first()
                        if matched_class:
                            fee_structure = AdmissionFeeStructure.objects.filter(
                                admission_form=admission.form,
                                class_name=matched_class,
                            ).first()

                    if not fee_structure:
                        fee_structure = AdmissionFeeStructure.objects.filter(
                            admission_form=admission.form,
                        ).first()

                    if fee_structure and fee_structure.fee_amount is not None:
                        fee_amount = float(fee_structure.fee_amount)
                    elif admission.form and admission.form.fees:
                        fee_amount = float(admission.form.fees)
                    else:
                        fee_amount = 0.0

                # Convert to paise for Razorpay
                razorpay_amount = int(fee_amount * 100)

                # Save fee in admission
                admission.fee_amount = fee_amount
                admission.save()

                # Get or create unverified fee record
                admission_fee = AdmissionFee.objects.filter(
                    admission_number=admission_number,
                    paid_at__isnull=True,
                ).first()

                if not admission_fee:
                    admission_fee = AdmissionFee.objects.create(
                        amount=fee_amount,
                        admission_number=admission_number,
                    )
                else:
                    admission_fee.amount = fee_amount
                    admission_fee.save()

                #   ============FOR INDIVIDUAL SCHOOL =============
                school = getattr(self.request.user, "school", None) or getattr(admission, "school", None)
                client_to_use, key_id_to_use, _ = get_school_razorpay(school)

                # Create Razorpay Order
                razor_order = client_to_use.order.create(
                    {
                        "amount": razorpay_amount,
                        "currency": "INR",
                    }
                )

                # Save razorpay order id
                admission_fee.razorpay_order_id = razor_order["id"]
                admission_fee.save()

                return Response(
                    {
                        "id": razor_order["id"],
                        "key": key_id_to_use,
                        "amount": razor_order["amount"],
                        "currency": "INR",
                        "admission_number": admission_number,
                    },
                    status=status.HTTP_200_OK,
                )

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


from django.utils import timezone


# =======for online payment=========


class VerifyPaymentView(APIView):
    def post(self, request):
        data = request.data

        order_id = data.get("razorpay_order_id")
        payment_id = data.get("razorpay_payment_id")
        signature = data.get("razorpay_signature")

        admission_number = data.get("admission_number")

        # Convert to integer if it's a string
        # student = Student.objects.filter(id =student_id).first()

        # if student.details_done:
        #     return Response({"error": "Payment process are already done"}, status=400)

        # print("RAZORPAY_ORDER_ID", order_id)
        # print("RAZORPAY_PAYMENT_ID", payment_id)
        # print("RAZORPAY_SIGNATURE", signature)

        if not all([order_id, payment_id, signature]):
            return Response({"error": "Missing payment parameters"}, status=400)

        try:
            payment = AdmissionFee.objects.get(razorpay_order_id=order_id)
        except AdmissionFee.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        adm_num = admission_number or getattr(payment, "admission_number", None)
        admission = None
        if adm_num:
            admission = Admission.objects.filter(
                admission_number=adm_num
            ).first()

        school = getattr(request.user, "school", None) or (admission.school if admission else getattr(payment, "school", None))
        _, _, secret = get_school_razorpay(school)

        message = f"{order_id}|{payment_id}"
        generated_signature = hmac.new(
            secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(generated_signature, signature):
            return Response({"status": "failed", "error": "Invalid signature"}, status=400)

        # form_data = AdmissionForm.objects.filter(id=form_id).first()
        # if not form_data:
        #     return Response({"error": "Form not found"}, status=404)

        # student = Student.objects.filter(id=student_id).first()
        # if not student:
        #     return Response({"error": "Student not found"}, status=404)

        # if student.details_done:
        #     return Response({"error": "Payment process are already done"}, status=404)

        with transaction.atomic():
            adm_num = admission_number or getattr(payment, "admission_number", None)
            admission = None
            if adm_num:
                admission = Admission.objects.filter(
                    admission_number=adm_num
                ).first()

            school = getattr(request.user, "school", None) or (admission.school if admission else None)
            payment.razorpay_payment_id = payment_id
            payment.razorpay_signature = signature
            payment.school = school
            payment.payment_mode = "online"
            payment.paid_at = timezone.now()
            payment.save()

            if admission:
                admission.pay_process = True
                admission.save()

        return Response({"status": "success"})




class OffilinePaymentView(APIView):

    def post(self, request):

        amount = request.data.get("amount")
        admission_number = request.data.get("admission_number")

        # Validation
        if not amount:
            return Response(
                {"error": "Amount is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not admission_number:
            return Response(
                {"error": "Admission number is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            amount = int(amount)
        except ValueError:
            return Response(
                {"error": "Invalid amount"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        admission = Admission.objects.filter(
            admission_number=admission_number
        ).first()

        if not admission:
            return Response(
                {"error": "Admission not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if admission.pay_process or AdmissionFee.objects.filter(admission_number=admission_number, paid_at__isnull=False).exists():
            return Response(
                {"error": "Admission fee has already been paid for this application"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            school = getattr(request.user, "school", None) or admission.school
            payment = AdmissionFee.objects.create(
                amount=amount,
                admission_number=admission_number,
                school=school,
                payment_mode="offline",
                paid_at=timezone.now(),
            )

            admission.pay_process = True
            admission.save()

        return Response(
            {
                "status": "success",
                "payment_id": payment.id,
                "admission_number": admission_number,
                "payment_mode": "offline",
            },
            status=status.HTTP_200_OK,
        )




class RazorpayWebhookView(APIView):
    def post(self, request):
        payload = request.body
        signature = request.headers.get("X-Razorpay-Signature")

        secret = settings.RAZOR_PAY_SECRET_KEY

        generated_signature = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()

        if generated_signature == signature:
            data = json.loads(payload)

            if data["event"] == "payment.captured":
                payment_data = data["payload"]["payment"]["entity"]

                order_id = payment_data["order_id"]

                try:
                    payment = AdmissionFee.objects.get(razorpay_order_id=order_id)
                    payment.status = "paid"
                    payment.save()
                except AdmissionFee.DoesNotExist:
                    pass

            return Response({"status": "ok"})

        return Response({"status": "invalid"}, status=400)


# NOT IN USE


class FeeTypeViewSet(ModelViewSet):
    queryset = FeeType.objects.all()
    serializer_class = FeeTypeSerializer
    permission_classes = [IsAuthenticated, IsFeeManager | IsClerkOrPrincipal]

    def get_queryset(self):
        user = self.request.user
        school = getattr(user, "school", None)
        if not school:
            staff = getattr(user, "staff", None)
            if staff and staff.school:
                school = staff.school
        return FeeType.objects.filter(school=school)

    def perform_create(self, serializer):
        user = self.request.user
        school = getattr(user, "school", None)
        if not school:
            staff = getattr(user, "staff", None)
            if staff and staff.school:
                school = staff.school
        serializer.save(school=school)




class FeeWiseClassViewSet(ModelViewSet):
    queryset = FeeWiseClass.objects.all()
    serializer_class = FeeWiseClassSerializer
    permission_classes = [IsAuthenticated, IsFeeManager | IsClerkOrPrincipal]

    def get_queryset(self):
        user = self.request.user
        school = getattr(user, "school", None)
        if not school:
            staff = getattr(user, "staff", None)
            if staff and staff.school:
                school = staff.school
        if not school:
            student = getattr(user, "student", None)
            if student and student.school:
                school = student.school

        queryset = FeeWiseClass.objects.filter(
            school=school
        ).select_related("feetype", "school_class")

        feetype = self.request.query_params.get("feetype")
        school_class = self.request.query_params.get("school_class")

        if feetype:
            queryset = queryset.filter(feetype_id=feetype)
        if school_class:
            queryset = queryset.filter(school_class_id=school_class)

        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        school = getattr(user, "school", None)
        if not school:
            staff = getattr(user, "staff", None)
            if staff and staff.school:
                school = staff.school
        serializer.save(school=school)




class SalaryComponentViewSet(ModelViewSet):
    queryset = SalaryComponent.objects.all()
    serializer_class = SalaryComponentSerializer
    permission_classes = [IsAuthenticated, IsFeeManager]

    def get_queryset(self):
        queryset = SalaryComponent.objects.filter(school=self.request.user.school)

        component_type = self.request.query_params.get("component_type")
        is_active = self.request.query_params.get("is_active")

        if component_type:
            queryset = queryset.filter(component_type=component_type)
        if is_active in ["true", "false"]:
            queryset = queryset.filter(is_active=is_active == "true")

        return queryset.order_by("name")

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)

    def destroy(self, request, *args, **kwargs):
        response = super().destroy(request, *args, **kwargs)

        return Response({"message": "Salary Component Deleted Successfully"})

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)

        return Response({"message": "Salary Component Update Successfully"})




class StaffSalaryComponentViewSet(ModelViewSet):
    queryset = StaffSalaryComponent.objects.all()
    serializer_class = StaffSalaryComponentSerializer
    permission_classes = [IsAuthenticated, IsFeeManager]

    def get_queryset(self):
        queryset = StaffSalaryComponent.objects.filter(
            staff__school=self.request.user.school
        ).select_related("staff", "component")

        staff = self.request.query_params.get("staff")
        component_type = self.request.query_params.get("component_type")
        is_active = self.request.query_params.get("is_active")

        if staff:
            queryset = queryset.filter(staff_id=staff)
        if component_type:
            queryset = queryset.filter(component__component_type=component_type)
        if is_active in ["true", "false"]:
            queryset = queryset.filter(is_active=is_active == "true")

        return queryset.order_by("staff__name", "component__name")

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        staff = Staff.objects.filter(id=response.data.get("staff")).first()
        return Response(
            {
                "message": "Salary Component Created Successfully",
                "staff": staff.name,
                "component_type": response.data.get("component_type"),
            }
        )




class StaffSalaryPaymentViewSet(ModelViewSet):
    queryset = StaffSalaryPayment.objects.all()
    serializer_class = StaffSalaryPaymentSerializer
    permission_classes = [IsAuthenticated, IsFeeManager]

    def get_serializer_class(self):
        if self.action == "create":
            return GenerateStaffSalaryPaymentSerializer
        return StaffSalaryPaymentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        response_serializer = StaffSalaryPaymentSerializer(
            payment, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        queryset = StaffSalaryPayment.objects.filter(
            school=self.request.user.school
        ).select_related("staff", "paid_by")

        staff = self.request.query_params.get("staff")
        salary_month = self.request.query_params.get("salary_month")
        payment_mode = self.request.query_params.get("payment_mode")
        payment_status = self.request.query_params.get("payment_status")

        if staff:
            queryset = queryset.filter(staff_id=staff)
        if salary_month:
            queryset = queryset.filter(salary_month=salary_month)
        if payment_mode:
            queryset = queryset.filter(payment_mode=payment_mode)
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)

        return queryset.order_by("-salary_month", "staff__name")




class StudentFeeViewSet(ModelViewSet):
    queryset = StudentFee.objects.all()
    serializer_class = StudentFeeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            StudentFee.objects.filter(school=self.request.user.school)
            .select_related(
                "academic_year",
                "student",
                "student__school_class",
                "feetype",
                "fee_wise_class",
            )
            .prefetch_related("payments")
        )

        student = self.request.query_params.get("student")
        school_class = self.request.query_params.get("school_class")
        academic_year = self.request.query_params.get("academic_year")
        feetype = self.request.query_params.get("feetype")
        status_value = self.request.query_params.get("status")
        billing_period = self.request.query_params.get("billing_period")
        is_rte_govt_claim = self.request.query_params.get("is_rte_govt_claim")
        rte_govt_status = self.request.query_params.get("rte_govt_status")
        is_rte = self.request.query_params.get("is_rte")

        if student:
            queryset = queryset.filter(student_id=student)
        if school_class:
            queryset = queryset.filter(student__school_class_id=school_class)
        if academic_year:
            queryset = queryset.filter(academic_year_id=academic_year)
        if feetype:
            queryset = queryset.filter(feetype_id=feetype)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if billing_period is not None:
            queryset = queryset.filter(billing_period=billing_period)
        if is_rte_govt_claim in ["true", "false"]:
            queryset = queryset.filter(is_rte_govt_claim=is_rte_govt_claim == "true")
        if rte_govt_status:
            queryset = queryset.filter(rte_govt_status=rte_govt_status)
        if is_rte in ["true", "false"]:
            queryset = queryset.filter(student__is_rte=is_rte == "true")

        return queryset.order_by("-created_at")

    def _sync_fee_statuses(self, student_fees):
        # Status and late fees are kept in sync during write operations (payment creation/deletion/updates).
        # Avoid heavy synchronous DB writes on GET requests across remote connections.
        pass

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        student_fees = list(page if page is not None else queryset)

        serializer = self.get_serializer(student_fees, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        save_kwargs = {"school": self.request.user.school}
        validated_due_date = serializer.validated_data.get("due_date")
        if not validated_due_date:
            billing_period = serializer.validated_data.get("billing_period")
            if billing_period and re.match(r"^\d{4}-\d{2}$", billing_period):
                try:
                    y, m = map(int, billing_period.split("-"))
                    save_kwargs["due_date"] = datetime.date(y, m, 10)
                except Exception:
                    pass
        serializer.save(**save_kwargs)




class MyStudentFeeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = Student.objects.filter(user=request.user).first()

        if not student:
            return Response(
                {"error": "Student profile not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        queryset = (
            StudentFee.objects.filter(student=student)
            .select_related(
                "academic_year",
                "student",
                "student__school_class",
                "feetype",
                "fee_wise_class",
            )
            .prefetch_related("payments")
        )

        status_value = request.query_params.get("status")
        academic_year = request.query_params.get("academic_year")
        billing_period = request.query_params.get("billing_period")

        if status_value:
            queryset = queryset.filter(status=status_value)
        if academic_year:
            queryset = queryset.filter(academic_year_id=academic_year)
        if billing_period is not None:
            queryset = queryset.filter(billing_period=billing_period)

        student_fees = list(queryset.order_by("-created_at"))
        serializer = StudentFeeSerializer(
            student_fees,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)




class StudentFeePaymentViewSet(ModelViewSet):
    queryset = StudentFeePayment.objects.all()
    serializer_class = StudentFeePaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        school = getattr(user, "school", None)
        if not school:
            staff = getattr(user, "staff", None)
            if staff and staff.school:
                school = staff.school

        queryset = StudentFeePayment.objects.all().select_related(
            "student_fee",
            "student",
            "student__school_class",
            "feetype",
            "collected_by",
            "verified_by",
        )
        if school:
            queryset = queryset.filter(school=school)

        student_fee = self.request.query_params.get("student_fee")
        student = self.request.query_params.get("student")
        school_class = self.request.query_params.get("school_class")
        feetype = self.request.query_params.get("feetype")
        payment_mode = self.request.query_params.get("payment_mode")
        is_verified = self.request.query_params.get("is_verified")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        receipt_number = self.request.query_params.get("receipt_number")
        payer_type = self.request.query_params.get("payer_type")
        is_rte_govt_claim = self.request.query_params.get("is_rte_govt_claim")

        if student_fee:
            queryset = queryset.filter(student_fee_id=student_fee)
        if student:
            queryset = queryset.filter(student_id=student)
        if school_class:
            queryset = queryset.filter(student__school_class_id=school_class)
        if feetype:
            queryset = queryset.filter(feetype_id=feetype)
        if payer_type:
            queryset = queryset.filter(payer_type=payer_type)
        if is_rte_govt_claim in ["true", "false"]:
            queryset = queryset.filter(student_fee__is_rte_govt_claim=is_rte_govt_claim == "true")
        if payment_mode:
            queryset = queryset.filter(payment_mode=payment_mode)
        if is_verified in ["true", "false"]:
            queryset = queryset.filter(is_verified=is_verified == "true")
        if date_from:
            queryset = queryset.filter(payment_date__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(payment_date__date__lte=date_to)
        if receipt_number:
            clean_rcpt = receipt_number.strip().lstrip("#")
            if clean_rcpt.isdigit():
                queryset = queryset.filter(
                    Q(receipt_number__iexact=receipt_number.strip()) |
                    Q(receipt_number__iexact=clean_rcpt) |
                    Q(id=int(clean_rcpt))
                )
            else:
                queryset = queryset.filter(
                    Q(receipt_number__iexact=receipt_number.strip()) |
                    Q(receipt_number__icontains=clean_rcpt)
                )

        return queryset.order_by("-payment_date", "-created_at")

    def perform_destroy(self, instance):
        student_fee = instance.student_fee
        instance.delete()
        student_fee.refresh_payment_status()

    @action(detail=False, methods=["post"], url_path="bulk-collect")
    def bulk_collect(self, request, *args, **kwargs):
        view = BulkCollectStudentFeePaymentView()
        view.request = request
        view.format_kwarg = kwargs.get("format", None)
        return view.post(request)


class RTESummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Sum
        user = request.user
        school = getattr(user, "school", None)
        if not school:
            staff = getattr(user, "staff", None)
            if staff and staff.school:
                school = staff.school
        if not school:
            return Response({"error": "No school found."}, status=400)

        rte_students = Student.objects.filter(school=school, is_rte=True).select_related("school_class")
        all_students = Student.objects.filter(school=school)
        classes = SchoolClass.objects.filter(school=school)

        class_quota = []
        for c in classes:
            total_in_class = all_students.filter(school_class=c).count()
            rte_in_class = rte_students.filter(school_class=c).count()
            pct = round((rte_in_class / total_in_class * 100), 1) if total_in_class > 0 else 0.0
            class_quota.append({
                "class_id": c.id,
                "class_name": c.school_class,
                "total_students": total_in_class,
                "rte_students": rte_in_class,
                "percentage": pct,
                "compliant": pct >= 25.0,
            })

        # Calculate actual RTE government fee claims
        actual_rte_claims = StudentFee.objects.filter(
            school=school,
            is_rte_govt_claim=True
        ).select_related("student", "feetype", "academic_year")

        total_claims_amount = actual_rte_claims.aggregate(total=Sum("rte_govt_claim_amount"))["total"] or Decimal("0.00")
        total_received_amount = actual_rte_claims.aggregate(total=Sum("rte_govt_paid_amount"))["total"] or Decimal("0.00")
        total_pending_amount = max(Decimal("0.00"), total_claims_amount - total_received_amount)

        claims_list = []
        for fee in actual_rte_claims.order_by("-created_at")[:50]:
            claims_list.append({
                "student_fee_id": fee.id,
                "student_id": fee.student_id,
                "student_name": f"{fee.student.surname or ''} {fee.student.name or ''}".strip(),
                "gr_no": fee.student.gr_no or "",
                "fee_type": fee.feetype.name,
                "billing_period": fee.billing_period,
                "claim_amount": fee.rte_govt_claim_amount,
                "paid_amount": fee.rte_govt_paid_amount,
                "balance_amount": fee.rte_govt_balance_amount,
                "status": fee.rte_govt_status,
                "status_display": fee.get_rte_govt_status_display(),
            })

        student_list = []
        for s in rte_students:
            student_claims = actual_rte_claims.filter(student=s)
            s_claim_total = student_claims.aggregate(total=Sum("rte_govt_claim_amount"))["total"] or Decimal("0.00")
            s_paid_total = student_claims.aggregate(total=Sum("rte_govt_paid_amount"))["total"] or Decimal("0.00")
            student_list.append({
                "id": s.id,
                "name": f"{s.surname or ''} {s.name or ''} {s.father_name or ''}".strip(),
                "gr_no": s.gr_no or "",
                "roll_no": s.roll_no or "",
                "school_class": s.school_class.school_class if s.school_class else "",
                "division": s.division or "",
                "admission_date": str(s.admission_date) if s.admission_date else "",
                "total_govt_claim": s_claim_total,
                "total_govt_received": s_paid_total,
                "claim_status": "Reimbursed" if (s_claim_total > 0 and s_paid_total >= s_claim_total) else "Pending Claim" if s_claim_total > 0 else "Eligible for Submission",
            })

        return Response({
            "school_name": school.name,
            "total_rte_students": len(rte_students),
            "total_students": all_students.count(),
            "overall_rte_percentage": round((len(rte_students) / all_students.count() * 100), 1) if all_students.count() > 0 else 0.0,
            "total_govt_claim_amount": total_claims_amount,
            "total_govt_received_amount": total_received_amount,
            "total_govt_pending_amount": total_pending_amount,
            "class_quota": class_quota,
            "claims": claims_list,
            "students": student_list,
        })


class BulkCollectStudentFeePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        import random
        user = request.user
        school = getattr(user, "school", None)
        if not school:
            staff = getattr(user, "staff", None)
            if staff and staff.school:
                school = staff.school

        items = request.data.get("items", [])
        if not items or not isinstance(items, list):
            return Response({"error": "No fee items provided for collection."}, status=status.HTTP_400_BAD_REQUEST)

        payer_type = request.data.get("payer_type", "student")
        payment_mode = request.data.get("payment_mode", "govt_rte" if payer_type == "government" else "cash")
        payment_date = request.data.get("payment_date") or timezone.now()
        transaction_id = request.data.get("transaction_id", "")
        note = request.data.get("note", "")

        # Generate a single unified receipt number for all items in this transaction
        current_year = timezone.now().year
        timestamp_str = timezone.now().strftime("%Y%m%d%H%M%S")
        rand_suffix = random.randint(1000, 9999)
        shared_receipt_number = f"RCPT-{current_year}-{timestamp_str}-{rand_suffix}"

        created_payments = []
        total_collected = Decimal("0.00")

        for item in items:
            fee_obj = None
            student_fee_id = item.get("student_fee_id") or item.get("id")
            
            # If it's already an existing StudentFee instance ID (integer or numeric string)
            if student_fee_id and str(student_fee_id).isdigit():
                fee_obj = StudentFee.objects.filter(id=int(student_fee_id)).first()
            
            # If it's virtual or not yet created, create the StudentFee
            if not fee_obj:
                student_id = item.get("student")
                fee_wise_class_id = item.get("fee_wise_class")
                billing_period = item.get("billing_period")
                academic_year_id = item.get("academic_year")

                if not student_id or not fee_wise_class_id or not billing_period:
                    continue

                student = Student.objects.filter(id=student_id).first()
                fee_wise_class = FeeWiseClass.objects.filter(id=fee_wise_class_id).first()
                if not student or not fee_wise_class:
                    continue

                academic_year = None
                if academic_year_id and str(academic_year_id) != "0":
                    academic_year = AcademicYear.objects.filter(id=academic_year_id).first()
                if not academic_year:
                    academic_year = (
                        AcademicYear.objects.filter(school=student.school, is_active=True).first()
                        or AcademicYear.objects.filter(school=student.school).first()
                    )

                due_date = item.get("due_date")
                if not due_date:
                    if "-" in str(billing_period) and len(str(billing_period)) == 7:
                        due_date = f"{billing_period}-10"
                    else:
                        due_date = timezone.now().date()

                fee_obj, _ = StudentFee.objects.get_or_create(
                    student=student,
                    academic_year=academic_year,
                    fee_wise_class=fee_wise_class,
                    billing_period=billing_period,
                    defaults={
                        "school": student.school or school,
                        "feetype": fee_wise_class.feetype,
                        "amount": fee_wise_class.amount,
                        "late_fee_enabled": fee_wise_class.late_fee_enabled,
                        "grace_days": fee_wise_class.grace_days,
                        "late_fee_type": fee_wise_class.late_fee_type,
                        "late_fee_amount": fee_wise_class.late_fee_amount,
                        "max_late_fee": fee_wise_class.max_late_fee,
                        "due_date": due_date,
                        "status": "pending",
                    }
                )

            if not fee_obj:
                continue

            fee_obj.apply_late_fee(save=True)
            fee_obj.refresh_payment_status()

            # Determine amount to collect for this item
            item_amount = item.get("amount")
            if payer_type == "government":
                remaining_balance = fee_obj.rte_govt_balance_amount
            else:
                remaining_balance = fee_obj.balance_amount

            if remaining_balance <= Decimal("0.00"):
                continue

            if item_amount is not None and str(item_amount).strip() != "":
                pay_amount = min(Decimal(str(item_amount)), remaining_balance)
            else:
                pay_amount = remaining_balance

            if pay_amount <= Decimal("0.00"):
                continue

            payment = StudentFeePayment.objects.create(
                school=fee_obj.school or school,
                student_fee=fee_obj,
                student=fee_obj.student,
                feetype=fee_obj.feetype,
                payer_type=payer_type,
                amount=pay_amount,
                payment_mode=payment_mode,
                transaction_id=transaction_id or None,
                receipt_number=shared_receipt_number,
                payment_date=payment_date,
                note=note or (f"Fee collection for {fee_obj.feetype.name} ({fee_obj.billing_period})" if fee_obj.feetype else ""),
                collected_by=user if user.is_authenticated else None,
                is_verified=payment_mode != "cheque",
                verified_by=user if (user.is_authenticated and payment_mode != "cheque") else None,
                verified_at=timezone.now() if payment_mode != "cheque" else None,
            )
            fee_obj.refresh_payment_status()
            created_payments.append(payment)
            total_collected += pay_amount

        if not created_payments:
            return Response({
                "error": "No pending fees could be collected. Selected fees may already be paid."
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "success": True,
            "receipt_number": shared_receipt_number,
            "total_amount": str(total_collected),
            "payments_count": len(created_payments),
            "payer_type": payer_type,
            "payment_mode": payment_mode,
            "message": f"Successfully collected {len(created_payments)} fees with receipt {shared_receipt_number}.",
            "payments": StudentFeePaymentSerializer(created_payments, many=True, context={"request": request}).data
        }, status=status.HTTP_201_CREATED)




class StudentFeeRazorpayOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        student_fee_id = request.data.get("student_fee")
        requested_amount = request.data.get("amount")

        try:
            student_fee, payment_school = get_student_fee_for_online_payment(
                request.user, student_fee_id
            )
        except StudentFee.DoesNotExist:
            return Response(
                {"error": "Student fee not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if student_fee.status == "cancelled":
            return Response(
                {"error": "Payment cannot be created for a cancelled fee"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        student_fee.apply_late_fee()

        try:
            amount = (
                Decimal(str(requested_amount))
                if requested_amount
                else student_fee.balance_amount
            )
        except Exception:
            return Response(
                {"error": "Invalid amount"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount <= 0:
            return Response(
                {"error": "Amount must be greater than 0"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount > student_fee.balance_amount:
            return Response(
                {
                    "error": f"Amount cannot be greater than remaining balance {student_fee.balance_amount}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        client_to_use, key_id_to_use, _ = get_school_razorpay(payment_school)
        amount_in_paise = int(amount * 100)
        razor_order = client_to_use.order.create(
            {
                "amount": amount_in_paise,
                "currency": "INR",
                "payment_capture": 1,
                "notes": {
                    "student_fee_id": str(student_fee.id),
                    "student_id": str(student_fee.student_id),
                    "fee_type": student_fee.feetype.name or "",
                },
            }
        )

        payment = StudentFeePayment.objects.create(
            school=payment_school,
            student_fee=student_fee,
            amount=amount,
            payment_mode="online",
            razorpay_order_id=razor_order["id"],
            collected_by=request.user,
            is_verified=False,
        )

        return Response(
            {
                "key": key_id_to_use,
                "order_id": razor_order["id"],
                "amount": razor_order["amount"],
                "currency": razor_order["currency"],
                "student_fee": student_fee.id,
                "payment": payment.id,
                "balance_amount": student_fee.balance_amount,
            },
            status=status.HTTP_201_CREATED,
        )




class StudentFeeRazorpayVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        order_id = request.data.get("razorpay_order_id")
        payment_id = request.data.get("razorpay_payment_id")
        signature = request.data.get("razorpay_signature")

        if not all([order_id, payment_id, signature]):
            return Response(
                {"error": "Missing Razorpay payment parameters"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = get_student_fee_payment_for_online_verify(
                request.user,
                order_id,
            )
        except Exception:
            payment = StudentFeePayment.objects.filter(razorpay_order_id=order_id).first()

        if not payment:
            return Response(
                {"error": "Payment order record not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        school = getattr(payment, "school", None) or getattr(request.user, "school", None)
        _, _, secret_to_use = get_school_razorpay(school)

        message = f"{order_id}|{payment_id}"
        generated_signature = hmac.new(
            secret_to_use.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(generated_signature, signature):
            return Response(
                {"status": "failed", "error": "Invalid payment signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if payment.is_verified:
            return Response(
                {
                    "status": "success",
                    "message": "Payment already verified",
                    "payment": StudentFeePaymentSerializer(payment).data,
                }
            )

        with transaction.atomic():
            payment.razorpay_payment_id = payment_id
            payment.razorpay_signature = signature
            payment.transaction_id = payment_id
            payment.is_verified = True
            payment.verified_by = request.user
            payment.verified_at = timezone.now()
            payment.payment_date = timezone.now()
            if not payment.receipt_number:
                payment.receipt_number = f"RZP-{payment.id}"
            payment.save()
            payment.student_fee.refresh_payment_status()

        return Response(
            {
                "status": "success",
                "payment": StudentFeePaymentSerializer(payment).data,
                "student_fee": StudentFeeSerializer(payment.student_fee).data,
            }
        )




class DueFeesView(APIView):
    permission_classes = [IsAuthenticated, Isparent]

    def get(self, request):

        student_ids = (
            Perents.objects.filter(
                user=request.user
            )
            .values_list(
                "perents_of_id",
                flat=True
            )
        )

        fees = StudentFee.objects.filter(
            student_id__in=student_ids,
            status__in=["pending", "partial"]
        )

        total_due = sum(
            fee.amount - fee.paid_amount
            for fee in fees
        )

        serializer = StudentFeeSerializer(
            fees,
            many=True
        )

        return Response({
            "total_due": total_due,
            "fees": serializer.data
        })
    



class PaymentHistoryView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        student = Student.objects.filter(user=request.user).first()
        if student:
            student_ids = [student.id]
        else:
            student_ids = list(Perents.objects.filter(user=request.user).values_list("perents_of_id", flat=True))

        payment_history = StudentFeePayment.objects.filter(
            student_fee__student_id__in=student_ids
        ).order_by("-payment_date")

        serializer = StudentFeePaymentSerializer(
            payment_history,
            many=True
        )

        return Response(serializer.data)
    


class FeesPaymentView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        student = Student.objects.filter(user=request.user).first()
        if student:
            student_ids = [student.id]
        else:
            student_ids = list(Perents.objects.filter(user=request.user).values_list("perents_of_id", flat=True))

        fees = StudentFee.objects.filter(
            student_id__in=student_ids
        ).order_by("-created_at")   # or "-billing_period"

        serializer = StudentFeeSerializer(fees, many=True)
        return Response(serializer.data)

    def post(self, request):
        fee_id = request.data.get("fee_id")

        student = Student.objects.filter(user=request.user).first()
        if student:
            student_ids = [student.id]
        else:
            student_ids = list(Perents.objects.filter(user=request.user).values_list("perents_of_id", flat=True))

        try:
            fee = StudentFee.objects.get(
                id=fee_id,
                student_id__in=student_ids
            )
        except StudentFee.DoesNotExist:
            return Response(
                {"error": "Fee record not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        amount_due = fee.amount - fee.paid_amount

        if amount_due <= 0:
            return Response(
                {"error": "Fee already paid"},
                status=status.HTTP_400_BAD_REQUEST
            )

        client = razorpay.Client(
            auth=(
                settings.RAZOR_PAY_KEY_ID,
                settings.RAZOR_PAY_SECRET_KEY
            )
        )

        order = client.order.create({
            "amount": int(amount_due * 100),
            "currency": "INR",
        })

        return Response({
            "order_id": order["id"],
            "amount_payable": amount_due,
            "key": settings.RAZOR_PAY_KEY_ID,
        })
    


class VerifypaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        fee_id = request.data.get("fee_id")
        razorpay_order_id = request.data.get("razorpay_order_id")
        razorpay_payment_id = request.data.get("razorpay_payment_id")
        razorpay_signature = request.data.get("razorpay_signature")

        student = Student.objects.filter(user=request.user).first()
        if student:
            student_ids = [student.id]
        else:
            student_ids = list(Perents.objects.filter(user=request.user).values_list("perents_of_id", flat=True))

        try:
            fee = StudentFee.objects.get(
                id=fee_id,
                student_id__in=student_ids
            )
        except StudentFee.DoesNotExist:
            return Response(
                {"error": "Fee record not found"},
                status=404
            )

        client = razorpay.Client(
            auth=(
                settings.RAZOR_PAY_KEY_ID,
                settings.RAZOR_PAY_SECRET_KEY
            )
        )

        if StudentFeePayment.objects.filter(
            razorpay_payment_id=razorpay_payment_id
        ).exists():
            return Response(
                {"error": "Payment already verified"},
                status=400
            )

        try:
            client.utility.verify_payment_signature({
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature
            })

        except Exception as e:
            print("RAZORPAY ERROR:", str(e))

            return Response(
                {"error": str(e)},
                status=400
            )

        amount_due = fee.amount - fee.paid_amount

        with transaction.atomic():

            StudentFeePayment.objects.create(
                student_fee=fee,
                student=fee.student,
                school=fee.school,
                amount=amount_due,
                payment_mode="online",
                transaction_id=razorpay_payment_id,
                razorpay_order_id=razorpay_order_id,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_signature=razorpay_signature,
                payment_date=timezone.now(),
                is_verified=True,
                verified_by=request.user,
                verified_at=timezone.now(),
            )

            fee.paid_amount += amount_due

            if fee.paid_amount >= fee.amount:
                fee.status = "paid"
            elif fee.paid_amount > 0:
                fee.status = "partial"
            else:
                fee.status = "pending"

            fee.save()

        return Response({
            "message": "Payment verified successfully",
            "amount_paid": amount_due,
            "fee_status": fee.status
        })




class BudgetViewset(ModelViewSet):
    queryset=Budget.objects.all()
    serializer_class=BudgetSerializer
    permission_classes=[Isinventory]

    def get_queryset(self):
        return Budget.objects.filter(school=self.request.user.school)
    
    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)




class BudgetExpenseViewset(ModelViewSet):
    queryset=BudgetExpense.objects.all()
    serializer_class=BudgetExpenseSerializer
    permission_classes=[Isinventory]

    def get_queryset(self):
        return BudgetExpense.objects.filter(budget__school=self.request.user.school)
    
    def perform_create(self, serializer):
        serializer.save()


class RTESummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Sum
        user = request.user
        school = getattr(user, "school", None)
        if not school:
            staff = getattr(user, "staff", None)
            if staff and staff.school:
                school = staff.school
        if not school:
            student = getattr(user, "student", None)
            if student and student.school:
                school = student.school

        students_qs = Student.objects.all()
        if school:
            students_qs = students_qs.filter(school=school)

        total_students = students_qs.count()
        rte_students_qs = students_qs.filter(is_rte=True).select_related("school_class")
        total_rte_students = rte_students_qs.count()

        overall_rte_percentage = round((total_rte_students / total_students * 100), 1) if total_students > 0 else 0.0

        classes_qs = SchoolClass.objects.all()
        if school:
            classes_qs = classes_qs.filter(school=school)

        class_quota = []
        for sc in classes_qs:
            c_total = students_qs.filter(school_class=sc).count()
            c_rte = students_qs.filter(school_class=sc, is_rte=True).count()
            c_pct = round((c_rte / c_total * 100), 1) if c_total > 0 else 0.0
            c_name = getattr(getattr(sc, "category", None), "class_name", None) or getattr(sc, "name", str(sc.id))
            class_quota.append({
                "class_id": sc.id,
                "class_name": c_name,
                "total_students": c_total,
                "rte_students": c_rte,
                "percentage": c_pct,
                "compliant": c_pct >= 25.0,
            })

        rte_fees_qs = StudentFee.objects.filter(student__in=rte_students_qs, is_rte_govt_claim=True)
        total_estimated_claim = float(rte_fees_qs.aggregate(total=Sum("rte_govt_claim_amount"))["total"] or 0.0)
        total_reimbursed_claim = float(rte_fees_qs.aggregate(total=Sum("rte_govt_paid_amount"))["total"] or 0.0)
        
        standard_reimbursement_rate = round(total_estimated_claim / total_rte_students, 2) if total_rte_students > 0 and total_estimated_claim > 0 else 5000.00
        if total_estimated_claim == 0 and total_rte_students > 0:
            total_estimated_claim = standard_reimbursement_rate * total_rte_students

        students_list = []
        for st in rte_students_qs:
            st_fees = rte_fees_qs.filter(student=st)
            st_claim = float(st_fees.aggregate(total=Sum("rte_govt_claim_amount"))["total"] or 0.0)
            st_paid = float(st_fees.aggregate(total=Sum("rte_govt_paid_amount"))["total"] or 0.0)
            
            if st_claim == 0:
                st_claim = standard_reimbursement_rate

            if st_paid >= st_claim and st_claim > 0:
                status_label = "Reimbursed"
            elif st_paid > 0:
                status_label = "Partially Reimbursed"
            else:
                status_label = "Government Claim Active"

            sc_obj = getattr(st, "school_class", None)
            c_name = getattr(getattr(sc_obj, "category", None), "class_name", None) or getattr(sc_obj, "name", "N/A") if sc_obj else "N/A"

            students_list.append({
                "id": st.id,
                "name": f"{st.name or ''} {st.surname or ''}".strip() or "Student",
                "gr_no": st.gr_no or f"GR-{st.id}",
                "roll_no": st.roll_no or "-",
                "school_class": c_name,
                "division": getattr(st.school_class, "division", "A") if st.school_class else "A",
                "admission_date": st.created_at.strftime("%Y-%m-%d") if getattr(st, "created_at", None) else "",
                "reimbursement_claim_amount": st_claim,
                "reimbursement_paid_amount": st_paid,
                "claim_status": status_label,
            })

        return Response({
            "school_name": getattr(school, "name", "School") if school else "School",
            "standard_reimbursement_rate": standard_reimbursement_rate,
            "total_rte_students": total_rte_students,
            "total_students": total_students,
            "overall_rte_percentage": overall_rte_percentage,
            "total_estimated_claim": total_estimated_claim,
            "total_reimbursed_claim": total_reimbursed_claim,
            "total_pending_claim": max(0.0, total_estimated_claim - total_reimbursed_claim),
            "class_quota": class_quota,
            "students": students_list,
        })








