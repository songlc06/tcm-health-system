from decimal import Decimal

from django.db import models
from django.urls import reverse
from django.utils import timezone


class Package(models.Model):
    """养生套餐（如 肩颈调理 10 次卡），由多个服务项目组合而成。"""

    STATUS_CHOICES = [("on", "在售"), ("off", "停售")]

    code = models.CharField("套餐编码", max_length=20, unique=True)
    name = models.CharField("套餐名称", max_length=60)
    description = models.TextField("套餐说明", blank=True)
    price = models.DecimalField("套餐原价(元)", max_digits=10, decimal_places=2, default=0)
    member_price = models.DecimalField("会员价(元)", max_digits=10, decimal_places=2, default=0)
    valid_days = models.IntegerField("有效期(天)", default=365)
    status = models.CharField("状态", max_length=10, choices=STATUS_CHOICES, default="on")
    is_recommended = models.BooleanField("推荐套餐", default=False)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "养生套餐"
        verbose_name_plural = "养生套餐"
        ordering = ["-is_recommended", "id"]

    def __str__(self):
        return f"{self.name}({self.code})"

    @property
    def total_times(self):
        return sum(item.times for item in self.items.all())

    @property
    def sale_price(self):
        return self.member_price if self.member_price else self.price


class PackageItem(models.Model):
    """套餐包含的服务项目与次数。"""

    package = models.ForeignKey(Package, verbose_name="套餐", on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey("services.HealthService", verbose_name="服务项目",
                                on_delete=models.PROTECT, related_name="package_items")
    times = models.IntegerField("包含次数", default=1)
    remark = models.CharField("备注", max_length=100, blank=True)

    class Meta:
        verbose_name = "套餐明细"
        verbose_name_plural = "套餐明细"
        unique_together = [("package", "service")]

    def __str__(self):
        return f"{self.package.name}-{self.service.name}x{self.times}"


class Order(models.Model):
    """套餐订单（学生 3 负责的套餐订单管理主体）。"""

    STATUS_CHOICES = [
        ("pending", "待付款"),
        ("paid", "已付款"),
        ("servicing", "服务中"),
        ("completed", "已完成"),
        ("cancelled", "已取消"),
        ("refunded", "已退款"),
    ]
    # 允许的状态流转：当前状态 -> 可流转到的状态
    STATUS_FLOW = {
        "pending": ["paid", "cancelled"],
        "paid": ["servicing", "refunded"],
        "servicing": ["completed", "refunded"],
        "completed": [],
        "cancelled": [],
        "refunded": [],
    }

    order_no = models.CharField("订单号", max_length=24, unique=True, db_index=True)
    member = models.ForeignKey("accounts.Member", verbose_name="会员", on_delete=models.PROTECT,
                               related_name="orders")
    package = models.ForeignKey(Package, verbose_name="套餐", on_delete=models.PROTECT, related_name="orders")
    quantity = models.IntegerField("购买数量", default=1)
    unit_price = models.DecimalField("单价(元)", max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField("明细合计(元)", max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField("优惠金额(元)", max_digits=10, decimal_places=2, default=0)
    pay_amount = models.DecimalField("应付金额(元)", max_digits=12, decimal_places=2, default=0)
    status = models.CharField("订单状态", max_length=20, choices=STATUS_CHOICES, default="pending")
    salesperson = models.ForeignKey("accounts.User", verbose_name="销售顾问", on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="orders")
    remark = models.TextField("订单备注", blank=True)
    cancel_reason = models.CharField("取消/退款原因", max_length=200, blank=True)
    created_at = models.DateTimeField("下单时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    paid_at = models.DateTimeField("付款时间", null=True, blank=True)
    completed_at = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        verbose_name = "套餐订单"
        verbose_name_plural = "套餐订单"
        ordering = ["-created_at"]
        permissions = [
            ("export_order", "导出套餐订单数据"),
            ("change_order_status", "变更订单状态"),
        ]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self):
        return f"{self.order_no} {self.member.name}"

    def get_absolute_url(self):
        return reverse("orders:detail", args=[self.pk])

    def recalc(self, save=True):
        """根据订单明细重算金额：明细合计 - 优惠 = 应付。"""
        total = sum((item.amount for item in self.items.all()), Decimal("0.00"))
        self.total_amount = total
        self.pay_amount = max(total - self.discount_amount, Decimal("0.00"))
        if save:
            self.save(update_fields=["total_amount", "pay_amount", "updated_at"])
        return self.pay_amount

    @property
    def can_change_status(self):
        return bool(self.STATUS_FLOW.get(self.status))

    @property
    def service_total(self):
        return sum(item.times_total for item in self.items.all())

    @property
    def service_used(self):
        return sum(item.times_used for item in self.items.all())


class OrderItem(models.Model):
    """订单明细：记录每项服务的次数、已用次数与金额，可独立维护。"""

    order = models.ForeignKey(Order, verbose_name="所属订单", on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey("services.HealthService", verbose_name="服务项目",
                                on_delete=models.PROTECT, related_name="order_items")
    times_total = models.IntegerField("购买次数", default=1)
    times_used = models.IntegerField("已用次数", default=0)
    unit_price = models.DecimalField("单价(元)", max_digits=10, decimal_places=2, default=0)
    remark = models.CharField("备注", max_length=100, blank=True)

    class Meta:
        verbose_name = "订单明细"
        verbose_name_plural = "订单明细"
        unique_together = [("order", "service")]

    def __str__(self):
        return f"{self.order.order_no}-{self.service.name}"

    @property
    def amount(self):
        return (self.unit_price or Decimal("0.00")) * self.times_total

    @property
    def times_left(self):
        return max(self.times_total - self.times_used, 0)

    @property
    def progress(self):
        if not self.times_total:
            return 0
        return int(self.times_used / self.times_total * 100)


class OrderStatusHistory(models.Model):
    """订单状态流转记录。"""

    order = models.ForeignKey(Order, verbose_name="订单", on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField("原状态", max_length=20, blank=True)
    to_status = models.CharField("新状态", max_length=20)
    operator = models.ForeignKey("accounts.User", verbose_name="操作人", on_delete=models.SET_NULL,
                                 null=True, blank=True)
    note = models.CharField("说明", max_length=200, blank=True)
    created_at = models.DateTimeField("操作时间", default=timezone.now)

    class Meta:
        verbose_name = "订单状态记录"
        verbose_name_plural = "订单状态记录"
        ordering = ["-created_at"]
