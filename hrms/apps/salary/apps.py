"""
模块 3「薪酬管理」应用配置。

对应文档：HRMS/code_artifact.md（SRS V1.1）
关联需求：FR-SAL-01 薪酬体系配置、FR-SAL-02 工资计算与发放、
          FR-SAL-03 加班与水电费登记

@author 王坤尧
"""

from django.apps import AppConfig


class SalaryConfig(AppConfig):
    """薪酬管理模块的注册信息。"""

    default_auto_field = 'django.db.models.BigAutoField'

    # 完整包路径：应用位于 apps/ 包下，必须带包前缀才能被 Django 正确加载
    name = 'apps.salary'

    verbose_name = '薪酬管理'
