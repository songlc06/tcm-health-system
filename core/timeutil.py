"""时间工具：统一获取"今天"。

项目设置 USE_TZ = False（教学环境使用本地时间），此时 Django 的
``timezone.localdate()`` 会因 naive datetime 报错，因此统一走本模块。
"""
from django.utils import timezone


def local_today():
    """返回今天的日期（兼容 USE_TZ 开/关两种配置）。"""
    now = timezone.now()
    if timezone.is_aware(now):
        return timezone.localtime(now).date()
    return now.date()


def local_now():
    """返回当前时间（兼容 USE_TZ 开/关两种配置）。"""
    return timezone.now()
