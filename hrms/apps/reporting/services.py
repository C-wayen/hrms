"""
报表统计聚合服务。

对应需求：FR-RPT-01 结构统计、FR-RPT-02 动态分析、FR-RPT-03 人员流动统计

为什么单独一层：报表最容易出错的地方不是 SQL，而是**口径**——
「谁算在职」「离职率的分母是什么」。这些口径必须同时体现在图表、
指标卡、数据接口和验证脚本四处；一旦散在视图里，迟早出现
「指标卡说在职 128 人、饼图加起来 131 人」这种自己跟自己对不上的局面。

================================================================================
统计口径（本模块的唯一真相）
================================================================================

【数据范围】一律只统计 is_deleted=False 的档案。
    软删除语义是「作废」，被作废的档案不应再出现在任何统计里。

【时点在职】以日期为准，而不是看 employ_status：
        入职日 ≤ 该日  且  （未离职 或 离职日 > 该日）
    为什么不看 employ_status：它是**当前值**，回头看历史时，
    一个月前的快照会被今天的状态改写，趋势线会整条跟着变。
    日期是已经发生的事实，不会变。

【新增】hire_date 落在统计期内。
【离职】resign_date 落在统计期内。
【离职率】当期离职人数 ÷ 期初在职人数。
    分母用期初而不是期末：期末人数已经被当期离职的人减掉了，
    拿它做分母会系统性高估离职率。

⚠️ 已知数据前提：Employee 的 employ_status 与 resign_date 是**两个独立字段**，
   当前「删除档案」只置 is_deleted，不会自动写 resign_date。
   因此要让离职趋势有意义，离职必须通过「办理离职」填写 resign_date 完成，
   而不是靠删除档案。本模块的口径以此为前提。

@author 王坤尧
"""

from datetime import date

from django.db.models import Count, Q
from django.db.models.functions import ExtractMonth

from apps.sysconf.models import Department, Employee
from apps.sysconf.scoping import department_and_children_ids
from apps.sysconf.utils import years_since

# =============================================================================
# 一、分桶规则
# =============================================================================

# 年龄段分桶：用 (下界, 上界, 标签) 三元组，左闭右闭。
# 不写成 '<25' 这样的字符串比较，是为了改边界时只改一处数字，
# 不会出现「标签改了、判断没改」的错位。
AGE_BUCKETS = (
    (0, 24, '25 岁以下'),
    (25, 34, '25-34 岁'),
    (35, 44, '35-44 岁'),
    (45, 54, '45-54 岁'),
    (55, 200, '55 岁及以上'),
)

# 工龄分桶同理；上界取 200 是为了兜住异常数据（如入职日期误填成 1900 年），
# 否则这类记录会静默地谁都不归属，图表总数对不上。
TENURE_BUCKETS = (
    (0, 0, '不满 1 年'),
    (1, 2, '1-2 年'),
    (3, 4, '3-4 年'),
    (5, 9, '5-9 年'),
    (10, 200, '10 年及以上'),
)


# =============================================================================
# 二、通用工具
# =============================================================================


def _bucketize(values, buckets):
    """把一串整数按分桶规则计数，输出 ECharts 需要的 [{name, value}] 结构。"""
    counts = {label: 0 for _, _, label in buckets}
    for value in values:
        if value is None:
            continue
        for low, high, label in buckets:
            if low <= value <= high:
                counts[label] += 1
                break
    return [{'name': label, 'value': counts[label]} for _, _, label in buckets]


def _scoped_employees(department=None):
    """统计范围内的档案（只排除已作废的），不带时点条件。"""
    queryset = Employee.objects.filter(is_deleted=False)
    if department is not None:
        # 取部门及其下级：只看单个部门会漏掉基层，而基层恰恰是人最多的
        queryset = queryset.filter(
            department_id__in=department_and_children_ids(department)
        )
    return queryset


def active_on(day, department=None):
    """某一天的在职员工查询集（时点快照口径）。

    做成查询集而不是只返回人数，是因为结构统计（FR-RPT-01）也要按
    「在职」来筛：离职员工的历史档案不应出现在性别比例、学历构成里。

    入职日为空的历史档案计入在内——不补日期是数据缺失，
    若把它们排除，在职人数会凭空少一截，比多算更难被发现。
    """
    return (
        _scoped_employees(department)
        .filter(Q(hire_date__lte=day) | Q(hire_date__isnull=True))
        .filter(Q(resign_date__isnull=True) | Q(resign_date__gt=day))
    )


def _active_employees(department=None):
    """当前在职员工（结构统计的默认口径）。"""
    return active_on(date.today(), department)


def _month_series(rows):
    """把 [{month: 1, count: 3}, ...] 补零成 12 个月的数组。

    必须补零：ECharts 折线图遇到缺失的月份，会把前后两点直接连起来，
    看上去像「这两三个月完全没有流动」，而真相是「这两个月没有数据」。
    """
    found = {row['month']: row['count'] for row in rows}
    return [found.get(month, 0) for month in range(1, 13)]


def _rate(numerator, denominator):
    """算百分比，保留 1 位小数。分母为 0 时返回 0 而不是抛异常。"""
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, 1)


# =============================================================================
# 三、FR-RPT-01 结构统计
# =============================================================================


def gender_distribution(department=None):
    """性别比例（饼图数据）。"""
    rows = (
        _active_employees(department)
        .values('gender')
        .annotate(count=Count('id'))
    )
    found = {row['gender']: row['count'] for row in rows}
    labels = dict(Employee.Gender.choices)

    # 按枚举顺序输出，而不是跟随数据库返回顺序：
    # 否则同一份数据刷新两次，饼图的颜色可能对调，看的人会以为数据变了
    series = [
        {'name': labels[value], 'value': found.get(value, 0)}
        for value, _ in Employee.Gender.choices
    ]

    # 历史上可能存在的空值或未知取值单独列一项，不藏起来
    known = {value for value, _ in Employee.Gender.choices}
    for gender, count in found.items():
        if gender not in known:
            series.append({'name': gender or '未填写', 'value': count})
    return series


def education_distribution(department=None):
    """学历构成（饼图数据）。"""
    rows = _active_employees(department).values('education').annotate(count=Count('id'))
    found = {row['education']: row['count'] for row in rows}
    labels = dict(Employee.Education.choices)

    series = [
        {'name': labels[value], 'value': found.get(value, 0)}
        for value, _ in Employee.Education.choices
    ]

    # 学历为空的记录单列：它反映的是档案完整度问题，
    # 如果不显示，各分片之和会小于在职总人数，看图的人会怀疑统计出错
    if found.get(''):
        series.append({'name': '未填写', 'value': found['']})
    return series


def age_distribution(department=None):
    """年龄段分布（柱状图数据）。"""
    today = date.today()
    births = (
        _active_employees(department)
        .filter(birth_date__isnull=False)
        .values_list('birth_date', flat=True)
    )
    return _bucketize((years_since(item, today) for item in births), AGE_BUCKETS)


def tenure_distribution(department=None):
    """工龄分布（柱状图数据）。"""
    today = date.today()
    hires = (
        _active_employees(department)
        .filter(hire_date__isnull=False)
        .values_list('hire_date', flat=True)
    )
    return _bucketize((years_since(item, today) for item in hires), TENURE_BUCKETS)


def _average(dates):
    """把一串日期换算成平均年数，保留 1 位小数。无数据时返回 0。"""
    values = [v for v in (years_since(item) for item in dates) if v is not None]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


def structure_overview(department=None):
    """结构统计页的头部指标（均按在职口径）。"""
    employees = _active_employees(department)
    return {
        'total': employees.count(),
        'avg_age': _average(
            employees.filter(birth_date__isnull=False).values_list('birth_date', flat=True)
        ),
        'avg_tenure': _average(
            employees.filter(hire_date__isnull=False).values_list('hire_date', flat=True)
        ),
        'male': employees.filter(gender=Employee.Gender.MALE).count(),
        'female': employees.filter(gender=Employee.Gender.FEMALE).count(),
    }


# =============================================================================
# 四、FR-RPT-02 动态分析
# =============================================================================


def headcount_at(day, department=None):
    """某一天的在职人数（时点快照）。口径说明见 active_on()。"""
    return active_on(day, department).count()


def flow_series(year, granularity='month'):
    """人员流动与离职率序列（FR-RPT-02、FR-RPT-03 的数据源）。

    granularity='month' 返回 12 个点，'quarter' 返回 4 个点。

    为什么流动与离职率放在一个函数里：两者的分子都是「当期离职人数」，
    拆成两个函数就是同一份数据查两遍，而且季度折算逻辑要写两次，必然走样。

    用数据库端 ExtractMonth 聚合，而不是把记录取回 Python 里分桶——
    1 万条档案下前者是一次查询，后者要传 1 万个日期对象过来。

    本函数**不支持部门筛选**：档案上只有当前部门，
    用它回溯历史会出现「这个月新增的 3 个人，下个月被算到别的部门」，
    趋势线会随人事调动凭空抖动。要看部门对比请用 department_flow()。
    """
    hire_rows = (
        Employee.objects
        .filter(is_deleted=False, hire_date__year=year)
        .annotate(month=ExtractMonth('hire_date'))
        .values('month').annotate(count=Count('id'))
    )
    resign_rows = (
        Employee.objects
        .filter(is_deleted=False, resign_date__year=year)
        .annotate(month=ExtractMonth('resign_date'))
        .values('month').annotate(count=Count('id'))
    )

    hires = _month_series(hire_rows)
    resignations = _month_series(resign_rows)
    # 期初人数取每月 1 日：折线图要的是「这个月开始了多少人」，
    # 用月末快照会把当月离职的人从当月抹掉，趋势看起来会比实际好看
    openings = [headcount_at(date(year, month, 1)) for month in range(1, 13)]

    if granularity == 'quarter':
        labels = [f'{year} Q{index}' for index in range(1, 5)]
        hires = _sum_by_quarter(hires)
        resignations = _sum_by_quarter(resignations)
        # 季度分母取该季度首月的期初人数，与月度口径的「期初」含义保持一致
        openings = [openings[index * 3] for index in range(4)]
    else:
        labels = [f'{month} 月' for month in range(1, 13)]

    # 【关键】比率不可加：季度离职率是「季度离职总数 ÷ 季度期初人数」，
    # 而不是把三个月的比率相加——2% + 3% + 4% 不等于 9%。
    # 这种错误在图上看不出异常，只有数字对不上时才会暴露。
    rates = [
        _rate(resignation, opening)
        for resignation, opening in zip(resignations, openings)
    ]

    return {
        'labels': labels,
        'hires': hires,
        'resignations': resignations,
        'net': [hire - resignation for hire, resignation in zip(hires, resignations)],
        'openings': openings,
        'rates': rates,
    }


def _sum_by_quarter(monthly):
    """把 12 个月的序列折成 4 个季度（求和）。"""
    return [sum(monthly[index * 3:(index + 1) * 3]) for index in range(4)]


def available_years():
    """报表可选的年份列表。

    取入职与离职日期的年份并集，再加上今年——
    有数据才有得选，一律从 2000 年开始列会让人挑花眼。
    """
    hire_years = (
        Employee.objects.filter(hire_date__isnull=False)
        .dates('hire_date', 'year')
    )
    resign_years = (
        Employee.objects.filter(resign_date__isnull=False)
        .dates('resign_date', 'year')
    )
    years = {item.year for item in hire_years} | {item.year for item in resign_years}
    years.add(date.today().year)
    return sorted(years, reverse=True)


# =============================================================================
# 五、FR-RPT-03 人员流动统计
# =============================================================================


def flow_summary(year, department=None):
    """人员流动总览：# 在职人员总数统计、新增人员统计、辞职人员统计。"""
    today = date.today()
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)

    employees = _scoped_employees(department)
    hires = employees.filter(hire_date__year=year).count()
    resignations = employees.filter(resign_date__year=year).count()

    # 期初 / 期末都用「年初 / 年末」的快照，跨年查询时也能对齐
    opening = headcount_at(year_start, department)
    closing = headcount_at(min(year_end, today), department)

    return {
        'year': year,
        'current_headcount': headcount_at(today, department),
        'opening_headcount': opening,
        'closing_headcount': closing,
        'hires': hires,
        'resignations': resignations,
        'net_growth': hires - resignations,
        'turnover_rate': _rate(resignations, opening),
    }


def department_flow(year):
    """各部门的人员流动对比（柱状图数据）。

    遍历部门逐个统计，而不是用 values('department').annotate() 分组：
    分组只能得到「有流动记录的那些部门」，而逐个遍历还能顺带把
    「一个新人都没招到」的部门也照顾到（它们只是不进图，见下）。

    按员工**当前**部门归属统计，与 monthly_flow 的口径说明一致：
    历史部门需要在调动记录里回溯，超出本报表的数据来源范围。
    """
    labels, hires, resignations = [], [], []
    for department in Department.objects.order_by('name'):
        scope = Employee.objects.filter(is_deleted=False, department=department)
        count_hires = scope.filter(hire_date__year=year).count()
        count_resign = scope.filter(resign_date__year=year).count()
        # 全年零流动的部门不进图：一排 0 会把有数据的柱子压扁，看不出差异
        if not count_hires and not count_resign:
            continue
        labels.append(department.name)
        hires.append(count_hires)
        resignations.append(count_resign)

    return {'labels': labels, 'hires': hires, 'resignations': resignations}


def recent_resignations(year, limit=20):
    """当年离职人员明细（表格数据）。

    顺带算出「在职时长」：入职到离职的整年数。
    这个数字比单纯的入职日期有用——它能一眼看出是不是短期离职，
    而短期离职往往意味着招聘或岗位匹配出了问题。
    """
    rows = []
    for employee in (
        Employee.objects
        .filter(is_deleted=False, resign_date__year=year)
        .select_related('department', 'position')
        .order_by('-resign_date')[:limit]
    ):
        rows.append({
            'employee': employee,
            # 截止日取离职当天，算出来的才是在职时长而非「距今多少年」
            'tenure': years_since(employee.hire_date, employee.resign_date),
        })
    return rows


def data_quality_notes(year):
    """口径一致性自检，返回待提醒的问题列表。

    为什么要把「数据问题」显示给用户：
    报表的口径以日期为准，若有人把 employ_status 改成「离职」却没填离职日期，
    这个人在趋势里仍被算作在职，报表和档案页就会各说各话。
    与其让人怀疑报表算错，不如直接把这类记录列出来。
    """
    notes = []

    resigned_without_date = Employee.objects.filter(
        is_deleted=False, employ_status=Employee.EmployStatus.RESIGNED,
        resign_date__isnull=True,
    ).count()
    if resigned_without_date:
        notes.append(
            f'{resigned_without_date} 名员工状态为「离职」但未填离职日期，'
            f'不会被计入离职趋势'
        )

    date_without_status = Employee.objects.filter(
        is_deleted=False, resign_date__isnull=False,
    ).exclude(employ_status=Employee.EmployStatus.RESIGNED).count()
    if date_without_status:
        notes.append(
            f'{date_without_status} 名员工已填离职日期但状态不是「离职」，'
            f'建议同步档案状态'
        )

    no_hire_date = Employee.objects.filter(
        is_deleted=False, hire_date__isnull=True
    ).count()
    if no_hire_date:
        notes.append(f'{no_hire_date} 名员工缺少入职日期，未纳入工龄与新增统计')

    return notes
