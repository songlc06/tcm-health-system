"""模板通用标签：分页、查询串保留、状态配色。"""
from django import template

register = template.Library()

BADGE_MAP = {
    # 通用
    "on": "success", "off": "secondary", "active": "success", "inactive": "secondary",
    # 订单
    "pending": "warning", "paid": "primary", "servicing": "info",
    "completed": "success", "cancelled": "secondary", "refunded": "danger",
    # 预约
    "confirmed": "primary", "finished": "success", "no_show": "danger",
    # 会员等级
    "bronze": "secondary", "silver": "info", "gold": "warning", "diamond": "primary",
}


@register.filter
def badge(value):
    """把业务状态映射为 Bootstrap 徽章配色。"""
    return BADGE_MAP.get(str(value), "secondary")


@register.filter
def money(value):
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


@register.filter
def get_item(mapping, key):
    if hasattr(mapping, "get"):
        return mapping.get(key)
    return None


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    """在保留当前筛选条件的前提下替换指定查询参数（用于分页链接）。"""
    request = context.get("request")
    query = request.GET.copy() if request else {}
    for key, value in kwargs.items():
        if value in (None, ""):
            query.pop(key, None)
        else:
            query[key] = value
    return query.urlencode() if hasattr(query, "urlencode") else ""


@register.simple_tag(takes_context=True)
def active_nav(context, url_name):
    request = context.get("request")
    if not request:
        return ""
    resolver = getattr(request, "resolver_match", None)
    if not resolver:
        return ""
    current = resolver.view_name or ""
    return "active" if current == url_name or current.startswith(url_name + "_") else ""


@register.inclusion_tag("core/_pager.html", takes_context=True)
def pager(context, page_obj):
    return {"page_obj": page_obj, "request": context.get("request")}
