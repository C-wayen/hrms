"""
薪酬管理模块路由。

路由命名与数据库中的导航菜单 url_name 一一对应（FR-SYS-03），
修改路由名时必须同步更新菜单配置，否则侧边栏会退化为不可点击的「#」。

@author 王坤尧
"""

from django.urls import path

from . import views

urlpatterns = [
    # --- 薪酬级别（FR-SAL-01）---
    path('levels/', views.SalaryLevelListView.as_view(), name='salarylevel-list'),
    path('levels/create/', views.SalaryLevelCreateView.as_view(), name='salarylevel-create'),
    path('levels/<int:pk>/edit/', views.SalaryLevelUpdateView.as_view(), name='salarylevel-update'),
    path('levels/<int:pk>/delete/', views.SalaryLevelDeleteView.as_view(), name='salarylevel-delete'),

    # --- 薪酬标准（FR-SAL-01、FR-SYS-02）---
    path('standards/', views.SalaryStandardListView.as_view(), name='salarystandard-list'),
    path('standards/create/', views.SalaryStandardCreateView.as_view(), name='salarystandard-create'),
    path('standards/<int:pk>/edit/', views.SalaryStandardUpdateView.as_view(), name='salarystandard-update'),
    path('standards/<int:pk>/delete/', views.SalaryStandardDeleteView.as_view(), name='salarystandard-delete'),

    # --- 加班登记（FR-SAL-03）---
    path('overtimes/', views.OvertimeRecordListView.as_view(), name='overtime-list'),
    path('overtimes/create/', views.OvertimeRecordCreateView.as_view(), name='overtime-create'),
    path('overtimes/<int:pk>/edit/', views.OvertimeRecordUpdateView.as_view(), name='overtime-update'),
    path('overtimes/<int:pk>/delete/', views.OvertimeRecordDeleteView.as_view(), name='overtime-delete'),

    # --- 水电费登记（FR-SAL-03）---
    path('utilities/', views.UtilityFeeRecordListView.as_view(), name='utilityfee-list'),
    path('utilities/create/', views.UtilityFeeRecordCreateView.as_view(), name='utilityfee-create'),
    path('utilities/<int:pk>/edit/', views.UtilityFeeRecordUpdateView.as_view(), name='utilityfee-update'),
    path('utilities/<int:pk>/delete/', views.UtilityFeeRecordDeleteView.as_view(), name='utilityfee-delete'),

    # --- 计件 / 计时产量（FR-SAL-02）---
    path('pieceworks/', views.PieceworkRecordListView.as_view(), name='piecework-list'),
    path('pieceworks/create/', views.PieceworkRecordCreateView.as_view(), name='piecework-create'),
    path('pieceworks/<int:pk>/edit/', views.PieceworkRecordUpdateView.as_view(), name='piecework-update'),
    path('pieceworks/<int:pk>/delete/', views.PieceworkRecordDeleteView.as_view(), name='piecework-delete'),

    # --- 工资核算与发放（FR-SAL-02）---
    # 注意：calculate 必须排在 <int:pk> 之前虽非必需（'calculate' 不是整数），
    # 但放在这里更符合「先特殊后一般」的阅读顺序
    path('records/calculate/', views.SalaryCalculateView.as_view(), name='salary-calculate'),
    path('records/pay/', views.salary_pay, name='salary-pay'),
    path('records/', views.SalaryRecordListView.as_view(), name='salaryrecord-list'),
    path('records/<int:pk>/', views.SalaryRecordDetailView.as_view(), name='salaryrecord-detail'),

    # --- 我的工资（FR-SAL-02 自助查询）---
    path('my-salary/', views.MySalaryListView.as_view(), name='my-salary'),
]
