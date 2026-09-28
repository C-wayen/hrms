#!/usr/bin/env python
"""Django 命令行管理入口（HRMS 项目）。

用法示例：
    python manage.py runserver          启动开发服务器
    python manage.py makemigrations     根据模型生成迁移文件
    python manage.py migrate            将迁移应用到数据库
    python manage.py createsuperuser    创建后台管理员账号
    python manage.py startapp <名称>    新建业务应用

注意：`django-admin.exe` 不在 PATH 上，请统一通过本文件操作。

@author 王坤尧
"""
import os
import sys


def main():
    """执行命令行管理任务。"""
    # 指定配置模块，Django 启动时据此加载 config/settings.py
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            """
            Couldn't import Django. Are you sure it's installed and 
            available on your PYTHONPATH environment variable? Did you 
            forget to activate a virtual environment?
            """
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
