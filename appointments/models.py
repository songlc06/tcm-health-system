from django.db import models
from django.urls import reverse
from django.utils import timezone
from core.timeutil import local_today

from core.utils import safe_filename


class Appointment(models.Model):
    """服务预约单（学生 4 负责的服务预约管理主体）。"""

    STATUS_CHOICES = [
        ("pending", "待审核"),
        ("confirmed", "已确认"),
        ("servicing", "服务中"),
        ("finished", "已完成"),
        ("cancelled", "已取消"),
        ("no_show", "已爽约"),
    ]
    STATUS_FLOW = {
        "pending": ["confirmed", "cancelled"],
        "confirmed": ["servicing", "cancelled", "no_show"],
        "servicing": ["finished"],
        "finished": [],
        "cancelled": [],
        "no_show": [],
    }
    SOURCE_CHOICES = [
        ("online", "线上下单"),
        ("phone", "电话预约"),
        ("onsite", "到店登记"),
        ("package", "套餐核销"),
    ]
    TIME_SLOTS = [
        ("09:00", "09:00"), ("10:00", "10:00"), ("11:00", "11:00"),
        ("13:30", "13:30"), ("14:30", "14:30"), ("15:30", "15:30"),
        ("16:30", "16:30"), ("19:00", "19:00"),
    ]

    appointment_no = models.CharField("预约单号", max_length=24, unique=True, db_index=True)
    member = models.ForeignKey("accounts.Member", verbose_name="会员", on_delete=models.PROTECT,
                               related_name="appointments")
    service = models.ForeignKey("services.HealthService", verbose_name="服务项目",
                                on_delete=models.PROTECT, related_name="appointments")
    order_item = models.ForeignKey("orders.OrderItem", verbose_name="关联订单明细",
                                   on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="appointments")
    therapist = models.ForeignKey("accounts.User", verbose_name="服务顾问", on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name="appointments",
                                  limit_choices_to={"role__in": ["therapist", "admin"]})
    appoint_date = models.DateField("预约日期")
    appoint_time = models.CharField("预约时段", max_length=10, choices=TIME_SLOTS, default="09:00")
    duration = models.IntegerField("预计时长(分钟)", default=60)
    status = models.CharField("预约状态", max_length=20, choices=STATUS_CHOICES, default="pending",
                              db_index=True)
    source = models.CharField("预约来源", max_length=20, choices=SOURCE_CHOICES, default="online")
    contact_phone = models.CharField("联系电话", max_length=20, blank=True)
    remark = models.TextField("会员诉求", blank=True)
    exception_note = models.TextField("异常备注", blank=True, help_text="迟到、改期、身体不适等特殊情况说明")
    exception_level = models.CharField("异常等级", max_length=10, default="normal",
                                       choices=[("normal", "正常"), ("attention", "需关注"), ("urgent", "紧急")])
    created_by = models.ForeignKey("accounts.User", verbose_name="创建人", on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="created_appointments")
    confirmed_by = models.ForeignKey("accounts.User", verbose_name="审核人", on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name="confirmed_appointments")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    confirmed_at = models.DateTimeField("确认时间", null=True, blank=True)
    finished_at = models.DateTimeField("完成时间", null=True, blank=True)
    cancelled_reason = models.CharField("取消原因", max_length=200, blank=True)

    class Meta:
        verbose_name = "服务预约"
        verbose_name_plural = "服务预约"
        ordering = ["-appoint_date", "appoint_time"]
        permissions = [
            ("review_appointment", "审核服务预约"),
            ("export_appointment", "导出预约数据"),
        ]
        indexes = [models.Index(fields=["status", "appoint_date"])]

    def __str__(self):
        return f"{self.appointment_no} {self.member.name}-{self.service.name}"

    def get_absolute_url(self):
        return reverse("appointments:detail", args=[self.pk])

    @property
    def can_transition(self):
        return bool(self.STATUS_FLOW.get(self.status))

    def allowed_actions(self):
        """返回当前状态可执行的动作列表：(动作码, 按钮文字, 颜色)。"""
        mapping = {
            "confirmed": ("confirm", "审核确认", "primary"),
            "cancelled": ("cancel", "取消预约", "outline-secondary"),
            "servicing": ("start", "开始服务", "info"),
            "finished": ("finish", "完成服务", "success"),
            "no_show": ("no_show", "标记爽约", "danger"),
        }
        return [mapping[s] for s in self.STATUS_FLOW.get(self.status, []) if s in mapping]

    @property
    def is_open(self):
        return self.status in ("pending", "confirmed", "servicing")

    @property
    def can_upload(self):
        return True


class AppointmentHistory(models.Model):
    """预约状态流转与处理记录，实现全过程追踪。"""

    appointment = models.ForeignKey(Appointment, verbose_name="预约单", on_delete=models.CASCADE,
                                    related_name="history")
    from_status = models.CharField("原状态", max_length=20, blank=True)
    to_status = models.CharField("新状态", max_length=20, blank=True)
    action = models.CharField("操作动作", max_length=40)
    operator = models.ForeignKey("accounts.User", verbose_name="操作人", on_delete=models.SET_NULL,
                                 null=True, blank=True)
    note = models.TextField("操作说明", blank=True)
    created_at = models.DateTimeField("操作时间", default=timezone.now)

    class Meta:
        verbose_name = "预约处理记录"
        verbose_name_plural = "预约处理记录"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.appointment.appointment_no} {self.action}"


def attachment_upload_to(instance, filename):
    return f"appointments/{local_today():%Y%m}/{safe_filename(filename)}"


class AppointmentAttachment(models.Model):
    """预约附件：体检报告、知情同意书、异常照片等。"""

    appointment = models.ForeignKey(Appointment, verbose_name="预约单", on_delete=models.CASCADE,
                                    related_name="attachments")
    file = models.FileField("附件", upload_to=attachment_upload_to)
    original_name = models.CharField("原始文件名", max_length=120)
    size = models.IntegerField("文件大小(字节)", default=0)
    content_type = models.CharField("文件类型", max_length=80, blank=True)
    note = models.CharField("附件说明", max_length=100, blank=True)
    uploaded_by = models.ForeignKey("accounts.User", verbose_name="上传人", on_delete=models.SET_NULL,
                                    null=True, blank=True)
    created_at = models.DateTimeField("上传时间", auto_now_add=True)

    class Meta:
        verbose_name = "预约附件"
        verbose_name_plural = "预约附件"
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name

    @property
    def size_kb(self):
        return round(self.size / 1024, 1)
