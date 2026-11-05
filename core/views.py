from datetime import timedelta

from django.contrib.auth.views import redirect_to_login
from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone
from .timeutil import local_today


def dashboard(request):
    """首页工作台：概览指标 + 近 7 日预约趋势 + 服务类别分布 + 最近预约。"""
    from accounts.models import Member
    from appointments.models import Appointment
    from orders.models import Order
    from services.models import HealthService

    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if getattr(request.user, "role", "") == "member":
        from django.shortcuts import redirect

        return redirect("accounts:profile")

    today = local_today()
    week_start = today - timedelta(days=6)

    revenue = Order.objects.filter(status__in=["paid", "servicing", "completed"]).aggregate(
        total=Sum("pay_amount")
    )["total"]

    cards = {
        "member_total": Member.objects.filter(is_active=True).count(),
        "service_total": HealthService.objects.filter(status="on").count(),
        "order_total": Order.objects.exclude(status="cancelled").count(),
        "appointment_today": Appointment.objects.filter(appoint_date=today).count(),
        "pending_confirm": Appointment.objects.filter(status="pending").count(),
        "revenue": float(revenue or 0),
    }

    trend = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        trend.append(
            {
                "date": day.strftime("%m-%d"),
                "count": Appointment.objects.filter(appoint_date=day).count(),
                "finished": Appointment.objects.filter(appoint_date=day, status="finished").count(),
            }
        )

    category_rows = (
        HealthService.objects.filter(status="on")
        .values("category__name")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    recent_appointments = (
        Appointment.objects.select_related("member", "service", "therapist")
        .order_by("-created_at")[:6]
    )

    return render(
        request,
        "core/dashboard.html",
        {
            "cards": cards,
            "trend": trend,
            "category_rows": list(category_rows),
            "recent_appointments": recent_appointments,
            "today": today,
        },
    )


def permission_denied(request, exception=None):
    return render(
        request,
        "core/403.html",
        {"message": "当前角色无权访问该功能，请联系管理员分配权限"},
        status=403,
    )


def page_not_found(request, exception=None):
    return render(request, "core/404.html", status=404)
