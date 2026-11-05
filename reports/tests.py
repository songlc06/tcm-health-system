"""学生 5（查询统计与日志）测试用例。

覆盖：① 按时间、人员、业务对象的多条件查询；② 统计数据汇总与图表数据；
③ 操作日志、结果导出与打印页面。
运行：python manage.py test reports
"""
from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from appointments.models import Appointment
from core.models import OperationLog
from core.test_factory import make_member, make_package, make_service, make_user
from core.timeutil import local_today
from orders.models import Order
from reports.datasets import DATASETS
from reports.statistics import build_statistics


class ReportBase(TestCase):
    def setUp(self):
        self.admin = make_user(username="report_admin", role="reporter")
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)

        self.member_a = make_member(name="查询甲", phone="13500000001", level="gold")
        self.member_b = make_member(name="查询乙", phone="13500000002", level="silver")
        self.package = make_package(code="RP001", name="查询套餐",
                                    services=[(make_service(code="RS001", name="查询服务"), 4)])
        self.order = Order.objects.create(
            order_no="TK202611040101", member=self.member_a, package=self.package,
            quantity=1, unit_price=Decimal("900"), total_amount=Decimal("900"),
            pay_amount=Decimal("900"), status="paid", salesperson=self.admin,
        )
        self.appt = Appointment.objects.create(
            appointment_no="YY202611040101", member=self.member_a, service=self.package.items.first().service,
            therapist=self.admin, appoint_date=local_today(), appoint_time="09:00",
            status="finished", source="online", created_by=self.admin,
        )
        OperationLog.objects.create(category="business", action="测试日志", target_type="Order",
                                    target_repr=self.order.order_no, username="report_admin",
                                    role="报表专员", path="/orders/", status_code=200)


class MultiConditionQueryTests(ReportBase):
    """① 按时间、人员或业务对象的多条件查询。"""

    def test_query_by_keyword(self):
        resp = self.client.get(reverse("reports:search"), {"dataset": "orders", "keyword": "查询甲"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total"], 1)

    def test_query_by_status_and_date_range(self):
        today = local_today().isoformat()
        resp = self.client.get(reverse("reports:search"), {
            "dataset": "orders", "status": "paid",
            "date_from": today, "date_to": today,
        })
        self.assertEqual(resp.context["total"], 1)

        resp = self.client.get(reverse("reports:search"), {
            "dataset": "orders", "status": "cancelled",
        })
        self.assertEqual(resp.context["total"], 0)

    def test_query_by_person(self):
        resp = self.client.get(reverse("reports:search"), {
            "dataset": "appointments", "person": self.admin.pk,
        })
        self.assertEqual(resp.context["total"], 1)

    def test_all_datasets_available(self):
        for key in DATASETS:
            resp = self.client.get(reverse("reports:search"), {"dataset": key})
            self.assertEqual(resp.status_code, 200, f"数据集 {key} 渲染失败")
            self.assertEqual(resp.context["dataset_key"], key)

    def test_members_and_services_dataset_filter(self):
        resp = self.client.get(reverse("reports:search"), {"dataset": "members", "status": "gold"})
        self.assertEqual(resp.context["total"], 1)
        resp = self.client.get(reverse("reports:search"), {"dataset": "services", "keyword": "查询服务"})
        self.assertEqual(resp.context["total"], 1)


class StatisticsTests(ReportBase):
    """② 统计数据汇总与基础图表。"""

    def test_statistics_page_renders(self):
        resp = self.client.get(reverse("reports:statistics"))
        self.assertEqual(resp.status_code, 200)
        stats = resp.context["stats"]
        self.assertIn("kpi", stats)
        self.assertEqual(stats["kpi"]["order_count"], 1)
        self.assertEqual(stats["kpi"]["revenue"], 900.0)
        self.assertEqual(stats["kpi"]["appointment_count"], 1)
        self.assertGreaterEqual(len(stats["daily"]["labels"]), 1)
        self.assertTrue(stats["status_pie"])

    def test_statistics_with_custom_range(self):
        today = local_today().isoformat()
        resp = self.client.get(reverse("reports:statistics"),
                              {"date_from": today, "date_to": today})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["date_from"], today)

    def test_build_statistics_service_ranking(self):
        stats = build_statistics(local_today(), local_today())
        names = stats["top_services"]["labels"]
        self.assertIn("查询服务", names)
        self.assertEqual(stats["service_rows"][0]["count"], 1)


class LogsExportPrintTests(ReportBase):
    """③ 操作日志、结果导出与打印页面。"""

    def test_logs_page_and_filter(self):
        resp = self.client.get(reverse("reports:logs"))
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.context["total"], 1)

        resp = self.client.get(reverse("reports:logs"), {"keyword": "测试日志"})
        self.assertEqual(resp.context["total"], 1)

    def test_export_csv_has_bom_and_rows(self):
        resp = self.client.get(reverse("reports:export"), {"dataset": "orders"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        self.assertIn("attachment", resp["Content-Disposition"])
        body = resp.content.decode("utf-8-sig")
        self.assertIn("订单号", body)
        self.assertIn("TK202611040101", body)
        # 导出动作被记入日志
        self.assertTrue(OperationLog.objects.filter(action="导出查询结果").exists())

    def test_export_respects_query_condition(self):
        resp = self.client.get(reverse("reports:export"),
                              {"dataset": "orders", "keyword": "不存在的会员"})
        body = resp.content.decode("utf-8-sig").strip().splitlines()
        self.assertEqual(len(body), 1)  # 只有表头

    def test_print_page(self):
        resp = self.client.get(reverse("reports:print"), {"dataset": "appointments"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "YY202611040101")

    def test_export_requires_permission(self):
        user = make_user(username="no_export", role="therapist")
        group = Group.objects.create(name="仅可查询")
        group.permissions.set(Permission.objects.filter(
            content_type__app_label="core", codename="query_report"))
        user.groups.add(group)
        self.client.force_login(user)
        resp = self.client.get(reverse("reports:search"))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(reverse("reports:export"))
        self.assertEqual(resp.status_code, 403)
