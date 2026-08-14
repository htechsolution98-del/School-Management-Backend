import hmac
import hashlib
from django.conf import settings
import razorpay
from sms_app.razorpay_client import client
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
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes

class FeeVerifyView(ModelViewSet):
    queryset = Admission.objects.all()
    serializer_class = FeesVerifySerializer
    permission_classes = [IsAuthenticated, IsFeeManager]
    lookup_field = "admission_number"

    def get_queryset(self):
        return Admission.objects.filter(
            pay_process=True, school=self.request.user.school
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
                if admission.form.fee_type == "general":
                    fee_amount = admission.form.fees
                    fee_amount = float(fee_amount)

                else:
                    # Get class field value
                    value_obj = AdmissionFieldValue.objects.filter(
                        admission=admission,
                        field__section__form=admission.form,
                        field__map_to_student_field="school_class",
                    ).first()

                    if not value_obj:
                        return Response(
                            {"error": "School class not found in admission form"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    # Convert class id
                    try:
                        class_id = int(value_obj.value)
                    except (TypeError, ValueError):
                        return Response(
                            {"error": "Invalid class id"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    # Get fee structure
                    fee_structure = AdmissionFeeStructure.objects.filter(
                        admission_form=admission.form,
                        class_name_id=class_id,
                    ).first()

                    if not fee_structure:
                        return Response(
                            {"error": "Fee structure not found"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    # Actual fee amount
                    fee_amount = float(fee_structure.fee_amount)

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
                client_to_use = client
                school = getattr(self.request.user, "school", None) or getattr(admission, "school", None)
                if school:
                    razorpay_data = RazorPayData.objects.filter(school_id=school.id).first()
                    if razorpay_data and razorpay_data.razorpay_key_id and razorpay_data.razorpay_secret_key:
                        client_to_use = razorpay.Client(
                            auth=(
                                razorpay_data.razorpay_key_id,
                                razorpay_data.razorpay_secret_key,
                            )
                        )

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
                        "key": settings.RAZOR_PAY_KEY_ID,
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

        secret = settings.RAZOR_PAY_SECRET_KEY
        message = f"{order_id}|{payment_id}"

        generated_signature = hmac.new(
            secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(generated_signature, signature):
            return Response({"status": "failed"}, status=400)

        try:
            payment = AdmissionFee.objects.get(razorpay_order_id=order_id)
        except AdmissionFee.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

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
    permission_classes = [IsAuthenticated, IsFeeManager]

    def get_queryset(self):
        return FeeType.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        school = self.request.user.school
        serializer.save(school=school)




class FeeWiseClassViewSet(ModelViewSet):
    queryset = FeeWiseClass.objects.all()
    serializer_class = FeeWiseClassSerializer
    permission_classes = [IsAuthenticated, IsFeeManager]

    def get_queryset(self):
        queryset = FeeWiseClass.objects.filter(
            school=self.request.user.school
        ).select_related("feetype", "school_class")

        feetype = self.request.query_params.get("feetype")
        school_class = self.request.query_params.get("school_class")

        if feetype:
            queryset = queryset.filter(feetype_id=feetype)
        if school_class:
            queryset = queryset.filter(school_class_id=school_class)

        return queryset

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)




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

        return queryset.order_by("-created_at")

    def _sync_fee_statuses(self, student_fees):
        for student_fee in student_fees:
            student_fee.apply_late_fee()
            student_fee.refresh_payment_status()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        student_fees = list(page if page is not None else queryset)
        self._sync_fee_statuses(student_fees)

        serializer = self.get_serializer(student_fees, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        self._sync_fee_statuses([instance])
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)




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
        for student_fee in student_fees:
            student_fee.apply_late_fee()
            student_fee.refresh_payment_status()

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
        queryset = StudentFeePayment.objects.filter(
            school=self.request.user.school
        ).select_related(
            "student_fee",
            "student",
            "student__school_class",
            "feetype",
            "collected_by",
            "verified_by",
        )

        student_fee = self.request.query_params.get("student_fee")
        student = self.request.query_params.get("student")
        school_class = self.request.query_params.get("school_class")
        feetype = self.request.query_params.get("feetype")
        payment_mode = self.request.query_params.get("payment_mode")
        is_verified = self.request.query_params.get("is_verified")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        receipt_number = self.request.query_params.get("receipt_number")

        if student_fee:
            queryset = queryset.filter(student_fee_id=student_fee)
        if student:
            queryset = queryset.filter(student_id=student)
        if school_class:
            queryset = queryset.filter(student__school_class_id=school_class)
        if feetype:
            queryset = queryset.filter(feetype_id=feetype)
        if payment_mode:
            queryset = queryset.filter(payment_mode=payment_mode)
        if is_verified in ["true", "false"]:
            queryset = queryset.filter(is_verified=is_verified == "true")
        if date_from:
            queryset = queryset.filter(payment_date__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(payment_date__date__lte=date_to)
        if receipt_number:
            if receipt_number.isdigit():
                queryset = queryset.filter(Q(receipt_number=receipt_number) | Q(id=int(receipt_number)))
            else:
                queryset = queryset.filter(receipt_number=receipt_number)

        return queryset.order_by("-payment_date", "-created_at")

    def perform_destroy(self, instance):
        student_fee = instance.student_fee
        instance.delete()
        student_fee.refresh_payment_status()


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

        amount_in_paise = int(amount * 100)
        razor_order = client.order.create(
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
                "key": settings.RAZOR_PAY_KEY_ID,
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

        message = f"{order_id}|{payment_id}"
        generated_signature = hmac.new(
            settings.RAZOR_PAY_SECRET_KEY.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(generated_signature, signature):
            return Response(
                {"status": "failed", "error": "Invalid payment signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = get_student_fee_payment_for_online_verify(
                request.user,
                order_id,
            )
        except StudentFeePayment.DoesNotExist:
            return Response(
                {"error": "Payment order not found"}, status=status.HTTP_404_NOT_FOUND
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

    permission_classes = [IsAuthenticated, Isparent]
    
    def get(self, request):

        student_ids = Perents.objects.filter(
            user=request.user
        ).values_list(
            "perents_of_id",
            flat=True
        )

        payment_history = StudentFeePayment.objects.filter(
            student_fee__student_id__in=student_ids
        ).order_by("-payment_date")

        serializer = StudentFeePaymentSerializer(
            payment_history,
            many=True
        )

        return Response(serializer.data)
    


class FeesPaymentView(APIView):
    permission_classes = [Isparent]
    
    def get(self, request):
        student_ids = Perents.objects.filter(
            user=request.user
        ).values_list(
            "perents_of_id",
            flat=True
        )

        fees = StudentFee.objects.filter(
            student_id__in=student_ids
        ).order_by("-created_at")   # or "-billing_period"

        serializer = StudentFeeSerializer(fees, many=True)
        return Response(serializer.data)
    def post(self, request):

        fee_id = request.data.get("fee_id")

        student_ids = Perents.objects.filter(
            user=request.user
        ).values_list(
            "perents_of_id",
            flat=True
        )
        print(student_ids)
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
    permission_classes = [IsAuthenticated, Isparent,Isstudent]

    def post(self, request):

        fee_id = request.data.get("fee_id")
        razorpay_order_id = request.data.get("razorpay_order_id")
        razorpay_payment_id = request.data.get("razorpay_payment_id")
        razorpay_signature = request.data.get("razorpay_signature")

        student_ids = Perents.objects.filter(
            user=request.user
        ).values_list(
            "perents_of_id",
            flat=True
        )

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



