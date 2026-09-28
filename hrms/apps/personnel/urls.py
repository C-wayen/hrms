"""
人事管理模块路由。

路由命名与数据库中的导航菜单 url_name 一一对应（FR-SYS-03），
修改路由名时必须同步更新菜单配置，否则侧边栏会退化为不可点击的「#」。

@author 王坤尧
"""

from django.urls import path

from . import views

urlpatterns = [
    # --- 职工档案（FR-PER-01）---
    path('employees/', views.EmployeeListView.as_view(), name='employee-list'),
    path('employees/create/', views.EmployeeCreateView.as_view(), name='employee-create'),
    path('employees/<int:pk>/', views.EmployeeDetailView.as_view(), name='employee-detail'),
    path('employees/<int:pk>/edit/', views.EmployeeUpdateView.as_view(), name='employee-update'),
    path('employees/<int:pk>/delete/', views.EmployeeDeleteView.as_view(), name='employee-delete'),

    # --- 转正申请（FR-PER-02）---
    path('regularizations/', views.RegularizationListView.as_view(), name='regularization-list'),
    path('regularizations/create/', views.RegularizationCreateView.as_view(), name='regularization-create'),
    path('regularizations/<int:pk>/approve/', views.regularization_approve, name='regularization-approve'),

    # --- 社保管理（FR-PER-02）---
    path('social-insurances/', views.SocialInsuranceListView.as_view(), name='socialinsurance-list'),
    path('social-insurances/create/', views.SocialInsuranceCreateView.as_view(), name='socialinsurance-create'),
    path('social-insurances/<int:pk>/edit/', views.SocialInsuranceUpdateView.as_view(), name='socialinsurance-update'),
    path('social-insurances/<int:pk>/delete/', views.SocialInsuranceDeleteView.as_view(), name='socialinsurance-delete'),

    # --- 考勤（FR-PER-03）---
    path('attendances/', views.AttendanceListView.as_view(), name='attendance-list'),
    path('attendances/create/', views.AttendanceCreateView.as_view(), name='attendance-create'),
    path('attendances/<int:pk>/edit/', views.AttendanceUpdateView.as_view(), name='attendance-update'),

    # --- 请假（FR-PER-03、UC-05）---
    path('leaves/', views.LeaveListView.as_view(), name='leave-list'),
    path('leaves/create/', views.LeaveCreateView.as_view(), name='leave-create'),
    path('leaves/<int:pk>/approve/', views.leave_approve, name='leave-approve'),

    # --- 奖罚登记（FR-PER-03）---
    path('reward-punishes/', views.RewardPunishListView.as_view(), name='rewardpunish-list'),
    path('reward-punishes/create/', views.RewardPunishCreateView.as_view(), name='rewardpunish-create'),
    path('reward-punishes/<int:pk>/edit/', views.RewardPunishUpdateView.as_view(), name='rewardpunish-update'),

    # --- 员工关怀（FR-PER-04）---
    path('birthdays/', views.birthday_list, name='birthday-list'),
]
