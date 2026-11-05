"""学生 4（服务预约管理）测试用例。

覆盖：① 预约任务/记录处理；② 审核、确认与状态流转；③ 异常备注、附件上传与历史追踪。
运行：python manage.py test appointments
"""
from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.test_factory import make_member, make_package, make_service, make_user
from core.timeutil import local_today
from appointments.models import Appointment, AppointmentAttachment, AppointmentHistory
from orders.models import Order, OrderItem


class AppointmentCreateTests(TestCase):
    """① 服务预约任务/记录处理。"""

    def setUp(self):
        self.staff = make_user(username="appt_staff", role="therapist")
        self.staff.is_superuser = True
        self.staff.save()
        self.client.force_login(self.staff)
        self.member = make_member(phone="13900000081")
        self.service = make_service(code="AP001", name="预约测试服务", duration=60)

    def test_create_appointment_generates_no_and_history(self):
        resp = self.client.post(reverse("appointments:create"), {
            "member": self.member.pk, "service": self.service.pk,
            "therapist": self.staff.pk, "appoint_date": local_today().isoformat(),
            "appoint_time": "10:00", "duration": 60, "source": "phone",
            "contact_phone": "", "remark": "肩颈不适",
        })
        appt = Appointment.objects.latest("id")
        self.assertRedirects(resp, reverse("appointments:detail", args=[appt.pk]))
        self.assertTrue(appt.appointment_no.startswith("YY"))
        self.assertEqual(appt.status, "pending")
        self.assertEqual(appt.contact_phone, self.member.phone)  # 自动带出会员手机号
        self.assertEqual(appt.history.count(), 1)
        self.assertEqual(appt.history.first().action, "创建预约")

    def test_past_date_rejected(self):
        from datetime import timedelta

        resp = self.client.post(reverse("appointments:create"), {
            "member": self.member.pk, "service": self.service.pk,
            "therapist": self.staff.pk,
            "appoint_date": (local_today() - timedelta(days=1)).isoformat(),
            "appoint_time": "10:00", "duration": 60, "source": "phone",
            "contact_phone": "", "remark": "",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "预约日期不能早于今天")

    def test_therapist_time_conflict_rejected(self):
        payload = {
            "member": self.member.pk, "service": self.service.pk,
            "therapist": self.staff.pk, "appoint_date": local_today().isoformat(),
            "appoint_time": "14:30", "duration": 60, "source": "onsite",
            "contact_phone": "", "remark": "",
        }
        self.client.post(reverse("appointments:create"), payload)
        resp = self.client.post(reverse("appointments:create"), payload)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "该顾问在此时段已有预约")

    def test_list_filter_by_status_and_keyword(self):
        Appointment.objects.create(
            appointment_no="YY202611040001", member=self.member, service=self.service,
            therapist=self.staff, appoint_date=local_today(), appoint_time="09:00",
            status="pending", created_by=self.staff,
        )
        resp = self.client.get(reverse("appointments:list"), {"status": "pending"})
        self.assertEqual(resp.context["total"], 1)
        resp = self.client.get(reverse("appointments:list"), {"keyword": self.member.name})
        self.assertEqual(resp.context["total"], 1)
        resp = self.client.get(reverse("appointments:list"), {"status": "finished"})
        self.assertEqual(resp.context["total"], 0)


class AppointmentTransitionTests(TestCase):
    """② 审核、确认或状态流转。"""

    def setUp(self):
        self.staff = make_user(username="appt_manager", role="service_manager")
        self.staff.is_superuser = True
        self.staff.save()
        self.client.force_login(self.staff)
        self.member = make_member(phone="13900000082")
        self.service = make_service(code="AP002", duration=45)
        self.appt = Appointment.objects.create(
            appointment_no="YY202611040002", member=self.member, service=self.service,
            therapist=self.staff, appoint_date=local_today(), appoint_time="11:00",
            status="pending", created_by=self.staff,
        )

    def test_full_status_flow(self):
        for action, expected in [("confirm", "confirmed"), ("start", "servicing"),
                                 ("finish", "finished")]:
            resp = self.client.post(reverse("appointments:transition", args=[self.appt.pk]),
                                    {"action": action, "note": f"执行 {action}"})
            self.assertRedirects(resp, reverse("appointments:detail", args=[self.appt.pk]))
            self.appt.refresh_from_db()
            self.assertEqual(self.appt.status, expected)

        self.assertIsNotNone(self.appt.confirmed_at)
        self.assertIsNotNone(self.appt.finished_at)
        self.assertEqual(self.appt.confirmed_by, self.staff)
        self.assertEqual(self.appt.history.count(), 3)

    def test_illegal_action_rejected(self):
        resp = self.client.post(reverse("appointments:transition", args=[self.appt.pk]),
                                {"action": "finish"}, follow=True)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, "pending")
        self.assertContains(resp, "不能执行")

    def test_confirm_requires_review_permission(self):
        reviewer = make_user(username="appt_reviewer", role="therapist")
        group = Group.objects.create(name="可改不可审")
        group.permissions.set(Permission.objects.filter(
            content_type__app_label="appointments", codename__in=["view_appointment", "change_appointment"]))
        reviewer.groups.add(group)
        self.client.force_login(reviewer)
        resp = self.client.post(reverse("appointments:transition", args=[self.appt.pk]),
                                {"action": "confirm"}, follow=True)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, "pending")
        self.assertContains(resp, "缺少「审核服务预约」权限")

    def test_finish_deducts_package_times(self):
        order = Order.objects.create(
            order_no="TK202611040009", member=self.member,
            package=make_package(code="AP-PKG"), quantity=1, unit_price=Decimal("900"),
            total_amount=Decimal("900"), pay_amount=Decimal("900"), status="servicing",
        )
        item = OrderItem.objects.create(order=order, service=self.service,
                                        times_total=5, times_used=1, unit_price=Decimal("180"))
        self.appt.order_item = item
        self.appt.save(update_fields=["order_item"])

        self.client.post(reverse("appointments:transition", args=[self.appt.pk]), {"action": "confirm"})
        self.client.post(reverse("appointments:transition", args=[self.appt.pk]), {"action": "start"})
        self.client.post(reverse("appointments:transition", args=[self.appt.pk]), {"action": "finish"})
        item.refresh_from_db()
        self.assertEqual(item.times_used, 2)

    def test_cancel_records_reason(self):
        self.client.post(reverse("appointments:transition", args=[self.appt.pk]),
                         {"action": "cancel", "note": "会员临时有事"})
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, "cancelled")
        self.assertEqual(self.appt.cancelled_reason, "会员临时有事")


@override_settings(MEDIA_ROOT="media_test")
class AppointmentTrackingTests(TestCase):
    """③ 异常备注、附件上传与历史记录追踪。"""

    def setUp(self):
        self.staff = make_user(username="appt_track", role="therapist")
        self.staff.is_superuser = True
        self.staff.save()
        self.client.force_login(self.staff)
        self.member = make_member(phone="13900000083")
        self.service = make_service(code="AP003")
        self.appt = Appointment.objects.create(
            appointment_no="YY202611040003", member=self.member, service=self.service,
            therapist=self.staff, appoint_date=local_today(), appoint_time="15:30",
            status="confirmed", created_by=self.staff,
        )

    def tearDown(self):
        import shutil
        from pathlib import Path

        shutil.rmtree(Path("media_test"), ignore_errors=True)

    def test_exception_note_saved_and_tracked(self):
        resp = self.client.post(reverse("appointments:note", args=[self.appt.pk]), {
            "exception_level": "urgent",
            "exception_note": "服务中出现头晕，已停止并观察",
        })
        self.assertRedirects(resp, reverse("appointments:detail", args=[self.appt.pk]))
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.exception_level, "urgent")
        self.assertIn("头晕", self.appt.exception_note)
        self.assertTrue(AppointmentHistory.objects.filter(
            appointment=self.appt, action="更新异常备注").exists())

    def test_attachment_upload_and_delete(self):
        upload = SimpleUploadedFile("report.txt", b"blood pressure ok", content_type="text/plain")
        resp = self.client.post(reverse("appointments:attachment_upload", args=[self.appt.pk]),
                                {"file": upload, "note": "体检报告"})
        self.assertRedirects(resp, reverse("appointments:detail", args=[self.appt.pk]))
        att = AppointmentAttachment.objects.get(appointment=self.appt)
        self.assertEqual(att.original_name, "report.txt")
        self.assertGreater(att.size, 0)
        self.assertTrue(AppointmentHistory.objects.filter(
            appointment=self.appt, action="上传附件").exists())

        resp = self.client.post(reverse("appointments:attachment_delete", args=[att.pk]))
        self.assertRedirects(resp, reverse("appointments:detail", args=[self.appt.pk]))
        self.assertFalse(AppointmentAttachment.objects.filter(pk=att.pk).exists())

    def test_invalid_extension_rejected(self):
        bad = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream")
        resp = self.client.post(reverse("appointments:attachment_upload", args=[self.appt.pk]),
                                {"file": bad, "note": ""}, follow=True)
        self.assertContains(resp, "不支持的文件类型")
        self.assertEqual(AppointmentAttachment.objects.count(), 0)

    def test_detail_page_shows_history_and_attachments(self):
        AppointmentHistory.objects.create(appointment=self.appt, action="创建预约",
                                          operator=self.staff, note="初始记录")
        resp = self.client.get(reverse("appointments:detail", args=[self.appt.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["history"]), 1)
        self.assertIn("attachments", resp.context)
