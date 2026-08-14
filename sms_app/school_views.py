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
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()

class FeatureView(ModelViewSet):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerialzer
    # permission_classes = [IsAuthenticated, Is_super_admin]

    http_method_names = ["get", "post", "delete"]

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"message": "Feature created successfully"}, status=201)




class SchoolFeatureView(ModelViewSet):
    queryset = SchoolFeature.objects.all()
    serializer_class = SchoolFeatureSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]




class GetFeatureView(ModelViewSet):
    queryset = SchoolFeature.objects.all()
    serializer_class = GetFeatureSerializer
    permission_classes = [IsAuthenticated]

    http_method_names = ["get"]

    def get_queryset(self):
        school = getattr(self.request.user, "school", None)
        if not school:
            return SchoolFeature.objects.none()

        qs = SchoolFeature.objects.filter(school=school, is_enabled=True)
        if not qs.exists():
            features = Feature.objects.all()
            if features.exists():
                sfs = [SchoolFeature(school=school, feature=f, is_enabled=True) for f in features]
                SchoolFeature.objects.bulk_create(sfs, ignore_conflicts=True)
                qs = SchoolFeature.objects.filter(school=school, is_enabled=True)
        return qs




class ChangeFeatureStatusVIew(ModelViewSet):
    queryset = SchoolFeature.objects.all()
    serializer_class = ChangeFeatureStatusSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]
    http_method_names = ["patch"]
    lookup_field = "id"


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
                existing_feature_ids = set(SchoolFeature.objects.filter(school=school).values_list('feature_id', flat=True))
                new_feature_ids = set(f.id for f in features)
                
                # Delete removed features
                to_delete = existing_feature_ids - new_feature_ids
                if to_delete:
                    SchoolFeature.objects.filter(school=school, feature_id__in=to_delete).delete()
                
                # Add new features
                to_add = new_feature_ids - existing_feature_ids
                if to_add:
                    new_sfs = [SchoolFeature(school=school, feature_id=fid, is_enabled=True) for fid in to_add]
                    SchoolFeature.objects.bulk_create(new_sfs, ignore_conflicts=True)


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



