"""
模块 5「报表与数据统计」应用配置。

本模块不含模型：所有报表均由其他模块的数据聚合而成，
通过 Django ORM 的 annotate/aggregate 生成，结果以 JsonResponse 供 ECharts 渲染。

对应文档：HRMS/code_artifact.md（SRS V1.1）
关联需求：FR-RPT-01 结构统计、FR-RPT-02 动态分析、FR-RPT-03 人员流动统计

@author 王坤尧
"""

from django.apps import AppConfig


class ReportingConfig(AppConfig):
    """报表统计模块的注册信息。"""

    default_auto_field = 'django.db.models.BigAutoField'

    # 完整包路径：应用位于 apps/ 包下，必须带包前缀才能被 Django 正确加载
    name = 'apps.reporting'

    verbose_name = '报表统计'
