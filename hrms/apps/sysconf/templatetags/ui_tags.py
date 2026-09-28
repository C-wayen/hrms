"""
通用界面标签。

这些标签被所有业务模块的列表页复用，属于基础设施，不属于某个具体模块。

@author 王坤尧
"""

from django import template
from django.http import QueryDict

register = template.Library()


@register.simple_tag(takes_context=True)
def query_string(context, **kwargs):
    """在当前查询参数基础上覆盖部分参数，返回新的查询串。

    用途：分页与排序链接必须保留筛选条件。
    若直接写 href="?page=2"，用户一旦筛选过部门，翻页就会丢掉筛选条件。

    例：当前为 ?q=张&department=3，执行 {% query_string page=2 %}
        得到 "q=%E5%BC%A0&department=3&page=2"

    传入空值表示移除该参数。
    """
    request = context.get('request')
    params = request.GET.copy() if request else QueryDict(mutable=True)

    for key, value in kwargs.items():
        if value is None or value == '':
            params.pop(key, None)
        else:
            params[key] = value

    return params.urlencode()


@register.filter
def badge_class(status):
    """把业务状态映射为 Bootstrap 徽章颜色，统一各页面的状态色调。

    集中一处维护，避免每个模板各写一套 if 判断导致颜色语义不一致。
    """
    mapping = {
        # 员工在职状态
        'regular': 'success',
        'probation': 'info',
        'intern': 'warning',
        'resigned': 'secondary',
        # 审批类状态
        'pending': 'warning',
        'approved': 'success',
        'rejected': 'danger',
        'cancelled': 'secondary',
        # 工资发放状态
        'draft': 'secondary',
        'paid': 'success',
        # 培训计划状态
        'ongoing': 'primary',
        'finished': 'success',
    }
    return mapping.get(status, 'secondary')
