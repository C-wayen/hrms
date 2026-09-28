"""
加分项「HR 智能应答机器人」应用配置。

对应文档：HRMS/code_artifact.md（SRS V1.1）
关联需求：FR-AI-01 智能 FAQ 问答、FR-AI-02 个人数据查询

@author 王坤尧
"""

from django.apps import AppConfig


class AssistantConfig(AppConfig):
    """智能应答机器人模块的注册信息。"""

    default_auto_field = 'django.db.models.BigAutoField'

    # 完整包路径：应用位于 apps/ 包下，必须带包前缀才能被 Django 正确加载
    name = 'apps.assistant'

    verbose_name = '智能应答'
