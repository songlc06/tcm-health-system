from django.contrib import admin

from .models import Order, OrderItem, OrderStatusHistory, Package, PackageItem


class PackageItemInline(admin.TabularInline):
    model = PackageItem
    extra = 0


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "price", "member_price", "valid_days", "status", "is_recommended")
    list_filter = ("status", "is_recommended")
    inlines = [PackageItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_no", "member", "package", "quantity", "pay_amount", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("order_no", "member__name", "member__phone")
    inlines = [OrderItemInline]


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "from_status", "to_status", "operator", "created_at")
