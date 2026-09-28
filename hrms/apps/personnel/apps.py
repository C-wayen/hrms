"""
模块 1「人事管理」应用配置。

对应文档：HRMS/code_artifact.md（SRS V1.1）
关联需求：FR-PER-01 职工档案管理、FR-PER-02 实习生与社保管理、
          FR-PER-03 考勤与请假、FR-PER-04 员工关怀

@author 王坤尧
"""

from django.apps import AppConfig


class PersonnelConfig(AppConfig):
    """人事管理模块的注册信息。"""

    default_auto_field = 'django.db.models.BigAutoField'

    # 完整包路径：应用位于 apps/ 包下，必须带包前缀才能被 Django 正确加载
    name = 'apps.personnel'

    verbose_name = '人事管理'
