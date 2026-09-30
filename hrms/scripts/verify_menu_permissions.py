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

from apps.sysconf.models import Employee  # noqa: E402

# 三种角色的代表账号，与 init_data.py 建立的演示数据对应
ACCOUNTS = [
    ('ADMIN001', '系统管理员'),
    ('E1002', 'HR 专员/经理'),
    ('E1001', '普通职工'),
]

# 只抓 <a class="nav-link" href="...">，分组折叠开关的 class 是
# "nav-link sidebar-group"，不会被误抓
LINK_RE = re.compile(r'<a class="nav-link"[^>]*href="([^"]*)"')

failures = []


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
if failures:
    print(f'[FAIL] 共 {len(failures)} 项未通过：')
    for item in failures:
        print(f'  - {item}')
    sys.exit(1)

print('[OK] 菜单、权限与兜底页全部验证通过。')
