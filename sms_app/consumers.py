from channels.generic.websocket import AsyncWebsocketConsumer
import json


class EventNotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]

        if self.user.is_anonymous:
            await self.close()
            return

        school_id = self.user.parent_profile.school.id

        self.group_name = f"school_{school_id}_parents"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def send_notification(self, event):
        await self.send(
            text_data=json.dumps({
                "title": event["title"],
                "message": event["message"],
                "notification_id": event.get("notification_id"),
                # "type": event.get("notification_type"),
            })
        )