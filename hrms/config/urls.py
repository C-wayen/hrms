"""
HRMS 根路由表。

本文件只做总调度：各业务模块的路由分散在各自 app 的 urls.py 中，
再通过 include() 挂载到这里，以保持根路由表简洁。

新增模块时在下方 urlpatterns 中追加一行，例如：
    path('personnel/', include('apps.personnel.urls')),   # 模块 1 人事管理

官方文档：https://docs.djangoproject.com/en/5.2/topics/http/urls/

@author 王坤尧
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from apps.sysconf import views as sysconf_views

urlpatterns = [
    # Django 自带后台。承载「用户与菜单管理」「数据字典」等系统级功能（FR-SYS-03）
    path('admin/', admin.site.urls),

    # --- 认证：使用内置视图，模板位于 templates/registration/ ---
    path('login/', auth_views.LoginView.as_view(), name='login'),
    # Django 5 起登出必须用 POST：模板中以表单提交，
    # 避免浏览器预取链接导致用户被意外登出
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # --- 业务模块：每个模块一个 urls.py，此处只做挂载 ---
    path('personnel/', include('apps.personnel.urls')),   # 模块 1 人事管理
    path('training/', include('apps.training.urls')),     # 模块 2 培训管理
    path('salary/', include('apps.salary.urls')),         # 模块 3 薪酬管理
    path('query/', include('apps.pubquery.urls')),        # 模块 4 公共查询
    path('report/', include('apps.reporting.urls')),      # 模块 5 报表统计
    path('assistant/', include('apps.assistant.urls')),   # 模块 6 智能助手

    # --- 系统设置（FR-SYS-01 ~ 03）：直接复用 Django Admin 的对应页面 ---
    # 不重复开发：admin 已能完整管理基础数据与权限，这里只补命名路由，
    # 让侧边栏菜单能正常跳转（用 pattern_name 而非硬编码 URL，改 admin 路径不受影响）
    path('system/departments/', RedirectView.as_view(
        pattern_name='admin:sysconf_department_changelist'), name='department-list'),
    path('system/dicts/', RedirectView.as_view(
        pattern_name='admin:sysconf_datadict_changelist'), name='datadict-list'),
    path('system/accounts/', RedirectView.as_view(
        pattern_name='admin:sysconf_employee_changelist'), name='employee-account'),
    path('system/menus/', RedirectView.as_view(
        pattern_name='admin:sysconf_menu_changelist'), name='menu-list'),

    # --- 首页仪表盘（放在最后，避免根路径抢占子模块路由）---
    path('', sysconf_views.home, name='home'),
]
