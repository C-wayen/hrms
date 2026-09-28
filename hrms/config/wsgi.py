"""
WSGI 配置：同步部署入口。

WSGI 是 Python Web 服务器（waitress / uWSGI / Gunicorn）与 Django 之间的标准接口。
部署时由 Web 服务器导入本模块的 ``application`` 对象。

开发阶段用不到本文件（runserver 自带处理），正式部署时才被加载。
官方文档：https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/

@author 王坤尧
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
