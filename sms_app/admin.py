from django.contrib import admin
from .models import *

# Register your models here.

admin.site.register(School)
admin.site.register(CustomUser)
admin.site.register(Staff)
admin.site.register(Feature)
admin.site.register(SchoolFeature)
admin.site.register(LeaveTemplate)
admin.site.register(LeaveRequest)
admin.site.register(LeaveType)
admin.site.register(LeavePerDay)
admin.site.register(StaffRemainingLeave)    