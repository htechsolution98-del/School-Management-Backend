from django.contrib import admin
from .models import *
admin.site.register(LeaveTemplate)
admin.site.register(LeaveRequest)
admin.site.register(LeavePerDay)
admin.site.register(StaffRemainingLeave)
admin.site.register(Staff)
admin.site.register(School)
admin.site.register(CustomUser)
# Register your models here.
