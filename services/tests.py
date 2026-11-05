"""学生 2（养生服务管理）测试用例。

覆盖：① 新增养生服务；② 编辑/删除/详情查看；③ 列表分页、关键字与条件筛选。
运行：python manage.py test services
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.test_factory import make_category, make_package, make_service, make_user
from services.models import HealthService, ServiceCategory, ServicePriceHistory


class ServiceCreateTests(TestCase):
    """① 养生服务信息新增。"""

    def setUp(self):
        self.admin = make_user(username="svc_admin", role="service_manager")
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)
        self.category = make_category(name="艾灸理疗", code="MOXA")

    def payload(self, **overrides):
        data = {
            "code": "SVC900",
            "name": "测试艾灸",
            "category": self.category.pk,
            "summary": "温和灸调理",
            "description": "详细说明",
            "duration": 60,
            "price": "268.00",
            "member_price": "238.00",
            "suitable_for": "阳虚体质",
            "contraindication": "实热体质慎用",
            "status": "on",
            "sort_order": 1,
        }
        data.update(overrides)
        return data

    def test_create_service_success(self):
        resp = self.client.post(reverse("services:create"), self.payload())
        self.assertRedirects(resp, reverse("services:list"))
        service = HealthService.objects.get(code="SVC900")
        self.assertEqual(service.created_by, self.admin)
        from core.models import OperationLog

        self.assertTrue(OperationLog.objects.filter(action="新增养生服务").exists())

    def test_code_is_upper_cased_and_unique(self):
        self.client.post(reverse("services:create"), self.payload(code="svc901"))
        self.assertTrue(HealthService.objects.filter(code="SVC901").exists())
        resp = self.client.post(reverse("services:create"), self.payload(code="SVC901", name="重名编码"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "服务编码已存在")

    def test_member_price_cannot_exceed_price(self):
        resp = self.client.post(reverse("services:create"),
                               self.payload(member_price="999.00"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "会员价不能高于标准价")

    def test_duration_range_validated(self):
        resp = self.client.post(reverse("services:create"), self.payload(duration=5))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "服务时长需在 10-480 分钟之间")


class ServiceEditDeleteTests(TestCase):
    """② 编辑、删除与详情查看。"""

    def setUp(self):
        self.admin = make_user(username="svc_admin2", role="service_manager")
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)
        self.service = make_service(code="SVC910", name="肩颈推拿", price="258.00", member_price="228.00")

    def update_payload(self, **overrides):
        data = {
            "code": self.service.code, "name": self.service.name,
            "category": self.service.category.pk, "summary": "更新后的简介",
            "description": "更新后的详情", "duration": 50, "price": "288.00",
            "member_price": "248.00", "suitable_for": "伏案人群",
            "contraindication": "皮肤破损禁用", "status": "off", "sort_order": 2,
        }
        data.update(overrides)
        return data

    def test_detail_page(self):
        resp = self.client.get(reverse("services:detail", args=[self.service.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "肩颈推拿")
        self.assertEqual(resp.context["service"], self.service)

    def test_update_records_price_history(self):
        resp = self.client.post(reverse("services:update", args=[self.service.pk]),
                                self.update_payload())
        self.assertRedirects(resp, reverse("services:list"))
        self.service.refresh_from_db()
        self.assertEqual(self.service.price, Decimal("288.00"))
        self.assertEqual(self.service.status, "off")
        history = ServicePriceHistory.objects.filter(service=self.service).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_price, Decimal("258.00"))
        self.assertEqual(history.new_price, Decimal("288.00"))
        self.assertEqual(history.changed_by, self.admin)

    def test_delete_unreferenced_service(self):
        free = make_service(code="SVC911", name="无人引用服务")
        resp = self.client.post(reverse("services:delete", args=[free.pk]))
        self.assertRedirects(resp, reverse("services:list"))
        self.assertFalse(HealthService.objects.filter(pk=free.pk).exists())

    def test_delete_referenced_service_is_blocked(self):
        make_package(services=[(self.service, 5)])
        resp = self.client.post(reverse("services:delete", args=[self.service.pk]))
        self.assertRedirects(resp, reverse("services:detail", args=[self.service.pk]))
        self.assertTrue(HealthService.objects.filter(pk=self.service.pk).exists())


class ServiceListTests(TestCase):
    """③ 列表分页、关键字与条件筛选。"""

    def setUp(self):
        self.admin = make_user(username="svc_admin3", role="service_manager")
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)
        cat_a = make_category(name="针灸推拿", code="TUINA")
        cat_b = make_category(name="艾灸理疗", code="MOXA2")
        for i in range(12):
            make_service(code=f"LST{i:03d}", name=f"测试服务{i}",
                         category=cat_a if i % 2 == 0 else cat_b,
                         price=f"{100 + i * 10}.00", member_price=f"{90 + i * 10}.00",
                         status="on" if i % 3 else "off")

    def test_pagination_default_page_size(self):
        resp = self.client.get(reverse("services:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["services"]), 8)
        self.assertEqual(resp.context["page_obj"].paginator.num_pages, 2)

    def test_custom_page_size(self):
        resp = self.client.get(reverse("services:list"), {"per_page": 5, "page": 2})
        self.assertEqual(len(resp.context["services"]), 5)

    def test_keyword_filter(self):
        resp = self.client.get(reverse("services:list"), {"keyword": "测试服务1"})
        self.assertEqual(resp.context["total"], 3)  # 1、10、11

    def test_status_and_price_filter(self):
        resp = self.client.get(reverse("services:list"),
                              {"status": "on", "price_min": "150", "price_max": "200"})
        names = [s.name for s in resp.context["services"]]
        self.assertTrue(all(n for n in names))
        for svc in resp.context["services"]:
            self.assertEqual(svc.status, "on")
            self.assertTrue(Decimal("150") <= svc.price <= Decimal("200"))

    def test_category_filter_and_sort(self):
        category = ServiceCategory.objects.get(code="MOXA2")
        resp = self.client.get(reverse("services:list"),
                              {"category": category.pk, "sort": "price_desc"})
        prices = [s.price for s in resp.context["services"]]
        self.assertEqual(prices, sorted(prices, reverse=True))
        self.assertTrue(all(s.category_id == category.pk for s in resp.context["services"]))
