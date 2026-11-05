from django.contrib import admin

from .models import HealthService, ServiceCategory, ServicePriceHistory


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "sort_order", "is_active")


@admin.register(HealthService)
class HealthServiceAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "duration", "price", "member_price", "status", "is_hot")
    list_filter = ("status", "is_hot", "category")
    search_fields = ("code", "name", "summary")


@admin.register(ServicePriceHistory)
class ServicePriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("service", "old_price", "new_price", "changed_by", "changed_at")
