"""
系统设置与安全模块视图。

关联需求：FR-SYS-01 权限控制、FR-SYS-03 用户与菜单管理、FR-PER-04 员工关怀

@author 王坤尧
"""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.personnel.models import LeaveRequest, RegularizationApply
from apps.sysconf.models import Department, Employee


@login_required
def home(request):
    """首页仪表盘。

    展示两类信息，回答「现在公司什么情况」与「我需要处理什么」：
      1. 关键指标卡片：在职人数、实习人数、部门数
      2. 待办提醒：本周生日员工（FR-PER-04）、待审批请假与转正申请
         （FR-PER-03 / FR-PER-02）

    查询均加 select_related，避免模板里访问 employee 时触发 N+1。
    """
    today = timezone.localdate()
    employees = Employee.objects.filter(is_deleted=False)

    stats = {
        'total': employees.count(),
        'on_job': employees.exclude(
            employ_status=Employee.EmployStatus.RESIGNED
        ).count(),
        'intern': employees.filter(employ_status=Employee.EmployStatus.INTERN).count(),
        'departments': Department.objects.filter(is_active=True).count(),
    }

    # 本周生日员工：按月日区间筛选，跨月时用两个条件取并集
    week_end = today + timedelta(days=7)
    if today.month == week_end.month:
        birthday_q = employees.filter(
            birth_date__month=today.month,
            birth_date__day__range=(today.day, week_end.day),
        )
    else:
        from django.db.models import Q

        birthday_q = employees.filter(
            Q(birth_date__month=today.month, birth_date__day__gte=today.day)
            | Q(birth_date__month=week_end.month, birth_date__day__lte=week_end.day)
        )

    context = {
        'stats': stats,
        'birthdays': birthday_q.select_related('department').order_by('birth_date__day')[:6],
        'pending_leaves': (
            LeaveRequest.objects
            .filter(status=LeaveRequest.LeaveStatus.PENDING, is_deleted=False)
            .select_related('employee', 'employee__department')
            .order_by('start_date')[:6]
        ),
        'pending_regularizations': (
            RegularizationApply.objects
            .filter(status=RegularizationApply.ApplyStatus.PENDING)
            .select_related('employee')
            .order_by('expect_regular_date')[:6]
        ),
        'today': today,
    }
    return render(request, 'home.html', context)
