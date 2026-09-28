"""
公共查询模块的 Django Admin 配置。

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

from django.contrib import admin

from .models import NotificationDoc


@admin.register(NotificationDoc)
class NotificationDocAdmin(admin.ModelAdmin):
    """人事变动通知单（FR-QRY-02）。"""

    list_display = ('doc_no', 'doc_type', 'title', 'employee', 'issue_date', 'issuer')
    list_filter = ('doc_type', 'issue_date')
    search_fields = ('doc_no', 'title', 'employee__real_name')
    list_select_related = ('employee', 'issuer')
    date_hierarchy = 'issue_date'
