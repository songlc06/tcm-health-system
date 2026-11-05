"""测试数据工厂：各功能包测试共用。"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.utils import timezone
from .timeutil import local_today

from accounts.models import Member, User
from orders.models import Package, PackageItem
from services.models import HealthService, ServiceCategory

DEFAULT_PASSWORD = "test123456"


def make_user(username="tester", role="admin", superuser=False, password=DEFAULT_PASSWORD, **extra):
    user = User.objects.create_user(
        username=username, password=password,
        display_name=extra.pop("display_name", username),
        role=role, **extra,
    )
    if superuser:
        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=["is_superuser", "is_staff"])
    return user


def make_staff_group(name, perms):
    group, _ = Group.objects.get_or_create(name=name)
    group.permissions.set(perms)
    return group


def make_member(name=None, phone=None, level="gold", user=None, **extra):
    seq = Member.objects.count() + 1
    name = name or f"测试会员{seq}"
    phone = phone or f"137{seq:08d}"
    return Member.objects.create(
        name=name, phone=phone, level=level, gender="F",
        birthday=local_today() - timedelta(days=365 * 30),
        constitution="平和质", health_notes="测试档案", user=user, **extra,
    )


def make_category(name=None, code=None):
    """分类名称与编码默认按序号自增，避免同一用例内重复。"""
    seq = ServiceCategory.objects.count() + 1
    return ServiceCategory.objects.create(
        name=name or f"测试分类{seq}", code=code or f"TC{seq:03d}")


def make_service(code=None, name=None, price="200.00", member_price="180.00",
                 duration=60, category=None, status="on"):
    seq = HealthService.objects.count() + 1
    return HealthService.objects.create(
        code=code or f"TS{seq:04d}", name=name or f"测试服务{seq}",
        category=category or make_category(),
        price=Decimal(price), member_price=Decimal(member_price),
        duration=duration, status=status, summary="测试用服务",
    )


def make_package(code=None, name="测试套餐", price="1000.00", member_price="900.00",
                 services=None, status="on"):
    seq = Package.objects.count() + 1
    code = code or f"TP{seq:04d}"
    package = Package.objects.create(
        code=code, name=name, price=Decimal(price), member_price=Decimal(member_price),
        valid_days=365, status=status, description="测试套餐",
    )
    for service, times in (services or [(make_service(), 5)]):
        PackageItem.objects.create(package=package, service=service, times=times)
    return package
