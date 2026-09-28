"""
薪酬管理模块数据模型。

本模块负责薪酬体系配置、考勤性收入的登记，以及最终工资的核算与发放：

    SalaryLevel        薪酬级别与基本工资            FR-SAL-01
    SalaryStandard     加班 / 水电 / 社保标准        FR-SAL-01、FR-SYS-02
    OvertimeRecord     加班登记                      FR-SAL-03
    UtilityFeeRecord   水电费扣费登记                FR-SAL-03
    PieceworkRecord    计件 / 计时产量登记           FR-SAL-02
    SalaryRecord       工资档案（核算结果）          FR-SAL-02

工资核算公式（SRS 4.3）：

    实发工资 = 基本工资 + 计件/计时工资 + 加班费 + 奖罚净额 − 水电扣费 − 社保自负部分

    其中「奖罚净额」= 本周期奖励合计 − 处罚合计，可为负（数据来自 FR-PER-03 奖罚登记）。

事务要求：批量生成 SalaryRecord 必须用 transaction.atomic() 包裹，
任一条失败则整批回滚，不得产生半截工资记录（SRS 5.3，测试用例 TC-SAL-02-02）。

幂等要求：同一员工同一周期只应存在一条工资档案（unique_together 约束）；
重复核算时更新已有记录而不再新增，且「已发放」记录不参与重算
（测试用例 TC-SAL-02-03、TC-SAL-02-04）。

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum


# =============================================================================
# 一、薪酬体系配置（FR-SAL-01）
# =============================================================================


class SalaryLevel(models.Model):
    """薪酬级别。

    对应 FR-SAL-01「设定薪酬级别」。员工通过 Employee.salary_level 关联到级别，
    核算工资时以级别的 base_salary 作为公式中的「基本工资」。
    """

    name = models.CharField('级别名称', max_length=50)
    code = models.CharField('级别编码', max_length=20, unique=True)
    base_salary = models.DecimalField('基本工资', max_digits=10, decimal_places=2)
    post_allowance = models.DecimalField(
        '岗位津贴', max_digits=10, decimal_places=2, default=0
    )
    remark = models.CharField('说明', max_length=200, blank=True)
    is_active = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '薪酬级别'
        verbose_name_plural = '薪酬级别'
        ordering = ['code']

    def __str__(self):
        return f'{self.name}（基本工资 {self.base_salary}）'


class SalaryStandard(models.Model):
    """薪酬与扣缴标准（全局配置）。

    对应 FR-SAL-01「设定加班补贴标准、水电费扣除标准」与 FR-SYS-02「社保比例配置」。

    设计说明：按 effective_date 保留多条历史记录，核算某个月工资时取「生效日期
    不晚于该周期」的最新一条。这样后续调整标准后重算历史工资，结果仍然正确——
    若只存一行并直接覆盖，历史工资就再也算不出来了。
    """

    effective_date = models.DateField('生效日期')
    overtime_workday_rate = models.DecimalField(
        '工作日加班倍率', max_digits=4, decimal_places=2, default=1.50,
        help_text='按劳动法：工作日加班为基本时薪的 1.5 倍',
    )
    overtime_weekend_rate = models.DecimalField(
        '休息日加班倍率', max_digits=4, decimal_places=2, default=2.00,
    )
    overtime_holiday_rate = models.DecimalField(
        '法定节假日加班倍率', max_digits=4, decimal_places=2, default=3.00,
    )
    monthly_work_hours = models.DecimalField(
        '月标准工时(小时)', max_digits=6, decimal_places=2, default=21.75 * 8,
        help_text='用于把月基本工资折算为时薪，默认 21.75 天 × 8 小时',
    )
    water_price = models.DecimalField(
        '水费单价(元/吨)', max_digits=8, decimal_places=2, default=0,
    )
    electricity_price = models.DecimalField(
        '电费单价(元/度)', max_digits=8, decimal_places=2, default=0,
    )
    social_insurance_ratio = models.DecimalField(
        '社保个人负担比例', max_digits=5, decimal_places=4, default=0,
        help_text='如 0.105 表示个人承担 10.5%',
    )
    is_active = models.BooleanField('是否启用', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '薪酬标准配置'
        verbose_name_plural = '薪酬标准配置'
        ordering = ['-effective_date']
        get_latest_by = 'effective_date'

    def __str__(self):
        return f'{self.effective_date} 起生效的标准'

    @classmethod
    def get_for_period(cls, salary_period: str):
        """取适用于指定薪酬周期（'YYYY-MM'）的标准。

        salary_period 为 '2026-09' 时，取生效日期早于 2026-10-01 的最新一条。

        上界用「下月 1 日」而不是拼接 '-31'：4、6、9、11 月根本没有 31 日，
        拼出来的 '2026-09-31' 会让 Django 直接抛 ValidationError。
        """
        year, month = (int(part) for part in salary_period.split('-'))
        next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)

        return (
            cls.objects.filter(is_active=True, effective_date__lt=next_month)
            .order_by('-effective_date')
            .first()
        )


# =============================================================================
# 二、津贴与扣减项的日常登记（FR-SAL-03）
# =============================================================================


class OvertimeRecord(models.Model):
    """加班登记。

    对应 FR-SAL-03「加班时长与事由登记」，是工资公式中「加班费」的数据来源。
    原始课程清单在薪酬模块下单独列有「加班登记」，本表即其实现。
    """

    class OvertimeType(models.TextChoices):
        """加班类型。不同类型对应 SalaryStandard 中的不同倍率。"""

        WORKDAY = 'workday', '工作日'
        WEEKEND = 'weekend', '休息日'
        HOLIDAY = 'holiday', '法定节假日'

    employee = models.ForeignKey(
        'sysconf.Employee',
        verbose_name='员工',
        on_delete=models.PROTECT,
        related_name='overtime_records',
    )
    overtime_date = models.DateField('加班日期')
    overtime_type = models.CharField(
        '加班类型', max_length=10, choices=OvertimeType.choices
    )
    hours = models.DecimalField('加班时长(小时)', max_digits=5, decimal_places=1)
    reason = models.CharField('加班事由', max_length=200, blank=True)
    # 冗余存薪酬周期（'YYYY-MM'），避免核算时反复按日期做范围查询，也便于按周期聚合
    salary_period = models.CharField('所属薪酬周期', max_length=7, db_index=True)

    is_deleted = models.BooleanField('是否已删除', default=False)
    created_by = models.ForeignKey(
        'sysconf.Employee',
        verbose_name='登记人',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '加班登记'
        verbose_name_plural = '加班登记'
        ordering = ['-overtime_date']
        indexes = [
            models.Index(fields=['employee', 'salary_period'], name='idx_ot_emp_period'),
        ]

    def __str__(self):
        return f'{self.employee.real_name} {self.overtime_date} 加班 {self.hours} 小时'


class UtilityFeeRecord(models.Model):
    """宿舍水电费扣费登记。

    对应 FR-SAL-03「水电费抄表与扣费登记」，是工资公式中「水电扣费」的数据来源。
    原始课程清单在薪酬模块下单独列有「水电费登记」，本表即其实现。

    金额在保存时按 SalaryStandard 的单价自动算出并落库，
    避免以后调整单价导致历史账单被重算。
    """

    employee = models.ForeignKey(
        'sysconf.Employee',
        verbose_name='员工',
        on_delete=models.PROTECT,
        related_name='utility_records',
    )
    salary_period = models.CharField('所属薪酬周期', max_length=7, db_index=True)
    water_usage = models.DecimalField('用水量(吨)', max_digits=8, decimal_places=2, default=0)
    electricity_usage = models.DecimalField('用电量(度)', max_digits=8, decimal_places=2, default=0)
    water_fee = models.DecimalField('水费(元)', max_digits=10, decimal_places=2, default=0)
    electricity_fee = models.DecimalField('电费(元)', max_digits=10, decimal_places=2, default=0)
    total_fee = models.DecimalField('合计扣费(元)', max_digits=10, decimal_places=2, default=0)
    remark = models.CharField('备注', max_length=200, blank=True)

    is_deleted = models.BooleanField('是否已删除', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '水电费登记'
        verbose_name_plural = '水电费登记'
        ordering = ['-salary_period']
        # 同一员工同一薪酬周期只应有一条水电费记录
        unique_together = [('employee', 'salary_period')]

    def __str__(self):
        return f'{self.employee.real_name} {self.salary_period} 水电费 {self.total_fee} 元'

    def save(self, *args, **kwargs):
        """落库前自动汇总合计扣费，防止手工填写不一致。"""
        self.total_fee = (self.water_fee or 0) + (self.electricity_fee or 0)
        super().save(*args, **kwargs)


# =============================================================================
# 三、计件 / 计时产量（FR-SAL-02 的数据来源）
# =============================================================================


class PieceworkRecord(models.Model):
    """计件 / 计时产量登记。

    对应 FR-SAL-02「支持计件工资与计时工资混合计算」。

    需求说明：课程原始功能清单中并没有「产量登记」这一条目，但「计件工资」
    必须依赖产量数据才能计算。若不建本表，计件工资就只能靠手工填一个总额，
    「支持计件与计时混合计算」这句话在答辩时站不住。因此这里补齐该数据来源。
    """

    class WorkMode(models.TextChoices):
        """计薪方式。同一员工同一周期可混用，核算时分别汇总后相加。"""

        PIECEWORK = 'piecework', '计件'
        TIMEWORK = 'timework', '计时'

    employee = models.ForeignKey(
        'sysconf.Employee',
        verbose_name='员工',
        on_delete=models.PROTECT,
        related_name='piecework_records',
    )
    salary_period = models.CharField('所属薪酬周期', max_length=7, db_index=True)
    work_date = models.DateField('生产日期')
    work_mode = models.CharField('计薪方式', max_length=10, choices=WorkMode.choices)
    product_name = models.CharField('产品 / 工序', max_length=100, blank=True)

    # 计件用字段
    quantity = models.DecimalField('数量(件)', max_digits=10, decimal_places=2, default=0)
    unit_price = models.DecimalField('单价(元/件)', max_digits=10, decimal_places=2, default=0)

    # 计时用字段
    hours = models.DecimalField('工时(小时)', max_digits=6, decimal_places=2, default=0)
    hourly_rate = models.DecimalField('时薪(元/小时)', max_digits=10, decimal_places=2, default=0)

    amount = models.DecimalField(
        '小计金额(元)', max_digits=12, decimal_places=2, default=0,
        help_text='保存时按计薪方式自动计算，不由人工填写',
    )
    remark = models.CharField('备注', max_length=200, blank=True)

    is_deleted = models.BooleanField('是否已删除', default=False)
    created_by = models.ForeignKey(
        'sysconf.Employee',
        verbose_name='登记人',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '计件/计时产量'
        verbose_name_plural = '计件/计时产量'
        ordering = ['-work_date']
        indexes = [
            models.Index(fields=['employee', 'salary_period'], name='idx_pw_emp_period'),
        ]

    def __str__(self):
        return f'{self.employee.real_name} {self.work_date} {self.get_work_mode_display()}'

    def save(self, *args, **kwargs):
        """落库前按计薪方式自动算出小计金额，避免人工填写出错。"""
        if self.work_mode == self.WorkMode.PIECEWORK:
            self.amount = (self.quantity or 0) * (self.unit_price or 0)
        else:
            self.amount = (self.hours or 0) * (self.hourly_rate or 0)
        super().save(*args, **kwargs)


# =============================================================================
# 四、工资档案（FR-SAL-02）
# =============================================================================


class SalaryRecord(models.Model):
    """工资档案 —— 一次核算的结果。

    对应 FR-SAL-02「生成工资档案；支持批量发放与历史薪酬查询」。

    各金额字段在核算时一次性算好并落库（而非每次展示时现算），原因：
    工资条是财务凭证，必须与发放当时一致，不能因标准调整而变动。
    """

    class PayStatus(models.TextChoices):
        """发放状态。"""

        DRAFT = 'draft', '待发放'
        PAID = 'paid', '已发放'

    employee = models.ForeignKey(
        'sysconf.Employee',
        verbose_name='员工',
        on_delete=models.PROTECT,
        related_name='salary_records',
    )
    salary_period = models.CharField('薪酬周期', max_length=7, db_index=True)

    # --- 公式各项（SRS 4.3）---
    base_salary = models.DecimalField('基本工资', max_digits=12, decimal_places=2, default=0)
    piecework_amount = models.DecimalField(
        '计件/计时工资', max_digits=12, decimal_places=2, default=0
    )
    overtime_amount = models.DecimalField('加班费', max_digits=12, decimal_places=2, default=0)
    reward_punish_amount = models.DecimalField(
        '奖罚净额',
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='本周期奖励合计减去处罚合计，可为负（数据来自 FR-PER-03 奖罚登记）',
    )
    utility_deduction = models.DecimalField(
        '水电扣费', max_digits=12, decimal_places=2, default=0
    )
    social_deduction = models.DecimalField(
        '社保自负部分', max_digits=12, decimal_places=2, default=0
    )
    net_pay = models.DecimalField(
        '实发工资', max_digits=12, decimal_places=2, default=0,
        help_text='由 calculate_net_pay() 按公式计算',
    )

    pay_status = models.CharField(
        '发放状态', max_length=10, choices=PayStatus.choices, default=PayStatus.DRAFT
    )
    paid_at = models.DateTimeField('发放时间', null=True, blank=True)
    remark = models.CharField('备注', max_length=200, blank=True)

    is_deleted = models.BooleanField('是否已删除', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '工资档案'
        verbose_name_plural = '工资档案'
        ordering = ['-salary_period', 'employee__employee_no']
        # 同一员工同一薪酬周期只允许一条工资记录，防止重复核算导致重发
        unique_together = [('employee', 'salary_period')]
        indexes = [
            models.Index(fields=['salary_period', 'pay_status'], name='idx_sal_period_status'),
        ]

    def __str__(self):
        return f'{self.employee.real_name} {self.salary_period} 实发 {self.net_pay}'

    def calculate_net_pay(self):
        """按 SRS 4.3 公式计算实发工资：

            实发工资 = 基本工资 + 计件/计时工资 + 加班费 + 奖罚净额
                       − 水电扣费 − 社保自负部分

        只赋值不保存，由调用方在事务内统一保存，便于批量核算时整体回滚。

        注意：奖罚净额用**加法**而非减法——其符号由字段自身正负决定，
        处罚多于奖励时该字段为负，相加即自动扣减。
        """
        self.net_pay = (
            (self.base_salary or 0)
            + (self.piecework_amount or 0)
            + (self.overtime_amount or 0)
            + (self.reward_punish_amount or 0)
            - (self.utility_deduction or 0)
            - (self.social_deduction or 0)
        )
        return self.net_pay

    @classmethod
    def aggregate_reward_punish(cls, employee, salary_period):
        """汇总某员工某薪酬周期的奖罚净额（FR-PER-03 → 工资公式的一项）。

        奖励计正、处罚计负，返回净额（可为负）；周期按 happen_date 的年月匹配。
        用数据库端聚合而非取回后在 Python 里循环累加，避免记录多时产生大量对象。
        """
        from apps.personnel.models import RewardPunish

        year, month = salary_period.split('-')
        result = RewardPunish.objects.filter(
            employee=employee,
            happen_date__year=int(year),
            happen_date__month=int(month),
        ).aggregate(
            reward=Sum('amount', filter=Q(record_type=RewardPunish.RecordType.REWARD)),
            punish=Sum('amount', filter=Q(record_type=RewardPunish.RecordType.PUNISH)),
        )
        return (result['reward'] or Decimal('0')) - (result['punish'] or Decimal('0'))
