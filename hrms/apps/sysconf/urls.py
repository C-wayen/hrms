"""
系统设置模块路由。

路由命名与数据库中的导航菜单 url_name 一一对应（FR-SYS-03）：
department-list / datadict-list / employee-account / menu-list
改名字必须同步改 scripts/init_data.py 里的 MENUS，否则侧边栏会退化为「#」。

这四个入口原先由 config/urls.py 直接 RedirectView 到 Django Admin，
现在改为本模块自己渲染，以便留在系统主框架内。

@author 王坤尧
"""

from django.urls import path

from . import views

urlpatterns = [
    # --- 组织机构（FR-SYS-02）---
    path('departments/', views.DepartmentListView.as_view(), name='department-list'),
    path('departments/create/', views.DepartmentCreateView.as_view(), name='department-create'),
    path('departments/<int:pk>/edit/', views.DepartmentUpdateView.as_view(), name='department-update'),
    path('departments/<int:pk>/delete/', views.DepartmentDeleteView.as_view(), name='department-delete'),

    # --- 数据字典（FR-SYS-02）---
    path('dicts/', views.DataDictListView.as_view(), name='datadict-list'),
    path('dicts/create/', views.DataDictCreateView.as_view(), name='datadict-create'),
    path('dicts/<int:pk>/edit/', views.DataDictUpdateView.as_view(), name='datadict-update'),
    path('dicts/<int:pk>/delete/', views.DataDictDeleteView.as_view(), name='datadict-delete'),

    # --- 用户与角色（FR-SYS-01、FR-SYS-03）---
    # 只有列表与编辑：新增账号等同于建档，走「人事管理 - 新增职工」，
    # 避免两处都能建人而字段校验不一致
    path('accounts/', views.EmployeeAccountListView.as_view(), name='employee-account'),
    path('accounts/<int:pk>/edit/', views.EmployeeAccountUpdateView.as_view(), name='account-update'),

    # --- 导航菜单（FR-SYS-03）---
    path('menus/', views.MenuListView.as_view(), name='menu-list'),
    path('menus/create/', views.MenuCreateView.as_view(), name='menu-create'),
    path('menus/<int:pk>/edit/', views.MenuUpdateView.as_view(), name='menu-update'),
    path('menus/<int:pk>/delete/', views.MenuDeleteView.as_view(), name='menu-delete'),
]
