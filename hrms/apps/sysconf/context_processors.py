"""
侧边栏菜单上下文处理器。

对应 FR-SYS-03「导航菜单配置与角色可见性绑定」：每次渲染页面时，
自动把「当前登录用户可见的菜单树」注入模板上下文，模板只负责展示，
不必在每个视图里重复查询菜单。

在 settings.TEMPLATES.OPTIONS.context_processors 中注册后全局生效。

@author 王坤尧
"""

from .models import Menu


def _visible(queryset, roles, is_superuser):
    """按角色过滤菜单。

    超级管理员不受 visible_roles 限制，可见全部启用菜单——
    否则一旦菜单配置出错，管理员自己也会被锁在门外。
    """
    queryset = queryset.filter(is_active=True)
    if is_superuser:
        return queryset
    return queryset.filter(visible_roles__in=roles).distinct()


def sidebar_menus(request):
    """注入 sidebar_menus：形如 [{menu, children}, ...] 的两级菜单树。"""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}

    roles = user.groups.all()

    # 一次性取出全部可见菜单后在内存中组树：
    # 若按「取顶级 → 逐个取子级」的方式查询，菜单越多 SQL 越多（N+1）。
    menus = _visible(Menu.objects.all(), roles, user.is_superuser).order_by('sort_order')

    children_map = {}
    tops = []
    for menu in menus:
        if menu.parent_id is None:
            tops.append(menu)
        else:
            children_map.setdefault(menu.parent_id, []).append(menu)

    tree = [{'menu': m, 'children': children_map.get(m.id, [])} for m in tops]
    return {'sidebar_menus': tree}
