# sms_app/routing.py

from django.urls import re_path
from .consumers import EventNotificationConsumer

websocket_urlpatterns = [
    re_path(
        r"ws/notifications/$",
        EventNotificationConsumer.as_asgi(),
    ),
]