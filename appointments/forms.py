"""学生 4 表单：预约创建、异常备注、附件上传。"""
from django import forms
from django.utils import timezone
from core.timeutil import local_today

from accounts.models import Member, User
from services.models import HealthService

from .models import Appointment, AppointmentAttachment


class BaseStyledForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "form-select"
            elif isinstance(widget, forms.FileInput):
                widget.attrs["class"] = "form-control"
            else:
                widget.attrs["class"] = "form-control"
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 3)


class AppointmentForm(BaseStyledForm):
    """① 服务预约记录处理：创建预约单。"""

    class Meta:
        model = Appointment
        fields = ["member", "service", "order_item", "therapist", "appoint_date", "appoint_time",
                  "duration", "source", "contact_phone", "remark"]
        widgets = {
            "appoint_date": forms.DateInput(attrs={"type": "date"}),
            "remark": forms.Textarea(attrs={"rows": 3, "placeholder": "会员主要诉求、身体状况等"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].queryset = Member.objects.filter(is_active=True).order_by("name")
        self.fields["service"].queryset = HealthService.objects.filter(status="on").order_by("name")
        self.fields["therapist"].queryset = User.objects.filter(
            role__in=["therapist", "admin"], is_active=True).order_by("display_name")
        self.fields["order_item"].queryset = (
            self.fields["order_item"].queryset.select_related("order__member", "service")
        )
        self.fields["order_item"].label = "关联订单明细（套餐核销）"
        self.fields["order_item"].help_text = "选择套餐订单中的服务次数，完成后自动扣减"
        self.fields["appoint_date"].initial = local_today()

    def clean_appoint_date(self):
        date = self.cleaned_data["appoint_date"]
        if date < local_today():
            raise forms.ValidationError("预约日期不能早于今天")
        return date

    def clean(self):
        data = super().clean()
        member, service = data.get("member"), data.get("service")
        item = data.get("order_item")
        therapist = data.get("therapist")
        date, slot = data.get("appoint_date"), data.get("appoint_time")

        if item and member and item.order.member_id != member.id:
            self.add_error("order_item", "该订单明细不属于所选会员")
        if item and service and item.service_id != service.id:
            self.add_error("order_item", "订单明细的服务项目与所选服务不一致")
        if item and item.times_left <= 0:
            self.add_error("order_item", "该明细剩余次数不足，无法预约")

        if therapist and date and slot:
            conflict = Appointment.objects.filter(
                therapist=therapist, appoint_date=date, appoint_time=slot,
                status__in=["pending", "confirmed", "servicing"],
            )
            if self.instance.pk:
                conflict = conflict.exclude(pk=self.instance.pk)
            if conflict.exists():
                self.add_error("appoint_time", "该顾问在此时段已有预约，请更换时段或顾问")
        if service and data.get("duration") and data["duration"] > service.duration + 30:
            self.add_error("duration", f"预约时长不宜超过服务标准时长（{service.duration} 分钟）")
        return data


class ExceptionNoteForm(BaseStyledForm):
    """③ 异常备注维护。"""

    class Meta:
        model = Appointment
        fields = ["exception_level", "exception_note"]
        widgets = {"exception_note": forms.Textarea(
            attrs={"rows": 3, "placeholder": "如：会员迟到 20 分钟；服务中出现头晕，已停止并观察"})}


class AttachmentForm(forms.ModelForm):
    """③ 附件上传。"""

    class Meta:
        model = AppointmentAttachment
        fields = ["file", "note"]
        widgets = {"note": forms.TextInput(attrs={"placeholder": "如：体检报告、知情同意书"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].widget.attrs.update({"class": "form-control"})
        self.fields["note"].widget.attrs.update({"class": "form-control"})
