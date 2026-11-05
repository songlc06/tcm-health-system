"""后台管理注册（便于教师核对数据，权限与前台一致）。"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Member, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "display_name", "role", "is_active", "is_staff", "date_joined")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("username", "display_name", "phone")
    fieldsets = UserAdmin.fieldsets + (
        ("业务信息", {"fields": ("role", "display_name", "phone", "last_login_ip")}),
    )


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("member_no", "name", "gender", "phone", "level", "points", "join_date", "is_active")
    list_filter = ("level", "is_active", "gender")
    search_fields = ("member_no", "name", "phone", "tags")
    readonly_fields = ("member_no", "created_at", "updated_at")
