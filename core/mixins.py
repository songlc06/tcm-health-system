"""权限混入类与公共视图基类。"""
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import render


class PermRequiredMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """登录 + 功能权限校验。

    已登录但缺少权限时返回 403 页面（接口访问权限拦截），未登录跳转登录页。
    raise_exception=True 让 Django 对已认证用户抛出 PermissionDenied。
    """

    raise_exception = True
    permission_denied_message = "当前角色无权访问该功能，请联系管理员分配权限"

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            return render(
                self.request,
                "core/403.html",
                {"message": self.permission_denied_message},
                status=403,
            )
        return super().handle_no_permission()
