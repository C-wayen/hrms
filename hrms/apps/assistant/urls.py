"""
智能应答机器人路由。

路由命名与数据库中的导航菜单 url_name 一一对应（FR-SYS-03），
修改路由名时必须同步更新菜单配置，否则该菜单项会从侧边栏消失。

@author 王坤尧
"""

from django.urls import path

from . import views

urlpatterns = [
    # --- 对话界面（FR-AI-01、FR-AI-02、UC-04）---
    path('', views.chat, name='assistant-chat'),

    # --- 问答接口（JSON）---
    path('ask/', views.ask, name='assistant-ask'),
]
