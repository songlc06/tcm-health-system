from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from core.timeutil import local_today


class User(AbstractUser):
    """统一用户表：内部员工（管理员/主管/专员/顾问）与会员共用一套登录体系。"""

    ROLE_CHOICES = [
        ("admin", "系统管理员"),
        ("service_manager", "服务主管"),
        ("order_clerk", "订单专员"),
        ("therapist", "健康顾问"),
        ("reporter", "报表专员"),
        ("member", "会员"),
    ]
    ROLE_GROUP_MAP = {
        "admin": "系统管理员",
        "service_manager": "服务主管",
        "order_clerk": "订单专员",
        "therapist": "健康顾问",
        "reporter": "报表专员",
        "member": "会员",
    }

    role = models.CharField("角色", max_length=30, choices=ROLE_CHOICES, default="member")
    display_name = models.CharField("姓名", max_length=30, blank=True)
    phone = models.CharField("联系电话", max_length=20, blank=True)
    last_login_ip = models.CharField("最近登录IP", max_length=45, blank=True)

    class Meta:
        verbose_name = "系统用户"
        verbose_name_plural = "系统用户"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.display_name or self.username

    @property
    def is_member(self):
        return self.role == "member"

    @property
    def is_internal(self):
        return self.is_staff or self.role != "member"

    def save(self, *args, **kwargs):
        if self.is_superuser and self.role != "admin":
            self.role = "admin"
        super().save(*args, **kwargs)


class Member(models.Model):
    """养生会员档案。"""

    LEVEL_CHOICES = [
        ("bronze", "普通会员"),
        ("silver", "银卡会员"),
        ("gold", "金卡会员"),
        ("diamond", "钻石会员"),
    ]
    LEVEL_DISCOUNT = {"bronze": 1.00, "silver": 0.95, "gold": 0.90, "diamond": 0.85}

    GENDER_CHOICES = [("M", "男"), ("F", "女"), ("U", "未知")]

    member_no = models.CharField("会员编号", max_length=20, unique=True, db_index=True)
    user = models.OneToOneField(
        "accounts.User", verbose_name="登录账号", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="member_profile",
    )
    name = models.CharField("会员姓名", max_length=30)
    gender = models.CharField("性别", max_length=1, choices=GENDER_CHOICES, default="U")
    birthday = models.DateField("出生日期", null=True, blank=True)
    phone = models.CharField("手机号", max_length=20, unique=True)
    level = models.CharField("会员等级", max_length=20, choices=LEVEL_CHOICES, default="bronze")
    points = models.IntegerField("积分", default=0)
    balance = models.DecimalField("账户余额", max_digits=10, decimal_places=2, default=0)
    constitution = models.CharField("中医体质", max_length=30, blank=True,
                                    help_text="如 平和质、气虚质、阳虚质、痰湿质等")
    health_notes = models.TextField("健康备注", blank=True)
    allergy = models.CharField("过敏史", max_length=120, blank=True)
    tags = models.CharField("标签", max_length=120, blank=True, help_text="逗号分隔，如 肩颈不适,睡眠差")
    join_date = models.DateField("入会日期", default=local_today)
    is_active = models.BooleanField("有效", default=True)
    remark = models.TextField("其他说明", blank=True)
    created_by = models.ForeignKey(
        "accounts.User", verbose_name="建档人", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_members",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "会员档案"
        verbose_name_plural = "会员档案"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["level", "is_active"])]

    def __str__(self):
        return f"{self.name}({self.member_no})"

    @property
    def age(self):
        if not self.birthday:
            return None
        today = local_today()
        return today.year - self.birthday.year - (
            (today.month, today.day) < (self.birthday.month, self.birthday.day)
        )

    @property
    def discount(self):
        return self.LEVEL_DISCOUNT.get(self.level, 1.0)

    @property
    def tag_list(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def save(self, *args, **kwargs):
        if not self.member_no:
            today = local_today().strftime("%Y%m")
            prefix = f"HY{today}"
            last = Member.objects.filter(member_no__startswith=prefix).order_by("-member_no").first()
            seq = 1
            if last:
                tail = last.member_no[len(prefix):]
                if tail.isdigit():
                    seq = int(tail) + 1
            self.member_no = f"{prefix}{seq:04d}"
        super().save(*args, **kwargs)
