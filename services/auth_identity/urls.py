from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sms_app.auth_views import CustomLoginView, CookieTokenRefreshView, ModuleView, InitDatabaseView
from rest_framework_simplejwt.views import TokenObtainPairView

router = DefaultRouter()
router.register(r"getmodule", ModuleView, basename="getmodule")

urlpatterns = [
    path("api/access/", CustomLoginView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("api/refresh/", CookieTokenRefreshView.as_view(), name="token_refresh_cookie"),
    path("api/init-database/", InitDatabaseView.as_view(), name="init_database"),
    path("api/v1/auth/", include(router.urls)),
]
