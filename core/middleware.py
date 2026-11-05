"""操作日志中间件：记录一次请求的关键信息，与业务日志互补。"""
import time

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

from .models import OperationLog
from .utils import get_client_ip

LOGGED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LOGGED_PATH_KEYWORDS = ("export", "print", "download")


class OperationLogMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request._start_time = time.perf_counter()
        return None

    def process_response(self, request, response):
        try:
            self._log(request, response)
        except Exception:
            pass
        return response

    def _log(self, request, response):
        path = request.path or "/"
        if path.startswith(settings.LOG_EXCLUDE_PREFIXES):
            return
        if path.startswith("/admin/jsi18n"):
            return
        if getattr(request, "_log_written", False):
            return

        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return

        method = request.method.upper()
        is_export = any(k in path.lower() for k in LOGGED_PATH_KEYWORDS)
        if method not in LOGGED_METHODS and not is_export:
            return

        start = getattr(request, "_start_time", None)
        duration = int((time.perf_counter() - start) * 1000) if start else None
        resolver = getattr(request, "resolver_match", None)
        view_name = ""
        if resolver:
            view_name = resolver.view_name or ""
        category = "query" if is_export else ("system" if path.startswith("/accounts/") else "business")
        action = "导出/打印" if is_export else f"提交 {method}"
        detail = f"{view_name} -> {response.status_code}" if view_name else f"{response.status_code}"
        if request.method == "POST" and request.POST:
            keys = [k for k in request.POST.keys() if k != "csrfmiddlewaretoken"]
            detail += " | 提交字段：" + "、".join(keys[:12])

        OperationLog.objects.create(
            category=category,
            action=action,
            username=getattr(user, "username", ""),
            role=user.get_role_display() if hasattr(user, "get_role_display") else "",
            method=method,
            path=path[:200],
            status_code=response.status_code,
            duration_ms=duration,
            ip=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:200],
            detail=detail,
        )
