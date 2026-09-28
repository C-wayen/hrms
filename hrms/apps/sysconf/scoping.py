"""
行级数据范围控制（Row-Level Data Scope）。

对应需求：FR-SYS-01 权限控制

为什么单独成一个模块：Django 自带的权限是**模型级**的，只能表达
「能否访问请假模型」，无法表达「普通职工只能看自己的请假 / 自己的工资条」。
这类行级规则必须在视图层落实，而「人事」「薪酬」两个模块都需要同一套规则，
各写一份迟早会走样，因此抽到这里共用。

@author 王坤尧
"""


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
