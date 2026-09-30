"""
侧边栏菜单上下文处理器。

对应 FR-SYS-03「导航菜单配置与角色可见性绑定」：每次渲染页面时，
自动把「当前登录用户可见的菜单树」注入模板上下文，模板只负责展示，
不必在每个视图里重复查询菜单。

在 settings.TEMPLATES.OPTIONS.context_processors 中注册后全局生效。

@author 王坤尧
"""

from django.urls import NoReverseMatch, reverse

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


def _has_route(menu) -> bool:
    """判断菜单指向的路由是否真的存在。

    路由还没实现的菜单项**直接不显示**，而不是渲染成 href="#" 的死链：
    看得见却点不动，会让人以为系统坏了；干脆不显示，就没这层误会。
    好处是页面实现之后菜单项自动出现，不必回头再去改菜单配置。
    """
    if not menu.url_name:
        return False
    try:
        reverse(menu.url_name)
    except NoReverseMatch:
        return False
    return True


def sidebar_menus(request):
    """注入 sidebar_menus：形如 [{menu, children}, ...] 的两级菜单树。"""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}

    roles = user.groups.all()

    # 一次性取出全部可见菜单后在内存中组树：
    # 若按「取顶级 → 逐个取子级」的方式查询，菜单越多 SQL 越多（N+1）。
    raw = list(_visible(Menu.objects.all(), roles, user.is_superuser).order_by('sort_order'))

    # 记下哪些顶级菜单原本带子菜单——过滤之后要靠它区分
    # 「本来就是单入口（如智能助手）」与「子项全被过滤掉了」
    parents_with_children = {menu.parent_id for menu in raw if menu.parent_id is not None}

    children_map = {}
    tops = []
    for menu in raw:
        if menu.parent_id is None:
            # 分组型的顶级菜单自身没有 url_name（它只是个折叠开关），
            # 因此不能拿 _has_route 去卡它——否则整个分组连同子项一起消失。
            # 真正需要可解析路由的，是「本身就是入口」的那种顶级菜单（如首页、智能助手）。
            if menu.id in parents_with_children or _has_route(menu):
                tops.append(menu)
        elif _has_route(menu):
            children_map.setdefault(menu.parent_id, []).append(menu)

    tree = []
    for menu in tops:
        children = children_map.get(menu.id, [])
        # 本来有子菜单、实现后一个可用的都不剩 → 整个分组不显示（点开是空的，没意义）
        if menu.id in parents_with_children and not children:
            continue
        tree.append({'menu': menu, 'children': children})

    return {'sidebar_menus': tree}
