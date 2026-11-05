"""学生 5：多条件查询数据集定义（查询、导出、打印三处复用）。"""
from django.db.models import Q

from accounts.models import Member
from appointments.models import Appointment
from core.models import OperationLog
from core.utils import parse_date
from orders.models import Order
from services.models import HealthService


def _range(params, field):
    """按日期范围追加过滤条件。"""
    date_from = parse_date(params.get("date_from"))
    date_to = parse_date(params.get("date_to"))
    if date_from:
        params_q = {f"{field}__gte": date_from}
    else:
        params_q = {}
    if date_to:
        params_q[f"{field}__lte"] = date_to
    return params_q


def orders_queryset(params):
    qs = Order.objects.select_related("member", "package", "salesperson")
    keyword = params.get("keyword", "").strip()
    status = params.get("status", "").strip()
    person = params.get("person", "").strip()

    if keyword:
        qs = qs.filter(Q(order_no__icontains=keyword) | Q(member__name__icontains=keyword)
                       | Q(member__phone__icontains=keyword) | Q(package__name__icontains=keyword))
    if status:
        qs = qs.filter(status=status)
    if person.isdigit():
        qs = qs.filter(salesperson_id=person)
    qs = qs.filter(**_range(params, "created_at__date"))
    return qs.order_by("-created_at")


def appointments_queryset(params):
    qs = Appointment.objects.select_related("member", "service", "therapist")
    keyword = params.get("keyword", "").strip()
    status = params.get("status", "").strip()
    person = params.get("person", "").strip()

    if keyword:
        qs = qs.filter(Q(appointment_no__icontains=keyword) | Q(member__name__icontains=keyword)
                       | Q(member__phone__icontains=keyword) | Q(service__name__icontains=keyword))
    if status:
        qs = qs.filter(status=status)
    if person.isdigit():
        qs = qs.filter(therapist_id=person)
    qs = qs.filter(**_range(params, "appoint_date"))
    return qs.order_by("-appoint_date", "appoint_time")


def members_queryset(params):
    qs = Member.objects.select_related("user")
    keyword = params.get("keyword", "").strip()
    status = params.get("status", "").strip()
    if keyword:
        qs = qs.filter(Q(name__icontains=keyword) | Q(phone__icontains=keyword)
                       | Q(member_no__icontains=keyword) | Q(tags__icontains=keyword))
    if status in ("bronze", "silver", "gold", "diamond"):
        qs = qs.filter(level=status)
    qs = qs.filter(**_range(params, "join_date"))
    return qs.order_by("-created_at")


def services_queryset(params):
    qs = HealthService.objects.select_related("category")
    keyword = params.get("keyword", "").strip()
    status = params.get("status", "").strip()
    if keyword:
        qs = qs.filter(Q(name__icontains=keyword) | Q(code__icontains=keyword)
                       | Q(category__name__icontains=keyword))
    if status:
        qs = qs.filter(status=status)
    qs = qs.filter(**_range(params, "created_at__date"))
    return qs.order_by("category__sort_order", "sort_order")


def logs_queryset(params):
    qs = OperationLog.objects.all()
    keyword = params.get("keyword", "").strip()
    status = params.get("status", "").strip()
    person = params.get("person", "").strip()
    if keyword:
        qs = qs.filter(Q(action__icontains=keyword) | Q(detail__icontains=keyword)
                       | Q(target_repr__icontains=keyword) | Q(path__icontains=keyword))
    if status:
        qs = qs.filter(category=status)
    if person:
        qs = qs.filter(username__icontains=person)
    qs = qs.filter(**_range(params, "created_at__date"))
    return qs.order_by("-created_at")


DATASETS = {
    "orders": {
        "title": "套餐订单",
        "headers": ["订单号", "会员", "手机号", "套餐", "数量", "应付金额(元)", "状态", "销售顾问", "下单时间"],
        "queryset": orders_queryset,
        "row": lambda o: [o.order_no, o.member.name, o.member.phone, o.package.name, o.quantity,
                          f"{o.pay_amount:.2f}", o.get_status_display(),
                          o.salesperson.display_name if o.salesperson else "",
                          o.created_at.strftime("%Y-%m-%d %H:%M")],
        "status_choices": Order.STATUS_CHOICES,
        "person_label": "销售顾问",
        "date_label": "下单日期",
    },
    "appointments": {
        "title": "服务预约",
        "headers": ["预约单号", "会员", "服务项目", "预约日期", "时段", "顾问", "状态", "异常等级", "创建时间"],
        "queryset": appointments_queryset,
        "row": lambda a: [a.appointment_no, a.member.name, a.service.name, a.appoint_date, a.appoint_time,
                          a.therapist.display_name if a.therapist else "", a.get_status_display(),
                          a.get_exception_level_display(), a.created_at.strftime("%Y-%m-%d %H:%M")],
        "status_choices": Appointment.STATUS_CHOICES,
        "person_label": "服务顾问",
        "date_label": "预约日期",
    },
    "members": {
        "title": "会员档案",
        "headers": ["会员编号", "姓名", "手机号", "等级", "积分", "余额(元)", "入会日期", "状态"],
        "queryset": members_queryset,
        "row": lambda m: [m.member_no, m.name, m.phone, m.get_level_display(), m.points,
                          f"{m.balance:.2f}", m.join_date, "有效" if m.is_active else "停用"],
        "status_choices": Member.LEVEL_CHOICES,
        "person_label": "所属顾问",
        "date_label": "入会日期",
    },
    "services": {
        "title": "养生服务",
        "headers": ["服务编码", "服务名称", "分类", "时长(分钟)", "标准价", "会员价", "状态", "创建时间"],
        "queryset": services_queryset,
        "row": lambda s: [s.code, s.name, s.category.name, s.duration, f"{s.price:.2f}",
                          f"{s.member_price:.2f}", s.get_status_display(),
                          s.created_at.strftime("%Y-%m-%d %H:%M")],
        "status_choices": HealthService.STATUS_CHOICES,
        "person_label": "创建人",
        "date_label": "创建日期",
    },
    "logs": {
        "title": "操作日志",
        "headers": ["时间", "操作人", "角色", "类别", "动作", "业务对象", "摘要", "状态码", "IP"],
        "queryset": logs_queryset,
        "row": lambda l: [l.created_at.strftime("%Y-%m-%d %H:%M:%S"), l.username, l.role,
                          l.get_category_display(), l.action, l.target_type,
                          l.target_repr or (l.detail[:40] if l.detail else ""),
                          l.status_code if l.status_code is not None else "—", l.ip],
        "status_choices": OperationLog.CATEGORY_CHOICES,
        "person_label": "操作人",
        "date_label": "操作日期",
    },
}
