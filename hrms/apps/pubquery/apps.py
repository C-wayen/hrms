"""
模块 4「公共查询」应用配置。

对应文档：HRMS/code_artifact.md（SRS V1.1）
关联需求：FR-QRY-01 多维检索、FR-QRY-02 通知套红与打印

@author 王坤尧
"""

from django.apps import AppConfig


class PubqueryConfig(AppConfig):
    """公共查询模块的注册信息。"""

    default_auto_field = 'django.db.models.BigAutoField'

    # 完整包路径：应用位于 apps/ 包下，必须带包前缀才能被 Django 正确加载
    name = 'apps.pubquery'

    verbose_name = '公共查询'
