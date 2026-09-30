"""报表统计模块端到端验证脚本。

用途：把 FR-RPT-01 ~ FR-RPT-03 的 **8 类统计图表逐项验证**一遍
（对应测试预案中「报表统计 ≥ 8 条用例、8 类统计图表逐项验证」的要求）。

验证方法：不用 services 的聚合函数去"自己验自己"，而是
    **把全部员工取回内存，用与 SQL 完全不同的方式遍历判定**，
再与接口输出比对。两者若一致，说明聚合链路（SQL → JSON → 结构）是对的。

本脚本可重复运行，末尾会清理自己造的测试数据：

    & 'D:\\rj\\conda_env\\envs\\aip\\python.exe' scripts\\verify_reporting.py

@author 王坤尧
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Windows 控制台默认按 GBK 编码，遇到「−」「≥」「≠」这类符号会直接抛
# UnicodeEncodeError，把验证脚本打断在半途——结论没出来，很难判断是代码错还是控制台错。
# 降级为替换字符，保证脚本能跑完并报出真实结论。
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client  # noqa: E402

from apps.reporting import services  # noqa: E402
from apps.sysconf.models import Department, Employee  # noqa: E402

# 测试账号工号前缀，便于精确清理
TEST_PREFIX = 'V9'
YEAR = 2026
failures = []


def check(label, actual, expected, strict=True):
    """比对一项结果。expected 可以是精确值，也可以是 (判定函数, 说明)。"""
    if callable(expected):
        passed = expected(actual)
        detail = f'实际 {actual}'
    else:
        passed = actual == expected
        detail = f'实际 {actual}，期望 {expected}'
    mark = 'OK  ' if passed else 'FAIL'
    print(f'  [{mark}] {label} — {detail}')
    if strict and not passed:
        failures.append(label)
    return passed


# =============================================================================
# 独立的"人肉"口径实现（刻意与 services.py 用不同写法）
# =============================================================================


def load_all():
    """把全部员工取回内存，后续所有统计都在 Python 里做。"""
    return list(
        Employee.objects
        .select_related('department')
        .all()
    )


def is_active_on(employee, day):
    """某一天是否在职——按日期判定，与 services.active_on 的 SQL 版本互为对照。"""
    if employee.is_deleted:
        return False
    if employee.hire_date and employee.hire_date > day:
        return False
    if employee.resign_date and employee.resign_date <= day:
        return False
    return True


def whole_years(start, end):
    """整年数（年龄 / 工龄），用另一套写法实现。"""
    if not start:
        return None
    return end.year - start.year - ((end.month, end.day) < (start.month, start.day))


def manual_bucket(employees, attr, buckets, end):
    """按分桶规则统计人数，返回 {标签: 人数}。"""
    counts = {label: 0 for _, _, label in buckets}
    for employee in employees:
        start = getattr(employee, attr)
        if not start:
            continue
        years = whole_years(start, end)
        for low, high, label in buckets:
            if low <= years <= high:
                counts[label] += 1
                break
    return counts


def manual_month_count(employees, attr, year):
    """按日期字段归属到 12 个月（越界或空值不计）。"""
    months = [0] * 12
    for employee in employees:
        value = getattr(employee, attr)
        if value and value.year == year:
            months[value.month - 1] += 1
    return months


def by_name(series):
    """把 [{name, value}] 转成 {name: value}，便于比对。"""
    return {item['name']: item['value'] for item in series}


# =============================================================================
# 准备与清理
# =============================================================================


def cleanup():
    """删掉本脚本造的测试员工（工号以 V9 开头）。"""
    Employee.objects.filter(employee_no__startswith=TEST_PREFIX).delete()


def seed():
    """补造离职与新增数据，让流动类图表有内容可验。

    数据刻意造成「同一季度内两个月都有离职，且期间有人入职」：
    这样该季度的期初人数会逐月变化，正确的季度离职率（分子分母各自求和再相除）
    与错误做法（把三个月的比率相加）才会算出**不同的结果**。
    若季度内只有一个月有人离职，两者数值恰好相等，
    那条断言就失去了区分力——等于没测。
    """
    departments = list(Department.objects.order_by('pk')[:2])
    rows = [
        # (工号, 姓名, 性别, 出生日期, 学历, 入职日期, 离职日期, 部门序号)
        ('V9001', '验证离职甲', 'M', date(1992, 5, 20), 'bachelor',
         date(2024, 3, 1), date(2026, 2, 10), 0),
        ('V9002', '验证离职乙', 'F', date(1996, 11, 8), 'master',
         date(2025, 6, 1), date(2026, 3, 20), 0),
        ('V9003', '验证新增丙', 'M', date(1999, 2, 14), 'college',
         date(2026, 2, 1), None, 1),
        ('V9004', '验证新增丁', 'F', date(2000, 9, 30), 'bachelor',
         date(2026, 2, 15), None, 1),
    ]
    for no, name, gender, birth, education, hire, resign, dept_index in rows:
        Employee.objects.create_user(
            username=no, password='Verify!2026',
            real_name=name, employee_no=no,
            id_card=f'11010119900101{no[-4:]}', gender=gender,
            birth_date=birth, education=education,
            hire_date=hire, resign_date=resign,
            employ_status=(
                Employee.EmployStatus.RESIGNED if resign
                else Employee.EmployStatus.REGULAR
            ),
            department=departments[dept_index % len(departments)],
        )


print('=' * 74)
print('准备：清理旧数据并补造测试员工')
print('=' * 74)
cleanup()
seed()

TODAY = date.today()
ALL = load_all()
ACTIVE = [item for item in ALL if is_active_on(item, TODAY)]
print(f'  员工总数 {len(ALL)}，其中当前在职 {len(ACTIVE)}（今天 {TODAY}）')

if len(ALL) < 5:
    print('[WARN] 员工数据过少，验证结果参考价值有限，建议先运行 init_data.py')


# =============================================================================
# FR-RPT-01 结构统计（4 类图表）
# =============================================================================
print()
print('=' * 74)
print('FR-RPT-01 结构统计：4 类图表逐项核对')
print('=' * 74)

# --- 图 1：性别比例 ---
actual_gender = by_name(services.gender_distribution())
expected_gender = {
    '男': len([e for e in ACTIVE if e.gender == 'M']),
    '女': len([e for e in ACTIVE if e.gender == 'F']),
}
# 性别为空的历史数据会以「未填写」单列，比对时也要算进来
blank_gender = len([e for e in ACTIVE if e.gender not in ('M', 'F')])
if blank_gender:
    expected_gender['未填写'] = blank_gender
check('图1 性别比例', actual_gender, expected_gender)
check('  性别合计 = 在职人数', sum(actual_gender.values()), len(ACTIVE))

# --- 图 2：年龄段分布 ---
actual_age = by_name(services.age_distribution())
expected_age = manual_bucket(ACTIVE, 'birth_date', services.AGE_BUCKETS, TODAY)
check('图2 年龄段分布', actual_age, expected_age)
missing_birth = len([e for e in ACTIVE if not e.birth_date])
print(f'         （{missing_birth} 人无出生日期，未纳入分桶，属预期行为）')

# --- 图 3：学历构成 ---
actual_education = by_name(services.education_distribution())
# 期望里要保留 0 值项：服务端刻意输出全部学历选项（含 0），
# 这样图表分类轴不会因为「这个月没人读博」而少一格
labels = dict(Employee.Education.choices)
expected_education = {}
for value, label in Employee.Education.choices:
    expected_education[label] = len([e for e in ACTIVE if e.education == value])
blank_education = len([e for e in ACTIVE if not e.education])
if blank_education:
    expected_education['未填写'] = blank_education
check('图3 学历构成', actual_education, expected_education)

# --- 图 4：工龄分布 ---
actual_tenure = by_name(services.tenure_distribution())
expected_tenure = manual_bucket(ACTIVE, 'hire_date', services.TENURE_BUCKETS, TODAY)
check('图4 工龄分布', actual_tenure, expected_tenure)


# =============================================================================
# FR-RPT-02 动态分析（折线图）
# =============================================================================
print()
print('=' * 74)
print(f'FR-RPT-02 动态分析：{YEAR} 年流动趋势与离职率')
print('=' * 74)

series = services.flow_series(YEAR, 'month')
expected_hires = manual_month_count(ALL, 'hire_date', YEAR)
expected_resign = manual_month_count(ALL, 'resign_date', YEAR)

check('图5 新增逐月（折线）', series['hires'], expected_hires)
check('图5 离职逐月（折线）', series['resignations'], expected_resign)
check('图5 净增逐月 = 新增 - 离职', series['net'],
      [h - r for h, r in zip(expected_hires, expected_resign)])
check('图5 月份轴 12 个点', len(series['labels']), 12)

# --- 图 6：离职率 ---
expected_openings = []
for month in range(1, 13):
    first_day = date(YEAR, month, 1)
    expected_openings.append(len([e for e in ALL if is_active_on(e, first_day)]))
check('图7 期初在职人数逐月', series['openings'], expected_openings)

expected_rates = [
    round(resign / opening * 100, 1) if opening else 0.0
    for resign, opening in zip(expected_resign, expected_openings)
]
check('图6 离职率逐月（折线）', series['rates'], expected_rates)

# --- 季度口径：比率不可加 ---
quarter_series = services.flow_series(YEAR, 'quarter')
expected_quarter_resign = [
    sum(expected_resign[index * 3:(index + 1) * 3]) for index in range(4)
]
check('季度离职人数 = 三个月求和', quarter_series['resignations'], expected_quarter_resign)
check('季度轴 4 个点', len(quarter_series['labels']), 4)

quarter_rates = quarter_series['rates']

# 正确的季度离职率：分子分母各自求和后再相除
expected_quarter_rates = [
    round(sum(expected_resign[index * 3:(index + 1) * 3])
          / expected_openings[index * 3] * 100, 1)
    if expected_openings[index * 3] else 0.0
    for index in range(4)
]
check('季度离职率 = 季度离职 ÷ 季度期初', quarter_rates, expected_quarter_rates)

# 并确认它确实不同于「把三个月的比率直接相加」：
# 比率不可加，2% + 3% + 4% 不等于 9%。
# 只有确认两种算法结果不同，上面那条口径说明才有意义。
sum_of_month_rates = [
    round(sum(expected_rates[index * 3:(index + 1) * 3]), 1) for index in range(4)
]
print(f'         （季度 {quarter_rates} ／ 三个月相加 {sum_of_month_rates}）')
check('季度离职率与「三个月比率相加」结果不同',
      quarter_rates != sum_of_month_rates, True)


# =============================================================================
# FR-RPT-03 人员流动统计
# =============================================================================
print()
print('=' * 74)
print('FR-RPT-03 人员流动统计：在职总数 / 新增 / 辞职 / 部门对比')
print('=' * 74)

summary = services.flow_summary(YEAR)
check('在职人员总数', summary['current_headcount'], len(ACTIVE))
check('年度新增人员', summary['hires'], sum(expected_hires))
check('年度辞职人员', summary['resignations'], sum(expected_resign))
check('净增 = 新增 - 辞职',
      summary['net_growth'], sum(expected_hires) - sum(expected_resign))

year_openings = len([e for e in ALL if is_active_on(e, date(YEAR, 1, 1))])
check('年初在职人数', summary['opening_headcount'], year_openings)
check('年度离职率分母为年初在职',
      summary['turnover_rate'],
      round(sum(expected_resign) / year_openings * 100, 1) if year_openings else 0.0)

# --- 图 8：各部门新增与辞职对比 ---
department_data = services.department_flow(YEAR)
check('图8 部门数 = 各部门标题数',
      len(department_data['labels']), len(department_data['hires']))

# 只应列出当年确实有进出的部门（零流动的部门刻意不进图，避免柱子被压扁）
flow_departments = {
    employee.department.name
    for employee in ALL
    if employee.department and (
        (employee.hire_date and employee.hire_date.year == YEAR)
        or (employee.resign_date and employee.resign_date.year == YEAR)
    )
}
check('图8 只列出当年有进出的部门',
      sorted(department_data['labels']), sorted(flow_departments))
check('图8 新增合计 = 全公司新增（含无部门者差异）',
      sum(department_data['hires']),
      len([e for e in ALL if e.hire_date and e.hire_date.year == YEAR and e.department_id]))
check('图8 辞职合计 = 全公司辞职（含无部门者差异）',
      sum(department_data['resignations']),
      len([e for e in ALL if e.resign_date and e.resign_date.year == YEAR and e.department_id]))

resignations = services.recent_resignations(YEAR)
check('离职明细条数 = 年度辞职人数', len(resignations), sum(expected_resign))
if resignations:
    first = resignations[0]
    manual = whole_years(first['employee'].hire_date, first['employee'].resign_date)
    check('离职明细含在职时长', first['tenure'], manual)

# --- 口径一致性自检 ---
print()
print('  口径一致性自检（data_quality_notes）：')
notes = services.data_quality_notes(YEAR)
print(f'    {notes if notes else "无异常"}')
check('正常数据下不产生离职口径告警',
      not [n for n in notes if '未填离职日期' in n or '状态不是' in n], True)


# =============================================================================
# HTTP 路径与权限
# =============================================================================
print()
print('=' * 74)
print('HTTP 路径与权限（测试客户端）')
print('=' * 74)

# 未登录时应被引导去登录页，而不是直接收到 403——
# 访客看到 403 只会以为站点坏了，看到登录页才知道该干什么
anonymous = Client(SERVER_NAME='127.0.0.1')
check('未登录访问结构统计 → 重定向登录页',
      anonymous.get('/report/structure/').status_code, 302)
check('未登录访问数据接口 → 重定向登录页',
      anonymous.get('/report/structure/data/').status_code, 302)

admin_user = Employee.objects.filter(is_superuser=True).first()
client = Client(SERVER_NAME='127.0.0.1')
client.force_login(admin_user)

for name, url in [
    ('结构统计页', '/report/structure/'),
    ('结构统计数据', '/report/structure/data/'),
    ('动态分析页', '/report/trend/'),
    ('动态分析数据', f'/report/trend/data/?year={YEAR}&granularity=month'),
    ('动态分析数据(季度)', f'/report/trend/data/?year={YEAR}&granularity=quarter'),
    ('动态分析数据(非法粒度)', '/report/trend/data/?year=abc&granularity=weekly'),
    ('人员流动统计页', '/report/turnover/'),
    ('人员流动统计数据', f'/report/turnover/data/?year={YEAR}'),
    ('结构统计(带部门筛选)', '/report/structure/?department=1'),
    ('人员流动统计(非法部门)', '/report/turnover/?department=99999'),
]:
    response = client.get(url)
    check(f'{name} GET', response.status_code, 200)

# 数据接口的 JSON 结构
payload = json.loads(client.get('/report/structure/data/').content)
check('结构统计接口含 4 组图表数据',
      sorted(key for key in payload if key != 'overview'),
      ['age', 'education', 'gender', 'tenure'])

trend_payload = json.loads(
    client.get(f'/report/trend/data/?year={YEAR}&granularity=month').content
)
check('动态分析接口含 6 个字段',
      sorted(trend_payload.keys()),
      ['hires', 'labels', 'net', 'openings', 'rates', 'resignations'])

# 普通职工应被挡在报表之外（403，而不是被重定向到登录页）
plain_group = Group.objects.filter(name='普通职工').first()
plain = Employee.objects.create_user(
    username='V9099', password='Verify!2026',
    real_name='验证普通职工', employee_no='V9099',
    id_card='110101199001019099', gender='F',
)
plain.groups.add(plain_group)
plain.save()

plain_client = Client(SERVER_NAME='127.0.0.1')
plain_client.force_login(plain)
check('普通职工访问结构统计 → 403',
      plain_client.get('/report/structure/').status_code, 403)
check('普通职工访问动态分析 → 403',
      plain_client.get('/report/trend/').status_code, 403)
check('普通职工访问流动统计 → 403',
      plain_client.get('/report/turnover/').status_code, 403)


# =============================================================================
# 清理
# =============================================================================
print()
print('=' * 74)
print('清理测试数据')
print('=' * 74)
cleanup()
plain.delete()
print(f'  剩余以 {TEST_PREFIX} 开头的员工：'
      f'{Employee.objects.filter(employee_no__startswith=TEST_PREFIX).count()} 人')

print()
if failures:
    print(f'[FAIL] 共 {len(failures)} 项未通过：')
    for item in failures:
        print(f'  - {item}')
    sys.exit(1)

print('[OK] 8 类统计图表与接口权限全部验证通过。')
