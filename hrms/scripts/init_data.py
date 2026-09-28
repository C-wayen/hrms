"""初始化 HRMS 基础数据。

幂等：可以重复运行，已存在的记录不会重复创建。

内容与对应需求：
    1. 三个角色（Django Group）及其权限树      FR-SYS-01 权限控制
    2. 部门组织树、岗位、数据字典              FR-SYS-02 基础数据
    3. 薪酬级别与薪酬标准                      FR-SAL-01 薪酬体系配置
    4. 导航菜单（按角色控制可见性）            FR-SYS-03 用户与菜单管理
    5. FAQ 知识库                              FR-AI-01 智能问答
    6. 演示用员工档案（不可登录，仅作数据）    FR-PER-01

用法：
    & 'D:\\rj\\conda_env\\envs\\aip\\python.exe' scripts\\init_data.py
"""

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import Group, Permission  # noqa: E402

from apps.assistant.models import FaqItem  # noqa: E402
from apps.salary.models import SalaryLevel, SalaryStandard  # noqa: E402
from apps.sysconf.models import DataDict, Department, Employee, Menu, Position  # noqa: E402


# =============================================================================
# 一、角色与权限（FR-SYS-01）
# =============================================================================

# 角色名 -> (可完全控制的 app, 只读的 app)
ROLE_SPEC = {
    '系统管理员': {
        'full': ['sysconf', 'personnel', 'salary', 'training', 'pubquery', 'assistant'],
        'readonly': [],
    },
    'HR 专员/经理': {
        'full': ['personnel', 'salary', 'training', 'pubquery', 'assistant'],
        # 组织架构、字典、菜单由系统管理员维护，HR 只读
        'readonly': ['sysconf'],
    },
    '普通职工': {
        # 普通职工不使用 admin 后台，权限用于前端视图的功能判定：
        # 提交请假、查看自己的档案/工资/考勤、使用智能问答
        'full': [],
        'readonly': [],
        'custom': [
            'add_leaverequest', 'view_leaverequest', 'change_leaverequest',
            'view_attendance', 'view_rewardpunish', 'view_salaryrecord',
            # 注意：不含 view_employee——档案列表会暴露全员信息，
            # 普通职工只能通过「我的档案」查看本人（由视图层按登录用户过滤）
            'view_faqitem', 'add_chatlog', 'view_chatlog',
        ],
    },
}


def _codenames(app_label: str, actions) -> list:
    """列出某 app 下所有模型的指定动作权限 codename。"""
    cts = Permission.objects.filter(content_type__app_label=app_label)
    return [f'{act}_{p.content_type.model}' for p in cts for act in actions]


def create_roles() -> dict:
    """建立三个角色并分配权限，返回角色名字典。"""
    roles = {}
    all_actions = ('add', 'change', 'delete', 'view')
    read_actions = ('view',)

    for role_name, spec in ROLE_SPEC.items():
        group, created = Group.objects.get_or_create(name=role_name)
        roles[role_name] = group

        codenames = set()
        for app_label in spec.get('full', []):
            codenames.update(_codenames(app_label, all_actions))
        for app_label in spec.get('readonly', []):
            codenames.update(_codenames(app_label, read_actions))
        codenames.update(spec.get('custom', []))

        perms = Permission.objects.filter(codename__in=codenames)
        group.permissions.set(perms)

        status = '新建' if created else '已存在'
        print(f'  [{status}] 角色「{role_name}」授权 {perms.count()} 项')

    return roles


# =============================================================================
# 二、部门 / 岗位 / 数据字典（FR-SYS-02）
# =============================================================================

DEPARTMENTS = [
    # (编码, 名称, 上级编码, 排序)
    ('HQ', '总公司', None, 1),
    ('TECH', '技术部', 'HQ', 1),
    ('TECH-BE', '后端组', 'TECH', 1),
    ('TECH-FE', '前端组', 'TECH', 2),
    ('HR', '人力资源部', 'HQ', 2),
    ('FIN', '财务部', 'HQ', 3),
    ('MKT', '市场部', 'HQ', 4),
    ('PROD', '生产部', 'HQ', 5),
    ('PROD-01', '装配车间', 'PROD', 1),
]

POSITIONS = [
    # (编码, 名称, 级别)
    ('GM', '总经理', 'M4'),
    ('TD', '技术总监', 'M2'),
    ('BE', '后端工程师', 'P3'),
    ('FE', '前端工程师', 'P3'),
    ('HRS', 'HR 专员', 'P2'),
    ('ACC', '会计', 'P2'),
    ('OP', '车间工人', 'P1'),
]

DICT_ITEMS = [
    ('政治面貌', '01', '中共党员'),
    ('政治面貌', '02', '共青团员'),
    ('政治面貌', '03', '民主党派'),
    ('政治面貌', '04', '群众'),
    ('民族', '01', '汉族'),
    ('民族', '02', '回族'),
    ('民族', '03', '满族'),
    ('婚姻状况', '01', '未婚'),
    ('婚姻状况', '02', '已婚'),
    ('婚姻状况', '03', '离异'),
    ('证书类别', '01', '职业资格'),
    ('证书类别', '02', '技能等级'),
    ('证书类别', '03', '专业技术职称'),
    ('证书类别', '04', '安全资质'),
    ('离职原因', '01', '个人原因'),
    ('离职原因', '02', '合同到期'),
    ('离职原因', '03', '公司裁员'),
]


def create_base_data() -> dict:
    """建立部门树、岗位与数据字典。"""
    dept_map = {}
    for code, name, parent_code, sort_order in DEPARTMENTS:
        dept, _ = Department.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'parent': dept_map.get(parent_code),
                'sort_order': sort_order,
            },
        )
        dept_map[code] = dept
    print(f'  [OK] 部门 {len(dept_map)} 个')

    pos_map = {}
    for code, name, level in POSITIONS:
        pos, _ = Position.objects.get_or_create(
            code=code, defaults={'name': name, 'level': level}
        )
        pos_map[code] = pos
    print(f'  [OK] 岗位 {len(pos_map)} 个')

    for dict_type, key, value in DICT_ITEMS:
        DataDict.objects.get_or_create(
            dict_type=dict_type,
            dict_key=key,
            defaults={'dict_value': value, 'sort_order': int(key)},
        )
    print(f'  [OK] 数据字典 {len(DICT_ITEMS)} 条')

    return {'departments': dept_map, 'positions': pos_map}


# =============================================================================
# 三、薪酬体系（FR-SAL-01）
# =============================================================================

SALARY_LEVELS = [
    ('P1', '初级', 4500, 300),
    ('P2', '中级', 6000, 500),
    ('P3', '高级', 9000, 800),
    ('P4', '资深', 13000, 1200),
    ('P5', '专家', 18000, 2000),
]


def create_salary_config() -> dict:
    """建立薪酬级别与全局薪酬标准。"""
    level_map = {}
    for code, name, base, allowance in SALARY_LEVELS:
        level, _ = SalaryLevel.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'base_salary': Decimal(base),
                'post_allowance': Decimal(allowance),
            },
        )
        level_map[code] = level
    print(f'  [OK] 薪酬级别 {len(level_map)} 个')

    SalaryStandard.objects.get_or_create(
        effective_date=date(2026, 1, 1),
        defaults={
            'overtime_workday_rate': Decimal('1.50'),
            'overtime_weekend_rate': Decimal('2.00'),
            'overtime_holiday_rate': Decimal('3.00'),
            'water_price': Decimal('4.50'),
            'electricity_price': Decimal('0.60'),
            'social_insurance_ratio': Decimal('0.1050'),
        },
    )
    print('  [OK] 薪酬标准 1 条')

    return level_map


# =============================================================================
# 四、导航菜单（FR-SYS-03）
# =============================================================================

# (菜单名, 路由名, 图标, 排序, 子菜单列表, 可见角色)
MENUS = [
    ('首页', 'home', 'bi-house', 1, [], ['系统管理员', 'HR 专员/经理', '普通职工']),

    ('人事管理', None, 'bi-people', 2, [
        ('职工档案', 'employee-list', '系统管理员', 'HR 专员/经理'),
        ('转正申请', 'regularization-list', '系统管理员', 'HR 专员/经理'),
        ('社保管理', 'socialinsurance-list', '系统管理员', 'HR 专员/经理'),
        ('考勤记录', 'attendance-list', '系统管理员', 'HR 专员/经理'),
        # 请假对普通职工也可见：他们进去只能看到自己的记录（视图层按数据范围过滤）
        ('请假申请', 'leave-list', '系统管理员', 'HR 专员/经理', '普通职工'),
        ('奖罚登记', 'rewardpunish-list', '系统管理员', 'HR 专员/经理'),
        ('员工关怀', 'birthday-list', '系统管理员', 'HR 专员/经理'),
    ], ['系统管理员', 'HR 专员/经理']),

    ('培训管理', None, 'bi-mortarboard', 3, [
        ('课程库', 'course-list', '系统管理员', 'HR 专员/经理'),
        ('培训计划', 'trainingplan-list', '系统管理员', 'HR 专员/经理'),
        ('培训记录与成绩', 'trainingrecord-list', '系统管理员', 'HR 专员/经理'),
    ], ['系统管理员', 'HR 专员/经理']),

    ('薪酬管理', None, 'bi-cash-stack', 4, [
        ('薪酬级别', 'salarylevel-list', '系统管理员', 'HR 专员/经理'),
        ('薪酬标准', 'salarystandard-list', '系统管理员', 'HR 专员/经理'),
        ('加班登记', 'overtime-list', '系统管理员', 'HR 专员/经理'),
        ('水电费登记', 'utilityfee-list', '系统管理员', 'HR 专员/经理'),
        ('产量登记', 'piecework-list', '系统管理员', 'HR 专员/经理'),
        ('工资核算与发放', 'salaryrecord-list', '系统管理员', 'HR 专员/经理'),
    ], ['系统管理员', 'HR 专员/经理']),

    ('公共查询', None, 'bi-search', 5, [
        ('多维检索', 'employee-search', '系统管理员', 'HR 专员/经理'),
        ('通知单打印', 'notification-list', '系统管理员', 'HR 专员/经理'),
    ], ['系统管理员', 'HR 专员/经理']),

    ('报表统计', None, 'bi-bar-chart', 6, [
        ('结构统计', 'report-structure', '系统管理员', 'HR 专员/经理'),
        ('动态分析', 'report-trend', '系统管理员', 'HR 专员/经理'),
    ], ['系统管理员', 'HR 专员/经理']),

    ('系统设置', None, 'bi-gear', 7, [
        ('组织机构', 'department-list', '系统管理员',),
        ('数据字典', 'datadict-list', '系统管理员',),
        ('用户与角色', 'employee-account', '系统管理员',),
        ('导航菜单', 'menu-list', '系统管理员',),
    ], ['系统管理员']),

    ('我的', None, 'bi-person', 8, [
        ('我的档案', 'my-profile', '系统管理员', 'HR 专员/经理', '普通职工'),
        ('我的工资', 'my-salary', '系统管理员', 'HR 专员/经理', '普通职工'),
        ('我的请假', 'my-leave', '系统管理员', 'HR 专员/经理', '普通职工'),
    ], ['系统管理员', 'HR 专员/经理', '普通职工']),

    ('智能助手', 'assistant-chat', 'bi-robot', 9, [], ['系统管理员', 'HR 专员/经理', '普通职工']),
]


def create_menus(roles: dict) -> None:
    """建立导航菜单并按角色分配可见性。

    幂等且会「收敛」：菜单属于配置而非业务数据，因此改了 MENUS 之后重新运行，
    必须把已经删掉的菜单项一并清理，并同步图标/排序/路由。
    否则改名后的旧菜单会一直挂在侧边栏上，而它的路由早已不存在，
    点进去只会得到「#」——很难判断是配置问题还是代码问题。
    """
    count = 0
    removed = 0

    def _roles(names):
        """把角色名映射为 Group 对象列表，跳过不存在的角色。"""
        return [roles[n] for n in names if n in roles]

    for title, url_name, icon, sort_order, children, role_names in MENUS:
        menu, _ = Menu.objects.get_or_create(title=title, parent=None)
        # 父菜单的图标、排序、路由也同步，避免改了 MENUS 却不生效
        menu.url_name = url_name or ''
        menu.icon = icon
        menu.sort_order = sort_order
        menu.save()
        menu.visible_roles.set(_roles(role_names))
        count += 1

        child_titles = []
        for child_order, child in enumerate(children, start=1):
            c_title, c_url, c_roles = child[0], child[1], child[2:]
            child_titles.append(c_title)

            c_menu, _ = Menu.objects.get_or_create(title=c_title, parent=menu)
            c_menu.url_name = c_url
            c_menu.sort_order = child_order
            c_menu.save()
            c_menu.visible_roles.set(_roles(c_roles))
            count += 1

        # 清掉本轮配置里已不存在的子菜单
        stale = menu.children.exclude(title__in=child_titles)
        removed += stale.count()
        stale.delete()

    print(f'  [OK] 导航菜单 {count} 项（清理过期菜单 {removed} 项）')


# =============================================================================
# 五、FAQ 知识库（FR-AI-01）
# =============================================================================

FAQS = [
    ('社保缴费比例是多少？',
     '公司现行社保缴费比例为：个人承担 10.5%，单位承担约 27%。具体明细可查看「我的社保」页面。',
     '社保,比例,缴费,五险', '薪酬福利'),
    ('请假流程是怎样的？',
     '登录后进入「我的请假」→ 填写请假类型、起止时间与事由 → 提交 → 系统通知部门负责人审批 → '
     '审批通过后自动计入考勤。审批结果会在站内通知中告知。',
     '请假,流程,怎么请假,审批', '考勤'),
    ('每月几号发工资？',
     '每月 15 日发放上月工资；如遇法定节假日则提前至最近一个工作日。',
     '工资,发放,几号,发薪', '薪酬福利'),
    ('年假有多少天？',
     '累计工作满 1 年不满 10 年的，年休假 5 天；满 10 年不满 20 年的 10 天；满 20 年的 15 天。'
     '入职当年按剩余日历天数折算。',
     '年假,休假,放假,假期', '考勤'),
    ('加班费怎么计算？',
     '工作日加班按基本时薪的 1.5 倍，休息日 2 倍，法定节假日 3 倍。'
     '基本时薪 = 基本工资 ÷ 月标准工时（21.75 天 × 8 小时）。',
     '加班,加班费,加班工资', '薪酬福利'),
    ('如何查询我的档案信息？',
     '登录后进入「我的档案」即可查看个人基本信息、任职信息与证书资质。如需修改请联系 HR。',
     '档案,个人信息,查询', '员工服务'),
]


def create_faqs() -> None:
    """建立 FAQ 知识库。"""
    for order, (question, answer, keywords, category) in enumerate(FAQS, start=1):
        FaqItem.objects.get_or_create(
            question=question,
            defaults={
                'answer': answer,
                'keywords': keywords,
                'category': category,
                'sort_order': order,
            },
        )
    print(f'  [OK] FAQ {len(FAQS)} 条')


# =============================================================================
# 六、演示员工档案（不可登录，仅作列表与报表数据）
# =============================================================================

# (工号, 姓名, 性别, 部门, 岗位, 薪酬级别, 学历, 入职日期, 出生日期)
# 不再单独设登录名：本项目「工号即账号」，username 由 Employee.save() 自动同步
DEMO_EMPLOYEES = [
    ('E1001', '张伟', 'M', 'PROD', 'OP', 'P1', 'college',
     date(2021, 3, 1), date(1988, 5, 12)),
    ('E1002', '李静', 'F', 'HR', 'HRS', 'P2', 'bachelor',
     date(2022, 7, 15), date(1995, 9, 3)),
    ('E1003', '王强', 'M', 'TECH-BE', 'BE', 'P3', 'bachelor',
     date(2020, 6, 1), date(1993, 2, 20)),
    ('E1004', '刘敏', 'F', 'FIN', 'ACC', 'P2', 'bachelor',
     date(2023, 2, 6), date(1996, 11, 8)),
    ('E1005', '陈浩', 'M', 'TECH-FE', 'FE', 'P3', 'master',
     date(2019, 9, 2), date(1992, 7, 25)),
    ('E1006', '赵晓雯', 'F', 'MKT', 'HRS', 'P2', 'college',
     date(2024, 4, 8), date(1998, 1, 30)),
    ('E1007', '孙鹏', 'M', 'PROD-01', 'OP', 'P1', 'below_college',
     date(2025, 8, 1), date(2000, 6, 18)),
    ('E1008', '周雅', 'F', 'TECH', 'TD', 'P4', 'master',
     date(2018, 5, 20), date(1990, 4, 16)),
]


def create_demo_employees(maps: dict, level_map: dict) -> None:
    """建立演示员工档案。

    统一使用不可用密码：这些记录只用于列表展示与报表统计，
    需要能登录的演示账号时，请在 admin 中单独为其设置密码。
    """
    created = 0
    for idx, (no, name, gender, dept_code, pos_code, level_code,
              education, hire_date, birth_date) in enumerate(DEMO_EMPLOYEES, start=1):
        if Employee.objects.filter(employee_no=no).exists():
            continue
        Employee.objects.create_user(
            username=no,  # 工号即账号
            real_name=name,
            employee_no=no,
            gender=gender,
            # 18 位 = 6 位地区码 + 8 位日期 + 4 位顺序号（纯演示数据）
            id_card=f'110101{19900101 + idx * 37:08d}{idx:04d}',
            education=education,
            phone=f'1380000{idx:04d}',
            political_status='群众',
            department=maps['departments'].get(dept_code),
            position=maps['positions'].get(pos_code),
            salary_level=level_map.get(level_code),
            employ_status=Employee.EmployStatus.REGULAR,
            hire_date=hire_date,
            birth_date=birth_date,
            is_active=True,
            # password 不传 → Django 会写入不可用密码，该账号无法登录
        )
        created += 1
    print(f'  [OK] 演示员工 新建 {created} 个，跳过 {len(DEMO_EMPLOYEES) - created} 个已存在的')


def assign_demo_roles(roles: dict) -> None:
    """给演示员工分配角色，模拟真实的人员构成。

    普通职工占多数，HR 专员少量——演示时可直接用 HR 账号登录，
    看到与系统管理员不同的菜单（验证 FR-SYS-03 的角色过滤）。
    """
    plan = {
        'E1001': ['普通职工'],
        'E1002': ['HR 专员/经理'],
        'E1003': ['普通职工'],
        'E1004': ['HR 专员/经理'],
        'E1005': ['普通职工'],
        'E1006': ['普通职工'],
        'E1007': ['普通职工'],
        'E1008': ['HR 专员/经理'],
    }
    for employee_no, role_names in plan.items():
        employee = Employee.objects.filter(employee_no=employee_no).first()
        if employee:
            employee.groups.set([roles[n] for n in role_names if n in roles])
    print(f'  [OK] 已为 {len(plan)} 个演示员工分配角色')


def main() -> int:
    print('=== 1. 角色与权限 (FR-SYS-01) ===')
    roles = create_roles()

    print('=== 2. 基础数据 (FR-SYS-02) ===')
    maps = create_base_data()

    print('=== 3. 薪酬体系 (FR-SAL-01) ===')
    level_map = create_salary_config()

    print('=== 4. 导航菜单 (FR-SYS-03) ===')
    create_menus(roles)

    print('=== 5. FAQ 知识库 (FR-AI-01) ===')
    create_faqs()

    print('=== 6. 演示员工档案 (FR-PER-01) ===')
    create_demo_employees(maps, level_map)
    assign_demo_roles(roles)

    print()
    print('[完成] 基础数据初始化结束，可重复运行本脚本。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
