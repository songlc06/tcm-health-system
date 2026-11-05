"""基于 Pandas 的统计数据汇总（学生 5 第②项）。"""
from datetime import timedelta

import pandas as pd
from django.utils import timezone
from core.timeutil import local_today

from accounts.models import Member
from appointments.models import Appointment
from core.models import OperationLog
from orders.models import Order


def _orders_df(start, end):
    rows = list(
        Order.objects.filter(created_at__date__gte=start, created_at__date__lte=end).values(
            "created_at", "pay_amount", "total_amount", "status", "quantity",
            "package__name", "member__id", "member__level", "salesperson__display_name",
        )
    )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["pay_amount"] = df["pay_amount"].astype(float)
        df["total_amount"] = df["total_amount"].astype(float)
        df["date"] = pd.to_datetime(df["created_at"]).dt.date
    return df


def _appointments_df(start, end):
    rows = list(
        Appointment.objects.filter(appoint_date__gte=start, appoint_date__lte=end).values(
            "appoint_date", "status", "source", "service__name", "service__category__name",
            "therapist__display_name", "member__level", "exception_level",
        )
    )
    df = pd.DataFrame(rows)
    return df


def build_statistics(start=None, end=None):
    """返回 KPI、趋势、分布与 TOP 排行，全部由 Pandas 汇总生成。"""
    today = local_today()
    end = end or today
    start = start or (end - timedelta(days=29))
    days = [d.date() for d in pd.date_range(start, end, freq="D")]

    odf = _orders_df(start, end)
    adf = _appointments_df(start, end)

    # ---------------- KPI
    paid_status = ["paid", "servicing", "completed"]
    order_count = int(len(odf)) if not odf.empty else 0
    valid_orders = odf[odf["status"].isin(paid_status)] if not odf.empty else odf
    revenue = float(valid_orders["pay_amount"].sum()) if not valid_orders.empty else 0.0
    avg_order = round(revenue / len(valid_orders), 2) if not valid_orders.empty else 0.0
    appt_count = int(len(adf)) if not adf.empty else 0
    finished = int((adf["status"] == "finished").sum()) if not adf.empty else 0
    finish_rate = round(finished / appt_count * 100, 1) if appt_count else 0.0
    new_members = Member.objects.filter(join_date__gte=start, join_date__lte=end).count()

    kpi = {
        "order_count": order_count,
        "revenue": round(revenue, 2),
        "avg_order": avg_order,
        "appointment_count": appt_count,
        "finish_rate": finish_rate,
        "new_members": new_members,
        "start": start,
        "end": end,
        "days": (end - start).days + 1,
    }

    # ---------------- 每日趋势
    if not odf.empty:
        order_daily = odf[odf["status"].isin(paid_status)].groupby("date")["pay_amount"].sum()
        order_daily = order_daily.reindex(days, fill_value=0).round(2)
        order_cnt_daily = odf.groupby("date")["pay_amount"].count().reindex(days, fill_value=0)
    else:
        order_daily = pd.Series([0] * len(days), index=days)
        order_cnt_daily = pd.Series([0] * len(days), index=days)

    if not adf.empty:
        appt_daily = adf.groupby("appoint_date").size().reindex(days, fill_value=0)
    else:
        appt_daily = pd.Series([0] * len(days), index=days)

    daily = {
        "labels": [d.strftime("%m-%d") for d in days],
        "order_amount": [round(float(v), 2) for v in order_daily.tolist()],
        "order_count": [int(v) for v in order_cnt_daily.tolist()],
        "appointment_count": [int(v) for v in appt_daily.tolist()],
    }

    # ---------------- 预约状态分布
    status_labels = dict(Appointment.STATUS_CHOICES)
    if not adf.empty:
        status_counts = adf.groupby("status").size().sort_values(ascending=False)
        status_pie = [{"name": status_labels.get(k, k), "value": int(v)} for k, v in status_counts.items()]
    else:
        status_pie = []

    # ---------------- 服务 TOP8（按预约量）
    if not adf.empty:
        top = adf.groupby("service__name").size().sort_values(ascending=False).head(8)
        top_services = {"labels": top.index.tolist(), "values": [int(v) for v in top.values]}
    else:
        top_services = {"labels": [], "values": []}

    # ---------------- 会员等级分布（下单会员）
    level_labels = dict(Member.LEVEL_CHOICES)
    if not odf.empty:
        unique_members = odf.drop_duplicates(subset=["member__id"])
        levels = unique_members["member__level"].fillna("bronze").value_counts()
        level_pie = [{"name": level_labels.get(k, k or "未设置"), "value": int(v)}
                     for k, v in levels.items()]
    else:
        level_pie = []

    # ---------------- 顾问工作量
    therapist_rows = []
    if not adf.empty:
        grouped = adf.groupby("therapist__display_name").agg(
            total=("status", "size"),
            finished=("status", lambda s: int((s == "finished").sum())),
        )
        grouped["rate"] = (grouped["finished"] / grouped["total"] * 100).round(1)
        grouped = grouped.sort_values("total", ascending=False)
        therapist_rows = [
            {"name": idx or "未分配", "total": int(row["total"]),
             "finished": int(row["finished"]), "rate": float(row["rate"])}
            for idx, row in grouped.iterrows()
        ]

    # ---------------- 服务经营汇总表（订单维度）
    service_rows = []
    if not odf.empty:
        pivot = odf.pivot_table(index="package__name", values="pay_amount", aggfunc="sum").round(2)
        counts = odf.groupby("package__name").size()
        for name, amount in pivot["pay_amount"].items():
            service_rows.append({"package": name, "amount": float(amount), "count": int(counts.get(name, 0))})
        service_rows.sort(key=lambda r: r["amount"], reverse=True)

    # ---------------- 日志活跃度
    log_count = OperationLog.objects.filter(created_at__date__gte=start, created_at__date__lte=end).count()

    return {
        "kpi": kpi,
        "daily": daily,
        "status_pie": status_pie,
        "top_services": top_services,
        "level_pie": level_pie,
        "therapist_rows": therapist_rows,
        "service_rows": service_rows[:8],
        "log_count": log_count,
    }
