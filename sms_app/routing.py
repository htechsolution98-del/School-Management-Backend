# sms_app/routing.py

from django.urls import re_path
from .consumers import EventNotificationConsumer,AttendanceNotificationConsumer

websocket_urlpatterns = [
    re_path(r"ws/notifications/$",EventNotificationConsumer.as_asgi()),
    re_path(r"ws/attendance/$", AttendanceNotificationConsumer.as_asgi()),

]