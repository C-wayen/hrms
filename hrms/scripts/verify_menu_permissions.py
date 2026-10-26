"""导航菜单与权限一致性验证脚本。

用途：把「已登录用户能看到的每一个入口都真的能打开」这件事变成可重复执行的检查。

为什么需要它：权限错误最典型的失败模式是「菜单里看得见、点进去 403」——
而这类问题在开发时极易被掩盖，因为**超级管理员的 is_superuser 恒为真**，
任何权限码写错都不会暴露。本项目就靠这套检查抓到过两类真问题：
    1. 视图与模板里把 Employee 的权限码写成 personnel.view_employee
       （该模型实际在 sysconf 下），导致 HR 被拒、连管理员都看不到操作按钮；
    2. 路由尚未实现的菜单项渲染成 href="#" 的死链，点了没反应。

检查内容：
    1. 侧边栏渲染出的每个链接都能打开（无 4xx/5xx）
    2. 侧边栏里没有 href="#" 死链
    3. 档案列表页的操作按钮按权限正确显示
    4. 403 兜底页使用自定义提示，而不是 Django 默认的纯文本页面
    5. 侧边栏只展开当前页面所属的分组，首页全部收起
    6. 「我的档案 / 我的请假」自助入口不越权（只看得到本人、不给审批入口）
    7. 默认密码（姓名首字母 + 888888）确实能用，自助改密流程正确且不掉线

    & 'D:\\rj\\conda_env\\envs\\aip\\python.exe' scripts\\verify_menu_permissions.py

@author 王坤尧
"""

import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Windows 控制台默认 GBK，遇到特殊符号会抛 UnicodeEncodeError 打断脚本
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402
from django.urls import NoReverseMatch, reverse  # noqa: E402

from apps.personnel.models import LeaveRequest  # noqa: E402
from apps.sysconf.models import Employee, Menu  # noqa: E402
from scripts.init_data import default_password  # noqa: E402

# 三种角色的代表账号，与 init_data.py 建立的演示数据对应
ACCOUNTS = [
    ('ADMIN001', '系统管理员'),
    ('E1002', 'HR 专员/经理'),
    ('E1001', '普通职工'),
]

# 只抓 <a class="nav-link" href="...">，分组折叠开关的 class 是
# "nav-link sidebar-group"，不会被误抓
LINK_RE = re.compile(r'<a class="nav-link"[^>]*href="([^"]*)"')

# 折叠容器：<div class="collapse show" id="menu-12">，展开时多一个 show
COLLAPSE_RE = re.compile(r'<div class="collapse( show)?" id="menu-(\d+)"')

failures = []


def expanded_menu_ids(html):
    """从页面 HTML 里取出当前处于展开状态的菜单分组 id。

    直接读渲染结果而不是去调用上下文处理器，
    这样模板里写错 show 条件也能被抽到。
    """
    return [int(menu_id) for show, menu_id in COLLAPSE_RE.findall(html) if show]


def check(label, condition, detail=''):
    """记录一条断言结果。"""
    mark = 'OK  ' if condition else 'FAIL'
    print(f'  [{mark}] {label}' + (f' — {detail}' if detail else ''))
    if not condition:
        failures.append(label)


def make_client(employee_no):
    """以指定员工身份登录的测试客户端。"""
    employee = Employee.objects.filter(employee_no=employee_no).first()
    if employee is None:
        return None
    client = Client(SERVER_NAME='127.0.0.1')
    client.force_login(employee)
    return client


def audit_sidebar(employee_no, role):
    """检查某角色侧边栏里每个链接都能打开，且没有死链。"""
    client = make_client(employee_no)
    if client is None:
        check(f'{role} 账号存在', False, f'找不到 {employee_no}')
        return

    html = client.get('/').content.decode('utf-8')
    hrefs = LINK_RE.findall(html)
    dead = [href for href in hrefs if not href or href == '#']
    live = [href for href in hrefs if href and href != '#']

    print(f'  {role}：侧边栏链接 {len(live)} 个')
    check(f'{role} 侧边栏无死链（href="#"）', not dead,
          f'死链 {len(dead)} 个：{dead}' if dead else '')

    broken = [
        f'{href} → HTTP {client.get(href).status_code}'
        for href in live
        if client.get(href).status_code >= 400
    ]
    check(f'{role} 侧边栏每个链接都能打开', not broken,
          '；'.join(broken) if broken else '')


print('=' * 74)
print('一、侧边栏链接可用性（看得见就必须进得去）')
print('=' * 74)
print()
for employee_no, role in ACCOUNTS:
    audit_sidebar(employee_no, role)
    print()


print('=' * 74)
print('二、操作按钮按权限显示（无权限就看不到按钮）')
print('=' * 74)

for employee_no, role in ACCOUNTS:
    client = make_client(employee_no)
    if client is None:
        continue
    response = client.get('/personnel/employees/')
    if response.status_code != 200:
        # 档案菜单对该角色不可见，因此访问被拒才是正确的
        check(f'{role} 访问档案列表被拒（菜单不可见）',
              response.status_code == 403, f'HTTP {response.status_code}')
        continue

    html = response.content.decode('utf-8')
    # 系统管理员与 HR 都能管理职工档案，三个按钮都应出现
    check(f'{role} 档案页有「新增」按钮', 'employees/create/' in html)
    check(f'{role} 档案页有「编辑」按钮', '/edit/' in html)
    check(f'{role} 档案页有「删除」按钮', '/delete/' in html)

print()
print('=' * 74)
print('三、403 兜底页')
print('=' * 74)

plain_client = make_client('E1001')
if plain_client is not None:
    response = plain_client.get('/report/structure/')
    html = response.content.decode('utf-8')
    check('普通职工访问报表被拒', response.status_code == 403,
          f'HTTP {response.status_code}')
    check('403 页使用自定义提示文案', '没有访问该功能的权限' in html)
    check('403 页提供返回首页入口', '返回首页' in html)
    check('403 页仍渲染侧边栏（不脱离系统）', 'sidebar-nav' in html)

print()
print('=' * 74)
print('四、侧边栏默认展开行为（只展开当前页所属分组）')
print('=' * 74)
print()

admin_client = make_client('ADMIN001')
if admin_client is not None:
    # 首页不落进任何分组，所以应该一个都不展开
    ids = expanded_menu_ids(admin_client.get('/').content.decode('utf-8'))
    check('首页默认所有分组收起', not ids, f'却展开了 {len(ids)} 个')

    # 遍历每一个子菜单：只有它所属的那一组应该是展开的。
    # 不写死页面清单，以后新增菜单本检查会自动覆盖到。
    unresolvable, checked, seen = [], 0, set()
    for child in Menu.objects.filter(parent__isnull=False).order_by('parent_id', 'sort_order'):
        if not child.url_name:
            continue
        try:
            path = reverse(child.url_name)
        except NoReverseMatch:
            unresolvable.append(f'{child.title}({child.url_name})')
            continue

        html = admin_client.get(path).content.decode('utf-8')
        # 「系统设置」那几项跳转到 Django Admin，那套页面没有本侧栏，无从判断展开态
        if 'sidebar-nav' not in html:
            continue
        if (path, child.parent_id) in seen:
            continue
        seen.add((path, child.parent_id))

        ids = expanded_menu_ids(html)
        check(f'{path} 只展开「{child.parent.title}」', ids == [child.parent_id],
              f'实际展开 {ids}（期望 [{child.parent_id}]）')
        checked += 1

    print(f'  （共检查 {checked} 个子菜单页）')
    if unresolvable:
        print(f'  [提示] 以下菜单配置找不到对应路由，不会出现在侧边栏：'
              f'{"、".join(unresolvable)}')

    # 不在菜单里的子页面（新增/编辑/审批）也要展开所属分组，
    # 否则点「新增职工」侧边栏会突然收起
    employee_list = Menu.objects.filter(url_name='employee-list').first()
    if employee_list is not None:
        path = reverse('employee-create')
        ids = expanded_menu_ids(admin_client.get(path).content.decode('utf-8'))
        check(f'{path} 也展开所属「人事管理」', ids == [employee_list.parent_id],
              f'实际展开 {ids}')

print('=' * 74)
print('五、我的档案 / 我的请假（自助入口不能越权）')
print('=' * 74)
print()

plain_client = make_client('E1001')
if plain_client is not None:
    me = Employee.objects.filter(employee_no='E1001').first()

    response = plain_client.get('/personnel/my-profile/')
    html = response.content.decode('utf-8')
    check('普通职工能打开我的档案', response.status_code == 200,
          f'HTTP {response.status_code}')
    check('我的档案展示的是本人', me.real_name in html and me.employee_no in html)
    # 普通职工没有 sysconf.view_employee 权限，页面上不该出现任何指向档案模块的入口
    check('我的档案不引导去无权限的档案列表', '/personnel/employees/' not in html)

    response = plain_client.get('/personnel/my-leaves/')
    html = response.content.decode('utf-8')
    check('普通职工能打开我的请假', response.status_code == 200,
          f'HTTP {response.status_code}')
    check('我的请假页标注了「只显示本人」', '只显示' in html)

    response = plain_client.get('/personnel/my-password/')
    check('普通职工能打开修改密码页', response.status_code == 200,
          f'HTTP {response.status_code}')

# 「我的请假」对任何角色都只看本人，且一律不给审批入口
for account, role in [('E1001', '普通职工'), ('E1002', 'HR 专员/经理')]:
    client = make_client(account)
    if client is None:
        continue
    html = client.get('/personnel/my-leaves/').content.decode('utf-8')
    # 「自己批自己的请假」绝不能发生，所以 HR 打开这一页也不该看到审批按钮
    check(f'{role} 的我的请假页无审批入口', '/approve/' not in html)

    others = (
        LeaveRequest.objects
        .filter(is_deleted=False)
        .exclude(employee__employee_no=account)
        .select_related('employee')
    )
    leaked = sorted({lv.employee.real_name for lv in others
                     if lv.employee.real_name in html})
    check(f'{role} 的我的请假页不出现他人记录', not leaked,
          f'出现了 {leaked}' if leaked else '')

print('=' * 74)
print('六、默认密码与自助改密（FR-SYS-03）')
print('=' * 74)
print()

DEFAULT_PWD = 'ZW888888'   # E1001 张伟：张 Z + 伟 W + 888888
NEW_PWD = 'Hrms@Test2026'


def fresh_client(username, password):
    """用账号密码真登录（而不是 force_login），验证密码本身是否可用。"""
    return Client(SERVER_NAME='127.0.0.1').login(username=username, password=password)


me = Client(SERVER_NAME='127.0.0.1')
logged_in = me.login(username='E1001', password=DEFAULT_PWD)
check('默认密码能登录（E1001 张伟 / ZW888888）', logged_in)
check('另一位员工的默认密码也对（E1002 李静 / LJ888888）',
      fresh_client('E1002', 'LJ888888'))

# 随机命名的批量员工：密码由姓名算出来，能登录才说明规则真的生效而不只是特例
samples = list(
    Employee.objects.filter(is_active=True, employee_no__gt='E1010')
    .order_by('employee_no')[:2]
)
for sample in samples:
    expected = default_password(sample.real_name)
    check(f'批量员工 {sample.employee_no} {sample.real_name} 默认密码可用',
          fresh_client(sample.employee_no, expected), f'期望密码 {expected}')

if logged_in:
    response = me.get('/personnel/my-password/')
    check('登录后能打开修改密码页', response.status_code == 200,
          f'HTTP {response.status_code}')

    # 当前密码错：必须拒绝，否则拿到别人未锁屏的会话就能改掉密码
    response = me.post('/personnel/my-password/', {
        'old_password': 'WrongOldPwd1',
        'new_password1': NEW_PWD, 'new_password2': NEW_PWD,
    })
    check('当前密码不对时拒绝修改',
          '当前密码不正确' in response.content.decode('utf-8')
          and not Employee.objects.get(employee_no='E1001').check_password(NEW_PWD))

    response = me.post('/personnel/my-password/', {
        'old_password': DEFAULT_PWD,
        'new_password1': NEW_PWD, 'new_password2': 'Mismatch@2026',
    })
    check('两次新密码不一致时拒绝修改',
          '不一致' in response.content.decode('utf-8'))

    # 改成功
    me.post('/personnel/my-password/', {
        'old_password': DEFAULT_PWD,
        'new_password1': NEW_PWD, 'new_password2': NEW_PWD,
    })
    check('新密码已生效',
          Employee.objects.get(employee_no='E1001').check_password(NEW_PWD))
    check('旧密码已失效', not fresh_client('E1001', DEFAULT_PWD))
    check('新密码可以登录', fresh_client('E1001', NEW_PWD))

    # 关键：改密后当前会话不能失效（update_session_auth_hash）
    response = me.get('/personnel/my-password/')
    check('改密后当前会话未掉线', response.status_code == 200,
          f'HTTP {response.status_code}')

    # 还原成默认密码，避免污染演示数据
    e1001 = Employee.objects.get(employee_no='E1001')
    e1001.set_password(DEFAULT_PWD)
    e1001.save(update_fields=['password'])
    check('已还原为默认密码',
          Employee.objects.get(employee_no='E1001').check_password(DEFAULT_PWD))

print()
if failures:
    print(f'[FAIL] 共 {len(failures)} 项未通过：')
    for item in failures:
        print(f'  - {item}')
    sys.exit(1)

print('[OK] 菜单、权限与兜底页全部验证通过。')
