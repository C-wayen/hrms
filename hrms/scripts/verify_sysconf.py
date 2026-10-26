"""系统设置模块验证脚本（FR-SYS-01 ~ FR-SYS-03）。

用途：把「组织机构 / 数据字典 / 用户与角色 / 导航菜单」四个页面
真的能增删改查这件事，变成可重复执行的检查。

为什么不能只检查「页面能打开」：HTTP 200 只说明模板渲染成功，
表单字段名写错、唯一约束没生效、PROTECT 外键被绕过——这些全都不会体现在状态码上。
所以本脚本一律 POST 真实数据，然后回数据库核对结果。

脚本自带造数与清理，可反复运行。

用法：
    & 'D:\\rj\\conda_env\\envs\\aip\\python.exe' scripts\\verify_sysconf.py

@author 王坤尧
"""

import os
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

from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client  # noqa: E402

from apps.sysconf.models import DataDict, Department, Employee, Menu  # noqa: E402

TEST_DEPT_CODE = 'TEST-DEPT'
TEST_DICT_TYPE = '测试类型'
TEST_MENU_TITLE = '测试菜单'
TEST_PASSWORD = 'Hrms@Test2026'

failures = []


def check(label, condition, detail=''):
    """记录一条断言结果。"""
    mark = 'OK  ' if condition else 'FAIL'
    print(f'  [{mark}] {label}' + (f' — {detail}' if detail else ''))
    if not condition:
        failures.append(label)


def admin_client():
    """以超级管理员身份登录的测试客户端。"""
    admin = Employee.objects.filter(is_superuser=True, is_deleted=False).first()
    if admin is None:
        print('[!] 找不到超级管理员，请先运行 scripts/create_superuser.py')
        sys.exit(1)
    client = Client(SERVER_NAME='127.0.0.1')
    client.force_login(admin)
    return client


def cleanup():
    """清掉上一轮可能残留的测试数据，保证脚本可重复运行。"""
    Menu.objects.filter(title=TEST_MENU_TITLE).delete()
    DataDict.objects.filter(dict_type=TEST_DICT_TYPE).delete()
    # 先删子部门再删父部门：parent 是 PROTECT，顺序反了会抛 ProtectedError
    Department.objects.filter(code=f'{TEST_DEPT_CODE}-CHILD').delete()
    Department.objects.filter(code=TEST_DEPT_CODE).delete()


client = admin_client()
cleanup()


def flush():
    """丢弃一次请求，把待显示的提示消息消费掉。

    消息文本里带着对象名称（「部门『测试部门』已建立」），
    不先消费就断言 '测试部门' in html，测到的是消息而不是页面内容——
    这类「断言缺区分力」的坑本项目已经踩过一次（季度离职率）。
    """
    client.get('/')


def sidebar_html():
    """取首页 HTML（侧边栏内容），取前先把提示消息消费掉。"""
    flush()
    return client.get('/').content.decode('utf-8')


# =============================================================================
print('=' * 74)
print('一、组织机构（FR-SYS-02）')
print('=' * 74)

resp = client.post('/system/departments/create/', {
    'code': TEST_DEPT_CODE, 'name': '测试部门', 'parent': '',
    'leader': '', 'sort_order': 99, 'is_active': 'on',
})
dept = Department.objects.filter(code=TEST_DEPT_CODE).first()
check('新增部门写入数据库', dept is not None,
      '' if dept else '表单校验未通过，部门未建立')

if dept is not None:
    flush()
    html = client.get('/system/departments/').content.decode('utf-8')
    check('列表页显示新部门', '测试部门' in html)

    # 上级部门不能选自己或自己的后代，否则组织树成环
    resp = client.post(f'/system/departments/{dept.pk}/edit/', {
        'code': TEST_DEPT_CODE, 'name': '测试部门', 'parent': str(dept.pk),
        'leader': '', 'sort_order': 99, 'is_active': 'on',
    })
    dept.refresh_from_db()
    check('上级部门拒绝选择自己', resp.status_code == 200 and dept.parent_id is None,
          f'HTTP {resp.status_code}，parent={dept.parent_id}')

    client.post(f'/system/departments/{dept.pk}/edit/', {
        'code': TEST_DEPT_CODE, 'name': '测试部门（改名）', 'parent': '',
        'leader': '', 'sort_order': 99, 'is_active': 'on',
    })
    dept.refresh_from_db()
    check('编辑部门生效', dept.name == '测试部门（改名）', f'当前名称：{dept.name}')

    # 有下级部门时删除应被 PROTECT 拦下，并给出一句人话而不是 500
    child = Department.objects.create(
        code=f'{TEST_DEPT_CODE}-CHILD', name='测试下级', parent=dept,
    )
    resp = client.post(f'/system/departments/{dept.pk}/delete/', follow=True)
    html = resp.content.decode('utf-8')
    check('有下级部门的部门删除被拒', Department.objects.filter(pk=dept.pk).exists())
    check('被拒时给出可读提示而非 500',
          resp.status_code == 200 and '无法删除' in html,
          f'HTTP {resp.status_code}')

    child.delete()
    client.post(f'/system/departments/{dept.pk}/delete/')
    check('无引用的部门可以删除',
          not Department.objects.filter(pk=dept.pk).exists())

print()
print('=' * 74)
print('二、数据字典（FR-SYS-02）')
print('=' * 74)

client.post('/system/dicts/create/', {
    'dict_type': TEST_DICT_TYPE, 'dict_key': 'T1', 'dict_value': '测试值一',
    'sort_order': 1, 'is_active': 'on', 'remark': '',
})
item = DataDict.objects.filter(dict_type=TEST_DICT_TYPE, dict_key='T1').first()
check('新增字典项写入数据库', item is not None)

if item is not None:
    # unique_together = (dict_type, dict_key) 必须真的生效
    resp = client.post('/system/dicts/create/', {
        'dict_type': TEST_DICT_TYPE, 'dict_key': 'T1', 'dict_value': '重复值',
        'sort_order': 2, 'is_active': 'on', 'remark': '',
    })
    duplicated = DataDict.objects.filter(
        dict_type=TEST_DICT_TYPE, dict_key='T1'
    ).count()
    check('重复的「类型 + 键」被拒绝', duplicated == 1, f'库里现有 {duplicated} 条')
    check('重复时回到表单页而不是报错', resp.status_code == 200,
          f'HTTP {resp.status_code}')

    flush()
    html = client.get('/system/dicts/', {'dict_type': TEST_DICT_TYPE}).content.decode('utf-8')
    check('按字典类型筛选生效', '测试值一' in html)

    client.post(f'/system/dicts/{item.pk}/delete/')
    check('字典项可以删除',
          not DataDict.objects.filter(pk=item.pk).exists())

print()
print('=' * 74)
print('三、用户与角色（FR-SYS-01、FR-SYS-03）')
print('=' * 74)

# 挑一个普通账号做实验：先把它的口令哈希原样备份，测完再写回去。
# 不再依赖「存在无密码账号」这个前提——默认密码上线后就没有这类账号了，
# 而备份哈希又能保证不会真的改掉谁的密码
target = (
    Employee.objects.filter(is_deleted=False, is_superuser=False)
    .order_by('employee_no')
    .first()
)
if target is None:
    check('存在可用于测试的普通账号', False)
else:
    original_password_hash = target.password
    original_groups = list(target.groups.all())
    original_state = (target.is_active, target.is_staff)
    target_no = target.employee_no

    resp = client.post(f'/system/accounts/{target.pk}/edit/', {
        'is_active': 'on', 'is_staff': '', 'groups': [],
        'new_password1': TEST_PASSWORD, 'new_password2': TEST_PASSWORD,
    })
    target.refresh_from_db()
    check('重置密码写入并做了哈希', target.check_password(TEST_PASSWORD),
          f'HTTP {resp.status_code}')
    # 表单里 groups 传了空列表：真的有清掉才算走通了 m2m 的保存
    if original_groups:
        check('清空角色生效', list(target.role_names) == [],
              f'当前角色：{list(target.role_names)}')

    fresh = Client(SERVER_NAME='127.0.0.1')
    check('用新密码可以登录', fresh.login(username=target_no, password=TEST_PASSWORD))

    role = Group.objects.filter(name='普通职工').first()
    if role is not None:
        client.post(f'/system/accounts/{target.pk}/edit/', {
            'is_active': 'on', 'is_staff': '', 'groups': [role.pk],
            'new_password1': '', 'new_password2': '',
        })
        target.refresh_from_db()
        check('分配角色生效', list(target.role_names) == ['普通职工'],
              f'当前角色：{list(target.role_names)}')

        flush()
        html = client.get('/system/accounts/', {'role': '普通职工'}).content.decode('utf-8')
        check('按角色筛选能筛出该账号', target_no in html)

    # 两次密码不一致必须被拦住
    resp = client.post(f'/system/accounts/{target.pk}/edit/', {
        'is_active': 'on', 'is_staff': '', 'groups': [],
        'new_password1': TEST_PASSWORD, 'new_password2': 'Mismatch@2026',
    })
    html = resp.content.decode('utf-8')
    check('两次密码不一致被拒绝', resp.status_code == 200 and '不一致' in html,
          f'HTTP {resp.status_code}')

    # 还原现场：连口令哈希也原样写回，脚本跑完数据库应与跑之前完全一致
    target.groups.set(original_groups)
    target.is_active, target.is_staff = original_state
    target.password = original_password_hash
    target.save(update_fields=['password'])
    check('测试账号的密码已原样还原',
          Employee.objects.get(pk=target.pk).password == original_password_hash)
    flush()

# 不能把自己锁在门外：本页是唯一能改后台访问权限的地方
admin = Employee.objects.filter(is_superuser=True, is_deleted=False).first()
admin_groups = list(admin.groups.all())
resp = client.post(f'/system/accounts/{admin.pk}/edit/', {
    'is_active': '', 'is_staff': 'on', 'groups': [],
    'new_password1': '', 'new_password2': '',
})
html = resp.content.decode('utf-8')
admin.refresh_from_db()
check('不能停用自己的账号', '不能停用自己' in html, f'HTTP {resp.status_code}')
check('被拒后账号确实没被改动',
      admin.is_active and list(admin.groups.all()) == admin_groups)

print()
print('=' * 74)
print('四、导航菜单（FR-SYS-03）')
print('=' * 74)

parent = Menu.objects.filter(title='系统设置', parent=None).first()
all_roles = list(Group.objects.all())
if parent is None:
    check('存在「系统设置」分组菜单', False)
else:
    client.post('/system/menus/create/', {
        'title': TEST_MENU_TITLE, 'url_name': 'datadict-list', 'parent': str(parent.pk),
        'icon': 'bi-bug', 'sort_order': 99, 'is_active': 'on',
        'visible_roles': [role.pk for role in all_roles],
    })
    item = Menu.objects.filter(title=TEST_MENU_TITLE).first()
    check('新增菜单写入数据库', item is not None)

    if item is not None:
        html = sidebar_html()
        check('新菜单立刻出现在侧边栏', TEST_MENU_TITLE in html)

        # 上级菜单不能选自己或自己的后代，否则菜单树成环
        resp = client.post(f'/system/menus/{item.pk}/edit/', {
            'title': TEST_MENU_TITLE, 'url_name': 'datadict-list', 'parent': str(item.pk),
            'icon': 'bi-bug', 'sort_order': 99, 'is_active': 'on',
            'visible_roles': [role.pk for role in all_roles],
        })
        item.refresh_from_db()
        check('上级菜单拒绝选择自己',
              resp.status_code == 200 and item.parent_id == parent.pk,
              f'HTTP {resp.status_code}，parent={item.parent_id}')

        # 路由名指向不存在的页面时，侧边栏应静默隐藏（避免死链）
        item.url_name = 'no-such-route-name'
        item.save()
        html = sidebar_html()
        check('路由不存在的菜单不出现在侧边栏', TEST_MENU_TITLE not in html)

        flush()
        html = client.get('/system/menus/').content.decode('utf-8')
        check('菜单页主动标出「路由不存在」', '路由不存在' in html)

        client.post(f'/system/menus/{item.pk}/delete/')
        check('菜单可以删除', not Menu.objects.filter(pk=item.pk).exists())

        html = sidebar_html()
        check('删除后侧边栏不再显示', TEST_MENU_TITLE not in html)

cleanup()

print()
if failures:
    print(f'[FAIL] 共 {len(failures)} 项未通过：')
    for item in failures:
        print(f'  - {item}')
    sys.exit(1)

print('[OK] 系统设置四个模块的增删改查全部验证通过。')
