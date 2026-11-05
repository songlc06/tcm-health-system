from django.contrib import admin

from .models import Menu, OperationLog


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "group", "perm_codename", "role_scope", "sort_order", "is_active")
    list_filter = ("group", "is_active")
    search_fields = ("code", "name", "perm_codename")


@admin.register(OperationLog)
class OperationLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "username", "role", "category", "action", "target_type", "status_code")
    list_filter = ("category", "status_code")
    search_fields = ("username", "action", "target_repr", "detail", "path")
    date_hierarchy = "created_at"
