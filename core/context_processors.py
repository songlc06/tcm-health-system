"""菜单导航上下文：按当前用户权限过滤菜单。"""
from .models import Menu


def navigation(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"nav_groups": [], "nav_menus": []}

    role = getattr(user, "role", "")
    menus = []
    for menu in Menu.objects.filter(is_active=True):
        if menu.role_scope and role not in [r.strip() for r in menu.role_scope.split(",") if r.strip()]:
            continue
        if not menu.perm_codename or user.has_perm(menu.perm_codename):
            menus.append(menu)

    group_labels = dict(Menu.GROUP_CHOICES)
    groups = []
    for code, label in Menu.GROUP_CHOICES:
        items = [m for m in menus if m.group == code]
        if items:
            groups.append({"code": code, "label": group_labels.get(code, label), "items": items})

    return {"nav_groups": groups, "nav_menus": menus}
