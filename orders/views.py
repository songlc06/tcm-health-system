"""学生 3：套餐订单管理（记录创建、明细维护、查询与状态查看）。"""
import csv
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from appointments.models import Appointment
from core.mixins import PermRequiredMixin
from core.utils import generate_business_no, paginate, parse_date, record_log

from .forms import OrderCreateForm, OrderItemForm
from .models import Order, OrderItem, OrderStatusHistory, Package


def _price_for(member, service):
    """明细单价：服务会员价为基础，再按会员等级折扣。"""
    base = service.member_price or service.price
    price = (Decimal(base) * Decimal(str(member.discount))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return price


class OrderListView(PermRequiredMixin, ListView):
    """③ 订单记录查询：单号/会员关键字 + 状态 + 套餐 + 时间范围，分页与汇总。"""

    model = Order
    template_name = "orders/order_list.html"
    permission_required = "orders.view_order"
    context_object_name = "orders"

    def get_queryset(self):
        qs = Order.objects.select_related("member", "package", "salesperson").annotate(
            item_count=Count("items", distinct=True)
        )
        keyword = self.request.GET.get("keyword", "").strip()
        status = self.request.GET.get("status", "").strip()
        package_id = self.request.GET.get("package", "").strip()
        date_from = parse_date(self.request.GET.get("date_from"))
        date_to = parse_date(self.request.GET.get("date_to"))

        if keyword:
            qs = qs.filter(
                Q(order_no__icontains=keyword) | Q(member__name__icontains=keyword)
                | Q(member__phone__icontains=keyword) | Q(member__member_no__icontains=keyword)
            )
        if status:
            qs = qs.filter(status=status)
        if package_id.isdigit():
            qs = qs.filter(package_id=package_id)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        ctx["page_obj"] = paginate(self.request, qs, 8)
        ctx["orders"] = ctx["page_obj"]
        ctx["packages"] = Package.objects.all()
        ctx["status_choices"] = Order.STATUS_CHOICES
        ctx["keyword"] = self.request.GET.get("keyword", "")
        ctx["status"] = self.request.GET.get("status", "")
        ctx["package_id"] = self.request.GET.get("package", "")
        ctx["date_from"] = self.request.GET.get("date_from", "")
        ctx["date_to"] = self.request.GET.get("date_to", "")
        ctx["total"] = qs.count()
        ctx["sum_amount"] = qs.aggregate(s=Sum("pay_amount"))["s"] or 0
        ctx["status_counts"] = {row["status"]: row["c"] for row in
                                qs.values("status").annotate(c=Count("id"))}
        return ctx


class OrderCreateView(PermRequiredMixin, CreateView):
    """① 创建订单：保存后按套餐自动展开明细并计算金额。"""

    model = Order
    form_class = OrderCreateForm
    template_name = "orders/order_form.html"
    permission_required = "orders.add_order"
    success_url = reverse_lazy("orders:list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        packages = Package.objects.filter(status="on").prefetch_related("items__service")
        ctx["package_payload"] = [
            {
                "id": p.id,
                "name": p.name,
                "price": float(p.member_price or p.price),
                "valid_days": p.valid_days,
                "items": [
                    {
                        "service": i.service.name,
                        "times": i.times,
                        "price": float(i.service.member_price or i.service.price),
                    }
                    for i in p.items.all()
                ],
            }
            for p in packages
        ]
        return ctx

    @transaction.atomic
    def form_valid(self, form):
        order = form.save(commit=False)
        order.order_no = generate_business_no("TK", Order)
        order.salesperson = self.request.user
        order.unit_price = order.package.sale_price
        order.save()

        for pi in order.package.items.select_related("service"):
            OrderItem.objects.create(
                order=order,
                service=pi.service,
                times_total=pi.times * order.quantity,
                unit_price=_price_for(order.member, pi.service),
                remark=pi.remark,
            )
        order.recalc()
        OrderStatusHistory.objects.create(
            order=order, from_status="", to_status=order.status, operator=self.request.user,
            note=f"创建订单，套餐「{order.package.name}」× {order.quantity}",
        )
        record_log(self.request, "创建套餐订单", target_type="Order", target_id=order.order_no,
                   target_repr=order.order_no,
                   detail=f"会员：{order.member.name}；套餐：{order.package.name}×{order.quantity}；"
                          f"应付：{order.pay_amount} 元")
        messages.success(self.request, f"订单 {order.order_no} 创建成功，共 {order.items.count()} 条明细")
        self.object = order
        return redirect("orders:detail", pk=order.pk)


class OrderDetailView(PermRequiredMixin, DetailView):
    """③ 订单详情与状态查看（含明细、状态时间轴、关联预约）。"""

    model = Order
    template_name = "orders/order_detail.html"
    permission_required = "orders.view_order"
    context_object_name = "order"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["items"] = self.object.items.select_related("service")
        ctx["history"] = self.object.history.select_related("operator")
        ctx["appointments"] = Appointment.objects.filter(
            order_item__order=self.object).select_related("service", "therapist", "member")
        action_labels = {
            "paid": ("确认收款", "primary"),
            "servicing": ("开始服务", "info"),
            "completed": ("完成订单", "success"),
            "cancelled": ("取消订单", "outline-secondary"),
            "refunded": ("办理退款", "danger"),
        }
        ctx["next_status"] = [
            {"value": s, "label": action_labels.get(s, (dict(Order.STATUS_CHOICES).get(s), "primary"))[0],
             "color": action_labels.get(s, ("", "primary"))[1]}
            for s in Order.STATUS_FLOW.get(self.object.status, [])
        ]
        ctx["status_choices"] = Order.STATUS_CHOICES
        return ctx


class OrderItemCreateView(PermRequiredMixin, CreateView):
    """② 追加订单明细。"""

    model = OrderItem
    form_class = OrderItemForm
    template_name = "orders/order_item_form.html"
    permission_required = "orders.change_order"

    def dispatch(self, request, *args, **kwargs):
        self.order = get_object_or_404(Order, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["order"] = self.order
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["order"] = self.order
        ctx["page_title"] = "追加订单明细"
        return ctx

    def form_valid(self, form):
        item = form.save(commit=False)
        item.order = self.order
        item.save()
        self.order.recalc()
        record_log(self.request, "新增订单明细", target_type="Order", target_id=self.order.order_no,
                   target_repr=self.order.order_no,
                   detail=f"{item.service.name} × {item.times_total}，单价 {item.unit_price}")
        messages.success(self.request, f"已追加明细：{item.service.name}")
        return redirect("orders:detail", pk=self.order.pk)


class OrderItemUpdateView(PermRequiredMixin, UpdateView):
    """② 维护订单明细（次数、已用次数、单价），并重算订单金额。"""

    model = OrderItem
    form_class = OrderItemForm
    template_name = "orders/order_item_form.html"
    permission_required = "orders.change_order"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["order"] = self.object.order
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["order"] = self.object.order
        ctx["page_title"] = f"维护明细 · {self.object.service.name}"
        return ctx

    def form_valid(self, form):
        # 明细没有独立详情页，保存后统一回到订单详情
        self.object = form.save()
        self.object.order.recalc()
        record_log(self.request, "修改订单明细", target_type="Order", target_id=self.object.order.order_no,
                   target_repr=self.object.order.order_no,
                   detail=f"{self.object.service.name}：{self.object.times_total} 次，已用 "
                          f"{self.object.times_used} 次，单价 {self.object.unit_price}")
        messages.success(self.request, "明细已更新，订单金额已重算")
        return redirect("orders:detail", pk=self.object.order.pk)


class OrderItemDeleteView(PermRequiredMixin, View):
    """② 删除订单明细（至少保留一条）。"""

    permission_required = "orders.change_order"

    def post(self, request, pk):
        item = get_object_or_404(OrderItem, pk=pk)
        order = item.order
        if order.items.count() <= 1:
            messages.error(request, "订单至少保留一条明细，无法删除")
            return redirect("orders:detail", pk=order.pk)
        name = item.service.name
        item.delete()
        order.recalc()
        record_log(request, "删除订单明细", target_type="Order", target_id=order.order_no,
                   target_repr=order.order_no, detail=f"删除明细：{name}")
        messages.success(request, f"明细「{name}」已删除")
        return redirect("orders:detail", pk=order.pk)


class OrderStatusUpdateView(PermRequiredMixin, View):
    """③ 订单状态流转（状态查看页上的操作按钮）。"""

    permission_required = "orders.change_order_status"

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        target = request.POST.get("to_status", "")
        allowed = Order.STATUS_FLOW.get(order.status, [])
        if target not in allowed:
            messages.error(request, f"不允许从「{order.get_status_display()}」流转到该状态")
            return redirect("orders:detail", pk=pk)

        old_status = order.status
        order.status = target
        update_fields = ["status", "updated_at"]
        if target == "paid":
            order.paid_at = timezone.now()
            update_fields.append("paid_at")
            order.member.points += int(order.pay_amount)
            order.member.save(update_fields=["points"])
        if target == "completed":
            order.completed_at = timezone.now()
            update_fields.append("completed_at")
        if target == "cancelled":
            order.cancel_reason = request.POST.get("note", "")[:200]
            update_fields.append("cancel_reason")
        order.save(update_fields=update_fields)
        OrderStatusHistory.objects.create(
            order=order, from_status=old_status, to_status=target, operator=request.user,
            note=request.POST.get("note", ""),
        )
        record_log(request, "变更订单状态", target_type="Order", target_id=order.order_no,
                   target_repr=order.order_no,
                   detail=f"{dict(Order.STATUS_CHOICES).get(old_status)} → "
                          f"{dict(Order.STATUS_CHOICES).get(target)}")
        messages.success(request, f"订单状态已更新为「{order.get_status_display()}」")
        return redirect("orders:detail", pk=pk)


class OrderExportView(PermRequiredMixin, View):
    """导出订单 CSV（接口权限控制）。"""

    permission_required = "orders.export_order"

    def get(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        response["Content-Disposition"] = 'attachment; filename="orders.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["订单号", "会员", "手机号", "套餐", "数量", "明细合计", "优惠", "应付",
                         "状态", "销售顾问", "下单时间"])
        for o in Order.objects.select_related("member", "package", "salesperson"):
            writer.writerow([o.order_no, o.member.name, o.member.phone, o.package.name, o.quantity,
                             o.total_amount, o.discount_amount, o.pay_amount, o.get_status_display(),
                             o.salesperson.display_name if o.salesperson else "",
                             o.created_at.strftime("%Y-%m-%d %H:%M")])
        record_log(request, "导出订单数据", category="query", target_type="Order",
                   detail=f"导出 {Order.objects.count()} 条订单")
        return response
