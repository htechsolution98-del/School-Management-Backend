from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from django.db.models import Q, Count
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
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()

class FeatureView(ModelViewSet):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerialzer
    http_method_names = ["get", "post", "delete"]

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

        # If no school features recorded yet at all, initialize them
        if not SchoolFeature.objects.filter(school=school).exists():
            features = Feature.objects.all()
            if features.exists():
                sfs = [SchoolFeature(school=school, feature=f, is_enabled=True) for f in features]
                SchoolFeature.objects.bulk_create(sfs, ignore_conflicts=True)

        return SchoolFeature.objects.filter(school=school, is_enabled=True)




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
                    from channels.layers import get_channel_layer
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

    def perform_create(self, serializer):
        features = serializer.validated_data.pop("feature_ids", [])
        name = serializer.validated_data.get("name")
        email = serializer.validated_data.get("email")

        if not email:
            raise serializers.ValidationError("Provide email for school admin user")

        # ✅ Generate unique school code
        school_code = generate_school_code(name)
        while User.objects.filter(username=school_code).exists():
            school_code = generate_school_code(name)

        with transaction.atomic():
            # ✅ Create user
            user = User.objects.create(username=school_code, email=email)
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
        #  Clear cache after create
        # cache.delete("school_list")

    # 🔹 Update + clear cache
    def perform_update(self, serializer):
        features = serializer.validated_data.pop("feature_ids", None)
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


        cache.delete("school_list")

        # 🔹 Force logout all active users of a deactivated school in real-time
        if is_being_deactivated:
            try:
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                channel_layer = get_channel_layer()
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
        instance.delete()
        cache.delete("school_list")

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
            })

        return Response({
            "summary": {
                "total_schools": total_schools,
                "active_schools": active_schools,
                "inactive_schools": inactive_schools,
                "total_students": total_students,
                "total_boys": total_boys,
                "total_girls": total_girls,
                "other_gender": other_gender,
                "total_staff": total_staff,
                "active_staff": active_staff,
                "teachers_count": teachers_count,
                "non_teaching_count": non_teaching_count,
                "total_features": total_features,
            },
            "schools": school_list,
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
                    student_id__in=student_ids,
                    field__label__icontains="gender",
                ).filter(
                    Q(value__iexact="Male") | Q(value__iexact="Boy") | Q(value__iexact="Boys") | Q(value__iexact="M")
                ).values_list("student_id", flat=True)
            )
            girl_ids = set(
                StudentFieldValue.objects.filter(
                    student_id__in=student_ids,
                    field__label__icontains="gender",
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

        # Features
        features = []
        for sf in SchoolFeature.objects.filter(school=school).select_related('feature'):
            features.append({
                "id": sf.id,
                "feature_id": sf.feature.id,
                "name": sf.feature.name,
                "is_enabled": sf.is_enabled,
            })

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
            "metrics": {
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
            },
            "classes": class_stats,
            "staff": staff_list,
            "features": features,
        })




class SchoolListView(generics.ListAPIView):
    queryset = School.objects.all()
    serializer_class = SchoolListSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]




class AnnouncementView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, id=None):
        Announcement.objects.filter(
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

            serializer = AnnouncementSerializer(announcement)
            return Response(serializer.data)
       
        announcements = Announcement.objects.filter(
            school=school
        ).order_by("-created_at")

        serializer = AnnouncementSerializer(announcements, many=True)
        return Response(serializer.data)
    def post(self,request):
        school=request.user.school
        serializer=AnnouncementSerializer(data=request.data)
        print("Before valid")
        if serializer.is_valid():
            print("yes valid")
            announcement=serializer.save(
                school=school
                
                 )
            print(AnnouncementSerializer().fields.keys())
            if announcement.is_everyone:
                group_name = f"school_{school.id}_choice_all"
            else:
                group_name = f"school_{school.id}_choice_{announcement.announcement_for}"



            channel_layer=get_channel_layer()
            
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type":"announcement_send",
                    "title":announcement.title,
                    "description":announcement.description
                    
                }
            )
            return Response(serializer.data,status=200)
        return Response(serializer.errors,status=400)
    def put(self, request, id):
        try:
            announcement = Announcement.objects.get(
                id=id,
                school=request.user.school
            )
        except Announcement.DoesNotExist:
            return Response(
                {"error": "Announcement not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer =AnnouncementSerializer(
            announcement,
            data=request.data,
            partial=False
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id):
        try:
            announcement = Announcement.objects.get(
                id=id,
                school=request.user.school
            )
        except Announcement.DoesNotExist:
            return Response(
                {"error": "Announcement not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        announcement.delete()

        return Response(
            {"message": "Announcement deleted successfully"},
            status=status.HTTP_204_NO_CONTENT
        )

        


from rest_framework_simplejwt.views import TokenRefreshView
from django.conf import settings



