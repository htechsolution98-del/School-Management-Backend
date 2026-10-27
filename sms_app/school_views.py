from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from django.db.models import Q, Count, Sum, ProtectedError
from django.db.models.functions import TruncMonth
from django.utils import timezone
from .models import *
from .serializer import *
from .permissions import *
from .utils import *
from .validators import normalize_mobile
import datetime
from django.core.cache import cache
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from channels.layers import get_channel_layer  # type: ignore
from asgiref.sync import async_to_sync

User = get_user_model()

class FeatureView(ModelViewSet):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerialzer
    http_method_names = ["get", "post", "patch", "delete"]

    def get_permissions(self):
        permissions: list = [IsAuthenticated()]
        if self.action not in ("list", "retrieve"):
            permissions.append(Is_super_admin())
        return permissions

    def list(self, request, *args, **kwargs):
        if not Feature.objects.exists():
            from sms_app.signals import seed_features_and_school_features
            seed_features_and_school_features()
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"message": "Feature created successfully"}, status=201)




class SchoolFeatureView(ModelViewSet):
    queryset = SchoolFeature.objects.all()
    serializer_class = SchoolFeatureSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]

    def perform_create(self, serializer):
        with transaction.atomic():
            instance = serializer.save()
            is_enabled = instance.is_enabled
            school = instance.school
            feature = instance.feature

            if school and feature:
                feature_name = feature.name.strip()
                staff_qs = Staff.objects.filter(school=school, category__iexact=feature_name)
                staff_qs.update(is_active=is_enabled)
                
                user_ids = list(staff_qs.values_list('user_id', flat=True))
                if user_ids:
                    User.objects.filter(id__in=user_ids).update(is_active=is_enabled)




class GetFeatureView(ModelViewSet):
    queryset = SchoolFeature.objects.all()
    serializer_class = GetFeatureSerializer
    permission_classes = [IsAuthenticated]

    http_method_names = ["get"]

    def get_queryset(self):
        user = self.request.user
        school = getattr(user, "school", None)
        if not school:
            school = getattr(user, "managed_school", None)
        if not school:
            school = School.objects.filter(login_id=user.id).first()
        if not school:
            return SchoolFeature.objects.none()

        qs = SchoolFeature.objects.filter(school=school, is_enabled=True, feature__is_active=True)
        if not SchoolFeature.objects.filter(school=school).exists():
            features = Feature.objects.all()
            if features.exists():
                sfs = [SchoolFeature(school=school, feature=f, is_enabled=True) for f in features]
                SchoolFeature.objects.bulk_create(sfs, ignore_conflicts=True)
                qs = SchoolFeature.objects.filter(school=school, is_enabled=True, feature__is_active=True)
        return qs




class ChangeFeatureStatusVIew(ModelViewSet):
    queryset = SchoolFeature.objects.all()
    serializer_class = ChangeFeatureStatusSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]
    http_method_names = ["patch"]
    lookup_field = "id"

    def perform_update(self, serializer):
        with transaction.atomic():
            instance = serializer.save()
            is_enabled = instance.is_enabled
            school = instance.school
            feature = instance.feature

            if school and feature:
                feature_name = feature.name.strip()
                staff_qs = Staff.objects.filter(school=school, category__iexact=feature_name)
                staff_qs.update(is_active=is_enabled)
                
                user_ids = list(staff_qs.values_list('user_id', flat=True))
                if user_ids:
                    User.objects.filter(id__in=user_ids).update(is_active=is_enabled)

                # 🔹 Real-time WebSocket broadcast to all connected dashboards of this school
                try:
                    from channels.layers import get_channel_layer  # type: ignore
                    from asgiref.sync import async_to_sync
                    channel_layer = get_channel_layer()
                    if channel_layer:
                        async_to_sync(channel_layer.group_send)(
                            f"school_{school.id}_choice_all",
                            {
                                "type": "feature_status_changed",
                                "feature_name": feature_name,
                                "is_enabled": is_enabled,
                            },
                        )
                except Exception as e:
                    print("Failed to broadcast feature status event:", e)


from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from django.db import transaction
from django.core.cache import cache
from rest_framework import serializers




class SchoolView(ModelViewSet):
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]

    # ✅ Cache-safe queryset
    def get_queryset(self):
        # cache_key = "school_list"
        # data = cache.get(cache_key)

        qs = School.objects.all().order_by("-created_at")
        # cache.set(cache_key, qs, timeout=300)
        return qs

    # NOTE: keeping School.email / School.phone aligned with the login user is
    # handled by the `sync_school_login_credentials` post_save receiver in
    # signals.py, so every write path stays consistent.

    def perform_create(self, serializer):
        features = serializer.validated_data.pop("feature_ids", [])
        trial_start = serializer.validated_data.pop("trial_start_date", None)
        trial_end = serializer.validated_data.pop("trial_end_date", None)
        pricing_model = serializer.validated_data.pop("pricing_model", "FLAT")
        monthly_p = serializer.validated_data.pop("monthly_price", 0)
        quarterly_p = serializer.validated_data.pop("quarterly_price", 0)
        half_yearly_p = serializer.validated_data.pop("half_yearly_price", 0)
        yearly_p = serializer.validated_data.pop("yearly_price", 0)
        gst_inc = serializer.validated_data.pop("gst_included", False)
        gst_pct = serializer.validated_data.pop("gst_percentage", 18.00)

        name = serializer.validated_data.get("name")
        email = serializer.validated_data.get("email")

        if not email:
            raise serializers.ValidationError("Provide email for school admin user")

        # ✅ Generate unique school code
        school_code = generate_school_code(name)
        while User.objects.filter(username=school_code).exists():
            school_code = generate_school_code(name)

        with transaction.atomic():
            # ✅ Create user (email + mobile are both login identifiers)
            user = User.objects.create(
                username=school_code,
                email=email.strip().lower(),
                mobile=normalize_mobile(serializer.validated_data.get("phone")) or None,
            )
            user.role = "admin(trustee)"  # if custom field exists
            user.set_password("123456")
            user.save()

            # ✅ Assign group
            group, _ = Group.objects.get_or_create(name="admin(trustee)")
            user.groups.add(group)

            # ✅ Create school with generated code
            school = serializer.save(login_id=user, code=school_code)

            # ✅ Bulk create school features
            school_features = [
                SchoolFeature(school=school, feature=feature, is_enabled=True)
                for feature in features
            ]

            SchoolFeature.objects.bulk_create(school_features, ignore_conflicts=True)

            # ✅ Link user to school
            user.school = school  # if field exists
            user.save()

            # 🌟 Create dedicated SubscriptionPlan for this School
            plan_name = f"{school.name} Plan"
            plan, _ = SubscriptionPlan.objects.get_or_create(
                name=plan_name,
                defaults={
                    "description": f"Subscription plan configured for {school.name}",
                    "pricing_model": pricing_model or "FLAT",
                    "monthly_price": monthly_p or 0,
                    "quarterly_price": quarterly_p or 0,
                    "half_yearly_price": half_yearly_p or 0,
                    "yearly_price": yearly_p or 0,
                    "gst_included": gst_inc,
                    "gst_percentage": gst_pct,
                    "trial_available": True,
                    "trial_duration_days": 14,
                    "is_active": True,
                }
            )

            # 🌟 Create SchoolSubscription with trial dates
            today = timezone.now().date()
            s_start = trial_start if trial_start else today
            s_end = trial_end if trial_end else (today + datetime.timedelta(days=14))
            
            SchoolSubscription.objects.create(
                school=school,
                plan=plan,
                plan_type="TRIAL",
                billing_model=pricing_model or "FLAT",
                billing_cycle="MONTHLY",
                flat_amount=monthly_p or 0,
                per_student_rate=monthly_p or 0,
                trial_start_date=s_start,
                trial_end_date=s_end,
                start_date=s_start,
                due_date=s_end,
                status="TRIAL",
                grace_period_days=3,
                auto_lock_on_due=True,
            )

        #  Clear cache after create
        # cache.delete("school_list")

    # 🔹 Update + clear cache
    def perform_update(self, serializer):
        features = serializer.validated_data.pop("feature_ids", None)
        trial_start = serializer.validated_data.pop("trial_start_date", None)
        trial_end = serializer.validated_data.pop("trial_end_date", None)
        pricing_model = serializer.validated_data.pop("pricing_model", None)
        monthly_p = serializer.validated_data.pop("monthly_price", None)
        quarterly_p = serializer.validated_data.pop("quarterly_price", None)
        half_yearly_p = serializer.validated_data.pop("half_yearly_price", None)
        yearly_p = serializer.validated_data.pop("yearly_price", None)
        gst_inc = serializer.validated_data.pop("gst_included", None)
        gst_pct = serializer.validated_data.pop("gst_percentage", None)

        is_being_deactivated = serializer.validated_data.get("is_active") is False
        with transaction.atomic():
            school = serializer.save()

            if features is not None:
                new_feature_ids = set(f.id for f in features)
                all_school_features = SchoolFeature.objects.filter(school=school)
                for sf in all_school_features:
                    should_be_enabled = sf.feature_id in new_feature_ids
                    if sf.is_enabled != should_be_enabled:
                        sf.is_enabled = should_be_enabled
                        sf.save()
                        
                        feat_name = sf.feature.name.strip()
                        staff_qs = Staff.objects.filter(school=school, category__iexact=feat_name)
                        staff_qs.update(is_active=should_be_enabled)
                        user_ids = list(staff_qs.values_list('user_id', flat=True))
                        if user_ids:
                            User.objects.filter(id__in=user_ids).update(is_active=should_be_enabled)

                existing_fids = set(all_school_features.values_list('feature_id', flat=True))
                to_add = new_feature_ids - existing_fids
                if to_add:
                    new_sfs = [SchoolFeature(school=school, feature_id=fid, is_enabled=True) for fid in to_add]
                    SchoolFeature.objects.bulk_create(new_sfs, ignore_conflicts=True)
                    for fid in to_add:
                        f_obj = Feature.objects.filter(id=fid).first()
                        if f_obj:
                            feat_name = f_obj.name.strip()
                            staff_qs = Staff.objects.filter(school=school, category__iexact=feat_name)
                            staff_qs.update(is_active=True)
                            user_ids = list(staff_qs.values_list('user_id', flat=True))
                            if user_ids:
                                User.objects.filter(id__in=user_ids).update(is_active=True)

            # 🌟 Update or create school's Subscription and Plan if pricing/trial fields passed
            sub = SchoolSubscription.objects.filter(school=school).first()
            if sub and sub.plan:
                plan = sub.plan
                if pricing_model: plan.pricing_model = pricing_model
                if monthly_p is not None: plan.monthly_price = monthly_p
                if quarterly_p is not None: plan.quarterly_price = quarterly_p
                if half_yearly_p is not None: plan.half_yearly_price = half_yearly_p
                if yearly_p is not None: plan.yearly_price = yearly_p
                if gst_inc is not None: plan.gst_included = gst_inc
                if gst_pct is not None: plan.gst_percentage = gst_pct
                plan.save()

            if sub:
                if trial_start: sub.trial_start_date = trial_start
                if trial_end:
                    sub.trial_end_date = trial_end
                    sub.due_date = trial_end
                if pricing_model: sub.billing_model = pricing_model
                if monthly_p is not None:
                    sub.flat_amount = monthly_p
                    sub.per_student_rate = monthly_p

                # Sync subscription status with school is_active
                if is_being_deactivated:
                    sub.status = "SUSPENDED"
                elif school.is_active and sub.status == "SUSPENDED":
                    sub.status = "ACTIVE" if sub.plan_type == "PAID" else "TRIAL"

                sub.save()

        cache.delete("school_list")

        # 🔹 Force logout all active users of a deactivated school in real-time
        if is_being_deactivated:
            try:
                from channels.layers import get_channel_layer  # type: ignore
                from asgiref.sync import async_to_sync
                channel_layer = get_channel_layer()
                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f"school_{school.id}_choice_all",
                        {
                            "type": "school_deactivated",
                            "message": "School is deactivated. Contact administrator.",
                        },
                    )
            except Exception as e:
                print("Failed to send school deactivation event:", e)

    # 🔹 Delete + clear cache
    def perform_destroy(self, instance):
        login_user = instance.login_id
        instance.delete()
        if login_user:
            try:
                login_user.delete()
            except Exception:
                pass
        cache.delete("school_list")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
            return Response({"message": "School deleted successfully."}, status=status.HTTP_200_OK)
        except ProtectedError:
            return Response(
                {"error": "Cannot delete school because active records (such as students) are linked to it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"error": f"Failed to delete school: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # 🔹 Custom response
    def create(self, request, *args, **kwargs):
        super().create(request, *args, **kwargs)
        return Response({"message": "School created Successfully"}, status=201)

    # 🔹 Global multi-tenant analytics for Super Admin
    @action(detail=False, methods=["get"], url_path="analytics")
    def analytics(self, request):
        schools_qs = School.objects.all().order_by("-created_at")
        total_schools = schools_qs.count()
        active_schools = schools_qs.filter(is_active=True).count()
        inactive_schools = schools_qs.filter(Q(is_active=False) | Q(is_active__isnull=True)).count()

        # All students
        all_students = Student.objects.all()
        total_students = all_students.count()

        # Boy / Girl student identification
        try:
            boy_student_ids = set(
                StudentFieldValue.objects.filter(
                    Q(field__label__icontains="gender") | Q(field__map_to_student_field__icontains="gender"),
                    Q(value__iexact="Male") | Q(value__iexact="Boy") | Q(value__iexact="Boys") | Q(value__iexact="M")
                ).values_list("student_id", flat=True)
            )
            girl_student_ids = set(
                StudentFieldValue.objects.filter(
                    Q(field__label__icontains="gender") | Q(field__map_to_student_field__icontains="gender"),
                    Q(value__iexact="Female") | Q(value__iexact="Girl") | Q(value__iexact="Girls") | Q(value__iexact="F")
                ).values_list("student_id", flat=True)
            )
        except Exception as e:
            print("Error querying student gender:", e)
            boy_student_ids = set()
            girl_student_ids = set()

        total_boys = len(boy_student_ids)
        total_girls = len(girl_student_ids)
        other_gender = max(total_students - total_boys - total_girls, 0)

        # All staff
        all_staff = Staff.objects.all()
        total_staff = all_staff.count()
        active_staff = all_staff.filter(is_active=True).count()
        teachers_count = all_staff.filter(category__iexact="TEACHER").count()
        non_teaching_count = max(total_staff - teachers_count, 0)

        # Total system modules/features
        total_features = Feature.objects.count()

        # Per school statistics
        school_list = []
        for school in schools_qs:
            sch_students = all_students.filter(school=school)
            sch_student_count = sch_students.count()
            sch_student_ids = set(sch_students.values_list("id", flat=True))

            sch_boys = len(sch_student_ids.intersection(boy_student_ids))
            sch_girls = len(sch_student_ids.intersection(girl_student_ids))
            sch_staff = all_staff.filter(school=school).count()
            sch_active_staff = all_staff.filter(school=school, is_active=True).count()
            sch_features = SchoolFeature.objects.filter(school=school, is_enabled=True).count()

            sch_classes = SchoolClass.objects.filter(school=school).count()
            sch_sub = SchoolSubscription.objects.filter(school=school).first()

            school_list.append({
                "id": school.id,
                "name": school.name or "Unnamed School",
                "code": school.code or "—",
                "email": school.email or "—",
                "phone": school.phone or "—",
                "city": school.city or "—",
                "state": school.state or "—",
                "country": school.country or "India",
                "pincode": school.pincode or "—",
                "is_active": school.is_active is not False,
                "created_at": school.created_at,
                "total_students": sch_student_count,
                "total_boys": sch_boys,
                "total_girls": sch_girls,
                "total_staff": sch_staff,
                "active_staff": sch_active_staff,
                "enabled_features": sch_features,
                "classes_count": sch_classes,
                "subscription_status": sch_sub.status if sch_sub else "NO_PLAN",
                "subscription_plan": sch_sub.plan.name if sch_sub and sch_sub.plan else (sch_sub.plan_type if sch_sub else "NO_PLAN"),
            })

        # Demographics
        rte_count = all_students.filter(is_rte=True).count()
        regular_count = max(total_students - rte_count, 0)

        # Monthly enrollment trends
        enrollment_trend = []
        trend_qs = (
            all_students.filter(admission_date__isnull=False)
            .annotate(month=TruncMonth("admission_date"))
            .values("month")
            .annotate(admissions=Count("id"))
            .order_by("month")
        )
        cum_total = 0
        for entry in trend_qs:
            m_dt = entry.get("month")
            if m_dt:
                adm = entry.get("admissions", 0)
                cum_total += adm
                enrollment_trend.append({
                    "month": m_dt.strftime("%b %Y"),
                    "raw_date": str(m_dt),
                    "admissions": adm,
                    "withdrawals": 0,
                    "total": cum_total,
                })

        # Class distribution
        class_distribution = []
        for c in (
            SchoolClass.objects.annotate(student_count=Count("student"))
            .filter(student_count__gt=0)
            .order_by("-student_count")[:8]
        ):
            class_distribution.append({
                "class_name": c.school_class or "Class",
                "students": c.student_count,
            })

        # Financials
        fee_agg = StudentFee.objects.aggregate(total=Sum("amount"), paid=Sum("paid_amount"))
        total_fees = float(fee_agg.get("total") or 0)
        paid_fees = float(fee_agg.get("paid") or 0)
        pending_fees = max(total_fees - paid_fees, 0)

        active_subs = SchoolSubscription.objects.filter(status="ACTIVE")
        monthly_rev = float(active_subs.aggregate(total=Sum("flat_amount")).get("total") or 0)
        today = timezone.now().date()
        expiring_soon = SchoolSubscription.objects.filter(
            due_date__gte=today,
            due_date__lte=today + datetime.timedelta(days=30),
        ).count()
        expired_count = SchoolSubscription.objects.filter(due_date__lt=today).count()

        financials = {
            "total_student_fees": total_fees,
            "collected_student_fees": paid_fees,
            "pending_student_fees": pending_fees,
            "subscription_monthly_projected": monthly_rev,
            "subscription_annual_projected": monthly_rev * 12,
            "active_subscriptions": active_subs.count(),
            "trial_subscriptions": SchoolSubscription.objects.filter(status="TRIAL").count(),
            "expiring_soon": expiring_soon,
            "expired_overdue": expired_count,
        }

        # Status distribution
        status_distribution = {
            "active": active_schools,
            "inactive": inactive_schools,
            "suspended": SchoolSubscription.objects.filter(status="SUSPENDED").count(),
            "activation_rate": round((active_schools / total_schools * 100), 1) if total_schools > 0 else 0,
        }

        return Response({
            "summary": {
                "total_schools": total_schools,
                "active_schools": active_schools,
                "inactive_schools": inactive_schools,
                "total_students": total_students,
                "total_boys": total_boys,
                "total_girls": total_girls,
                "other_gender": other_gender,
                "rte_students": rte_count,
                "regular_students": regular_count,
                "total_staff": total_staff,
                "active_staff": active_staff,
                "teachers_count": teachers_count,
                "non_teaching_count": non_teaching_count,
                "total_features": total_features,
            },
            "schools": school_list,
            "enrollment_trend": enrollment_trend,
            "class_distribution": class_distribution,
            "financials": financials,
            "status_distribution": status_distribution,
        })

    # 🔹 School specific telemetry & demographics detail
    @action(detail=True, methods=["get"], url_path="details")
    def details(self, request, pk=None):
        school = self.get_object()

        # Students in this school
        sch_students = Student.objects.filter(school=school)
        total_students = sch_students.count()
        rte_students = sch_students.filter(is_rte=True).count()
        student_ids = set(sch_students.values_list("id", flat=True))

        try:
            boy_ids = set(
                StudentFieldValue.objects.filter(
                    student_id__in=student_ids
                ).filter(
                    Q(field__label__icontains="gender") | Q(field__map_to_student_field__icontains="gender")
                ).filter(
                    Q(value__iexact="Male") | Q(value__iexact="Boy") | Q(value__iexact="Boys") | Q(value__iexact="M")
                ).values_list("student_id", flat=True)
            )
            girl_ids = set(
                StudentFieldValue.objects.filter(
                    student_id__in=student_ids
                ).filter(
                    Q(field__label__icontains="gender") | Q(field__map_to_student_field__icontains="gender")
                ).filter(
                    Q(value__iexact="Female") | Q(value__iexact="Girl") | Q(value__iexact="Girls") | Q(value__iexact="F")
                ).values_list("student_id", flat=True)
            )
        except Exception:
            boy_ids = set()
            girl_ids = set()

        total_boys = len(boy_ids)
        total_girls = len(girl_ids)
        other_gender = max(total_students - total_boys - total_girls, 0)

        # Staff in this school
        sch_staff = Staff.objects.filter(school=school)
        total_staff = sch_staff.count()
        active_staff = sch_staff.filter(is_active=True).count()
        teachers_count = sch_staff.filter(category__iexact="TEACHER").count()
        non_teaching_count = max(total_staff - teachers_count, 0)

        staff_list = []
        for st in sch_staff.order_by("-id")[:15]:
            staff_list.append({
                "id": st.id,
                "name": st.name or "Staff Member",
                "email": st.email or "—",
                "mobile": st.mobile or "—",
                "category": st.category or "OTHER",
                "is_active": st.is_active,
            })

        # Classes breakdown
        classes = SchoolClass.objects.filter(school=school)
        class_stats = []
        for c in classes:
            c_studs = sch_students.filter(school_class=c)
            c_stud_ids = set(c_studs.values_list("id", flat=True))
            class_stats.append({
                "id": c.id,
                "name": c.school_class,
                "total_students": c_studs.count(),
                "boys": len(c_stud_ids.intersection(boy_ids)),
                "girls": len(c_stud_ids.intersection(girl_ids)),
            })

        # Students detailed list for filtration in classes view
        student_list = []
        for s in sch_students.select_related("school_class", "academic_year").order_by("school_class__school_class", "roll_no", "name"):
            g_val = "Male" if s.id in boy_ids else ("Female" if s.id in girl_ids else "Other")
            # Avoid repeating surname if father_name already ends with surname
            fn_parts = [s.name]
            if s.father_name:
                fn_parts.append(s.father_name)
            if s.surname:
                if not (s.father_name and s.father_name.strip().lower().endswith(s.surname.strip().lower())):
                    fn_parts.append(s.surname)
            full_name = " ".join(part for part in fn_parts if part).strip() or s.name or "Student"
            student_list.append({
                "id": s.id,
                "name": full_name,
                "first_name": s.name or "",
                "surname": s.surname or "",
                "father_name": s.father_name or "",
                "mother_name": s.mother_name or "",
                "class_id": s.school_class_id,
                "class_name": s.school_class.school_class if s.school_class else "Unassigned",
                "division": s.division or "",
                "roll_no": s.roll_no or "—",
                "gr_no": s.gr_no or "—",
                "gender": g_val,
                "mobile": s.mobile or "—",
                "is_rte": s.is_rte,
                "is_verified": s.is_verified,
                "admission_date": str(s.admission_date) if s.admission_date else None,
                "dob": str(s.date_of_birth) if s.date_of_birth else None,
                "aadhar_number": s.aadhar_number or "—",
            })

        # Features
        features = []
        for sf in SchoolFeature.objects.filter(school=school).select_related('feature'):
            features.append({
                "id": sf.id,
                "feature_id": sf.feature.id,
                "name": sf.feature.name,
                "is_enabled": sf.is_enabled,
            })

        metrics_data = {
            "total_students": total_students,
            "total_boys": total_boys,
            "total_girls": total_girls,
            "other_gender": other_gender,
            "rte_students": rte_students,
            "total_staff": total_staff,
            "active_staff": active_staff,
            "teachers_count": teachers_count,
            "non_teaching_count": non_teaching_count,
            "total_classes": classes.count(),
        }

        fees_data = {
            "total": float(StudentFee.objects.filter(school=school).aggregate(total=Sum("amount")).get("total") or 0),
            "collected": float(StudentFee.objects.filter(school=school).aggregate(paid=Sum("paid_amount")).get("paid") or 0),
            "pending": max(
                float(StudentFee.objects.filter(school=school).aggregate(total=Sum("amount")).get("total") or 0)
                - float(StudentFee.objects.filter(school=school).aggregate(paid=Sum("paid_amount")).get("paid") or 0),
                0,
            ),
        }

        return Response({
            "school": {
                "id": school.id,
                "name": school.name,
                "code": school.code,
                "index_no": school.index_no,
                "email": school.email,
                "phone": school.phone,
                "address": school.address,
                "city": school.city,
                "state": school.state,
                "country": school.country,
                "pincode": school.pincode,
                "logo": school.logo.url if school.logo else None,
                "is_active": school.is_active is not False,
                "created_at": school.created_at,
            },
            "metrics": metrics_data,
            "summary_metrics": metrics_data,
            "classes": class_stats,
            "students": student_list,
            "staff": staff_list,
            "features": features,
            "modules": features,
            "fees": fees_data,
            "fees_summary": fees_data,
        })




class SchoolListView(generics.ListAPIView):
    queryset = School.objects.all()
    serializer_class = SchoolListSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]




def broadcast_announcement(announcement, school=None, user=None):
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            return
        if not school:
            school = announcement.school
        if not user:
            user = announcement.created_by

        author_name = f"{user.first_name} {user.last_name}".strip() if user else "Administration"
        if not author_name and user:
            author_name = user.username or "Administration"

        ws_payload = {
            "type": "announcement_send",
            "id": announcement.id,
            "title": announcement.title,
            "description": announcement.description,
            "announcement_for": announcement.announcement_for or "ALL",
            "is_everyone": announcement.is_everyone,
            "priority": announcement.priority,
            "created_at": announcement.created_at.isoformat() if announcement.created_at else timezone.now().isoformat(),
            "expires_at": announcement.expires_at.isoformat() if announcement.expires_at else None,
            "created_by": user.username if user else "admin",
            "created_by_name": author_name,
            "created_by_role": announcement.created_by_role or "ADMIN",
            "target_class": announcement.target_class_id,
            "target_class_name": getattr(announcement.target_class, "school_class", None) if announcement.target_class else None,
            "target_division": announcement.target_division,
            "target_student": announcement.target_student_id,
            "target_student_name": f"{announcement.target_student.name} {announcement.target_student.surname}".strip() if announcement.target_student else None,
            "target_user": announcement.target_user_id,
            "target_user_name": f"{announcement.target_user.first_name} {announcement.target_user.last_name}".strip() if announcement.target_user else None,
        }

        # If targeted to a specific individual user, ONLY send to that user's private group and creator's group!
        if announcement.target_user_id:
            async_to_sync(channel_layer.group_send)(
                f"school_{school.id}_user_{announcement.target_user_id}",
                ws_payload
            )
            if user and user.id != announcement.target_user_id:
                async_to_sync(channel_layer.group_send)(
                    f"school_{school.id}_user_{user.id}",
                    ws_payload
                )
        elif announcement.target_student_id:
            st = announcement.target_student
            if st and st.user_id:
                async_to_sync(channel_layer.group_send)(
                    f"school_{school.id}_user_{st.user_id}",
                    ws_payload
                )
            if user and (not st or st.user_id != user.id):
                async_to_sync(channel_layer.group_send)(
                    f"school_{school.id}_user_{user.id}",
                    ws_payload
                )
        else:
            # If for everyone, send to choice_all
            if announcement.is_everyone or (announcement.announcement_for or "").upper() == "ALL":
                async_to_sync(channel_layer.group_send)(
                    f"school_{school.id}_choice_all",
                    ws_payload
                )
            elif announcement.announcement_for:
                # Targeted to specific role group(s)
                import re
                roles = [r.strip().upper() for r in announcement.announcement_for.split(",") if r.strip()]
                for r in roles:
                    sanitized = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", r)
                    async_to_sync(channel_layer.group_send)(
                        f"school_{school.id}_choice_{sanitized}",
                        ws_payload
                    )
    except Exception as e:
        print("Failed to broadcast announcement WebSocket message:", e)


class AnnouncementView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id=None):
        # Auto-clean expired announcements
        Announcement.objects.filter(
            expires_at__isnull=False,
            expires_at__lte=timezone.now()
        ).delete()

        school = getattr(request.user, "school", None)
        if not school:
            return Response([], status=status.HTTP_200_OK)

        if id:
            try:
                announcement = Announcement.objects.get(
                    id=id,
                    school=school
                )
            except Announcement.DoesNotExist:
                return Response(
                    {"error": "Announcement not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            serializer = AnnouncementSerializer(announcement, context={"request": request})
            return Response(serializer.data)

        user = request.user
        role = str(getattr(user, "role", "") or "").strip().upper()

        # Management roles see all school announcements, plus direct notifications targeted to them
        is_management = (
            user.is_superuser
            or user.is_staff
            or role in [
                "ADMIN(TRUSTEE)",
                "TRUSTEE",
                "ADMIN",
                "SUPERADMIN",
                "SUPER_ADMIN",
                "PRINCIPAL",
                "VICE PRINCIPAL",
            ]
        )

        if is_management:
            announcements = Announcement.objects.filter(school=school).filter(
                models.Q(target_user__isnull=True) | models.Q(target_user=user) | models.Q(created_by=user)
            )
        elif role == "STUDENT":
            student = Student.objects.filter(user=user, school=school).first()
            base_q = (
                models.Q(target_user__isnull=True)
                & (
                    models.Q(is_everyone=True)
                    | models.Q(announcement_for__iexact="ALL")
                    | models.Q(announcement_for__iexact="STUDENT")
                    | models.Q(announcement_for__icontains="STUDENT")
                    | models.Q(announcement_for__iexact="STUDENTS_PARENTS")
                    | models.Q(announcement_for__iexact="STUDENT_PARENT")
                    | models.Q(announcement_for__isnull=True)
                    | models.Q(announcement_for="")
                )
            )
            if student:
                student_q = (
                    (models.Q(target_student__isnull=True) & models.Q(target_class__isnull=True))
                    | models.Q(target_student=student)
                    | (
                        models.Q(target_class=student.school_class)
                        & (models.Q(target_division__isnull=True) | models.Q(target_division="") | models.Q(target_division__iexact=student.division or ""))
                    )
                )
                announcements = Announcement.objects.filter(school=school).filter(
                    (base_q & student_q) | models.Q(target_user=user)
                )
            else:
                announcements = Announcement.objects.filter(school=school).filter(
                    (base_q & models.Q(target_student__isnull=True)) | models.Q(target_user=user)
                )
        elif role in ["PARENT", "PARENTS"]:
            student = Student.objects.filter(models.Q(user=user) | models.Q(mobile=getattr(user, "mobile", "")), school=school).first()
            base_q = (
                models.Q(target_user__isnull=True)
                & (
                    models.Q(is_everyone=True)
                    | models.Q(announcement_for__iexact="ALL")
                    | models.Q(announcement_for__iexact="PARENT")
                    | models.Q(announcement_for__icontains="PARENT")
                    | models.Q(announcement_for__iexact="STUDENTS_PARENTS")
                    | models.Q(announcement_for__iexact="STUDENT_PARENT")
                    | models.Q(announcement_for__isnull=True)
                    | models.Q(announcement_for="")
                )
            )
            if student:
                student_q = (
                    (models.Q(target_student__isnull=True) & models.Q(target_class__isnull=True))
                    | models.Q(target_student=student)
                    | (
                        models.Q(target_class=student.school_class)
                        & (models.Q(target_division__isnull=True) | models.Q(target_division="") | models.Q(target_division__iexact=student.division or ""))
                    )
                )
                announcements = Announcement.objects.filter(school=school).filter(
                    (base_q & student_q) | models.Q(target_user=user)
                )
            else:
                announcements = Announcement.objects.filter(school=school).filter(
                    (base_q & models.Q(target_student__isnull=True)) | models.Q(target_user=user)
                )
        elif role in ["TRANSPORT", "TRANSPORTATION", "DRIVER"]:
            announcements = Announcement.objects.filter(
                school=school
            ).filter(
                models.Q(target_user=user)
                | (
                    models.Q(target_user__isnull=True)
                    & (
                        models.Q(is_everyone=True)
                        | models.Q(announcement_for__iexact="ALL")
                        | models.Q(announcement_for__iexact="TRANSPORT")
                        | models.Q(announcement_for__icontains="TRANSPORT")
                        | models.Q(announcement_for__isnull=True)
                        | models.Q(announcement_for="")
                    )
                )
            )
        else:
            # Staff roles (Teacher, Clerk, Fee Manager, Librarian, Principal, Trustee, etc.)
            role_token_q = models.Q(announcement_for__iexact=role) | models.Q(announcement_for__icontains=role)
            if role in ["FEES", "FEES MANAGEMENT", "FEE-MANAGER", "FEE_MANAGER", "ACCOUNTANT"]:
                role_target_q = (
                    role_token_q
                    | models.Q(announcement_for__icontains="FEE")
                    | models.Q(announcement_for__icontains="ACCOUNTANT")
                )
            elif role in ["CLERK", "ASSISTANT CLERK", "ASSISTANT_CLERK", "ASSISTANTCLERK"]:
                role_target_q = role_token_q | models.Q(announcement_for__icontains="CLERK")
            elif role == "LIBRARIAN":
                role_target_q = role_token_q | models.Q(announcement_for__icontains="LIBRARIAN")
            elif role == "TEACHER":
                role_target_q = role_token_q | models.Q(announcement_for__icontains="TEACHER")
            elif role in ["PRINCIPAL", "VICE PRINCIPAL"]:
                role_target_q = role_token_q | models.Q(announcement_for__icontains="PRINCIPAL")
            elif role in ["TRUSTEE", "ADMIN(TRUSTEE)", "ADMIN"]:
                role_target_q = role_token_q | models.Q(announcement_for__icontains="TRUSTEE") | models.Q(announcement_for__icontains="ADMIN")
            elif role in ["INVENTORY", "INVENTORY-MANAGER", "INVENTORY_MANAGER", "INVENTORY MANAGER"]:
                role_target_q = role_token_q | models.Q(announcement_for__icontains="INVENTORY")
            else:
                role_target_q = role_token_q

            general_q = (
                models.Q(target_user__isnull=True)
                & (
                    models.Q(is_everyone=True)
                    | models.Q(announcement_for__iexact="ALL")
                    | models.Q(announcement_for__isnull=True)
                    | models.Q(announcement_for="")
                    | role_target_q
                )
            )
            direct_q = models.Q(target_user=user) | models.Q(created_by=user)

            announcements = Announcement.objects.filter(school=school).filter(general_q | direct_q)

        announcements = announcements.order_by("-created_at")
        serializer = AnnouncementSerializer(announcements, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        user = request.user
        role = str(getattr(user, "role", "") or "").strip().upper()

        # Disallow Student, Parent, Transport from creating announcements
        disallowed_roles = ["STUDENT", "PARENT", "PARENTS", "TRANSPORT", "TRANSPORTATION", "DRIVER"]
        if role in disallowed_roles:
            return Response(
                {"error": "You do not have permission to create announcements. Students, parents, and transport staff are view-only."},
                status=status.HTTP_403_FORBIDDEN
            )

        school = getattr(user, "school", None)
        if not school:
            return Response({"error": "User does not belong to any school."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = AnnouncementSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            created_role = role if role else "STAFF"
            announcement = serializer.save(
                school=school,
                created_by=user,
                created_by_role=created_role
            )

            # Broadcast via websocket helper
            broadcast_announcement(announcement, school, user)

            # Record activity log
            try:
                from .activity_logger import log_activity
                log_activity(
                    user=user,
                    action="PUBLISH",
                    module="ANNOUNCEMENTS",
                    title="Announcement Published",
                    description=f"Published announcement: '{announcement.title}' for audience: {announcement.announcement_for or 'ALL'}",
                    school=school,
                    extra_data={"announcement_id": announcement.id, "title": announcement.title, "audience": announcement.announcement_for},
                    request=request,
                )
            except Exception:
                pass

            response_serializer = AnnouncementSerializer(announcement, context={"request": request})
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, id):
        user = request.user
        role = str(getattr(user, "role", "") or "").strip().upper()
        school = getattr(user, "school", None)

        try:
            announcement = Announcement.objects.get(
                id=id,
                school=school
            )
        except Announcement.DoesNotExist:
            return Response(
                {"error": "Announcement not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check permissions: Management or the original creator can edit
        is_management = (
            user.is_superuser
            or user.is_staff
            or role in [
                "ADMIN(TRUSTEE)",
                "TRUSTEE",
                "ADMIN",
                "SUPERADMIN",
                "SUPER_ADMIN",
                "PRINCIPAL",
                "VICE PRINCIPAL",
            ]
        )
        if not is_management and announcement.created_by_id != user.id:
            return Response(
                {"error": "You can only edit announcements created by yourself."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = AnnouncementSerializer(
            announcement,
            data=request.data,
            partial=True,
            context={"request": request}
        )

        if serializer.is_valid():
            updated_announcement = serializer.save()
            return Response(AnnouncementSerializer(updated_announcement, context={"request": request}).data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id):
        user = request.user
        role = str(getattr(user, "role", "") or "").strip().upper()
        school = getattr(user, "school", None)

        try:
            announcement = Announcement.objects.get(
                id=id,
                school=school
            )
        except Announcement.DoesNotExist:
            return Response(
                {"error": "Announcement not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        is_management = (
            user.is_superuser
            or user.is_staff
            or role in [
                "ADMIN(TRUSTEE)",
                "TRUSTEE",
                "ADMIN",
                "SUPERADMIN",
                "SUPER_ADMIN",
                "PRINCIPAL",
                "VICE PRINCIPAL",
            ]
        )
        if not is_management and announcement.created_by_id != user.id:
            return Response(
                {"error": "You can only delete announcements created by yourself."},
                status=status.HTTP_403_FORBIDDEN
            )

        announcement.delete()

        return Response(
            {"message": "Announcement deleted successfully"},
            status=status.HTTP_200_OK
        )


class AnnouncementRecipientsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        school = getattr(user, "school", None)
        if not school:
            return Response([])

        target_role = (request.query_params.get("role") or "").strip().upper()
        search_query = (request.query_params.get("q") or "").strip()
        class_id = request.query_params.get("class_id")
        division = request.query_params.get("division")
        student_id = request.query_params.get("student_id")

        results = []

        if target_role == "STUDENT":
            students_qs = Student.objects.filter(school=school)
            if class_id:
                students_qs = students_qs.filter(school_class_id=class_id)
            if division and division != "ALL":
                students_qs = students_qs.filter(division__iexact=division)
            if student_id:
                students_qs = students_qs.filter(id=student_id)
            if search_query:
                students_qs = students_qs.filter(
                    models.Q(name__icontains=search_query)
                    | models.Q(surname__icontains=search_query)
                    | models.Q(roll_no__icontains=search_query)
                    | models.Q(gr_no__icontains=search_query)
                )
            for s in students_qs.select_related("school_class")[:60]:
                results.append({
                    "id": s.id,
                    "student_id": s.id,
                    "user_id": s.user_id if s.user else None,
                    "name": f"{s.name} {s.surname}".strip(),
                    "role": "STUDENT",
                    "roll_no": s.roll_no or "",
                    "class_name": getattr(s.school_class, "school_class", ""),
                    "division": s.division or "",
                    "details": f"Roll: {s.roll_no or 'N/A'} • Class: {getattr(s.school_class, 'school_class', '')} {s.division or ''}".strip(),
                })
        elif target_role in ["PARENT", "PARENTS"]:
            students_qs = Student.objects.filter(school=school)
            if class_id:
                students_qs = students_qs.filter(school_class_id=class_id)
            if division and division != "ALL":
                students_qs = students_qs.filter(division__iexact=division)
            if student_id:
                students_qs = students_qs.filter(id=student_id)
            if search_query:
                students_qs = students_qs.filter(
                    models.Q(father_name__icontains=search_query)
                    | models.Q(mother_name__icontains=search_query)
                    | models.Q(name__icontains=search_query)
                    | models.Q(surname__icontains=search_query)
                    | models.Q(mobile__icontains=search_query)
                )
            from django.contrib.auth import get_user_model
            UserModel = get_user_model()
            seen_keys = set()
            for s in students_qs.select_related("school_class")[:60]:
                p_name = s.father_name or s.mother_name or f"Parent of {s.name} {s.surname}".strip()
                p_key = f"{s.id}_{s.mobile or ''}"
                if p_key in seen_keys:
                    continue
                seen_keys.add(p_key)

                parent_user = None
                if s.mobile:
                    parent_user = UserModel.objects.filter(school=school, role__icontains="parent").filter(
                        models.Q(mobile=s.mobile) | models.Q(username=s.mobile)
                    ).first()

                results.append({
                    "id": s.id,
                    "student_id": s.id,
                    "user_id": parent_user.id if parent_user else (s.user_id if s.user else None),
                    "name": p_name,
                    "role": "PARENT",
                    "father_name": s.father_name or "",
                    "mother_name": s.mother_name or "",
                    "mobile": s.mobile or "",
                    "student_name": f"{s.name} {s.surname}".strip(),
                    "student_roll": s.roll_no or "",
                    "class_name": getattr(s.school_class, "school_class", ""),
                    "division": s.division or "",
                    "details": f"Ward: {s.name} {s.surname} (Class {getattr(s.school_class, 'school_class', '')} {s.division or ''}) • Ph: {s.mobile or 'N/A'}",
                })
        else:
            from django.contrib.auth import get_user_model
            UserModel = get_user_model()

            staff_members = Staff.objects.filter(school=school, user__isnull=False).select_related("user")
            staff_user_ids = set(staff_members.values_list("user_id", flat=True))
            direct_user_ids = set(UserModel.objects.filter(school=school).values_list("id", flat=True))
            all_uids = staff_user_ids.union(direct_user_ids)

            staff_map = {st.user_id: st for st in staff_members}

            candidate_users = UserModel.objects.filter(id__in=all_uids).exclude(is_superuser=True)
            if search_query:
                sq = search_query.lower()
                matching_uids = []
                for u in candidate_users:
                    st = staff_map.get(u.id)
                    st_name = (st.name or "").lower() if st else ""
                    if (
                        sq in (u.username or "").lower()
                        or sq in (u.first_name or "").lower()
                        or sq in (u.last_name or "").lower()
                        or sq in (u.email or "").lower()
                        or sq in st_name
                    ):
                        matching_uids.append(u.id)
                candidate_users = candidate_users.filter(id__in=matching_uids)

            target_norm = target_role.lower()

            for u in candidate_users[:60]:
                st = staff_map.get(u.id)
                u_role = (u.role or "").lower()
                st_cat = (st.category or "").lower() if st else ""
                st_desig = (st.designation or "").lower() if st else ""

                hit = False
                if not target_role or target_role == "ALL":
                    hit = True
                elif target_role == "CLERK":
                    hit = "clerk" in u_role or "clerk" in st_cat or "clerk" in st_desig
                elif target_role == "TEACHER":
                    hit = "teacher" in u_role or "teacher" in st_cat or "teaching" in st_cat
                elif target_role == "PRINCIPAL":
                    hit = "principal" in u_role or "principal" in st_cat or "principal" in st_desig
                elif target_role == "TRUSTEE":
                    hit = "trustee" in u_role or "admin" in u_role or "trustee" in st_cat
                elif target_role in ["FEE-MANAGER", "FEES", "ACCOUNTANT"]:
                    hit = "fee" in u_role or "accountant" in u_role or "fee" in st_cat or "accountant" in st_cat
                elif target_role == "LIBRARIAN":
                    hit = "librarian" in u_role or "librarian" in st_cat
                elif target_role in ["TRANSPORT", "DRIVER"]:
                    hit = "transport" in u_role or "driver" in u_role or "transport" in st_cat
                elif target_role in ["INVENTORY", "INVENTORY-MANAGER", "INVENTORY_MANAGER"]:
                    hit = "inventory" in u_role or "inventory" in st_cat
                else:
                    hit = target_norm in u_role or target_norm in st_cat

                if hit:
                    user_full_name = f"{u.first_name} {u.last_name}".strip()
                    display_name = user_full_name or (st.name if st else "") or u.username
                    role_label = (st.category if st and st.category else u.role) or target_role
                    results.append({
                        "id": u.id,
                        "user_id": u.id,
                        "name": display_name,
                        "role": role_label.upper(),
                        "details": f"{u.email or u.username} • {role_label.capitalize()}",
                    })

        return Response(results)


class HolidayCalendarView(APIView):
    permission_classes = [IsAuthenticated]

    def _is_manager(self, user):
        role = str(getattr(user, "role", "") or "").upper()
        return bool(
            user.is_superuser
            or user.is_staff
            or role in [
                "ADMIN(TRUSTEE)",
                "TRUSTEE",
                "ADMIN",
                "SUPERADMIN",
                "SUPER_ADMIN",
                "PRINCIPAL",
                "VICE PRINCIPAL",
                "CLERK",
                "ASSISTANT CLERK",
                "ASSISTANT_CLERK",
                "ASSISTANTCLERK",
            ]
        )

    def get(self, request, id=None):
        school = getattr(request.user, "school", None)
        if not school:
            return Response([], status=status.HTTP_200_OK)

        if id:
            try:
                event = Holiday.objects.get(id=id, school=school)
            except Holiday.DoesNotExist:
                return Response({"error": "Event not found"}, status=status.HTTP_404_NOT_FOUND)
            serializer = HolidaySerializer(event, context={"request": request})
            return Response(serializer.data)

        # Auto-seed default holidays if school currently has no holidays
        if Holiday.objects.filter(school=school).count() == 0:
            try:
                from .holiday_defaults import seed_default_school_holidays
                seed_default_school_holidays(school)
            except Exception:
                pass

        queryset = Holiday.objects.filter(school=school)

        # Optional filters
        year = request.query_params.get("year")
        month = request.query_params.get("month")
        event_type = request.query_params.get("event_type")
        is_holiday = request.query_params.get("is_holiday")

        if year:
            queryset = queryset.filter(Q(start_date__year=year) | Q(end_date__year=year))
        if month:
            queryset = queryset.filter(Q(start_date__month=month) | Q(end_date__month=month))
        if event_type:
            if event_type.upper() == "HOLIDAY":
                queryset = queryset.filter(Q(event_type__iexact="HOLIDAY") | Q(is_holiday=True))
            else:
                queryset = queryset.filter(event_type__iexact=event_type)
        if is_holiday is not None:
            val = is_holiday.lower() in ["true", "1"]
            queryset = queryset.filter(is_holiday=val)

        queryset = queryset.order_by("start_date")
        serializer = HolidaySerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        user = request.user
        if not self._is_manager(user):
            return Response(
                {"error": "Permission denied. Only Principal, Clerk, or Trustee can add events & holidays."},
                status=status.HTTP_403_FORBIDDEN
            )

        school = getattr(user, "school", None)
        if not school:
            return Response({"error": "User does not belong to any school."}, status=status.HTTP_400_BAD_REQUEST)

        # If manual reseed action requested
        if request.data.get("action") == "seed_defaults":
            from .holiday_defaults import seed_default_school_holidays
            count = seed_default_school_holidays(school)
            events = Holiday.objects.filter(school=school).order_by("start_date")
            serializer = HolidaySerializer(events, many=True, context={"request": request})
            return Response({"message": f"Successfully seeded {count} public holidays.", "events": serializer.data}, status=status.HTTP_200_OK)

        serializer = HolidaySerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            inst = serializer.save(school=school, created_by=user)

            # Auto-create announcement notification for the scheduled event
            try:
                target_aud = (request.data.get("target_audience") or "ALL").strip()
                is_all = target_aud.upper() in ["ALL", "EVERYONE"]
                event_ann = Announcement.objects.create(
                    school=school,
                    title=f"New {inst.event_type.title()}: {inst.name}",
                    description=(
                        f"{inst.name} is scheduled on {inst.start_date}"
                        + (f" to {inst.end_date}" if inst.end_date and str(inst.end_date) != str(inst.start_date) else "")
                        + (f". Location: {inst.location}" if getattr(inst, "location", None) else "")
                        + (f". {inst.description}" if getattr(inst, "description", None) else "")
                    ).strip(),
                    announcement_for=target_aud if not is_all else "ALL",
                    is_everyone=is_all,
                    priority="IMPORTANT" if inst.is_holiday else "NORMAL",
                    created_by=user,
                    created_by_role=str(getattr(user, "role", "") or "MANAGEMENT").upper(),
                )
                broadcast_announcement(event_ann, school, user)
            except Exception as e:
                print("Failed to broadcast event announcement:", e)

            try:
                from .activity_logger import log_activity
                log_activity(
                    user=user,
                    action="CREATE",
                    module="EVENTS",
                    title=f"Created {inst.event_type.title()}: {inst.name}",
                    description=f"{user.username} scheduled a new {inst.event_type.lower()} from {inst.start_date} to {inst.end_date}",
                    school=school,
                    extra_data={"event_id": inst.id, "name": inst.name, "event_type": inst.event_type},
                    request=request,
                )
            except Exception:
                pass
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, id=None):
        user = request.user
        if not self._is_manager(user):
            return Response(
                {"error": "Permission denied. Only Principal, Clerk, or Trustee can update events & holidays."},
                status=status.HTTP_403_FORBIDDEN
            )

        school = getattr(user, "school", None)
        if not school:
            return Response({"error": "User does not belong to any school."}, status=status.HTTP_400_BAD_REQUEST)

        if not id:
            return Response({"error": "Event ID is required for update."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            event = Holiday.objects.get(id=id, school=school)
        except Holiday.DoesNotExist:
            return Response({"error": "Event not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = HolidaySerializer(event, data=request.data, partial=True, context={"request": request})
        if serializer.is_valid():
            inst = serializer.save()
            try:
                from .activity_logger import log_activity
                log_activity(
                    user=user,
                    action="UPDATE",
                    module="EVENTS",
                    title=f"Updated {inst.event_type.title()}: {inst.name}",
                    description=f"{user.username} modified {inst.name}",
                    school=school,
                    extra_data={"event_id": inst.id, "name": inst.name},
                    request=request,
                )
            except Exception:
                pass
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id=None):
        user = request.user
        if not self._is_manager(user):
            return Response(
                {"error": "Permission denied. Only Principal, Clerk, or Trustee can delete events & holidays."},
                status=status.HTTP_403_FORBIDDEN
            )

        school = getattr(user, "school", None)
        if not school:
            return Response({"error": "User does not belong to any school."}, status=status.HTTP_400_BAD_REQUEST)

        if not id:
            return Response({"error": "Event ID is required for deletion."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            event = Holiday.objects.get(id=id, school=school)
        except Holiday.DoesNotExist:
            return Response({"error": "Event not found"}, status=status.HTTP_404_NOT_FOUND)

        event_name = event.name
        event.delete()
        try:
            from .activity_logger import log_activity
            log_activity(
                user=user,
                action="DELETE",
                module="EVENTS",
                title=f"Deleted Event/Holiday: {event_name}",
                description=f"{user.username} removed event/holiday '{event_name}'",
                school=school,
                extra_data={"name": event_name},
                request=request,
            )
        except Exception:
            pass
        return Response({"message": "Event deleted successfully"}, status=status.HTTP_200_OK)

        


from rest_framework_simplejwt.views import TokenRefreshView
from django.conf import settings



