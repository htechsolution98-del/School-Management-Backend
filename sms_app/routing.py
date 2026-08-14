# sms_app/routing.py

from django.urls import re_path
from .consumers import EventNotificationConsumer,AttendanceNotificationConsumer,ProgressReportNotificationConsumer,StudyMaterialConsumer,AnnouncementConsumer

websocket_urlpatterns = [
    re_path(r"^(?:api/)?ws/notifications/$", EventNotificationConsumer.as_asgi()),
    re_path(r"^(?:api/)?ws/attendance/$", AttendanceNotificationConsumer.as_asgi()),
    re_path(r"^(?:api/)?ws/progress-report/$", ProgressReportNotificationConsumer.as_asgi()),
    re_path(r"^(?:api/)?ws/study-material/$", StudyMaterialConsumer.as_asgi()),
    re_path(r"^(?:api/)?ws/announcement/$", AnnouncementConsumer.as_asgi()),
]