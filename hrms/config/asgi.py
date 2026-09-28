"""
ASGI 配置：异步部署入口。

ASGI 是 WSGI 的异步升级版，支持 WebSocket、SSE 等长连接场景。
本项目面向表单填报与数据展示，不使用长连接；本文件保留以备后续扩展
（例如将 AI 应答机器人改为逐字流式输出时会用到）。

官方文档：https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/

@author 王坤尧
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_asgi_application()
