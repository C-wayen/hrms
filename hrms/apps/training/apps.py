"""
模块 2「培训管理」应用配置。

对应文档：HRMS/code_artifact.md（SRS V1.1）
关联需求：FR-TRN-01 课程与方案管理、FR-TRN-02 专项培训

@author 王坤尧
"""

from django.apps import AppConfig


class TrainingConfig(AppConfig):
    """培训管理模块的注册信息。"""

    default_auto_field = 'django.db.models.BigAutoField'

    # 完整包路径：应用位于 apps/ 包下，必须带包前缀才能被 Django 正确加载
    name = 'apps.training'

    verbose_name = '培训管理'
