"""学生 3 表单：订单创建与明细维护。"""
from decimal import Decimal

from django import forms

from accounts.models import Member
from services.models import HealthService

from .models import Order, OrderItem, Package


class BaseStyledForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "form-select"
            else:
                widget.attrs["class"] = "form-control"
            if isinstance(widget, forms.NumberInput):
                widget.attrs.setdefault("step", "0.01")


class OrderCreateForm(BaseStyledForm):
    """① 创建套餐订单业务记录。"""

    class Meta:
        model = Order
        fields = ["member", "package", "quantity", "discount_amount", "remark"]
        widgets = {"remark": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].queryset = Member.objects.filter(is_active=True).order_by("name")
        self.fields["package"].queryset = Package.objects.filter(status="on").prefetch_related("items__service")
        self.fields["member"].label = "购买会员"
        self.fields["package"].label = "养生套餐"
        self.fields["quantity"].initial = 1
        self.fields["discount_amount"].initial = 0
        self.fields["quantity"].widget.attrs.update({"min": 1, "max": 20})
        self.fields["discount_amount"].widget.attrs.update({"min": 0})

    def clean_quantity(self):
        qty = self.cleaned_data["quantity"]
        if qty < 1 or qty > 20:
            raise forms.ValidationError("购买数量需在 1-20 之间")
        return qty

    def clean_discount_amount(self):
        amount = self.cleaned_data.get("discount_amount") or Decimal("0.00")
        if amount < 0:
            raise forms.ValidationError("优惠金额不能为负")
        return amount


class OrderItemForm(BaseStyledForm):
    """② 订单明细维护。"""

    class Meta:
        model = OrderItem
        fields = ["service", "times_total", "times_used", "unit_price", "remark"]

    def __init__(self, *args, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.order = order or (self.instance.order if self.instance.pk else None)
        self.fields["service"].queryset = HealthService.objects.filter(status="on").order_by("name")
        for f in ("times_total", "times_used"):
            self.fields[f].widget.attrs.update({"min": 0})
        self.fields["unit_price"].widget.attrs.update({"min": 0})

    def clean(self):
        data = super().clean()
        service, total, used = data.get("service"), data.get("times_total"), data.get("times_used")
        if self.order and service:
            qs = OrderItem.objects.filter(order=self.order, service=service)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("service", "该服务已在订单明细中，请直接修改原明细")
        if total is not None and used is not None and used > total:
            self.add_error("times_used", "已用次数不能超过购买次数")
        if total is not None and total <= 0:
            self.add_error("times_total", "购买次数必须大于 0")
        return data
