"""通用工具：日志写入、单号生成、分页与附件校验。"""
import os
import uuid
from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.utils import timezone
from .timeutil import local_today

from .models import OperationLog


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def record_log(request, action, *, category="business", target_type="", target_id="",
               target_repr="", detail="", status_code=None):
    """写入一条业务操作日志；标记 request 已写日志，供中间件去重。"""
    user = getattr(request, "user", None)
    username = ""
    role = ""
    if user is not None and user.is_authenticated:
        username = user.username
        role = getattr(user, "get_role_display", lambda: "")()
    try:
        OperationLog.objects.create(
            category=category,
            action=action,
            target_type=target_type,
            target_id=str(target_id or ""),
            target_repr=str(target_repr or "")[:120],
            detail=detail,
            username=username,
            role=role,
            method=request.method,
            path=request.path,
            status_code=status_code,
            ip=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:200],
        )
        request._log_written = True
    except Exception:  # 日志失败不应影响主流程
        pass


def generate_business_no(prefix, queryset, field_name="order_no"):
    """生成形如 TK202611040001 的业务单号。

    queryset 既可以传模型类（如 Order），也可以传 Manager / QuerySet。
    """
    manager = getattr(queryset, "objects", queryset)
    today = local_today().strftime("%Y%m%d")
    base = f"{prefix}{today}"
    last = manager.filter(**{f"{field_name}__startswith": base}).order_by(f"-{field_name}").first()
    seq = 1
    if last:
        tail = getattr(last, field_name)[len(base):]
        if tail.isdigit():
            seq = int(tail) + 1
    return f"{base}{seq:04d}"


def paginate(request, queryset, per_page=10):
    """统一分页，per_page 可由 URL 参数覆盖（最大 100）。"""
    try:
        per_page = int(request.GET.get("per_page", per_page))
    except (TypeError, ValueError):
        per_page = 10
    per_page = max(5, min(per_page, 100))
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def validate_upload(file_obj):
    """附件校验：大小与扩展名。返回 (ok, message)。"""
    from django.conf import settings

    if file_obj is None:
        return False, "请选择要上传的文件"
    if file_obj.size > settings.MAX_UPLOAD_SIZE:
        return False, f"文件超过 {settings.MAX_UPLOAD_SIZE // 1024 // 1024}MB 限制"
    ext = os.path.splitext(file_obj.name)[1].lower()
    if ext not in settings.ALLOWED_UPLOAD_EXT:
        return False, f"不支持的文件类型 {ext}，仅允许：" + "、".join(settings.ALLOWED_UPLOAD_EXT)
    return True, ""


def safe_filename(name):
    """避免中文/特殊字符文件名导致的存储问题。"""
    ext = os.path.splitext(name)[1].lower()
    return f"{uuid.uuid4().hex}{ext}"


def parse_date(value, default=None):
    if not value:
        return default
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return default


def add_minutes(base_dt, minutes):
    from datetime import timedelta

    return base_dt + timedelta(minutes=minutes)


def raise_validation(message):
    raise ValidationError(message)
