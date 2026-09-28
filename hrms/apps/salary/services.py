"""
薪酬核算服务。

把 SRS 4.3 的工资公式从视图层剥离出来放在这里，原因有三：
    1. 核算既是「一次算全公司」的批量任务，又要支持「对某个月重算」，
       还可能被测试脚本直接调用——写进视图后公式就和 HTTP 请求纠缠在一起，
       无法脱离浏览器单独验证；
    2. 公式是这份系统里最需要被逐项核对的部分，集中在一处才好对照 SRS；
    3. 事务边界（整批成功或整批回滚）只有在这里才表述得清楚。

对应文档：HRMS/code_artifact.md（SRS V1.1）4.3 工资核算公式、5.3 事务要求

@author 王坤尧
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Count, Sum

from apps.personnel.models import Attendance, SocialInsurance
from apps.sysconf.models import Employee

from .models import (
    OvertimeRecord,
    PieceworkRecord,
    SalaryRecord,
    SalaryStandard,
    UtilityFeeRecord,
)

# 【金额口径】统一保留 2 位小数。用 ROUND_HALF_UP 而非 Python 默认的
# 银行家舍入（ROUND_HALF_EVEN），是为了与财务手工对账的直觉一致：
# 0.125 四舍五入到 0.13，而不是 0.12。
MONEY = Decimal('0.01')

# 工资档案中需要用核算结果整体覆盖的字段
_RECALC_FIELDS = (
    'base_salary',
    'piecework_amount',
    'overtime_amount',
    'reward_punish_amount',
    'utility_deduction',
    'social_deduction',
    'net_pay',
)


def _money(value) -> Decimal:
    """把任意数值收敛为 2 位小数的 Decimal。

    公式里会有除法（折算加班时薪），结果可能带很多位小数；
    若不在每个中间结果上收敛，多次相加后尾差会累积到分位上。
    """
    if value is None:
        value = 0
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


# =============================================================================
# 一、公式各项的计算（SRS 4.3）
# =============================================================================


def calculate_overtime_amount(records, base_salary, standard) -> Decimal:
    """计算加班费（FR-SAL-03）。

    口径（Q2 决策）：加班时薪 = 基本工资 ÷ 月标准工时，
    再按加班类型套用倍率（工作日 1.5 / 休息日 2.0 / 法定节假日 3.0）。

    这里用 Python 循环而不是数据库聚合：因为倍率随加班类型变化，
    且倍率本身来自薪酬标准（会随生效日期改变），写成 SQL 的 CASE WHEN
    反而更难读、更难改。单个员工单月的加班条数是个位数量级，循环的代价可忽略。
    """
    if standard is None or not standard.monthly_work_hours:
        return Decimal('0')

    hourly_rate = Decimal(base_salary or 0) / Decimal(standard.monthly_work_hours)
    rate_map = {
        OvertimeRecord.OvertimeType.WORKDAY: standard.overtime_workday_rate,
        OvertimeRecord.OvertimeType.WEEKEND: standard.overtime_weekend_rate,
        OvertimeRecord.OvertimeType.HOLIDAY: standard.overtime_holiday_rate,
    }

    total = Decimal('0')
    for record in records:
        rate = rate_map.get(record.overtime_type)
        if rate is None:
            continue
        total += hourly_rate * Decimal(record.hours or 0) * Decimal(rate)
    return _money(total)


def resolve_social_deduction(employee, salary_period, base_salary, standard):
    """确定「社保自负部分」（Q1 决策）。

    优先采用该月已登记的社保缴费记录中的个人承担合计——这是真实缴费数据；
    若当月尚未登记，则按「薪酬标准中的个人负担比例 × 基本工资」估算。

    返回值带一个「来源」标记，写进工资条备注。原因：估算值与实缴值混在一起
    而不加区分，财务看到工资条无法判断这个数字能不能直接拿去对账。
    """
    record = SocialInsurance.objects.filter(
        employee=employee, period=salary_period
    ).first()
    if record:
        return _money(record.personal_total), '实缴'

    if standard is not None and standard.social_insurance_ratio:
        estimated = Decimal(base_salary or 0) * Decimal(standard.social_insurance_ratio)
        return _money(estimated), '按比例估算'

    return Decimal('0'), '无记录'


def attendance_summary(employee, salary_period) -> str:
    """汇总该周期考勤，作为工资条备注（对应 SRS 6.3 时序图「获取考勤」）。

    考勤不直接参与公式加减，但请假审批会写入考勤记录，
    把结果记进工资条备注，才能让「考勤 → 薪酬」这条数据链在界面上看得见。
    """
    year, month = (int(part) for part in salary_period.split('-'))
    rows = (
        Attendance.objects
        .filter(employee=employee, work_date__year=year, work_date__month=month)
        .values('status')
        .annotate(count=Count('id'))
    )

    labels = dict(Attendance.AttendanceStatus.choices)
    parts = [f'{labels.get(row["status"], row["status"])}{row["count"]} 天' for row in rows]
    if not parts:
        return ''

    text = '考勤：' + '、'.join(parts)
    # remark 字段是 varchar(200)，超长会被数据库按严格模式直接拒绝，这里先截断
    return text[:180]


def build_salary_record(employee, salary_period, standard) -> SalaryRecord:
    """求值一次公式，返回**尚未保存**的工资档案。

    拆出「构造」与「落库」两步，是为了让批量核算可以在一个事务里
    先算完再统一保存——中途任何一条失败都能整批回滚（测试用例 TC-SAL-02-02）。
    """
    level = employee.salary_level
    base_salary = _money(level.base_salary if level else 0)

    # 计件与计时在模型层按 work_mode 分别算好 amount，这里直接取和
    piecework_amount = _money(
        PieceworkRecord.objects.filter(
            employee=employee, salary_period=salary_period, is_deleted=False
        ).aggregate(total=Sum('amount'))['total']
    )

    overtime_amount = calculate_overtime_amount(
        OvertimeRecord.objects.filter(
            employee=employee, salary_period=salary_period, is_deleted=False
        ),
        base_salary,
        standard,
    )

    # 奖罚净额由 SalaryRecord 自己聚合（奖励为正、处罚为负），保持口径唯一
    reward_punish_amount = _money(
        SalaryRecord.aggregate_reward_punish(employee, salary_period)
    )

    utility = UtilityFeeRecord.objects.filter(
        employee=employee, salary_period=salary_period, is_deleted=False
    ).first()
    utility_deduction = _money(utility.total_fee if utility else 0)

    social_deduction, social_source = resolve_social_deduction(
        employee, salary_period, base_salary, standard
    )

    record = SalaryRecord(
        employee=employee,
        salary_period=salary_period,
        base_salary=base_salary,
        piecework_amount=piecework_amount,
        overtime_amount=overtime_amount,
        reward_punish_amount=reward_punish_amount,
        utility_deduction=utility_deduction,
        social_deduction=social_deduction,
        remark=attendance_summary(employee, salary_period),
    )
    record.calculate_net_pay()

    # 把「社保数字是怎么来的」记在实例上，便于视图/模板展示时不重复查库
    record.social_source = social_source
    return record


# =============================================================================
# 二、批量核算（FR-SAL-02）
# =============================================================================


class SalaryCalculationError(Exception):
    """核算前置条件不满足时抛出，由视图转成用户可读的提示。"""


def calculate_for_period(salary_period, employees=None):
    """核算指定薪酬周期内一批员工的工资并落库。

    返回值：(统计字典, 适用的薪酬标准, 未参与核算的说明文本)

    幂等（Q3 决策）：同一「员工 + 周期」已存在记录时**原地更新**而不是新增，
    依赖 SalaryRecord 的 unique_together 约束兜底——即使并发点了两次核算，
    数据库也不会出现两条工资记录（测试用例 TC-SAL-02-03）。

    发放锁定（Q3 决策）：已发放（paid）的记录一律跳过。工资条是财务凭证，
    已发出的钱不能因为后来补录了一条加班就悄悄改掉（测试用例 TC-SAL-02-04）。

    事务：整个循环包在一个 transaction.atomic() 里，任一条出错全部回滚，
    不会留下「算了一半」的工资表（SRS 5.3，测试用例 TC-SAL-02-02）。
    """
    standard = SalaryStandard.get_for_period(salary_period)
    if standard is None:
        raise SalaryCalculationError(
            f'没有找到适用于 {salary_period} 的薪酬标准，请先在「薪酬标准」中配置。'
        )

    if employees is None:
        employees = (
            Employee.objects
            .filter(is_deleted=False, salary_level__isnull=False)
            .exclude(employ_status=Employee.EmployStatus.RESIGNED)
            .select_related('department', 'salary_level')
            .order_by('employee_no')
        )

    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'total': 0}
    notes = []

    with transaction.atomic():
        # 先把该周期已有的记录一次取出做成映射，避免循环里逐个查库（N+1）
        existing_map = {
            record.employee_id: record
            for record in SalaryRecord.objects.filter(salary_period=salary_period)
        }

        for employee in employees:
            stats['total'] += 1
            existing = existing_map.get(employee.pk)

            if existing and existing.pay_status == SalaryRecord.PayStatus.PAID:
                stats['skipped'] += 1
                continue

            fresh = build_salary_record(employee, salary_period, standard)

            if existing:
                for field in _RECALC_FIELDS:
                    setattr(existing, field, getattr(fresh, field))
                existing.remark = fresh.remark
                existing.save()
                stats['updated'] += 1
            else:
                fresh.save()
                stats['created'] += 1

    # 说明哪些人没被算到：不提示的话，用户会以为「怎么少了两个人」
    no_level = Employee.objects.filter(
        is_deleted=False, salary_level__isnull=True
    ).exclude(employ_status=Employee.EmployStatus.RESIGNED).count()
    if no_level:
        notes.append(f'{no_level} 名员工未配置薪酬级别，本次未参与核算')
    if stats['skipped']:
        notes.append(f"{stats['skipped']} 条记录已发放，按规则跳过未重算")

    return stats, standard, '；'.join(notes)
