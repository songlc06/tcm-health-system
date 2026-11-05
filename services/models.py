from django.db import models
from django.urls import reverse
from django.utils import timezone


class ServiceCategory(models.Model):
    """养生服务分类，如 针灸推拿、艾灸理疗、中药调理。"""

    name = models.CharField("分类名称", max_length=40, unique=True)
    code = models.CharField("分类编码", max_length=20, unique=True)
    description = models.CharField("分类说明", max_length=200, blank=True)
    sort_order = models.IntegerField("排序", default=0)
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        verbose_name = "服务分类"
        verbose_name_plural = "服务分类"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class HealthService(models.Model):
    """养生服务项目（学生 2 负责的养生服务管理主体）。"""

    STATUS_CHOICES = [("on", "上架"), ("off", "下架")]

    code = models.CharField("服务编码", max_length=20, unique=True, db_index=True)
    name = models.CharField("服务名称", max_length=60)
    category = models.ForeignKey(
        ServiceCategory, verbose_name="所属分类", on_delete=models.PROTECT, related_name="services"
    )
    summary = models.CharField("服务简介", max_length=200, blank=True)
    description = models.TextField("服务详情", blank=True)
    duration = models.IntegerField("服务时长(分钟)", default=60)
    price = models.DecimalField("标准价(元)", max_digits=10, decimal_places=2, default=0)
    member_price = models.DecimalField("会员价(元)", max_digits=10, decimal_places=2, default=0)
    suitable_for = models.CharField("适宜人群", max_length=200, blank=True)
    contraindication = models.CharField("禁忌说明", max_length=200, blank=True)
    status = models.CharField("状态", max_length=10, choices=STATUS_CHOICES, default="on")
    is_hot = models.BooleanField("热门推荐", default=False)
    sort_order = models.IntegerField("排序", default=0)
    created_by = models.ForeignKey(
        "accounts.User", verbose_name="创建人", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_services",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "养生服务"
        verbose_name_plural = "养生服务"
        ordering = ["sort_order", "-created_at"]
        permissions = [("export_healthservice", "导出养生服务数据")]
        indexes = [models.Index(fields=["status", "category"])]

    def __str__(self):
        return f"{self.name}({self.code})"

    def get_absolute_url(self):
        return reverse("services:detail", args=[self.pk])

    @property
    def display_price(self):
        return self.member_price if self.member_price else self.price

    @property
    def status_color(self):
        return "success" if self.status == "on" else "secondary"


class ServicePriceHistory(models.Model):
    """服务价格变更留痕（辅助学生 2 的编辑功能做信息留痕）。"""

    service = models.ForeignKey(HealthService, verbose_name="服务", on_delete=models.CASCADE,
                                related_name="price_history")
    old_price = models.DecimalField("原价", max_digits=10, decimal_places=2)
    new_price = models.DecimalField("新价", max_digits=10, decimal_places=2)
    old_member_price = models.DecimalField("原会员价", max_digits=10, decimal_places=2)
    new_member_price = models.DecimalField("新会员价", max_digits=10, decimal_places=2)
    changed_by = models.ForeignKey("accounts.User", verbose_name="操作人", on_delete=models.SET_NULL,
                                   null=True, blank=True)
    changed_at = models.DateTimeField("变更时间", default=timezone.now)

    class Meta:
        verbose_name = "服务价格变更记录"
        verbose_name_plural = "服务价格变更记录"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.service.name} {self.old_price}->{self.new_price}"
