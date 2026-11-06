# sms_app/routing.py

from typing import Any, cast
from django.urls import re_path
from .consumers import (
    EventNotificationConsumer,
    AttendanceNotificationConsumer,
    ProgressReportNotificationConsumer,
    StudyMaterialConsumer,
    AnnouncementConsumer,
    LeaveConsumer,
)

# Cast ASGI application instances to Any to satisfy Django URL routing type definitions
websocket_urlpatterns = [
    re_path(r"^(?:api/)?ws/notifications/$", cast(Any, EventNotificationConsumer.as_asgi())),
    re_path(r"^(?:api/)?ws/attendance/$", cast(Any, AttendanceNotificationConsumer.as_asgi())),
    re_path(r"^(?:api/)?ws/progress-report/$", cast(Any, ProgressReportNotificationConsumer.as_asgi())),
    re_path(r"^(?:api/)?ws/study-material/$", cast(Any, StudyMaterialConsumer.as_asgi())),
    re_path(r"^(?:api/)?ws/announcement/$", cast(Any, AnnouncementConsumer.as_asgi())),
    re_path(r"^(?:api/)?ws/leaves/$", cast(Any, LeaveConsumer.as_asgi())),
]
