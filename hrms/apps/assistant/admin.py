"""
智能应答机器人模块的 Django Admin 配置。

HR 可在后台直接维护 FAQ 知识库（增删条目、改关键词），
调整应答效果不需要改代码。

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

from django.contrib import admin

from .models import ChatLog, FaqItem


@admin.register(FaqItem)
class FaqItemAdmin(admin.ModelAdmin):
    """FAQ 知识库（FR-AI-01）。"""

    list_display = ('question', 'category', 'keywords', 'hit_count', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('question', 'keywords', 'answer')
    # 命中次数由问答逻辑累加，不应人工编辑
    readonly_fields = ('hit_count',)


@admin.register(ChatLog)
class ChatLogAdmin(admin.ModelAdmin):
    """问答记录（FR-AI-01、FR-AI-02）。

    全部字段只读：日志用于事后排查「为什么这次答得不对」，
    能被手工改写的日志就没有可信度。
    """

    list_display = ('created_at', 'employee', 'question', 'source', 'elapsed_ms')
    list_filter = ('source', 'created_at')
    search_fields = ('question', 'answer')
    list_select_related = ('employee', 'matched_faq')
    date_hierarchy = 'created_at'
    readonly_fields = [f.name for f in ChatLog._meta.fields]

    def has_add_permission(self, request):
        """禁止在后台手工新增日志，只能由问答流程写入。"""
        return False
