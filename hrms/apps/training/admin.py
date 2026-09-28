"""
培训管理模块的 Django Admin 配置。

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

from django.contrib import admin

from .models import Course, TrainingPlan, TrainingRecord


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    """培训课程库（FR-TRN-01）。"""

    list_display = ('code', 'name', 'course_type', 'instructor', 'duration_hours', 'is_active')
    list_filter = ('course_type', 'is_active')
    search_fields = ('code', 'name', 'instructor')


@admin.register(TrainingPlan)
class TrainingPlanAdmin(admin.ModelAdmin):
    """内部培训计划（FR-TRN-01）。"""

    list_display = ('name', 'course', 'start_date', 'end_date', 'location', 'status', 'planned_headcount')
    list_filter = ('status', 'start_date')
    search_fields = ('name', 'course__name')
    list_select_related = ('course', 'organizer')
    filter_horizontal = ('target_departments',)
    date_hierarchy = 'start_date'


@admin.register(TrainingRecord)
class TrainingRecordAdmin(admin.ModelAdmin):
    """培训与考核成绩（FR-TRN-02）。"""

    list_display = ('employee', 'plan', 'attend_status', 'score', 'certificate_no')
    list_filter = ('attend_status', 'plan')
    search_fields = ('employee__real_name', 'employee__employee_no', 'plan__name')
    list_select_related = ('employee', 'plan')
