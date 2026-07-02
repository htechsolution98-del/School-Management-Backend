from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json
from .models import Student,Perents


class EventNotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]

        if self.user.is_anonymous:
            await self.close()
            return

        self.group_names = await self.get_parent_groups()

        if not self.group_names:
            await self.close()
            return

        for group_name in self.group_names:
            await self.channel_layer.group_add(
                group_name,
                self.channel_name
            )

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_names"):
            for group_name in self.group_names:
                await self.channel_layer.group_discard(
                    group_name,
                    self.channel_name
                )

    async def send_notification(self, event):
        await self.send(
            text_data=json.dumps({
                "notification_id": event.get("notification_id"),
                "title": event.get("title"),
                "message": event.get("message"),
            })
        )

    @database_sync_to_async
    def get_parent_groups(self):

        groups = []

        parent_records = (
            Perents.objects
            .select_related("perents_of")
            .filter(user=self.user)
        )

        for parent in parent_records:
            student = parent.perents_of

            if student.school_id and student.school_class_id:
                groups.append(
                    f"school_{student.school_id}_class_{student.school_class_id}_parents"
                )

        return list(set(groups))


        
class AttendanceNotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        print("connected")
        self.user = self.scope["user"]
        print("User",self.user)
        if self.user.is_anonymous:
            print("Anonymous user")
            await self.close()
            return

        self.group_names = await self.get_groups()
        print("GROUPS:", self.group_names)
        if not self.group_names:
            await self.close()
            return

        for group_name in self.group_names:
            await self.channel_layer.group_add(
                group_name,
                self.channel_name
            )
            print("Connected to:", group_name)

        await self.accept()
        print("Connection accepted")

    async def disconnect(self, close_code):

        if hasattr(self, "group_names"):

            for group_name in self.group_names:

                await self.channel_layer.group_discard(
                    group_name,
                    self.channel_name
                )

    async def attendance_message(self, event):

        await self.send(
            text_data=json.dumps({
                "title": event["title"],
                "message": event["message"],
            })
        )

    @database_sync_to_async
    def get_groups(self):

        parent_records = (
            Perents.objects.filter(
                user=self.user
            )
        )

        groups = []

        for parent in parent_records:

            groups.append(
                f"school_{parent.school_id}_student_{parent.perents_of_id}_attendance"
            )

        return groups
    



class ProgressReportNotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]

        if self.user.is_anonymous:
            await self.close()
            return

        groups = await self.get_groups()

        if not groups:
            await self.close()
            return

        self.group_names = groups

        for group_name in self.group_names:
            await self.channel_layer.group_add(
                group_name,
                self.channel_name
            )
            print("Connected to:", group_name)

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_names"):
            for group_name in self.group_names:
                await self.channel_layer.group_discard(
                    group_name,
                    self.channel_name
                )

    async def progressreport_message(self, event):
        await self.send(
            text_data=json.dumps({
                "student": event["student"],
                "month": event["month"],
                "year": event["year"],
                "attendance_percentage": event["attendance_percentage"],
                "overall_score": event["overall_score"],
                "grade": event["grade"],
                "discipline": event["discipline"],
                "communication_skills": event["communication_skills"],
                "emotional_development": event["emotional_development"],
                "social_development": event["social_development"],
                "freindly_with_others": event["freindly_with_others"],
                "remark": event["remark"],
            })
        )

    @database_sync_to_async
    def get_groups(self):

        parent_records = Perents.objects.filter(
            user=self.user
        ).select_related("perents_of")

        groups = []

        for parent in parent_records:
            student = parent.perents_of

            groups.append(
                f"school_{student.school_id}_student_{student.id}_progress-report"
            )

        return groups
    
class StudyMaterialConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.user = self.scope["user"]
        print("user:",self.user)
       
        if self.user.is_anonymous:
            print("anonymous user")
            await self.close()
            return

        group = await self.get_groups()
        print(group)

        if not group:
            await self.close()
            return

        self.group_name = group

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        print("after accept")

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def studymaterial(self, event):
        await self.send(
            text_data=json.dumps({
                "subject": event.get("subject"),
                "student_class": event.get("student_class"),
                "material_type": event.get("material_type"),
                "title": event.get("title"),
                "description": event.get("description"),
                "file": event.get("file"),
            })
        )

    @database_sync_to_async
    def get_groups(self):
        try:
            student = Student.objects.get(user=self.user)
            print(student)

            return f"student_{student.school_id}_class_{student.school_class_id}"

        except Student.DoesNotExist:
            return None
    


