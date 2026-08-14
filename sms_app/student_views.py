from rest_framework.views import APIView
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
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
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action

class AdmissionFormViewSet(ModelViewSet):
    queryset = AdmissionForm.objects.all()
    serializer_class = AdmissionFormSerializer
    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsCLerk()]

    lookup_field = "unique_link"
    # access form via UUID

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return AdmissionFormViewSerializer
        return AdmissionFormSerializer

    def get_queryset(self):
        user = getattr(self.request, "user", None)
        if user and getattr(user, "school", None):
            return AdmissionForm.objects.filter(school=user.school)
        school_id = self.request.query_params.get("school_id")
        school_slug = self.request.query_params.get("school_slug")
        if school_id or school_slug:
            filters = {"is_active": True}
            if school_id:
                filters["school_id"] = school_id
            if school_slug:
                filters["school__slug"] = school_slug
            return AdmissionForm.objects.filter(**filters)
        return AdmissionForm.objects.filter(is_active=True)

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_val = self.kwargs.get(lookup_url_kwarg)
        queryset = self.filter_queryset(self.get_queryset())
        if lookup_val and str(lookup_val).isdigit():
            obj = queryset.filter(id=lookup_val).first()
            if obj:
                self.check_object_permissions(self.request, obj)
                return obj
        return super().get_object()

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()

        return Response(
            {
                "message": "Form created successfully",
            },
            status=status.HTTP_201_CREATED,
        )


# ====this view set for view admission form field====




class FormStatus(ModelViewSet):
    queryset = AdmissionForm.objects.all()
    serializer_class = ChangeFormStatus
    permission_classes = [IsAuthenticated, IsCLerk]
    http_method_names = ["patch"]

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        is_active = request.data.get("is_active")

        with transaction.atomic():
            # If setting this form to active
            if is_active is True or is_active == "true":
                # Make all other forms inactive
                AdmissionForm.objects.exclude(id=instance.id).filter(
                    school=user.school
                ).update(is_active=False)

            # Update current instance
            serializer = self.get_serializer(instance, data=request.data, partial=True)

            serializer.is_valid(raise_exception=True)
            serializer.save()

        return Response(
            {
                "message": "Form Public successfully",
                # "data": serializer.data
            },
            status=status.HTTP_200_OK,
        )


# for send form link


class ManualStudentView(ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = ManualStudentSerializer
    http_method_names = ["post"]

    def perform_create(self, serializer):

        return serializer.save(school=self.request.user.school)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        return Response({"message": "Student Added Successfully"})


from rest_framework import generics




class FormSubmissionViewSet(ModelViewSet):
    queryset = Admission.objects.all()
    permission_classes = [IsClerkOrTempUser]
    serializer_class = AdmissionSubmissionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # def get_serializer_class(self):
    #     if self.action in ['list', 'retrieve']:
    #         return FormSubmissionReadSerializer
    #     return FormSubmissionSerializer

    # def perform_create(self, serializer):
    #     serializer.save(user=self.request.user)




class DocumentSubmissionView(ModelViewSet):
    queryset = AdmissionDocument.objects.all()
    serializer_class = AdmissionDocumentSubmissionSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsClerkOrTempUser]

    def _get_uploaded_documents(self, request):
        data = request.data
        files = request.FILES

        document_fields = (
            data.getlist("document_field")
            if hasattr(data, "getlist")
            else [data.get("document_field")]
        )
        uploaded_files = (
            files.getlist("file")
            if hasattr(files, "getlist")
            else [files.get("file") or data.get("file")]
        )

        # Simple payload, supports one or many repeated keys:
        # document_field=<id>, file=<uploaded file>
        # document_field=<id>, file=<uploaded file>
        if any(value is not None for value in document_fields) or uploaded_files:
            max_count = max(len(document_fields), len(uploaded_files))
            return [
                {
                    "document_field": (
                        document_fields[index] if index < len(document_fields) else None
                    ),
                    "file": (
                        uploaded_files[index] if index < len(uploaded_files) else None
                    ),
                }
                for index in range(max_count)
            ]

        documents = []
        i = 0

        while True:
            document_field = data.get(f"documents[{i}][document_field]") or data.get(
                f"documents.{i}.document_field"
            )
            file = (
                files.get(f"documents[{i}][file]")
                or data.get(f"documents[{i}][file]")
                or files.get(f"documents.{i}.file")
                or data.get(f"documents.{i}.file")
            )

            if document_field is None and file is None:
                break

            documents.append(
                {
                    "document_field": document_field,
                    "file": file,
                }
            )

            i += 1

        return documents

    def create(self, request, *args, **kwargs):
        data = request.data

        documents = self._get_uploaded_documents(request)

        final_data = {
            "admission_number": data.get("admission_number"),
            "documents": documents,
        }

        serializer = self.get_serializer(data=final_data)
        serializer.is_valid(raise_exception=True)

        # SAVE ONLY ONCE
        self.perform_create(serializer)

        admission_number = data.get("admission_number")
        fee_amount = 0

        if admission_number:

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

            if admission.form.fee_type == "general":

                fee_amount = float(admission.form.fees)

            else:

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

                try:
                    class_id = int(value_obj.value)

                except (TypeError, ValueError):
                    return Response(
                        {"error": "Invalid class id"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                fee_structure = AdmissionFeeStructure.objects.filter(
                    admission_form=admission.form,
                    class_name_id=class_id,
                ).first()

                if not fee_structure:
                    return Response(
                        {"error": "Fee structure not found"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                fee_amount = float(fee_structure.fee_amount)

        return Response(
            {
                "message": "Documents uploaded successfully",
                "fee_amount": fee_amount,
                "admission_number": admission_number,
            },
            status=status.HTTP_201_CREATED,
        )


# ==================UPDATE SUBMITED DATA BY CLERK===================


class TempUserAdmissionViewSet(ReadOnlyModelViewSet):
    serializer_class = TempUserAdmissionDataSerializer

    def get_queryset(self):
        return (
            Admission.objects.filter(
                temp_user=self.request.user,
                admission_number__isnull=False,
            )
            .exclude(admission_number="")
            .select_related("school", "form")
            .prefetch_related("field_values__field__section")
        )




class TempUserListViewSet(ReadOnlyModelViewSet):

    serializer_class = TempUserListSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        print("School:", self.request.user.school)

        return TempUser.objects.select_related("user").filter(
            user__school=self.request.user.school
        )

    @action(
        detail=False,
        methods=["post"],
        permission_classes=[IsAuthenticated, IsCLerk],
        url_path="deactivate-all",
    )
    
    def deactivate_all(self, request):
        User.objects.filter(groups__name="temp_user", school=request.user.school).update(is_active=False)
        return Response(
            {"message": "All temp users have been deactivated."},
            status=status.HTTP_200_OK,
        ) 

    @action(
        detail=True,
        methods=["patch"],
        permission_classes=[IsAuthenticated, IsCLerk],
        url_path="activate",
    )
    def activate(self, request, pk=None):
        temp_user = self.get_object()
        is_active = request.data.get("is_active")

        if is_active is None:
            return Response(
                {
                    "message": "Send is_active=true or is_active=false in the request body."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # if str(is_active).lower() in ["true", "1"]:
        #     with transaction.atomic():
        #         User.objects.filter(groups__name="temp_user").exclude(
        #             pk=temp_user.user.pk
        #         ).update(is_active=False)
        #         temp_user.user.is_active = True
        #         temp_user.user.save()

        #     return Response(
        #         {
        #             "message": "Selected temp user activated and all others have been deactivated."
        #         },
        #         status=status.HTTP_200_OK,
        #     )
        
        
        if str(is_active).lower() in ["true", "1"]:
            temp_user.user.is_active = True
            temp_user.user.save()
            return Response(
                {"message": "Selected temp user has been activated."},
                status=status.HTTP_200_OK,
            )   

        if str(is_active).lower() in ["false", "0"]:
            temp_user.user.is_active = False
            temp_user.user.save()
            return Response(
                {"message": "Selected temp user has been deactivated."},
                status=status.HTTP_200_OK,
            )

        return Response(
            {"message": "Invalid is_active value. Use true or false."},
            status=status.HTTP_400_BAD_REQUEST,
        )


# ----------TO GET ADMISSION DATA TO TRUSTEE----------------




class AdmissionReadOnlyViewSet(ReadOnlyModelViewSet):
    serializer_class = GetAdmissionDataSerializer
    permission_classes = [IsAuthenticated, IsClerkOrPrincipal]

    def get_queryset(self):
        user = self.request.user
        return (
            Admission.objects.filter(school=user.school)
            .prefetch_related("field_values", "documents")
        )




class AdmissionReceiptViewSet(ReadOnlyModelViewSet):
    serializer_class = AdmissionReceiptDataSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "admission_number"

    def get_queryset(self):
        return (
            Admission.objects.filter(
                school=self.request.user.school,
                pay_process=True,
            )
            .select_related("form", "temp_user", "school")
            .prefetch_related(
                "field_values__field__section",
                "documents__document_field",
            )
        )


# ======================================================================




class AdmissionUpdateViewSet(ModelViewSet):
    queryset = Admission.objects.all()
    serializer_class = AdmissionUpdateSerializer
    lookup_field = "admission_number"
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        return Admission.objects.filter(school=self.request.user.school)

    def get_serializer_class(self):
        # if self.action in ["update", "partial_update"]:
        return AdmissionUpdateSerializer
        # return admissionViewSerializer

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response(
            {
                "message": "Admission updated successfully",
                "data": response.data,
            },
            status=response.status_code,
        )


# ==================================================================================
# class FormSubmissionReadView(ModelViewSet):
#     queryset = Student.objects.all()
#     serializer_class = FormSubmissionReadSerializer


#  =========update document by clerk after submission=====




class AdmissionDocumentViewSet(ModelViewSet):

    queryset = Admission.objects.all()

    lookup_field = "admission_number"

    permission_classes = [IsAuthenticated, IsCLerk]

    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return Admission.objects.filter(school=self.request.user.school)

    def get_serializer_class(self):

        if self.action in ["update", "partial_update"]:
            return AdmissionDocumentUpdateSerializer

        return AdmissionDocumentUpdateSerializer

    def update(self, request, *args, **kwargs):

        partial = kwargs.pop("partial", False)

        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        self.perform_update(serializer)

        return Response(
            {
                "message": "Admission documents updated successfully",
                "admission_number": instance.admission_number,
            },
            status=status.HTTP_200_OK,
        )

    def partial_update(self, request, *args, **kwargs):

        kwargs["partial"] = True

        return self.update(request, *args, **kwargs)


# ======================================================

import razorpay

# class RazorpayOrderView(APIView):

#     def post(self, request):

#         amount = request.data.get("amount")
#         admission_number = request.data.get("admission_number")

#         # Validation
#         if not amount:
#             return Response(
#                 {"error": "Amount is required"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         if not admission_number:
#             return Response(
#                 {"error": "Admission number is required"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         try:
#             amount = int(amount) * 100
#         except ValueError:
#             return Response(
#                 {"error": "Invalid amount"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         # Save temporary payment record
#         with transaction.atomic():


#             admission = Admission.objects.filter(
#             admission_number=admission_number
#         ).first()

#         if not admission:
#             return Response(
#                 {"error": "Admission not found"},
#                 status=status.HTTP_404_NOT_FOUND,
#             )


#         # Get class field value
#         value_obj = AdmissionFieldValue.objects.filter(
#             admission=admission,
#             field__section__form=admission.form,
#             field__map_to_student_field="school_class"
#         ).first()

#         if not value_obj:
#             raise serializers.ValidationError({
#                 "message": "School class not found in admission form."
#             })

#         try:
#             class_id = int(value_obj.value)
#         except (TypeError, ValueError):
#             raise serializers.ValidationError({
#                 "message": "Invalid class id."
#             })

#         # Get fee structure
#         fee = AdmissionFeeStructure.objects.filter(
#             admission_form=admission.form,
#             class_name_id=class_id
#         ).first()


#         if not fee:
#             raise serializers.ValidationError({
#                 "message": "Fee amount is not valid for this class."
#             })
#         fee  = float(fee.fee_amount)

#         admission.fee_amount = fee
#         admission.save()

#         admission_fee = AdmissionFee.objects.create(
#                 amount=fee,
#                 admission_number=admission_number,
#             )
#         #   ============FOR INDIVIDUAL SCHOOL =============

#         school = self.request.user.school

#         # razorpay_data = RazorPayData.objects.filter(school_id=school.id).first()

#         # if not razorpay_data:
#         #     return Response(
#         #         {"error": "Razorpay configuration not found"},
#         #         status=status.HTTP_400_BAD_REQUEST,
#         #     )

#         # # Create dynamic razorpay client
#         # client = razorpay.Client(
#         #     auth=(
#         #         razorpay_data.razorpay_key_id,
#         #         razorpay_data.razorpay_secret_key,
#         #     )
#         # )
#         # ----------------------------------------------------
#         # Create Razorpay Order
#         # print(fee.fee_amount)
#         razor_order = client.order.create(
#             {
#                 "amount": fee,
#                 "currency": "INR",
#                 "payment_capture": 1,
#             }
#         )

#         # Save order id
#         admission_fee.razorpay_order_id = razor_order["id"]
#         admission_fee.save()

#         return Response(
#             {
#                 "id": razor_order["id"],
#                 "key": settings.RAZOR_PAY_KEY_ID,  # "key": razorpay_data.razorpay_key_id, FOR INDIVIDUAL SCHOOL
#                 "amount": razor_order["amount"],
#                 "currency": "INR",
#                 "admission_number": admission_number,
#             },
#             status=status.HTTP_200_OK,
#         )




class ClerkVerifyView(ModelViewSet):
    queryset = Admission.objects.all()
    serializer_class = ClerkVerifySerializer
    permission_classes = [IsAuthenticated, IsCLerk]
    lookup_field = "admission_number"
    http_method_names = ["patch"]

    def get_queryset(self):
        return Admission.objects.filter(school=self.request.user.school)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response(
            {"message": "Clerk updated successfully"}, status=status.HTTP_200_OK
        )


# class PrincipleVerifyView(ModelViewSet):
#     queryset = Student.objects.all()
#     serializer_class = PrincipleVerifySerializr

#     def get_queryset(self):
#         school = self.request.user.school
#         return Student.objects.filter(clerk_verified=True, school=school)


# ======Fee Verify View =============




class GetStudentView(ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = GetStudentSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        school = self.request.user.school
        queryset = Student.objects.filter(school = school)

        school_class = self.request.query_params.get("school_class")

        if school_class:
            queryset = queryset.filter(school_class=school_class)

        return queryset




