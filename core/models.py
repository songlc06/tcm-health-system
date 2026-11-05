from django.db import models


class Menu(models.Model):
    """系统菜单：菜单与访问权限（permission codename）绑定，实现"菜单级权限配置"。"""

    GROUP_CHOICES = [
        ("member", "会员服务"),
        ("service", "养生服务"),
        ("order", "套餐订单"),
        ("appointment", "服务预约"),
        ("report", "统计与日志"),
        ("system", "系统管理"),
    ]

    code = models.CharField("菜单编码", max_length=50, unique=True)
    name = models.CharField("菜单名称", max_length=50)
    url_name = models.CharField("路由名称", max_length=80)
    perm_codename = models.CharField("所需权限", max_length=100, blank=True,
                                     help_text="如 services.view_healthservice，留空表示登录即可访问")
    icon = models.CharField("图标", max_length=40, default="bi-circle")
    role_scope = models.CharField(
        "适用角色", max_length=120, blank=True,
        help_text="逗号分隔的角色编码（如 member,therapist），留空表示全部角色",
    )
    group = models.CharField("分组", max_length=20, choices=GROUP_CHOICES, default="service")
    sort_order = models.IntegerField("排序", default=0)
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        verbose_name = "系统菜单"
        verbose_name_plural = "系统菜单"
        ordering = ["group", "sort_order", "id"]

    def __str__(self):
        return self.name


class OperationLog(models.Model):
    """操作日志：既记录 HTTP 请求维度，也记录业务动作维度。"""

    CATEGORY_CHOICES = [
        ("auth", "登录认证"),
        ("business", "业务操作"),
        ("query", "查询导出"),
        ("system", "系统管理"),
    ]

    category = models.CharField("日志类别", max_length=20, choices=CATEGORY_CHOICES, default="business")
    action = models.CharField("操作动作", max_length=50)
    target_type = models.CharField("业务对象", max_length=40, blank=True)
    target_id = models.CharField("对象标识", max_length=40, blank=True)
    target_repr = models.CharField("对象摘要", max_length=120, blank=True)
    detail = models.TextField("详细内容", blank=True)
    username = models.CharField("操作人", max_length=60, blank=True)
    role = models.CharField("角色", max_length=30, blank=True)
    method = models.CharField("请求方法", max_length=10, blank=True)
    path = models.CharField("请求路径", max_length=200, blank=True)
    status_code = models.IntegerField("响应状态", null=True, blank=True)
    duration_ms = models.IntegerField("耗时(ms)", null=True, blank=True)
    ip = models.CharField("IP 地址", max_length=45, blank=True)
    user_agent = models.CharField("客户端", max_length=200, blank=True)
    created_at = models.DateTimeField("操作时间", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "操作日志"
        verbose_name_plural = "操作日志"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["username", "created_at"]),
            models.Index(fields=["target_type", "target_id"]),
        ]
        permissions = [
            ("view_statistics", "查看查询统计"),
            ("export_report", "导出报表数据"),
            ("query_report", "多条件查询报表"),
        ]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.username} {self.action}"
