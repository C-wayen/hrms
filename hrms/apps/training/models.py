"""
培训管理模块数据模型。

    Course          培训课程库                FR-TRN-01
    TrainingPlan    内部培训计划              FR-TRN-01
    TrainingRecord  培训 / 考核记录与成绩     FR-TRN-02

设计说明：课程与计划分开建表——课程是可复用的知识资产（一门课可以办很多期），
计划是一次具体的办班活动。培训记录挂在计划上而非课程上，这样才能区分
「同一门课不同期的成绩」。

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

from django.db import models

from apps.sysconf.models import Employee


class Course(models.Model):
    """培训课程库。

    对应 FR-TRN-01「建立培训课程库」。
    """

    class CourseType(models.TextChoices):
        """课程类型。区分「内部培训」与「一线工培训」两条需求线。"""

        INTERNAL = 'internal', '内部培训'
        EXTERNAL = 'external', '外部培训'
        FRONTLINE = 'frontline', '一线工技能培训'

    name = models.CharField('课程名称', max_length=100)
    code = models.CharField('课程编码', max_length=20, unique=True)
    course_type = models.CharField('课程类型', max_length=20, choices=CourseType.choices)
    instructor = models.CharField('讲师', max_length=50, blank=True)
    duration_hours = models.DecimalField(
        '课时(小时)', max_digits=5, decimal_places=1, default=0
    )
    description = models.TextField('课程简介', blank=True)
    is_active = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '培训课程'
        verbose_name_plural = '培训课程'
        ordering = ['code']

    def __str__(self):
        return self.name


class TrainingPlan(models.Model):
    """内部培训计划（一次具体的办班活动）。

    对应 FR-TRN-01「制定内部培训计划」。
    """

    class PlanStatus(models.TextChoices):
        """计划状态。"""

        DRAFT = 'draft', '草稿'
        ONGOING = 'ongoing', '进行中'
        FINISHED = 'finished', '已结束'
        CANCELLED = 'cancelled', '已取消'

    name = models.CharField('计划名称', max_length=100)
    course = models.ForeignKey(
        Course,
        verbose_name='培训课程',
        on_delete=models.PROTECT,
        related_name='plans',
    )
    start_date = models.DateField('开始日期')
    end_date = models.DateField('结束日期')
    location = models.CharField('培训地点', max_length=100, blank=True)
    target_departments = models.ManyToManyField(
        'sysconf.Department',
        verbose_name='面向部门',
        blank=True,
        related_name='training_plans',
        help_text='留空表示面向全体员工',
    )
    planned_headcount = models.PositiveIntegerField('计划人数', default=0)
    status = models.CharField(
        '计划状态', max_length=20, choices=PlanStatus.choices, default=PlanStatus.DRAFT
    )
    organizer = models.ForeignKey(
        Employee, verbose_name='负责人',
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    remark = models.CharField('备注', max_length=200, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '培训计划'
        verbose_name_plural = '培训计划'
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['status', 'start_date'], name='idx_plan_status_date'),
        ]

    def __str__(self):
        return f'{self.name}（{self.start_date}~{self.end_date}）'


class TrainingRecord(models.Model):
    """培训 / 考核记录与成绩。

    对应 FR-TRN-02「一线工人技能培训考核与成绩登记」。
    """

    class AttendStatus(models.TextChoices):
        """参与与考核状态。"""

        ENROLLED = 'enrolled', '已报名'
        ATTENDED = 'attended', '已参加'
        ABSENT = 'absent', '缺勤'
        PASSED = 'passed', '考核通过'
        FAILED = 'failed', '考核未通过'

    plan = models.ForeignKey(
        TrainingPlan,
        verbose_name='培训计划',
        on_delete=models.CASCADE,
        related_name='records',
    )
    employee = models.ForeignKey(
        Employee,
        verbose_name='参训员工',
        on_delete=models.CASCADE,
        related_name='training_records',
    )
    attend_status = models.CharField(
        '参与状态', max_length=20, choices=AttendStatus.choices, default=AttendStatus.ENROLLED
    )
    score = models.DecimalField(
        '考核成绩', max_digits=5, decimal_places=1, null=True, blank=True
    )
    certificate_no = models.CharField('结业证书编号', max_length=50, blank=True)
    remark = models.CharField('备注', max_length=200, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '培训记录'
        verbose_name_plural = '培训记录'
        ordering = ['-created_at']
        # 同一计划下同一员工只能有一条记录
        unique_together = [('plan', 'employee')]
        indexes = [
            models.Index(fields=['employee', 'attend_status'], name='idx_tr_emp_status'),
        ]

    def __str__(self):
        return f'{self.employee.real_name} - {self.plan.name}'
