"""
人事管理模块的 Django Admin 配置。

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

from django.contrib import admin

from .models import (
    Attendance, Certificate, LeaveRequest, RegularizationApply,
    RewardPunish, SocialInsurance, TransferRecord,
)


@admin.register(TransferRecord)
class TransferRecordAdmin(admin.ModelAdmin):
    """调动记录（FR-PER-01）。"""

    list_display = (
        'employee', 'transfer_type', 'effective_date',
        'before_department', 'after_department', 'reason',
    )
    list_filter = ('transfer_type', 'effective_date')
    search_fields = ('employee__real_name', 'employee__employee_no', 'reason')
    list_select_related = ('employee', 'before_department', 'after_department')
    date_hierarchy = 'effective_date'


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    """证书资质（FR-PER-01）。"""

    list_display = ('employee', 'name', 'category', 'issue_date', 'expire_date')
    list_filter = ('category', 'issue_date')
    search_fields = ('employee__real_name', 'name', 'cert_no')
    list_select_related = ('employee',)


@admin.register(SocialInsurance)
class SocialInsuranceAdmin(admin.ModelAdmin):
    """社保缴纳记录（FR-PER-02）。"""

    list_display = ('employee', 'period', 'insurance_base', 'personal_total', 'company_total')
    list_filter = ('period',)
    search_fields = ('employee__real_name', 'employee__employee_no')
    list_select_related = ('employee',)


@admin.register(RegularizationApply)
class RegularizationApplyAdmin(admin.ModelAdmin):
    """转正申请审批（FR-PER-02）。

    approver / approved_at 为只读：应由审批动作写入，
    而不是管理员手填，否则审批时间与审批人会不一致。
    """

    list_display = ('employee', 'apply_date', 'original_status', 'expect_regular_date', 'status', 'approver')
    list_filter = ('status', 'original_status', 'apply_date')
    search_fields = ('employee__real_name', 'employee__employee_no')
    list_select_related = ('employee', 'approver')
    readonly_fields = ('approved_at',)


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    """考勤记录（FR-PER-03）。"""

    list_display = ('employee', 'work_date', 'status', 'check_in', 'check_out', 'work_hours')
    list_filter = ('status', 'work_date')
    search_fields = ('employee__real_name', 'employee__employee_no')
    list_select_related = ('employee',)
    date_hierarchy = 'work_date'


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    """请假申请与审批（FR-PER-03、UC-05）。"""

    list_display = ('employee', 'leave_type', 'start_date', 'end_date', 'days', 'status', 'approver')
    list_filter = ('status', 'leave_type', 'start_date')
    search_fields = ('employee__real_name', 'employee__employee_no', 'reason')
    list_select_related = ('employee', 'approver')
    date_hierarchy = 'start_date'
    readonly_fields = ('approved_at',)


@admin.register(RewardPunish)
class RewardPunishAdmin(admin.ModelAdmin):
    """奖罚登记（FR-PER-03）。"""

    list_display = ('employee', 'record_type', 'happen_date', 'title', 'amount')
    list_filter = ('record_type', 'happen_date')
    search_fields = ('employee__real_name', 'title')
    list_select_related = ('employee',)
    date_hierarchy = 'happen_date'
