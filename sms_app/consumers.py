from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json


class EventNotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]

        if self.user.is_anonymous:
            await self.close()
            return

        school_id = await self.get_school_id()

        if not school_id:
            await self.close()
            return

        self.group_name = f"school_{school_id}_parents"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def send_notification(self, event):
        await self.send(text_data=json.dumps({
            "title": event.get("title"),
            "message": event.get("message"),
            "notification_id": event.get("notification_id"),
        }))

    @database_sync_to_async
    def get_school_id(self):
        """
        Safe way to fetch school id for BOTH parent and teacher
        """
        user = self.user

        # If parent login
        if hasattr(user, "parent_profile"):
            return user.parent_profile.school.id

        # If staff/teacher login
        if hasattr(user, "staff"):
            return user.staff.school.id

        return None