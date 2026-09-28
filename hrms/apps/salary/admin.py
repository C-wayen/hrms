"""
薪酬管理模块的 Django Admin 配置。

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

from django.contrib import admin

from .models import (
    OvertimeRecord, PieceworkRecord, SalaryLevel, SalaryRecord,
    SalaryStandard, UtilityFeeRecord,
)


@admin.register(SalaryLevel)
class SalaryLevelAdmin(admin.ModelAdmin):
    """薪酬级别（FR-SAL-01）。"""

    list_display = ('code', 'name', 'base_salary', 'post_allowance', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


@admin.register(SalaryStandard)
class SalaryStandardAdmin(admin.ModelAdmin):
    """薪酬与扣缴标准（FR-SAL-01、FR-SYS-02 社保比例）。

    按生效日期保留多条历史记录，核算时取对应周期的版本。
    """

    list_display = (
        'effective_date', 'overtime_workday_rate', 'overtime_weekend_rate',
        'overtime_holiday_rate', 'water_price', 'electricity_price',
        'social_insurance_ratio', 'is_active',
    )
    list_filter = ('is_active',)
    date_hierarchy = 'effective_date'


@admin.register(OvertimeRecord)
class OvertimeRecordAdmin(admin.ModelAdmin):
    """加班登记（FR-SAL-03）。"""

    list_display = ('employee', 'overtime_date', 'overtime_type', 'hours', 'salary_period')
    list_filter = ('overtime_type', 'salary_period')
    search_fields = ('employee__real_name', 'employee__employee_no')
    list_select_related = ('employee',)
    date_hierarchy = 'overtime_date'


@admin.register(UtilityFeeRecord)
class UtilityFeeRecordAdmin(admin.ModelAdmin):
    """水电费扣费登记（FR-SAL-03）。"""

    list_display = ('employee', 'salary_period', 'water_fee', 'electricity_fee', 'total_fee')
    list_filter = ('salary_period',)
    search_fields = ('employee__real_name', 'employee__employee_no')
    list_select_related = ('employee',)


@admin.register(PieceworkRecord)
class PieceworkRecordAdmin(admin.ModelAdmin):
    """计件/计时产量登记（FR-SAL-02）。

    amount 为只读：由 save() 按计薪方式自动算得，不允许人工填写，
    否则计件工资的基数就可以被随意篡改。
    """

    list_display = ('employee', 'work_date', 'work_mode', 'product_name', 'quantity', 'hours', 'amount')
    list_filter = ('work_mode', 'salary_period')
    search_fields = ('employee__real_name', 'product_name')
    list_select_related = ('employee',)
    readonly_fields = ('amount',)
    date_hierarchy = 'work_date'


@admin.register(SalaryRecord)
class SalaryRecordAdmin(admin.ModelAdmin):
    """工资档案（FR-SAL-02）。

    net_pay 为只读：必须由 calculate_net_pay() 按公式算出，
    手工修改实发工资会破坏工资条的可信度。
    """

    list_display = (
        'employee', 'salary_period', 'base_salary', 'piecework_amount',
        'overtime_amount', 'reward_punish_amount',
        'utility_deduction', 'social_deduction',
        'net_pay', 'pay_status',
    )
    list_filter = ('pay_status', 'salary_period')
    search_fields = ('employee__real_name', 'employee__employee_no')
    list_select_related = ('employee',)
    readonly_fields = ('net_pay', 'paid_at')
    date_hierarchy = 'created_at'
