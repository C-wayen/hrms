"""
模块 6「系统设置与安全」应用配置。

对应文档：HRMS/code_artifact.md（SRS V1.1）
关联需求：FR-SYS-01 权限控制、FR-SYS-02 基础数据、FR-SYS-03 用户与菜单管理

@author 王坤尧
"""

from django.apps import AppConfig


class SysconfConfig(AppConfig):
    """系统设置与安全模块的注册信息。"""

    # 模型主键统一使用 64 位自增整数（与 MySQL BIGINT 对应）
    default_auto_field = 'django.db.models.BigAutoField'

    # 完整包路径：应用位于 apps/ 包下，必须带包前缀才能被 Django 正确加载
    name = 'apps.sysconf'

    # Django Admin 与权限列表中显示的中文名
    verbose_name = '系统设置'
