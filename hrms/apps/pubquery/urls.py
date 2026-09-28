"""
公共查询模块路由。

路由命名与数据库中的导航菜单 url_name 一一对应（FR-SYS-03）。

@author 王坤尧
"""

from django.urls import path

from . import views

urlpatterns = [
    # --- 多维检索（FR-QRY-01）---
    path('search/', views.employee_search, name='employee-search'),

    # --- 人事变动通知单（FR-QRY-02）---
    path('notifications/', views.NotificationDocListView.as_view(), name='notification-list'),
    path('notifications/create/', views.NotificationDocCreateView.as_view(), name='notification-create'),
    path('notifications/<int:pk>/edit/', views.NotificationDocUpdateView.as_view(), name='notification-update'),
    path('notifications/<int:pk>/print/', views.notification_print, name='notification-print'),
]
