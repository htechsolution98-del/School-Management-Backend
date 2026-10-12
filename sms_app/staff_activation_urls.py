from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .staff_activation_views import StaffActivationViewSet

router = DefaultRouter()
router.register('staff-activation', StaffActivationViewSet, basename='staff-activation')
urlpatterns = [path('api/', include(router.urls))]
