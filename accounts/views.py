"""学生 1：用户注册/登录/退出、会员档案维护、角色与菜单/接口权限配置。"""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from core.mixins import PermRequiredMixin
from core.models import Menu, OperationLog
from core.utils import paginate, record_log

from .forms import (LoginForm, MemberForm, MemberProfileForm, MemberRegisterForm, UserRoleForm)
from .models import Member, User

PERM_APP_ORDER = ["accounts", "services", "orders", "appointments", "core"]
PERM_APP_LABEL = {
    "accounts": "会员与账号",
    "services": "养生服务",
    "orders": "套餐订单",
    "appointments": "服务预约",
    "core": "系统与日志",
}


# ------------------------------------------------------------------ 认证
class RegisterView(CreateView):
    """① 会员注册（游客可访问）。"""

    template_name = "accounts/register.html"
    form_class = MemberRegisterForm
    success_url = reverse_lazy("accounts:profile")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        record_log(self.request, "会员注册", category="auth", target_type="Member",
                   target_id=user.member_profile.member_no, target_repr=user.display_name,
                   detail=f"新会员注册：{user.username}")
        messages.success(self.request, f"注册成功，会员编号 {user.member_profile.member_no}，已自动登录")
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, "注册信息有误，请检查后重试")
        return super().form_invalid(form)


class UserLoginView(LoginView):
    """① 用户/会员统一登录入口，按角色跳转。"""

    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        ip = self.request.META.get("REMOTE_ADDR", "")
        User.objects.filter(pk=user.pk).update(last_login_ip=ip)
        record_log(self.request, "登录系统", category="auth", target_type="User",
                   target_id=user.pk, target_repr=user.username,
                   detail=f"角色：{user.get_role_display()}；IP：{ip}")
        return response

    def form_invalid(self, form):
        record_log(self.request, "登录失败", category="auth",
                   detail=f"账号：{self.request.POST.get('username', '')}")
        messages.error(self.request, "账号或密码错误，请重新输入")
        return super().form_invalid(form)

    def get_success_url(self):
        if self.request.user.role == "member":
            return reverse("accounts:profile")
        return super().get_success_url()


class UserLogoutView(LogoutView):
    """① 退出登录。"""

    next_page = reverse_lazy("accounts:login")

    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            record_log(request, "退出登录", category="auth", target_type="User",
                       target_id=request.user.pk, target_repr=request.user.username)
        messages.info(request, "您已安全退出")
        return super().post(request, *args, **kwargs)


# ------------------------------------------------------------------ 会员中心（会员本人）
class ProfileView(LoginRequiredMixin, UpdateView):
    """② 会员中心：查看并维护本人基础资料。"""

    template_name = "accounts/profile.html"
    form_class = MemberProfileForm
    success_url = reverse_lazy("accounts:profile")

    def get_object(self, queryset=None):
        member = getattr(self.request.user, "member_profile", None)
        if member is None:
            return None
        return member

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and getattr(request.user, "member_profile", None) is None:
            # 员工账号没有会员档案：展示账号信息页，保留"个人中心"入口可用
            if request.method == "GET":
                return render(request, "accounts/staff_profile.html", {
                    "target_user": request.user,
                    "groups": request.user.groups.all(),
                    "perm_count": len(request.user.get_all_permissions()),
                    "recent_logs": OperationLog.objects.filter(
                        username=request.user.username)[:10],
                })
            messages.warning(request, "当前账号未绑定会员档案，请使用员工账号在“会员档案”中操作")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        member = self.object
        ctx["member"] = member
        ctx["orders"] = member.orders.select_related("package").order_by("-created_at")[:5]
        ctx["appointments"] = member.appointments.select_related("service").order_by("-appoint_date")[:5]
        ctx["order_count"] = member.orders.count()
        ctx["appointment_count"] = member.appointments.count()
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        record_log(self.request, "修改个人资料", target_type="Member", target_id=self.object.member_no,
                   target_repr=self.object.name, detail="会员本人更新基础资料")
        messages.success(self.request, "资料已更新")
        return response


# ------------------------------------------------------------------ 会员档案管理（员工）
class MemberListView(PermRequiredMixin, ListView):
    """② 会员档案列表：关键字 + 等级 + 状态筛选，分页。"""

    model = Member
    template_name = "accounts/member_list.html"
    permission_required = "accounts.view_member"
    context_object_name = "members"

    def get_queryset(self):
        qs = Member.objects.select_related("user").annotate(
            order_count=Count("orders", distinct=True),
            appointment_count=Count("appointments", distinct=True),
        )
        keyword = self.request.GET.get("keyword", "").strip()
        level = self.request.GET.get("level", "").strip()
        status = self.request.GET.get("status", "").strip()
        if keyword:
            qs = qs.filter(
                Q(name__icontains=keyword) | Q(phone__icontains=keyword)
                | Q(member_no__icontains=keyword) | Q(tags__icontains=keyword)
            )
        if level:
            qs = qs.filter(level=level)
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_obj"] = paginate(self.request, self.get_queryset(), 10)
        ctx["members"] = ctx["page_obj"]
        ctx["levels"] = Member.LEVEL_CHOICES
        ctx["keyword"] = self.request.GET.get("keyword", "")
        ctx["level"] = self.request.GET.get("level", "")
        ctx["status"] = self.request.GET.get("status", "")
        ctx["total"] = self.get_queryset().count()
        return ctx


class MemberCreateView(PermRequiredMixin, CreateView):
    """② 会员建档（员工代客建档，可绑定登录账号）。"""

    model = Member
    form_class = MemberForm
    template_name = "accounts/member_form.html"
    permission_required = "accounts.add_member"
    success_url = reverse_lazy("accounts:member_list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        record_log(self.request, "新增会员档案", target_type="Member", target_id=self.object.member_no,
                   target_repr=self.object.name,
                   detail=f"等级：{self.object.get_level_display()}；手机：{self.object.phone}")
        messages.success(self.request, f"会员建档成功，编号 {self.object.member_no}")
        return response


class MemberUpdateView(PermRequiredMixin, UpdateView):
    """② 会员资料与等级维护（等级变更留痕）。"""

    model = Member
    form_class = MemberForm
    template_name = "accounts/member_form.html"
    permission_required = "accounts.change_member"
    success_url = reverse_lazy("accounts:member_list")

    def form_valid(self, form):
        old = Member.objects.get(pk=self.object.pk)
        old_level = old.level
        response = super().form_valid(form)
        changes = []
        if old_level != self.object.level:
            changes.append(f"等级 {old.get_level_display()} → {self.object.get_level_display()}")
        if old.phone != self.object.phone:
            changes.append("手机号变更")
        record_log(self.request, "修改会员档案", target_type="Member", target_id=self.object.member_no,
                   target_repr=self.object.name, detail="；".join(changes) or "更新基础资料")
        messages.success(self.request, "会员信息已保存")
        return response


class MemberDetailView(PermRequiredMixin, DetailView):
    """② 会员详情：档案 + 订单 + 预约全景。"""

    model = Member
    template_name = "accounts/member_detail.html"
    permission_required = "accounts.view_member"
    context_object_name = "member"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["orders"] = self.object.orders.select_related("package").order_by("-created_at")[:10]
        ctx["appointments"] = (
            self.object.appointments.select_related("service", "therapist").order_by("-appoint_date")[:10]
        )
        ctx["total_paid"] = sum(o.pay_amount for o in self.object.orders.filter(
            status__in=["paid", "servicing", "completed"]))
        return ctx


# ------------------------------------------------------------------ 角色与权限（学生 1 第③项）
class RoleListView(PermRequiredMixin, ListView):
    """③ 角色列表：查看角色、成员数、权限数。"""

    template_name = "accounts/role_list.html"
    permission_required = "auth.view_group"
    context_object_name = "roles"

    def get_queryset(self):
        return Group.objects.annotate(
            member_count=Count("user", distinct=True),
            perm_count=Count("permissions", distinct=True),
        ).order_by("id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["role_total"] = User.objects.count()
        return ctx


def _permission_matrix():
    """构建“业务对象 × 操作”的接口权限矩阵。"""
    cts = ContentType.objects.filter(app_label__in=PERM_APP_ORDER).select_related()
    rows = []
    for app in PERM_APP_ORDER:
        app_rows = []
        for ct in sorted([c for c in cts if c.app_label == app],
                         key=lambda c: (c.model_class()._meta.verbose_name if c.model_class() else c.model)):
            model_cls = ct.model_class()
            if model_cls is None:
                continue
            verbose = model_cls._meta.verbose_name
            perms = list(Permission.objects.filter(content_type=ct).order_by("codename"))
            if not perms:
                continue
            # 把 codename 前缀（add/change/delete/view/其他）转成中文动作名
            action_map = {"add": "新增", "change": "修改", "delete": "删除", "view": "查看"}
            items = []
            for p in perms:
                prefix = p.codename.split("_")[0]
                items.append({"perm": p, "action": action_map.get(prefix, p.name)})
            order = {"查看": 0, "新增": 1, "修改": 2, "删除": 3}
            items.sort(key=lambda x: (order.get(x["action"], 9), x["perm"].codename))
            app_rows.append({"model": verbose, "items": items})
        if app_rows:
            rows.append({"app": app, "label": PERM_APP_LABEL.get(app, app), "models": app_rows})
    return rows


class RolePermissionView(PermRequiredMixin, UpdateView):
    """③ 角色权限配置：勾选菜单 + 接口操作权限，保存后立即生效。"""

    template_name = "accounts/role_permission.html"
    permission_required = "auth.change_group"
    model = Group
    fields = ["name"]
    context_object_name = "role"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        role = self.object
        owned = set(role.permissions.values_list("id", flat=True))

        menu_groups = []
        for code, label in Menu.GROUP_CHOICES:
            menus = []
            for menu in Menu.objects.filter(group=code, is_active=True):
                required_perm = None
                if menu.perm_codename and "." in menu.perm_codename:
                    app_label, codename = menu.perm_codename.split(".", 1)
                    required_perm = Permission.objects.filter(
                        content_type__app_label=app_label, codename=codename).first()
                menus.append({
                    "menu": menu,
                    "checked": bool(required_perm and required_perm.id in owned),
                    "required": bool(required_perm),
                })
            if menus:
                menu_groups.append({"code": code, "label": label, "menus": menus})

        ctx["menu_groups"] = menu_groups
        ctx["matrix"] = _permission_matrix()
        ctx["owned"] = owned
        ctx["members"] = role.user_set.all()[:20]
        return ctx

    def form_valid(self, form):
        role = form.save(commit=False)
        selected = {int(i) for i in self.request.POST.getlist("perms") if str(i).isdigit()}

        # 菜单勾选自动补齐其对应权限，实现"菜单权限"与"接口权限"联动
        menu_codes = self.request.POST.getlist("menus")
        auto_added = []
        for menu in Menu.objects.filter(code__in=menu_codes):
            if not menu.perm_codename or "." not in menu.perm_codename:
                continue
            app_label, codename = menu.perm_codename.split(".", 1)
            perm = Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()
            if perm and perm.id not in selected:
                selected.add(perm.id)
                auto_added.append(menu.name)

        role.save()
        role.permissions.set(Permission.objects.filter(id__in=selected))
        record_log(self.request, "配置角色权限", category="system", target_type="Group",
                   target_id=role.id, target_repr=role.name,
                   detail=f"菜单 {len(menu_codes)} 项，权限 {len(selected)} 项"
                          + (f"；菜单联动权限：{'、'.join(auto_added)}" if auto_added else ""))
        messages.success(self.request,
                         f"角色「{role.name}」权限已更新：菜单 {len(menu_codes)} 项、接口权限 {len(selected)} 项")
        return redirect("accounts:role_list")


class UserListView(PermRequiredMixin, ListView):
    """③ 用户列表与角色分配入口。"""

    template_name = "accounts/user_list.html"
    permission_required = "auth.view_user"
    context_object_name = "users"

    def get_queryset(self):
        qs = User.objects.prefetch_related("groups").order_by("-date_joined")
        keyword = self.request.GET.get("keyword", "").strip()
        role = self.request.GET.get("role", "").strip()
        if keyword:
            qs = qs.filter(Q(username__icontains=keyword) | Q(display_name__icontains=keyword)
                           | Q(phone__icontains=keyword))
        if role:
            qs = qs.filter(role=role)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_obj"] = paginate(self.request, self.get_queryset(), 10)
        ctx["users"] = ctx["page_obj"]
        ctx["roles"] = User.ROLE_CHOICES
        ctx["keyword"] = self.request.GET.get("keyword", "")
        ctx["role"] = self.request.GET.get("role", "")
        return ctx


class UserRoleUpdateView(PermRequiredMixin, UpdateView):
    """③ 给用户分配角色与附加权限组。"""

    model = User
    form_class = UserRoleForm
    template_name = "accounts/user_form.html"
    permission_required = "auth.change_user"
    success_url = reverse_lazy("accounts:user_list")
    context_object_name = "target_user"

    def form_valid(self, form):
        response = super().form_valid(form)
        role_group = self.object.groups.model.objects.filter(
            name=User.ROLE_GROUP_MAP.get(self.object.role, ""))
        if role_group.exists():
            self.object.groups.add(*role_group)
        record_log(self.request, "分配用户角色", category="system", target_type="User",
                   target_id=self.object.pk, target_repr=self.object.username,
                   detail=f"角色 → {self.object.get_role_display()}；权限组："
                          f"{'、'.join(self.object.groups.values_list('name', flat=True))}")
        messages.success(self.request, "用户角色已更新")
        return response
