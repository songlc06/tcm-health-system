"""学生 5：多条件查询、统计汇总与图表、日志与结果导出/打印。"""
import csv
from datetime import timedelta

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from core.timeutil import local_today

from accounts.models import User
from core.mixins import PermRequiredMixin
from core.models import OperationLog
from core.utils import paginate, parse_date, record_log

from .datasets import DATASETS
from .statistics import build_statistics


def _context(request, dataset_key, limit=200):
    dataset = DATASETS.get(dataset_key) or DATASETS["orders"]
    qs = dataset["queryset"](request.GET)
    page_obj = paginate(request, qs, 15)
    rows = [dataset["row"](obj) for obj in page_obj.object_list]
    return {
        "dataset_key": dataset_key,
        "dataset": dataset,
        "datasets": DATASETS,
        "page_obj": page_obj,
        "rows": rows,
        "headers": dataset["headers"],
        "total": qs.count(),
        "query": request.GET,
        "keyword": request.GET.get("keyword", ""),
        "status": request.GET.get("status", ""),
        "person": request.GET.get("person", ""),
        "date_from": request.GET.get("date_from", ""),
        "date_to": request.GET.get("date_to", ""),
        "persons": User.objects.filter(is_active=True).order_by("display_name"),
        "status_choices": dataset["status_choices"],
    }


class SearchView(PermRequiredMixin, View):
    """① 按时间、人员、业务对象的多条件查询。"""

    permission_required = "core.query_report"
    template_name = "reports/search.html"

    def get(self, request):
        key = request.GET.get("dataset", "orders")
        ctx = _context(request, key)
        record_log(request, "多条件查询", category="query", target_type="Report",
                   target_repr=ctx["dataset"]["title"],
                   detail=f"关键字={ctx['keyword'] or '空'}；状态={ctx['status'] or '全部'}；"
                          f"时间={ctx['date_from'] or '不限'}~{ctx['date_to'] or '不限'}；命中 {ctx['total']} 条")
        return render(request, self.template_name, ctx)


class ExportView(PermRequiredMixin, View):
    """③ 按当前查询条件导出 CSV（Excel 可直接打开）。"""

    permission_required = "core.export_report"

    def get(self, request):
        key = request.GET.get("dataset", "orders")
        dataset = DATASETS.get(key) or DATASETS["orders"]
        qs = dataset["queryset"](request.GET)[:5000]
        count = qs.count()

        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        filename = f"{key}_{local_today():%Y%m%d}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(dataset["headers"])
        for obj in qs:
            writer.writerow(dataset["row"](obj))

        record_log(request, "导出查询结果", category="query", target_type="Report",
                   target_repr=dataset["title"],
                   detail=f"导出「{dataset['title']}」{count} 条；条件：{request.GET.urlencode()}")
        return response


class PrintView(PermRequiredMixin, View):
    """③ 打印友好页面（浏览器打印 / 另存 PDF）。"""

    permission_required = "core.query_report"
    template_name = "reports/print.html"

    def get(self, request):
        key = request.GET.get("dataset", "orders")
        dataset = DATASETS.get(key) or DATASETS["orders"]
        qs = dataset["queryset"](request.GET)[:300]
        rows = [dataset["row"](obj) for obj in qs]
        record_log(request, "打印查询结果", category="query", target_type="Report",
                   target_repr=dataset["title"], detail=f"打印 {len(rows)} 条记录")
        return render(request, self.template_name, {
            "dataset": dataset, "headers": dataset["headers"], "rows": rows,
            "query": request.GET, "printed_at": timezone.now(), "operator": request.user,
            "keyword": request.GET.get("keyword", ""),
            "date_from": request.GET.get("date_from", ""),
            "date_to": request.GET.get("date_to", ""),
        })


class StatisticsView(PermRequiredMixin, View):
    """② 统计汇总 + ECharts 图表（数据由 Pandas 清洗汇总）。"""

    permission_required = "core.view_statistics"
    template_name = "reports/statistics.html"

    def get(self, request):
        today = local_today()
        start = parse_date(request.GET.get("date_from"), today - timedelta(days=29))
        end = parse_date(request.GET.get("date_to"), today)
        if start > end:
            start, end = end, start
        stats = build_statistics(start, end)
        record_log(request, "查看统计报表", category="query", target_type="Report",
                   detail=f"统计区间 {start}~{end}")
        return render(request, self.template_name, {
            "stats": stats,
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
        })


class LogListView(PermRequiredMixin, View):
    """③ 操作日志查询（独立入口，可导出）。"""

    permission_required = "core.view_operationlog"
    template_name = "reports/logs.html"

    def get(self, request):
        ctx = _context(request, "logs")
        ctx["categories"] = OperationLog.CATEGORY_CHOICES
        return render(request, self.template_name, ctx)
