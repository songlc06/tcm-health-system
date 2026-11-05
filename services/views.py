"""学生 2：养生服务管理（新增、编辑/删除/详情、列表分页与筛选）。"""
import csv

from django import forms
from django.contrib import messages
from django.db.models import Count, ProtectedError, Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from core.mixins import PermRequiredMixin
from core.utils import paginate, record_log

from .models import HealthService, ServiceCategory, ServicePriceHistory


class ServiceForm(forms.ModelForm):
    class Meta:
        model = HealthService
        fields = ["code", "name", "category", "summary", "description", "duration", "price",
                  "member_price", "suitable_for", "contraindication", "status", "is_hot", "sort_order"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

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

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        qs = HealthService.objects.filter(code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("服务编码已存在")
        return code

    def clean(self):
        data = super().clean()
        price, member_price = data.get("price"), data.get("member_price")
        if price is not None and price <= 0:
            self.add_error("price", "标准价必须大于 0")
        if price is not None and member_price is not None and member_price > price:
            self.add_error("member_price", "会员价不能高于标准价")
        duration = data.get("duration")
        if duration is not None and not (10 <= duration <= 480):
            self.add_error("duration", "服务时长需在 10-480 分钟之间")
        return data


class ServiceListView(PermRequiredMixin, ListView):
    """③ 列表分页 + 关键字/分类/状态/价格区间筛选。"""

    model = HealthService
    template_name = "services/service_list.html"
    permission_required = "services.view_healthservice"
    context_object_name = "services"

    def get_queryset(self):
        qs = HealthService.objects.select_related("category").annotate(
            package_count=Count("package_items", distinct=True)
        )
        keyword = self.request.GET.get("keyword", "").strip()
        category = self.request.GET.get("category", "").strip()
        status = self.request.GET.get("status", "").strip()
        price_min = self.request.GET.get("price_min", "").strip()
        price_max = self.request.GET.get("price_max", "").strip()
        sort = self.request.GET.get("sort", "").strip()

        if keyword:
            qs = qs.filter(
                Q(name__icontains=keyword) | Q(code__icontains=keyword)
                | Q(summary__icontains=keyword) | Q(suitable_for__icontains=keyword)
            )
        if category:
            qs = qs.filter(category_id=category)
        if status:
            qs = qs.filter(status=status)
        if price_min.replace(".", "", 1).isdigit():
            qs = qs.filter(price__gte=price_min)
        if price_max.replace(".", "", 1).isdigit():
            qs = qs.filter(price__lte=price_max)

        sort_map = {
            "price_asc": "price", "price_desc": "-price",
            "new": "-created_at", "duration": "duration",
        }
        return qs.order_by(sort_map.get(sort, "sort_order"), "-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_obj"] = paginate(self.request, self.get_queryset(), 8)
        ctx["services"] = ctx["page_obj"]
        ctx["categories"] = ServiceCategory.objects.filter(is_active=True)
        ctx["total"] = self.get_queryset().count()
        ctx["query"] = self.request.GET
        ctx["keyword"] = self.request.GET.get("keyword", "")
        ctx["category_id"] = self.request.GET.get("category", "")
        ctx["status"] = self.request.GET.get("status", "")
        ctx["price_min"] = self.request.GET.get("price_min", "")
        ctx["price_max"] = self.request.GET.get("price_max", "")
        ctx["sort"] = self.request.GET.get("sort", "")
        ctx["on_count"] = HealthService.objects.filter(status="on").count()
        ctx["off_count"] = HealthService.objects.filter(status="off").count()
        return ctx


class ServiceCreateView(PermRequiredMixin, CreateView):
    """① 新增养生服务。"""

    model = HealthService
    form_class = ServiceForm
    template_name = "services/service_form.html"
    permission_required = "services.add_healthservice"
    success_url = reverse_lazy("services:list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "新增养生服务"
        return ctx

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        record_log(self.request, "新增养生服务", target_type="HealthService", target_id=self.object.pk,
                   target_repr=f"{self.object.name}({self.object.code})",
                   detail=f"分类：{self.object.category.name}；价格：{self.object.price} 元；时长：{self.object.duration} 分钟")
        messages.success(self.request, f"服务「{self.object.name}」已创建")
        return response


class ServiceUpdateView(PermRequiredMixin, UpdateView):
    """② 编辑养生服务，价格变化自动留痕。"""

    model = HealthService
    form_class = ServiceForm
    template_name = "services/service_form.html"
    permission_required = "services.change_healthservice"
    success_url = reverse_lazy("services:list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = f"编辑服务 · {self.object.name}"
        ctx["price_history"] = self.object.price_history.select_related("changed_by")[:5]
        return ctx

    def form_valid(self, form):
        old = HealthService.objects.get(pk=self.object.pk)
        old_price, old_member_price = old.price, old.member_price
        response = super().form_valid(form)
        if (old_price, old_member_price) != (self.object.price, self.object.member_price):
            ServicePriceHistory.objects.create(
                service=self.object, old_price=old_price, new_price=self.object.price,
                old_member_price=old_member_price, new_member_price=self.object.member_price,
                changed_by=self.request.user,
            )
        record_log(self.request, "编辑养生服务", target_type="HealthService", target_id=self.object.pk,
                   target_repr=f"{self.object.name}({self.object.code})",
                   detail=f"状态：{self.object.get_status_display()}；价格：{old_price}→{self.object.price}")
        messages.success(self.request, "服务信息已保存")
        return response


class ServiceDetailView(PermRequiredMixin, DetailView):
    """② 详情查看：基本信息 + 套餐引用 + 预约记录。"""

    model = HealthService
    template_name = "services/service_detail.html"
    permission_required = "services.view_healthservice"
    context_object_name = "service"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["package_items"] = self.object.package_items.select_related("package")
        ctx["appointments"] = self.object.appointments.select_related("member", "therapist")[:8]
        ctx["price_history"] = self.object.price_history.select_related("changed_by")[:8]
        ctx["appointment_count"] = self.object.appointments.count()
        return ctx


class ServiceDeleteView(PermRequiredMixin, DeleteView):
    """② 删除养生服务（被套餐/订单/预约引用时禁止物理删除，提示改为下架）。"""

    model = HealthService
    template_name = "services/service_confirm_delete.html"
    permission_required = "services.delete_healthservice"
    success_url = reverse_lazy("services:list")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        name, pk = self.object.name, self.object.pk
        try:
            self.object.delete()
        except ProtectedError:
            messages.error(request, f"「{name}」已被套餐/订单/预约引用，无法删除，建议修改状态为“下架”")
            return redirect("services:detail", pk=pk)
        record_log(request, "删除养生服务", target_type="HealthService", target_id=pk,
                   target_repr=name, detail="物理删除服务项目")
        messages.success(request, f"服务「{name}」已删除")
        return redirect(self.success_url)


class ServiceExportView(PermRequiredMixin, View):
    """辅助：服务清单导出 CSV（接口权限控制）。"""

    permission_required = "services.export_healthservice"

    def get(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = 'attachment; filename="health_services.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["服务编码", "服务名称", "分类", "时长(分钟)", "标准价", "会员价", "状态", "创建时间"])
        qs = HealthService.objects.select_related("category")
        keyword = request.GET.get("keyword", "").strip()
        if keyword:
            qs = qs.filter(Q(name__icontains=keyword) | Q(code__icontains=keyword))
        for s in qs:
            writer.writerow([s.code, s.name, s.category.name, s.duration, s.price, s.member_price,
                             s.get_status_display(), s.created_at.strftime("%Y-%m-%d %H:%M")])
        record_log(request, "导出养生服务", category="query", target_type="HealthService",
                   detail=f"导出 {qs.count()} 条服务记录")
        return response
