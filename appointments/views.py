"""学生 4：服务预约管理（记录处理、审核确认与状态流转、异常备注/附件/历史追踪）。"""
import csv

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView
from core.timeutil import local_today

from core.mixins import PermRequiredMixin
from core.utils import generate_business_no, paginate, parse_date, record_log, validate_upload

from .forms import AppointmentForm, AttachmentForm, ExceptionNoteForm
from .models import Appointment, AppointmentAttachment, AppointmentHistory


class AppointmentListView(PermRequiredMixin, ListView):
    """① 预约任务列表：状态、日期、会员、顾问、来源多条件筛选。"""

    model = Appointment
    template_name = "appointments/appointment_list.html"
    permission_required = "appointments.view_appointment"
    context_object_name = "appointments"

    def get_queryset(self):
        qs = Appointment.objects.select_related("member", "service", "therapist", "confirmed_by")
        keyword = self.request.GET.get("keyword", "").strip()
        status = self.request.GET.get("status", "").strip()
        date_from = parse_date(self.request.GET.get("date_from"))
        date_to = parse_date(self.request.GET.get("date_to"))
        therapist_id = self.request.GET.get("therapist", "").strip()
        source = self.request.GET.get("source", "").strip()

        if keyword:
            qs = qs.filter(
                Q(appointment_no__icontains=keyword) | Q(member__name__icontains=keyword)
                | Q(member__phone__icontains=keyword) | Q(service__name__icontains=keyword)
            )
        if status:
            qs = qs.filter(status=status)
        if date_from:
            qs = qs.filter(appoint_date__gte=date_from)
        if date_to:
            qs = qs.filter(appoint_date__lte=date_to)
        if therapist_id.isdigit():
            qs = qs.filter(therapist_id=therapist_id)
        if source:
            qs = qs.filter(source=source)
        return qs.order_by("-appoint_date", "appoint_time")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        ctx["page_obj"] = paginate(self.request, qs, 8)
        ctx["appointments"] = ctx["page_obj"]
        ctx["status_choices"] = Appointment.STATUS_CHOICES
        ctx["sources"] = Appointment.SOURCE_CHOICES
        from accounts.models import User

        ctx["therapists"] = User.objects.filter(role__in=["therapist", "admin"], is_active=True)
        ctx["keyword"] = self.request.GET.get("keyword", "")
        ctx["status"] = self.request.GET.get("status", "")
        ctx["date_from"] = self.request.GET.get("date_from", "")
        ctx["date_to"] = self.request.GET.get("date_to", "")
        ctx["therapist_id"] = self.request.GET.get("therapist", "")
        ctx["source"] = self.request.GET.get("source", "")
        ctx["total"] = qs.count()
        ctx["pending_count"] = Appointment.objects.filter(status="pending").count()
        ctx["today_count"] = Appointment.objects.filter(appoint_date=local_today()).count()
        ctx["status_counts"] = {row["status"]: row["c"] for row in
                                qs.values("status").annotate(c=Count("id"))}
        return ctx


class AppointmentCreateView(PermRequiredMixin, CreateView):
    """① 预约登记：保存后写入处理记录并预占时段。"""

    model = Appointment
    form_class = AppointmentForm
    template_name = "appointments/appointment_form.html"
    permission_required = "appointments.add_appointment"
    success_url = reverse_lazy("appointments:list")

    def get_initial(self):
        initial = super().get_initial()
        member_id = self.request.GET.get("member")
        if member_id and member_id.isdigit():
            initial["member"] = member_id
        item_id = self.request.GET.get("order_item")
        if item_id and item_id.isdigit():
            initial["order_item"] = item_id
        return initial

    @transaction.atomic
    def form_valid(self, form):
        appt = form.save(commit=False)
        appt.appointment_no = generate_business_no("YY", Appointment, "appointment_no")
        appt.created_by = self.request.user
        appt.contact_phone = appt.contact_phone or appt.member.phone
        appt.save()
        AppointmentHistory.objects.create(
            appointment=appt, from_status="", to_status=appt.status, action="创建预约",
            operator=self.request.user,
            note=f"{appt.appoint_date} {appt.appoint_time} {appt.service.name}",
        )
        record_log(self.request, "创建服务预约", target_type="Appointment", target_id=appt.appointment_no,
                   target_repr=appt.appointment_no,
                   detail=f"会员：{appt.member.name}；服务：{appt.service.name}；"
                          f"时间：{appt.appoint_date} {appt.appoint_time}")
        messages.success(self.request, f"预约单 {appt.appointment_no} 已创建，等待审核确认")
        return redirect("appointments:detail", pk=appt.pk)


class AppointmentDetailView(PermRequiredMixin, DetailView):
    """③ 预约详情：状态流转 + 异常备注 + 附件 + 全量历史。"""

    model = Appointment
    template_name = "appointments/appointment_detail.html"
    permission_required = "appointments.view_appointment"
    context_object_name = "appointment"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["history"] = self.object.history.select_related("operator")
        ctx["attachments"] = self.object.attachments.select_related("uploaded_by")
        ctx["actions"] = self.object.allowed_actions()
        ctx["note_form"] = ExceptionNoteForm(instance=self.object)
        ctx["attachment_form"] = AttachmentForm()
        ctx["status_choices"] = Appointment.STATUS_CHOICES
        return ctx


# 动作码 -> (目标状态, 动作名称, 是否需要审核权限)
TRANSITIONS = {
    "confirm": ("confirmed", "审核确认", True),
    "start": ("servicing", "开始服务", False),
    "finish": ("finished", "完成服务", False),
    "cancel": ("cancelled", "取消预约", False),
    "no_show": ("no_show", "标记爽约", False),
}


class AppointmentTransitionView(PermRequiredMixin, View):
    """② 审核、确认与状态流转，全流程留痕；完成时自动核销套餐次数。"""

    permission_required = "appointments.change_appointment"

    @transaction.atomic
    def post(self, request, pk):
        appt = get_object_or_404(Appointment, pk=pk)
        action = request.POST.get("action", "")
        note = request.POST.get("note", "").strip()
        if action not in TRANSITIONS:
            messages.error(request, "未知的操作")
            return redirect("appointments:detail", pk=pk)

        target, action_name, need_review = TRANSITIONS[action]
        if target not in Appointment.STATUS_FLOW.get(appt.status, []):
            messages.error(request, f"当前状态「{appt.get_status_display()}」不能执行「{action_name}」")
            return redirect("appointments:detail", pk=pk)
        if need_review and not request.user.has_perm("appointments.review_appointment"):
            messages.error(request, "缺少「审核服务预约」权限，无法确认预约")
            return redirect("appointments:detail", pk=pk)

        old_status = appt.status
        old_label = appt.get_status_display()
        appt.status = target
        update_fields = ["status", "updated_at"]

        if target == "confirmed":
            appt.confirmed_by = request.user
            appt.confirmed_at = timezone.now()
            update_fields += ["confirmed_by", "confirmed_at"]
        if target == "finished":
            appt.finished_at = timezone.now()
            update_fields.append("finished_at")
            if appt.order_item_id:
                item = appt.order_item
                if item.times_used < item.times_total:
                    item.times_used += 1
                    item.save(update_fields=["times_used"])
        if target == "cancelled":
            appt.cancelled_reason = note[:200]
            update_fields.append("cancelled_reason")

        appt.save(update_fields=update_fields)
        AppointmentHistory.objects.create(
            appointment=appt, from_status=old_status, to_status=target,
            action=action_name, operator=request.user, note=note or "—",
        )
        record_log(request, f"预约{action_name}", target_type="Appointment",
                   target_id=appt.appointment_no, target_repr=appt.appointment_no,
                   detail=f"{old_label} → {appt.get_status_display()}；备注：{note or '无'}")
        messages.success(request, f"预约状态：{old_label} → {appt.get_status_display()}")
        return redirect("appointments:detail", pk=pk)


class AppointmentNoteView(PermRequiredMixin, View):
    """③ 异常备注维护。"""

    permission_required = "appointments.change_appointment"

    def post(self, request, pk):
        appt = get_object_or_404(Appointment, pk=pk)
        form = ExceptionNoteForm(request.POST, instance=appt)
        if not form.is_valid():
            messages.error(request, "异常备注保存失败，请检查填写内容")
            return redirect("appointments:detail", pk=pk)
        form.save()
        AppointmentHistory.objects.create(
            appointment=appt, from_status=appt.status, to_status=appt.status,
            action="更新异常备注", operator=request.user,
            note=f"[{appt.get_exception_level_display()}] {appt.exception_note}",
        )
        record_log(request, "更新预约异常备注", target_type="Appointment",
                   target_id=appt.appointment_no, target_repr=appt.appointment_no,
                   detail=f"等级：{appt.get_exception_level_display()}；内容：{appt.exception_note[:120]}")
        messages.success(request, "异常备注已保存")
        return redirect("appointments:detail", pk=pk)


class AppointmentAttachmentUploadView(PermRequiredMixin, View):
    """③ 附件上传（类型/大小校验）。"""

    permission_required = "appointments.change_appointment"

    def post(self, request, pk):
        appt = get_object_or_404(Appointment, pk=pk)
        upload = request.FILES.get("file")
        ok, msg = validate_upload(upload)
        if not ok:
            messages.error(request, msg)
            return redirect("appointments:detail", pk=pk)

        att = AppointmentAttachment.objects.create(
            appointment=appt, file=upload, original_name=upload.name,
            size=upload.size, content_type=upload.content_type or "",
            note=request.POST.get("note", "")[:100], uploaded_by=request.user,
        )
        AppointmentHistory.objects.create(
            appointment=appt, from_status=appt.status, to_status=appt.status,
            action="上传附件", operator=request.user, note=att.original_name,
        )
        record_log(request, "上传预约附件", target_type="Appointment",
                   target_id=appt.appointment_no, target_repr=appt.appointment_no,
                   detail=f"{att.original_name}（{att.size_kb} KB）")
        messages.success(request, f"附件「{att.original_name}」上传成功")
        return redirect("appointments:detail", pk=pk)


class AppointmentAttachmentDeleteView(PermRequiredMixin, View):
    """③ 删除附件（同时删除物理文件）。"""

    permission_required = "appointments.change_appointment"

    def post(self, request, pk):
        att = get_object_or_404(AppointmentAttachment, pk=pk)
        appt = att.appointment
        name = att.original_name
        if att.file:
            att.file.delete(save=False)
        att.delete()
        record_log(request, "删除预约附件", target_type="Appointment",
                   target_id=appt.appointment_no, target_repr=appt.appointment_no, detail=name)
        messages.success(request, f"附件「{name}」已删除")
        return redirect("appointments:detail", pk=appt.pk)


class AppointmentExportView(PermRequiredMixin, View):
    """导出预约数据（接口权限控制）。"""

    permission_required = "appointments.export_appointment"

    def get(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = 'attachment; filename="appointments.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["预约单号", "会员", "手机号", "服务项目", "预约日期", "时段",
                         "服务顾问", "状态", "来源", "异常等级", "异常备注", "创建时间"])
        qs = Appointment.objects.select_related("member", "service", "therapist")
        for a in qs:
            writer.writerow([a.appointment_no, a.member.name, a.member.phone, a.service.name,
                             a.appoint_date, a.appoint_time,
                             a.therapist.display_name if a.therapist else "",
                             a.get_status_display(), a.get_source_display(),
                             a.get_exception_level_display(), a.exception_note,
                             a.created_at.strftime("%Y-%m-%d %H:%M")])
        record_log(request, "导出预约数据", category="query", target_type="Appointment",
                   detail=f"导出 {qs.count()} 条预约")
        return response
