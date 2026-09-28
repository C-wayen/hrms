"""
培训管理模块路由。

路由命名与数据库中的导航菜单 url_name 一一对应（FR-SYS-03），
修改路由名时必须同步更新菜单配置。

@author 王坤尧
"""

from django.urls import path

from . import views

urlpatterns = [
    # --- 培训课程库（FR-TRN-01）---
    path('courses/', views.CourseListView.as_view(), name='course-list'),
    path('courses/create/', views.CourseCreateView.as_view(), name='course-create'),
    path('courses/<int:pk>/edit/', views.CourseUpdateView.as_view(), name='course-update'),

    # --- 培训计划（FR-TRN-01）---
    path('plans/', views.TrainingPlanListView.as_view(), name='trainingplan-list'),
    path('plans/create/', views.TrainingPlanCreateView.as_view(), name='trainingplan-create'),
    path('plans/<int:pk>/edit/', views.TrainingPlanUpdateView.as_view(), name='trainingplan-update'),

    # --- 培训记录与成绩（FR-TRN-02）---
    path('records/', views.TrainingRecordListView.as_view(), name='trainingrecord-list'),
    path('records/create/', views.TrainingRecordCreateView.as_view(), name='trainingrecord-create'),
    path('records/<int:pk>/edit/', views.TrainingRecordUpdateView.as_view(), name='trainingrecord-update'),
]
