"""学生 3（套餐订单管理）测试用例。

覆盖：① 订单业务记录创建；② 订单明细数据维护；③ 订单记录查询与状态查看。
运行：python manage.py test orders
"""
from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from accounts.models import Member
from core.test_factory import make_member, make_package, make_service, make_user
from orders.models import Order, OrderItem, OrderStatusHistory


class OrderCreateTests(TestCase):
    """① 套餐订单业务记录创建。"""

    def setUp(self):
        self.admin = make_user(username="order_admin", role="order_clerk")
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)
        self.member = make_member(phone="13800000081", level="gold")
        s1 = make_service(code="OS001", name="推拿A", price="200.00", member_price="180.00")
        s2 = make_service(code="OS002", name="艾灸B", price="300.00", member_price="280.00")
        self.package = make_package(code="OP001", name="组合套餐", services=[(s1, 6), (s2, 4)])

    def test_create_order_expands_items_and_amount(self):
        resp = self.client.post(reverse("orders:create"), {
            "member": self.member.pk, "package": self.package.pk,
            "quantity": 2, "discount_amount": "100.00", "remark": "测试下单",
        })
        order = Order.objects.latest("id")
        self.assertRedirects(resp, reverse("orders:detail", args=[order.pk]))
        self.assertTrue(order.order_no.startswith("TK"))
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.items.count(), 2)

        gold_discount = Decimal("0.90")
        expected = (Decimal("180.00") * 6 * 2 + Decimal("280.00") * 4 * 2) * gold_discount
        self.assertEqual(order.total_amount, expected.quantize(Decimal("0.01")))
        self.assertEqual(order.pay_amount, (expected - Decimal("100.00")).quantize(Decimal("0.01")))
        self.assertEqual(order.items.first().times_total, 12)
        self.assertTrue(OrderStatusHistory.objects.filter(order=order, note__contains="创建订单").exists())

    def test_quantity_and_discount_validation(self):
        bad_qty = self.client.post(reverse("orders:create"), {
            "member": self.member.pk, "package": self.package.pk, "quantity": 50,
            "discount_amount": "0", "remark": "",
        })
        self.assertEqual(bad_qty.status_code, 200)
        self.assertContains(bad_qty, "购买数量需在 1-20 之间")

        bad_discount = self.client.post(reverse("orders:create"), {
            "member": self.member.pk, "package": self.package.pk, "quantity": 1,
            "discount_amount": "-5", "remark": "",
        })
        self.assertContains(bad_discount, "优惠金额不能为负")


class OrderItemTests(TestCase):
    """② 订单明细数据维护。"""

    def setUp(self):
        self.admin = make_user(username="item_admin", role="order_clerk")
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)
        self.member = make_member(phone="13800000082", level="bronze")
        self.service_a = make_service(code="OI001", name="明细服务A", member_price="100.00")
        self.service_b = make_service(code="OI002", name="明细服务B", member_price="200.00")
        self.package = make_package(code="OP002", services=[(self.service_a, 5)])
        self.order = self._create_order()

    def _create_order(self):
        self.client.post(reverse("orders:create"), {
            "member": self.member.pk, "package": self.package.pk,
            "quantity": 1, "discount_amount": "0", "remark": "",
        })
        return Order.objects.latest("id")

    def test_add_item_and_recalc(self):
        resp = self.client.post(reverse("orders:item_add", args=[self.order.pk]), {
            "service": self.service_b.pk, "times_total": 3, "times_used": 0,
            "unit_price": "200.00", "remark": "追加",
        })
        self.assertRedirects(resp, reverse("orders:detail", args=[self.order.pk]))
        self.assertEqual(self.order.items.count(), 2)
        self.order.refresh_from_db()
        self.assertEqual(self.order.total_amount, Decimal("1100.00"))

    def test_duplicate_service_rejected(self):
        resp = self.client.post(reverse("orders:item_add", args=[self.order.pk]), {
            "service": self.service_a.pk, "times_total": 2, "times_used": 0,
            "unit_price": "100.00", "remark": "",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "该服务已在订单明细中")

    def test_update_item_times_used_cannot_exceed_total(self):
        item = self.order.items.first()
        resp = self.client.post(reverse("orders:item_update", args=[item.pk]), {
            "service": item.service.pk, "times_total": 2, "times_used": 5,
            "unit_price": "100.00", "remark": "",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "已用次数不能超过购买次数")

    def test_update_item_recalculates_amount(self):
        item = self.order.items.first()
        resp = self.client.post(reverse("orders:item_update", args=[item.pk]), {
            "service": item.service.pk, "times_total": 10, "times_used": 2,
            "unit_price": "100.00", "remark": "加购",
        })
        self.assertRedirects(resp, reverse("orders:detail", args=[self.order.pk]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.total_amount, Decimal("1000.00"))

    def test_delete_last_item_is_blocked(self):
        item = self.order.items.first()
        self.client.post(reverse("orders:item_delete", args=[item.pk]))
        self.assertEqual(self.order.items.count(), 1)


class OrderQueryAndStatusTests(TestCase):
    """③ 订单记录查询与状态查看。"""

    def setUp(self):
        self.admin = make_user(username="query_admin", role="order_clerk")
        self.admin.is_superuser = True
        self.admin.save()
        self.member = make_member(name="订单会员", phone="13800000083", points=0)
        self.package = make_package(code="OP003", services=[(make_service(code="OQ001"), 3)])
        self.order = Order.objects.create(
            order_no="TK202611040001", member=self.member, package=self.package,
            quantity=1, unit_price=Decimal("900.00"), total_amount=Decimal("900.00"),
            pay_amount=Decimal("900.00"), status="pending", salesperson=self.admin,
        )
        OrderItem.objects.create(order=self.order, service=self.package.items.first().service,
                                 times_total=3, unit_price=Decimal("300.00"))
        self.client.force_login(self.admin)

    def test_detail_page_shows_items_and_status(self):
        resp = self.client.get(reverse("orders:detail", args=[self.order.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.order.order_no)
        self.assertEqual(resp.context["items"].count(), 1)
        self.assertTrue(resp.context["next_status"])

    def test_list_query_by_keyword_and_status(self):
        resp = self.client.get(reverse("orders:list"), {"keyword": self.order.order_no})
        self.assertEqual(resp.context["total"], 1)
        resp = self.client.get(reverse("orders:list"), {"status": "paid"})
        self.assertEqual(resp.context["total"], 0)

    def test_status_transition_paid_then_servicing(self):
        resp = self.client.post(reverse("orders:status", args=[self.order.pk]), {"to_status": "paid"})
        self.assertRedirects(resp, reverse("orders:detail", args=[self.order.pk]))
        self.order.refresh_from_db()
        self.member.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        self.assertIsNotNone(self.order.paid_at)
        self.assertEqual(self.member.points, 900)  # 付款送等额积分
        self.assertTrue(OrderStatusHistory.objects.filter(
            order=self.order, to_status="paid").exists())

    def test_illegal_transition_rejected(self):
        resp = self.client.post(reverse("orders:status", args=[self.order.pk]),
                                {"to_status": "completed"}, follow=True)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending")
        self.assertContains(resp, "不允许从")

    def test_status_change_requires_permission(self):
        user = make_user(username="no_perm_clerk", role="order_clerk")
        group = Group.objects.create(name="只读订单")
        group.permissions.set(Permission.objects.filter(
            codename__in=["view_order"], content_type__app_label="orders"))
        user.groups.add(group)
        self.client.force_login(user)
        resp = self.client.post(reverse("orders:status", args=[self.order.pk]), {"to_status": "paid"})
        self.assertEqual(resp.status_code, 403)
