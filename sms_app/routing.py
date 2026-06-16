# sms_app/routing.py

from django.urls import re_path
from .consumers import EventNotificationConsumer,AttendanceNotificationConsumer,ProgressReportNotificationConsumer

websocket_urlpatterns = [
    re_path(r"ws/notifications/$",EventNotificationConsumer.as_asgi()),
    re_path(r"ws/attendance/$", AttendanceNotificationConsumer.as_asgi()),
    re_path(r"ws/progress-report/$", ProgressReportNotificationConsumer.as_asgi()),
]