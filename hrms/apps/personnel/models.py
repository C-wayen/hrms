"""
人事管理模块数据模型。

本模块是 HRMS 的业务核心，覆盖员工从入职到离职的全生命周期：

    TransferRecord      调动 / 晋升 / 调薪记录      FR-PER-01
    Certificate         证书资质                    FR-PER-01
    SocialInsurance     社保基数与缴纳记录          FR-PER-02
    RegularizationApply 实习 / 试用转正申请          FR-PER-02
    Attendance          日常考勤                    FR-PER-03
    LeaveRequest        请假申请与审批（UC-05）      FR-PER-03
    RewardPunish        奖罚事件登记                FR-PER-03

关于 FR-PER-04「员工关怀」：生日提醒不建表，由 Employee.birth_date
实时推算（见 Employee.age 与报表模块的生日查询），避免每天同步一份冗余数据。

员工主表 Employee 位于 apps.sysconf（因其同时是登录账号），本模块通过
外键引用它。

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

from django.db import models

from apps.sysconf.models import Employee


# =============================================================================
# 一、档案类记录（FR-PER-01）
# =============================================================================


class TransferRecord(models.Model):
    """员工调动记录。

    对应 FR-PER-01「调动记录管理」。每次岗位/部门/薪酬级别变动都留一条记录，
    形成可追溯的调动历史；Employee 表上只保留「当前值」。

    设计说明：前后值成对保存（before_* / after_*）而非只存新值，
    这样查看历史时无需倒推，也不怕后续档案被修改。
    """

    class TransferType(models.TextChoices):
        """调动类型。"""

        TRANSFER = 'transfer', '部门调动'
        PROMOTION = 'promotion', '晋升'
        DEMOTION = 'demotion', '降职'
        SALARY_ADJUST = 'salary_adjust', '调薪'

    employee = models.ForeignKey(
        Employee,
        verbose_name='员工',
        on_delete=models.PROTECT,
        related_name='transfer_records',
    )
    transfer_type = models.CharField(
        '调动类型', max_length=20, choices=TransferType.choices
    )
    effective_date = models.DateField('生效日期')
    reason = models.CharField('调动原因', max_length=200)

    before_department = models.ForeignKey(
        'sysconf.Department', verbose_name='原部门',
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    after_department = models.ForeignKey(
        'sysconf.Department', verbose_name='新部门',
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    before_position = models.ForeignKey(
        'sysconf.Position', verbose_name='原岗位',
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    after_position = models.ForeignKey(
        'sysconf.Position', verbose_name='新岗位',
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )

    doc_no = models.CharField(
        '通知单编号', max_length=30, blank=True,
        help_text='关联 FR-QRY-02 生成的人事变动通知单',
    )
    operator = models.ForeignKey(
        Employee, verbose_name='经办人',
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '调动记录'
        verbose_name_plural = '调动记录'
        ordering = ['-effective_date']

    def __str__(self):
        return f'{self.employee.real_name} {self.get_transfer_type_display()} {self.effective_date}'


class Certificate(models.Model):
    """员工证书资质。

    对应 FR-PER-01「证书资质录入与导出」。
    """

    employee = models.ForeignKey(
        Employee,
        verbose_name='员工',
        on_delete=models.CASCADE,
        related_name='certificates',
    )
    name = models.CharField('证书名称', max_length=100)
    category = models.CharField(
        '证书类别', max_length=50, blank=True, help_text='取值来自数据字典'
    )
    cert_no = models.CharField('证书编号', max_length=50, blank=True)
    issuing_authority = models.CharField('发证机构', max_length=100, blank=True)
    issue_date = models.DateField('发证日期', null=True, blank=True)
    expire_date = models.DateField(
        '有效期至', null=True, blank=True,
        help_text='为空表示长期有效；到期前应提醒续期',
    )
    attachment = models.FileField(
        '扫描件', upload_to='certificates/%Y/', blank=True,
        help_text='对应 FR-PER-01 的证书资质录入',
    )
    remark = models.CharField('备注', max_length=200, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '证书资质'
        verbose_name_plural = '证书资质'
        ordering = ['-issue_date']
        indexes = [
            models.Index(fields=['employee', 'name'], name='idx_cert_emp_name'),
        ]

    def __str__(self):
        return f'{self.employee.real_name} - {self.name}'


# =============================================================================
# 二、社保与转正（FR-PER-02）
# =============================================================================


class SocialInsurance(models.Model):
    """社保基数与缴纳记录。

    对应 FR-PER-02「员工社保基数与缴纳记录维护」。
    个人承担合计（personal_total）是工资公式中「社保自负部分」的数据来源。

    按「员工 + 缴费月份」逐月建记录而非只存当前基数：
    社保基数每年调整一次，只存当前值会导致历史工资条无法复核。
    """

    employee = models.ForeignKey(
        Employee,
        verbose_name='员工',
        on_delete=models.PROTECT,
        related_name='social_insurances',
    )
    period = models.CharField('缴费月份', max_length=7, db_index=True, help_text='格式 YYYY-MM')
    insurance_base = models.DecimalField('缴费基数', max_digits=12, decimal_places=2)

    pension_personal = models.DecimalField('养老保险(个人)', max_digits=10, decimal_places=2, default=0)
    medical_personal = models.DecimalField('医疗保险(个人)', max_digits=10, decimal_places=2, default=0)
    unemployment_personal = models.DecimalField('失业保险(个人)', max_digits=10, decimal_places=2, default=0)
    housing_fund_personal = models.DecimalField('住房公积金(个人)', max_digits=10, decimal_places=2, default=0)
    personal_total = models.DecimalField(
        '个人承担合计', max_digits=10, decimal_places=2, default=0,
        help_text='工资核算时作为「社保自负部分」扣减',
    )

    pension_company = models.DecimalField('养老保险(单位)', max_digits=10, decimal_places=2, default=0)
    medical_company = models.DecimalField('医疗保险(单位)', max_digits=10, decimal_places=2, default=0)
    unemployment_company = models.DecimalField('失业保险(单位)', max_digits=10, decimal_places=2, default=0)
    housing_fund_company = models.DecimalField('住房公积金(单位)', max_digits=10, decimal_places=2, default=0)
    company_total = models.DecimalField('单位承担合计', max_digits=10, decimal_places=2, default=0)

    remark = models.CharField('备注', max_length=200, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '社保缴纳记录'
        verbose_name_plural = '社保缴纳记录'
        ordering = ['-period']
        # 同一员工同一月份只应有一条记录，防止重复缴纳
        unique_together = [('employee', 'period')]

    def __str__(self):
        return f'{self.employee.real_name} {self.period} 社保'

    def save(self, *args, **kwargs):
        """落库前自动汇总个人与单位承担合计，避免总分不一致。"""
        self.personal_total = sum((
            self.pension_personal or 0,
            self.medical_personal or 0,
            self.unemployment_personal or 0,
            self.housing_fund_personal or 0,
        ))
        self.company_total = sum((
            self.pension_company or 0,
            self.medical_company or 0,
            self.unemployment_company or 0,
            self.housing_fund_company or 0,
        ))
        super().save(*args, **kwargs)


class RegularizationApply(models.Model):
    """实习生 / 试用期员工的转正申请。

    对应 FR-PER-02「实习生转正申请」。

    这是一条审批流：员工本人或 HR 发起 → 部门负责人填写意见 → HR 审批。
    审批通过后由视图调用 approve()，自动把 Employee 的状态改为「正式」
    并写入转正日期，因此转正结果不需要人工二次修改档案。
    """

    class ApplyStatus(models.TextChoices):
        """审批状态机。"""

        PENDING = 'pending', '待审批'
        APPROVED = 'approved', '已通过'
        REJECTED = 'rejected', '已驳回'

    employee = models.ForeignKey(
        Employee,
        verbose_name='申请人',
        on_delete=models.CASCADE,
        related_name='regularization_applies',
    )
    apply_date = models.DateField('申请日期')
    original_status = models.CharField(
        '申请时状态',
        max_length=20,
        choices=Employee.EmployStatus.choices,
        help_text='通常为「实习」或「试用」，转正后据此判断是否合规',
    )
    expect_regular_date = models.DateField('期望转正日期')

    self_evaluation = models.TextField('自我评价', blank=True)
    department_opinion = models.TextField('部门意见', blank=True)
    hr_opinion = models.TextField('HR 意见', blank=True)

    status = models.CharField(
        '审批状态', max_length=20, choices=ApplyStatus.choices, default=ApplyStatus.PENDING
    )
    approver = models.ForeignKey(
        Employee, verbose_name='审批人',
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    approved_at = models.DateTimeField('审批时间', null=True, blank=True)

    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '转正申请'
        verbose_name_plural = '转正申请'
        ordering = ['-apply_date']
        indexes = [
            models.Index(fields=['status', 'apply_date'], name='idx_reg_status_date'),
        ]

    def __str__(self):
        return f'{self.employee.real_name} 转正申请（{self.get_status_display()}）'


# =============================================================================
# 三、考勤、请假与奖罚（FR-PER-03）
# =============================================================================


class Attendance(models.Model):
    """日常考勤记录。

    对应 FR-PER-03「考勤」。请假审批通过后会生成状态为「请假」的考勤记录，
    因此本表同时是薪酬核算中出勤天数的依据。
    """

    class AttendanceStatus(models.TextChoices):
        """考勤状态。"""

        NORMAL = 'normal', '正常'
        LATE = 'late', '迟到'
        EARLY_LEAVE = 'early_leave', '早退'
        ABSENT = 'absent', '旷工'
        LEAVE = 'leave', '请假'

    employee = models.ForeignKey(
        Employee,
        verbose_name='员工',
        on_delete=models.CASCADE,
        related_name='attendances',
    )
    work_date = models.DateField('考勤日期')
    status = models.CharField(
        '考勤状态', max_length=20, choices=AttendanceStatus.choices, default=AttendanceStatus.NORMAL
    )
    check_in = models.TimeField('上班打卡', null=True, blank=True)
    check_out = models.TimeField('下班打卡', null=True, blank=True)
    work_hours = models.DecimalField(
        '工作时长(小时)', max_digits=5, decimal_places=2, default=0
    )
    remark = models.CharField('备注', max_length=200, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '考勤记录'
        verbose_name_plural = '考勤记录'
        ordering = ['-work_date']
        # 同一员工同一天只应有一条考勤记录
        unique_together = [('employee', 'work_date')]
        indexes = [
            models.Index(fields=['work_date', 'status'], name='idx_att_date_status'),
        ]

    def __str__(self):
        return f'{self.employee.real_name} {self.work_date} {self.get_status_display()}'


class LeaveRequest(models.Model):
    """请假申请与审批。

    对应 FR-PER-03「请假申请、审批流转」与 **UC-05**。
    SRS 6.4 的活动图描述的正是本表的流转过程：

        提交 → 校验 → 待审批 → 审批
                              ├─ 通过 → 写入考勤、联动薪酬
                              └─ 驳回 → 记录意见，状态不变

    软删除说明：请假记录属于需要追溯的业务凭证，删除时置 is_deleted
    而非物理删除（与 Q4 的决策一致）。
    """

    class LeaveType(models.TextChoices):
        """请假类型。"""

        ANNUAL = 'annual', '年假'
        SICK = 'sick', '病假'
        PERSONAL = 'personal', '事假'
        MARRIAGE = 'marriage', '婚假'
        MATERNITY = 'maternity', '产假'
        BEREAVEMENT = 'bereavement', '丧假'

    class LeaveStatus(models.TextChoices):
        """审批状态机，与活动图的判定节点一一对应。"""

        PENDING = 'pending', '待审批'
        APPROVED = 'approved', '已通过'
        REJECTED = 'rejected', '已驳回'
        CANCELLED = 'cancelled', '已撤销'

    employee = models.ForeignKey(
        Employee,
        verbose_name='申请人',
        on_delete=models.PROTECT,
        related_name='leave_requests',
    )
    leave_type = models.CharField('请假类型', max_length=20, choices=LeaveType.choices)
    start_date = models.DateField('开始日期')
    end_date = models.DateField('结束日期')
    days = models.DecimalField(
        '请假天数', max_digits=5, decimal_places=1,
        help_text='支持半天（0.5）；不自动计算，因需扣除周末与法定节假日',
    )
    reason = models.TextField('请假事由')

    status = models.CharField(
        '审批状态', max_length=20, choices=LeaveStatus.choices, default=LeaveStatus.PENDING
    )
    approver = models.ForeignKey(
        Employee, verbose_name='审批人',
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    approve_opinion = models.TextField('审批意见', blank=True)
    approved_at = models.DateTimeField('审批时间', null=True, blank=True)

    is_deleted = models.BooleanField('是否已删除', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '请假申请'
        verbose_name_plural = '请假申请'
        ordering = ['-start_date']
        indexes = [
            # 待审批列表与按状态筛选是最高频查询（HR 处理请假）
            models.Index(fields=['status', 'start_date'], name='idx_leave_status_date'),
            models.Index(fields=['employee', 'status'], name='idx_leave_emp_status'),
        ]

    def __str__(self):
        return f'{self.employee.real_name} {self.get_leave_type_display()} {self.start_date}~{self.end_date}'

    @property
    def day_count(self) -> int:
        """自然日天数，仅作展示参考；实际请假天数以 days 字段为准。"""
        return (self.end_date - self.start_date).days + 1


class RewardPunish(models.Model):
    """奖罚事件登记。

    对应 FR-PER-03「奖罚事件登记」。奖金/罚款金额可参与当月工资核算。
    """

    class RecordType(models.TextChoices):
        """记录类型。"""

        REWARD = 'reward', '奖励'
        PUNISH = 'punish', '处罚'

    employee = models.ForeignKey(
        Employee,
        verbose_name='员工',
        on_delete=models.PROTECT,
        related_name='reward_punishes',
    )
    record_type = models.CharField('类型', max_length=20, choices=RecordType.choices)
    happen_date = models.DateField('发生日期')
    title = models.CharField('事项名称', max_length=100)
    amount = models.DecimalField(
        '金额(元)', max_digits=10, decimal_places=2, default=0,
        help_text='奖励为正、处罚为正数并在核算时按类型决定加减',
    )
    description = models.TextField('详细说明', blank=True)
    operator = models.ForeignKey(
        Employee, verbose_name='登记人',
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '奖罚登记'
        verbose_name_plural = '奖罚登记'
        ordering = ['-happen_date']
        indexes = [
            models.Index(fields=['employee', 'happen_date'], name='idx_rp_emp_date'),
        ]

    def __str__(self):
        return f'{self.employee.real_name} {self.get_record_type_display()} {self.title}'
