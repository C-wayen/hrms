"""
数据范围控制（Data Scope）。

包含两部分：
    1. 行级数据范围（DataScopeMixin）——普通职工只能看自己的记录
    2. 组织结构范围（department_and_children_ids）——按部门筛选时是否下钻到下级

对应需求：FR-SYS-01 权限控制、FR-RPT-01 ~ FR-RPT-03 报表统计

为什么单独成一个模块：Django 自带的权限是**模型级**的，只能表达
「能否访问请假模型」，无法表达「普通职工只能看自己的请假 / 自己的工资条」。
这类行级规则必须在视图层落实，而「人事」「薪酬」「报表」多个模块都要用同一套规则，
各写一份迟早会走样，因此抽到这里共用。

@author 王坤尧
"""

from apps.sysconf.models import Department


class DataScopeMixin:
    """按当前用户角色收窄列表的数据范围。

    判定依据是 Employee.can_view_all（由所属角色决定）：
    能看全量的不加过滤，否则一律过滤为 employee=当前登录用户。
    """

    def scope_queryset(self, queryset):
        """按当前用户的数据范围过滤查询集。

        前提：传入的模型必须有名为 employee 的外键。
        """
        if getattr(self.request.user, 'can_view_all', False):
            return queryset
        return queryset.filter(employee=self.request.user)


def department_and_children_ids(department) -> list:
    """取某个部门及其所有下级部门的 id 列表。

    只按单个部门过滤会漏掉下级部门的员工；组织树一旦有两层以上，
    漏掉的恰恰是人数最多的基层部门。这里按层向下遍历，直到没有子部门。

    薪酬核算的「核算范围」与报表的「部门筛选」都要用，因此与 DataScopeMixin
    放在一起——两者都是「数据范围」问题，只是维度不同（按人 / 按组织）。
    """
    ids = [department.pk]
    frontier = [department.pk]
    while frontier:
        children = list(
            Department.objects.filter(parent_id__in=frontier).values_list('pk', flat=True)
        )
        ids.extend(children)
        frontier = children
    return ids
