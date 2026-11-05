"""学生 1（用户与会员管理）测试用例。

覆盖：① 注册/登录/退出；② 会员建档、等级与资料维护；③ 角色、菜单与接口权限配置。
运行：python manage.py test accounts
"""
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from core.test_factory import DEFAULT_PASSWORD, make_member, make_user


class AuthFlowTests(TestCase):
    """① 用户注册 / 登录 / 退出。"""

    def test_register_creates_user_and_member_profile(self):
        resp = self.client.post(reverse("accounts:register"), {
            "username": "newmember",
            "display_name": "新会员",
            "phone": "13600000001",
            "gender": "F",
            "birthday": "1995-05-06",
            "constitution": "气虚质",
            "health_notes": "容易疲劳",
            "password1": "Tcm@2026demo",
            "password2": "Tcm@2026demo",
        })
        self.assertRedirects(resp, reverse("accounts:profile"))
        user = self.client.session["_auth_user_id"]
        from accounts.models import Member, User

        user = User.objects.get(pk=user)
        self.assertEqual(user.role, "member")
        self.assertTrue(Member.objects.filter(user=user, name="新会员").exists())
        member = Member.objects.get(user=user)
        self.assertTrue(member.member_no.startswith("HY"))
        # 注册即登录，个人中心可访问
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)

    def test_register_rejects_duplicate_phone(self):
        make_member(phone="13600000002")
        resp = self.client.post(reverse("accounts:register"), {
            "username": "dupuser", "display_name": "重复手机号", "phone": "13600000002",
            "gender": "M", "password1": "Tcm@2026demo", "password2": "Tcm@2026demo",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "该手机号已注册会员")

    def test_login_then_logout(self):
        make_user(username="staff01", role="service_manager")
        ok = self.client.login(username="staff01", password=DEFAULT_PASSWORD)
        self.assertTrue(ok)
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(resp, reverse("accounts:login"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_login_failure_is_logged(self):
        from core.models import OperationLog

        make_user(username="staff02")
        self.client.post(reverse("accounts:login"), {"username": "staff02", "password": "wrong"})
        self.assertTrue(OperationLog.objects.filter(action="登录失败").exists())


class MemberManageTests(TestCase):
    """② 会员建档、等级与基础资料维护。"""

    def setUp(self):
        self.admin = make_user(username="admin1", role="admin")
        self.admin.is_superuser = True
        self.admin.is_staff = True
        self.admin.save()
        self.client.force_login(self.admin)

    def test_create_member_with_auto_number(self):
        resp = self.client.post(reverse("accounts:member_create"), {
            "name": "李测试", "gender": "F", "phone": "13700000011", "level": "gold",
            "points": 100, "balance": "0.00", "constitution": "阳虚质",
            "health_notes": "怕冷", "allergy": "无", "tags": "怕冷", "is_active": "on", "remark": "",
        })
        self.assertRedirects(resp, reverse("accounts:member_list"))
        from accounts.models import Member

        member = Member.objects.get(phone="13700000011")
        self.assertTrue(member.member_no.startswith("HY"))
        self.assertEqual(member.level, "gold")

    def test_update_level_and_log(self):
        member = make_member(phone="13700000012", level="bronze")
        resp = self.client.post(reverse("accounts:member_update", args=[member.pk]), {
            "name": member.name, "gender": member.gender, "birthday": "",
            "phone": member.phone, "level": "diamond", "points": 500, "balance": "0.00",
            "constitution": "", "health_notes": "", "allergy": "", "tags": "",
            "is_active": "on", "remark": "",
        })
        self.assertRedirects(resp, reverse("accounts:member_list"))
        member.refresh_from_db()
        self.assertEqual(member.level, "diamond")
        from core.models import OperationLog

        self.assertTrue(OperationLog.objects.filter(
            action="修改会员档案", detail__contains="钻石会员").exists())

    def test_member_list_filter(self):
        make_member(name="张三", phone="13700000013", level="gold")
        make_member(name="李四", phone="13700000014", level="silver")
        resp = self.client.get(reverse("accounts:member_list"), {"level": "gold", "keyword": "张"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["members"]), 1)
        self.assertEqual(resp.context["members"][0].name, "张三")


class RolePermissionTests(TestCase):
    """③ 角色、菜单与接口访问权限配置。"""

    def setUp(self):
        self.admin = make_user(username="admin2", role="admin")
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)

    def test_role_page_renders_matrix(self):
        from core.models import Menu

        Menu.objects.create(code="member_list", name="会员档案", url_name="accounts:member_list",
                            perm_codename="accounts.view_member", group="member")
        resp = self.client.get(reverse("accounts:role_list"))
        self.assertEqual(resp.status_code, 200)
        group = Group.objects.create(name="测试角色")
        resp = self.client.get(reverse("accounts:role_permission", args=[group.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("matrix", resp.context)
        self.assertTrue(resp.context["menu_groups"])

    def test_menu_selection_grants_related_permission(self):
        group = Group.objects.create(name="仅会员管理")
        perm = Permission.objects.get(codename="view_member")
        resp = self.client.post(reverse("accounts:role_permission", args=[group.pk]), {
            "name": group.name,
            "perms": [str(perm.pk)],
            "menus": ["member_list"],  # 菜单勾选应自动补齐 accounts.view_member
        })
        self.assertRedirects(resp, reverse("accounts:role_list"))
        group.refresh_from_db()
        self.assertIn(perm, group.permissions.all())

    def test_permission_denied_returns_403(self):
        member_user = make_user(username="pure_member", role="member")
        make_member(user=member_user, phone="13700000015")
        self.client.force_login(member_user)
        resp = self.client.get(reverse("services:list"))
        self.assertEqual(resp.status_code, 403)
        # 会员被引导到自己的会员中心
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_user_role_assignment(self):
        target = make_user(username="clerk1", role="member")
        resp = self.client.post(reverse("accounts:user_role", args=[target.pk]), {
            "display_name": "订单专员甲", "phone": "13700000016",
            "role": "order_clerk", "groups": [], "is_active": "on",
        })
        self.assertRedirects(resp, reverse("accounts:user_list"))
        target.refresh_from_db()
        self.assertEqual(target.role, "order_clerk")
