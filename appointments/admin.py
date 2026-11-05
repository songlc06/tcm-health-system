from django.contrib import admin

from .models import Appointment, AppointmentAttachment, AppointmentHistory


class AppointmentHistoryInline(admin.TabularInline):
    model = AppointmentHistory
    extra = 0


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("appointment_no", "member", "service", "appoint_date", "appoint_time",
                    "therapist", "status", "exception_level")
    list_filter = ("status", "source", "exception_level", "appoint_date")
    search_fields = ("appointment_no", "member__name", "member__phone")
    date_hierarchy = "appoint_date"
    inlines = [AppointmentHistoryInline]


@admin.register(AppointmentAttachment)
class AppointmentAttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "appointment", "size_kb", "uploaded_by", "created_at")
