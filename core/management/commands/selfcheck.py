"""系统自检：用 Django 测试客户端逐页访问，验证 5 个功能包的页面与权限是否正常。

用法：
    python manage.py selfcheck            # 全量检查（含各角色权限校验）
    python manage.py selfcheck --verbose  # 打印每个请求的返回码
"""
from django.core.management.base import BaseCommand
from django.test import Client

# (说明, URL, 期望状态码)
ANONYMOUS_PAGES = [
    ("登录页", "/accounts/login/"),
    ("注册页", "/accounts/register/"),
]

ADMIN_PAGES = [
    ("工作台", "/"),
    ("会员档案列表", "/accounts/members/"),
    ("会员详情", "/accounts/members/{member}/"),
    ("会员编辑", "/accounts/members/{member}/edit/"),
    ("会员建档", "/accounts/members/create/"),
    ("个人中心", "/accounts/profile/"),
    ("用户管理", "/accounts/users/"),
    ("角色列表", "/accounts/roles/"),
    ("养生服务列表", "/services/"),
    ("养生服务新增", "/services/create/"),
    ("养生服务详情", "/services/{service}/"),
    ("养生服务编辑", "/services/{service}/edit/"),
    ("养生服务删除确认", "/services/{service}/delete/"),
    ("养生服务导出", "/services/export/"),
    ("套餐订单列表", "/orders/"),
    ("套餐订单新增", "/orders/create/"),
    ("套餐订单详情", "/orders/{order}/"),
    ("套餐订单导出", "/orders/export/"),
    ("服务预约列表", "/appointments/"),
    ("服务预约登记", "/appointments/create/"),
    ("服务预约详情", "/appointments/{appointment}/"),
    ("服务预约导出", "/appointments/export/"),
    ("多条件查询", "/reports/search/"),
    ("多条件查询-预约集", "/reports/search/?dataset=appointments"),
    ("多条件查询-会员集", "/reports/search/?dataset=members"),
    ("多条件查询-服务集", "/reports/search/?dataset=services"),
    ("多条件查询-日志集", "/reports/search/?dataset=logs"),
    ("统计报表", "/reports/statistics/"),
    ("统计报表-区间", "/reports/statistics/?date_from=2026-01-01&date_to=2026-12-31"),
    ("操作日志", "/reports/logs/"),
    ("打印页", "/reports/print/?dataset=orders"),
    ("结果导出", "/reports/export/?dataset=orders"),
    ("后台管理", "/admin/"),
]

# 角色 -> 应被拒绝（403）的页面
DENIED_CHECKS = [
    ("member01", "会员访问养生服务管理", "/services/"),
    ("member01", "会员访问订单管理", "/orders/"),
    ("therapist", "健康顾问访问服务新增", "/services/create/"),
    ("clerk", "订单专员访问统计报表", "/reports/statistics/"),
    ("reporter", "报表专员访问订单新增", "/orders/create/"),
]


class Command(BaseCommand):
    help = "逐页访问关键 URL，检查页面渲染与角色权限"

    def add_arguments(self, parser):
        parser.add_argument("--verbose", action="store_true", help="打印每个请求结果")

    @staticmethod
    def _sample_ids():
        """取每个业务对象的一个真实主键，供详情/编辑页检查。"""
        from accounts.models import Member
        from appointments.models import Appointment
        from orders.models import Order
        from services.models import HealthService

        def first_pk(model, fallback=1):
            pk = model.objects.order_by("pk").values_list("pk", flat=True).first()
            return pk if pk is not None else fallback

        return {
            "member": first_pk(Member),
            "service": first_pk(HealthService),
            "order": first_pk(Order),
            "appointment": first_pk(Appointment),
        }

    def handle(self, *args, **options):
        verbose = options["verbose"]
        failures = []
        checks = 0

        def hit(client, label, url, expect=200, who=""):
            nonlocal checks
            checks += 1
            try:
                resp = client.get(url)
                code = resp.status_code
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{label} {url} 异常：{exc}")
                if verbose:
                    self.stdout.write(f"  [ERR] {label} {url}: {exc}")
                return
            if code != expect:
                failures.append(f"{label} {url} 返回 {code}，期望 {expect}")
            if verbose:
                flag = "OK " if code == expect else "FAIL"
                self.stdout.write(f"  [{flag}] {code} {url} {label}")

        # 1) 匿名访问
        anon = Client()
        for label, url in ANONYMOUS_PAGES:
            hit(anon, label, url, 200, "匿名")

        # 2) 管理员全量（详情页 ID 取库中真实主键，避免主键自增导致 404）
        admin = Client()
        if not admin.login(username="admin", password="demo123456"):
            self.stderr.write(self.style.ERROR("管理员登录失败，请先执行 python manage.py seed_demo"))
            return
        ids = self._sample_ids()
        for label, url in ADMIN_PAGES:
            hit(admin, label, url.format(**ids))

        # 3) 各角色权限拦截
        for username, label, url in DENIED_CHECKS:
            client = Client()
            if not client.login(username=username, password="demo123456"):
                failures.append(f"{username} 登录失败")
                continue
            hit(client, label, url, 403)

        self.stdout.write("")
        if failures:
            self.stderr.write(self.style.ERROR(f"自检完成：{checks - len(failures)}/{checks} 通过"))
            for item in failures:
                self.stderr.write(self.style.ERROR("  - " + item))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(f"自检通过：{checks}/{checks} 个检查点全部正常"))
