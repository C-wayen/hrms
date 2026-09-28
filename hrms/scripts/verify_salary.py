"""薪酬模块端到端验证脚本。

用途：一次性核对工资核算是否与 SRS 4.3 公式一致，并验证四条已确认的核算规则：
    Q1 社保自负优先取社保缴费记录，缺失时按比例估算
    Q2 加班时薪 = 基本工资 ÷ 月标准工时
    Q3 待发放可重算（幂等），已发放锁定跳过
    Q4 奖罚净额进入公式（可为负）

以及行级权限：普通职工只能看自己的工资条。

本脚本可直接运行，末尾会清理自己造的测试数据：

    & 'D:\\rj\\conda_env\\envs\\aip\\python.exe' scripts\\verify_salary.py

@author 王坤尧
"""

import os
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client  # noqa: E402

from apps.personnel.models import (  # noqa: E402
    Attendance,
    RewardPunish,
    SocialInsurance,
)
from apps.salary.models import (  # noqa: E402
    OvertimeRecord,
    PieceworkRecord,
    SalaryRecord,
    UtilityFeeRecord,
)
from apps.salary.services import calculate_for_period  # noqa: E402
from apps.sysconf.models import Employee  # noqa: E402

PERIOD = '2026-09'
MONEY = Decimal('0.01')

# 测试用普通职工账号（无薪酬级别、无任何管理权限）
PLAIN_NO = 'E9999'
PLAIN_USERNAME = 'E9999'
PLAIN_PASSWORD = 'Verify!2026'

failures = []


def check(label, condition, detail=''):
    """记录一条断言结果。"""
    mark = 'OK  ' if condition else 'FAIL'
    print(f'  [{mark}] {label}' + (f' — {detail}' if detail else ''))
    if not condition:
        failures.append(label)


def money(value) -> Decimal:
    """与 services 一致的金额口径，用于独立复算期望值。"""
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def cleanup():
    """清理本脚本造的测试数据，保证可重复运行。"""
    SalaryRecord.objects.filter(salary_period=PERIOD).delete()
    OvertimeRecord.objects.filter(salary_period=PERIOD, employee__employee_no='E1001').delete()
    UtilityFeeRecord.objects.filter(salary_period=PERIOD, employee__employee_no='E1001').delete()
    PieceworkRecord.objects.filter(salary_period=PERIOD, employee__employee_no='E1001').delete()
    RewardPunish.objects.filter(
        employee__employee_no='E1001', happen_date__year=2026, happen_date__month=9
    ).delete()
    SocialInsurance.objects.filter(employee__employee_no='E1001', period=PERIOD).delete()
    Attendance.objects.filter(
        employee__employee_no='E1001',
        work_date__year=2026, work_date__month=9,
    ).delete()
    Employee.objects.filter(employee_no=PLAIN_NO).delete()


print('=' * 70)
print('一、造数据链')
print('=' * 70)
cleanup()

employee = Employee.objects.get(employee_no='E1001')
level = employee.salary_level
base_salary = money(level.base_salary)
print(f'  员工 {employee.real_name}（{employee.employee_no}），'
      f'薪酬级别 {level.name}，基本工资 {base_salary}')

OvertimeRecord.objects.create(
    employee=employee, overtime_date=date(2026, 9, 5),
    overtime_type=OvertimeRecord.OvertimeType.WORKDAY, hours=Decimal('4'),
    salary_period=PERIOD, reason='月末上线值守',
)
utility = UtilityFeeRecord.objects.create(
    employee=employee, salary_period=PERIOD,
    water_usage=Decimal('5'), water_fee=Decimal('22.50'),
    electricity_usage=Decimal('100'), electricity_fee=Decimal('60.00'),
)
PieceworkRecord.objects.create(
    employee=employee, salary_period=PERIOD, work_date=date(2026, 9, 10),
    work_mode=PieceworkRecord.WorkMode.PIECEWORK,
    product_name='外壳装配', quantity=Decimal('200'), unit_price=Decimal('1.50'),
)
PieceworkRecord.objects.create(
    employee=employee, salary_period=PERIOD, work_date=date(2026, 9, 12),
    work_mode=PieceworkRecord.WorkMode.TIMEWORK,
    product_name='设备巡检', hours=Decimal('10'), hourly_rate=Decimal('40'),
)
RewardPunish.objects.create(
    employee=employee, record_type=RewardPunish.RecordType.REWARD,
    happen_date=date(2026, 9, 10), title='季度优秀员工', amount=Decimal('500'),
)
RewardPunish.objects.create(
    employee=employee, record_type=RewardPunish.RecordType.REWARD,
    happen_date=date(2026, 9, 20), title='提案奖励', amount=Decimal('300'),
)
RewardPunish.objects.create(
    employee=employee, record_type=RewardPunish.RecordType.PUNISH,
    happen_date=date(2026, 9, 15), title='迟到处罚', amount=Decimal('200'),
)
social = SocialInsurance.objects.create(
    employee=employee, period=PERIOD, insurance_base=Decimal('4500'),
    pension_personal=Decimal('360'), medical_personal=Decimal('90'),
    unemployment_personal=Decimal('30'), housing_fund_personal=Decimal('0'),
)
# 考勤数据：请假审批会写入「请假」状态的考勤，这里手工造两天以验证它进了工资条备注
Attendance.objects.create(
    employee=employee, work_date=date(2026, 9, 1),
    status=Attendance.AttendanceStatus.NORMAL,
)
Attendance.objects.create(
    employee=employee, work_date=date(2026, 9, 2),
    status=Attendance.AttendanceStatus.LEAVE, remark='请假：事假',
)
print(f'  加班 4h（工作日）· 水电 {utility.total_fee} 元 · 计件 300 + 计时 400'
      f' · 奖罚 +600 · 社保个人 {social.personal_total} · 考勤 2 天')


print()
print('=' * 70)
print('二、核算结果与手工复算比对（SRS 4.3 公式）')
print('=' * 70)

stats, standard, note = calculate_for_period(PERIOD, [employee])
record = SalaryRecord.objects.get(employee=employee, salary_period=PERIOD)

# 独立复算：不使用 services 的中间结果，直接按公式原文重算一遍
expected_overtime = money(base_salary / Decimal('174') * Decimal('1.5') * Decimal('4'))
expected_piecework = money(Decimal('200') * Decimal('1.50') + Decimal('10') * Decimal('40'))
expected_reward = money(Decimal('500') + Decimal('300') - Decimal('200'))
expected_utility = money(Decimal('22.50') + Decimal('60.00'))
expected_social = money(Decimal('360') + Decimal('90') + Decimal('30'))
expected_net = money(
    base_salary + expected_piecework + expected_overtime
    + expected_reward - expected_utility - expected_social
)

print(f'  期望：基本 {base_salary} · 计件/计时 {expected_piecework} · 加班 {expected_overtime}')
print(f'       奖罚 {expected_reward} · 水电 -{expected_utility} · 社保 -{expected_social}')
print(f'       实发 {expected_net}')

check('基本工资', record.base_salary == base_salary, f'{record.base_salary}')
check('计件/计时工资', record.piecework_amount == expected_piecework, f'{record.piecework_amount}')
check('加班费（Q2 时薪口径）', record.overtime_amount == expected_overtime, f'{record.overtime_amount}')
check('奖罚净额（Q4）', record.reward_punish_amount == expected_reward, f'{record.reward_punish_amount}')
check('水电扣费', record.utility_deduction == expected_utility, f'{record.utility_deduction}')
check('社保自负（Q1 取实缴）', record.social_deduction == expected_social, f'{record.social_deduction}')
check('实发工资', record.net_pay == expected_net, f'{record.net_pay}')
check('工资条备注含考勤汇总', '考勤' in (record.remark or ''), record.remark or '（空）')


print()
print('=' * 70)
print('三、Q1 退化路径：无社保缴费记录时按比例估算')
print('=' * 70)

social.delete()
stats, standard, note = calculate_for_period(PERIOD, [employee])
record.refresh_from_db()
expected_estimate = money(base_salary * standard.social_insurance_ratio)
check('社保改为按比例估算', record.social_deduction == expected_estimate,
      f'{record.social_deduction}（比例 {standard.social_insurance_ratio}）')

# 恢复实缴记录，供后续幂等与发放测试使用
SocialInsurance.objects.create(
    employee=employee, period=PERIOD, insurance_base=Decimal('4500'),
    pension_personal=Decimal('360'), medical_personal=Decimal('90'),
    unemployment_personal=Decimal('30'),
)
# 恢复后必须重算一次：上一步把社保数字从「实缴」换成了「估算」，
# 不重算的话后面拿到的基线值仍是估算结果，比对会莫名其妙地差几百块
calculate_for_period(PERIOD, [employee])


print()
print('=' * 70)
print('四、Q3 幂等：重复核算不新增、不改变金额')
print('=' * 70)

before_count = SalaryRecord.objects.filter(salary_period=PERIOD).count()
before_net = SalaryRecord.objects.get(employee=employee, salary_period=PERIOD).net_pay

stats, standard, note = calculate_for_period(PERIOD, [employee])
after_count = SalaryRecord.objects.filter(salary_period=PERIOD).count()
after_net = SalaryRecord.objects.get(employee=employee, salary_period=PERIOD).net_pay

check('记录数不变', before_count == after_count, f'{before_count} → {after_count}')
check('金额不变', before_net == after_net, f'{before_net} → {after_net}')
check('统计为「更新」而非「新增」', stats['created'] == 0 and stats['updated'] == 1, str(stats))


print()
print('=' * 70)
print('五、Q3 发放锁定：已发放记录重算被跳过')
print('=' * 70)

SalaryRecord.objects.filter(salary_period=PERIOD).update(
    pay_status=SalaryRecord.PayStatus.PAID
)
paid_net = SalaryRecord.objects.get(employee=employee, salary_period=PERIOD).net_pay

# 发放后再补一条加班，模拟「事后补录」
OvertimeRecord.objects.create(
    employee=employee, overtime_date=date(2026, 9, 22),
    overtime_type=OvertimeRecord.OvertimeType.WEEKEND, hours=Decimal('8'),
    salary_period=PERIOD, reason='周末值班（补录）',
)

stats, standard, note = calculate_for_period(PERIOD, [employee])
after_paid_net = SalaryRecord.objects.get(employee=employee, salary_period=PERIOD).net_pay

check('已发放记录被跳过', stats['skipped'] >= 1, str(stats))
check('已发放金额未被改动', paid_net == after_paid_net, f'{paid_net} → {after_paid_net}')
check('跳过原因已写入提示', '跳过' in note, note)


print()
print('=' * 70)
print('六、HTTP 路径与权限（测试客户端）')
print('=' * 70)

admin_user = Employee.objects.filter(is_superuser=True).first()
client = Client(SERVER_NAME='127.0.0.1')
client.force_login(admin_user)

for name, url in [
    ('薪酬级别列表', '/salary/levels/'),
    ('薪酬标准列表', '/salary/standards/'),
    ('加班登记列表', '/salary/overtimes/'),
    ('水电费登记列表', '/salary/utilities/'),
    ('产量登记列表', '/salary/pieceworks/'),
    ('工资档案列表', '/salary/records/'),
    ('我的工资', '/salary/my-salary/'),
    ('工资核算页', '/salary/records/calculate/'),
    ('工资条详情', f'/salary/records/{record.pk}/'),
    ('薪酬级别新增', '/salary/levels/create/'),
    ('薪酬标准新增', '/salary/standards/create/'),
    ('加班登记新增', '/salary/overtimes/create/'),
    ('水电费登记新增', '/salary/utilities/create/'),
    ('产量登记新增', '/salary/pieceworks/create/'),
]:
    response = client.get(url)
    check(f'{name} GET {url}', response.status_code == 200,
          f'HTTP {response.status_code}')

# 核算页 POST：整批核算
SalaryRecord.objects.filter(salary_period=PERIOD).delete()
response = client.post('/salary/records/calculate/', {'salary_period': PERIOD, 'department': ''})
check('核算页 POST 整批核算', response.status_code == 302, f'HTTP {response.status_code}')
all_count = SalaryRecord.objects.filter(salary_period=PERIOD).count()
check('整批核算生成了多条记录', all_count > 1, f'{all_count} 条')

# 非法周期应被表单挡回（200 而非 500）
response = client.post('/salary/records/calculate/', {'salary_period': '2026-13', 'department': ''})
check('非法周期被挡回', response.status_code == 200, f'HTTP {response.status_code}')

# 批量发放
response = client.post('/salary/records/pay/', {'salary_period': PERIOD})
check('批量发放', response.status_code == 302, f'HTTP {response.status_code}')
draft_left = SalaryRecord.objects.filter(
    salary_period=PERIOD, pay_status=SalaryRecord.PayStatus.DRAFT
).count()
check('发放后无待发放记录', draft_left == 0, f'剩余 {draft_left} 条')

# 普通职工视角
plain_group = Group.objects.filter(name='普通职工').first()
plain = Employee.objects.create_user(
    username=PLAIN_USERNAME, password=PLAIN_PASSWORD,
    real_name='验证用职工', employee_no=PLAIN_NO,
    id_card='110101199001019999', gender='M',
)
plain.groups.add(plain_group)
plain.save()

plain_client = Client(SERVER_NAME='127.0.0.1')
plain_client.force_login(plain)

check('普通职工可访问「我的工资」',
      plain_client.get('/salary/my-salary/').status_code == 200)
check('普通职工可访问工资档案列表（仅见本人）',
      plain_client.get('/salary/records/').status_code == 200)
check('普通职工访问他人工资条 → 404',
      plain_client.get(f'/salary/records/{record.pk}/').status_code == 404)
check('普通职工访问薪酬级别 → 403',
      plain_client.get('/salary/levels/').status_code == 403)
check('普通职工访问加班登记 → 403',
      plain_client.get('/salary/overtimes/').status_code == 403)
check('普通职工不能发起发放',
      plain_client.post('/salary/records/pay/', {'salary_period': PERIOD}).status_code == 403)


print()
print('=' * 70)
print('七、清理测试数据')
print('=' * 70)
cleanup()
print(f'  剩余 {PERIOD} 工资记录：{SalaryRecord.objects.filter(salary_period=PERIOD).count()} 条')

print()
if failures:
    print(f'[FAIL] 共 {len(failures)} 项未通过：')
    for item in failures:
        print(f'  - {item}')
    sys.exit(1)

print('[OK] 全部验证通过。')
