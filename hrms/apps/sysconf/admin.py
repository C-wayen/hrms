"""
系统设置与安全模块的 Django Admin 配置。

在本项目中 /admin/ 不只是调试工具，它直接承载两项需求：
    用户与菜单管理   FR-SYS-03
    基础数据维护     FR-SYS-02（部门、岗位、数据字典）

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import DataDict, Department, Employee, Menu, Position


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """部门管理（FR-SYS-02 组织机构树形管理）。"""

    list_display = ('code', 'name', 'parent', 'leader', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')
    list_select_related = ('parent', 'leader')
    ordering = ('sort_order', 'code')


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    """岗位管理（FR-SYS-02）。"""

    list_display = ('code', 'name', 'level', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')


@admin.register(DataDict)
class DataDictAdmin(admin.ModelAdmin):
    """数据字典管理（FR-SYS-02）：集中维护政治面貌、请假类型等枚举值。"""

    list_display = ('dict_type', 'dict_key', 'dict_value', 'sort_order', 'is_active')
    list_filter = ('dict_type', 'is_active')
    search_fields = ('dict_type', 'dict_key', 'dict_value')


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    """导航菜单管理（FR-SYS-03）：配置菜单项与可见角色。"""

    list_display = ('title', 'parent', 'url_name', 'sort_order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('title', 'url_name')
    filter_horizontal = ('visible_roles',)


@admin.register(Employee)
class EmployeeAdmin(BaseUserAdmin):
    """员工账号与人事档案（合一维护）。

    继承 UserAdmin 以保留密码修改、角色与权限分配等内置能力，
    并追加人事档案字段组，使一个页面就能完成「人 + 账号」的维护。
    对应 FR-PER-01 职工档案管理与 FR-SYS-01 权限控制。
    """

    list_display = (
        'employee_no', 'real_name', 'department',
        'position', 'employ_status', 'is_active',
    )
    list_filter = ('employ_status', 'gender', 'department', 'is_active', 'is_deleted')
    search_fields = ('employee_no', 'real_name', 'username', 'phone', 'id_card')
    ordering = ('employee_no',)
    list_select_related = ('department', 'position')
    filter_horizontal = ('groups', 'user_permissions')

    # username 只读：它由 employee_no 自动同步（工号即账号），
    # 允许手改就又会变成两套标识
    readonly_fields = ('username', 'created_at', 'updated_at')

    # 完全自定义字段组，而非拼接 BaseUserAdmin.fieldsets：
    # 拼接会因为 email 等字段与默认组重复而触发 admin.E012 检查错误
    fieldsets = (
        (None, {
            'fields': ('username', 'password'),
            'description': '登录名与工号自动保持一致（工号即账号），无需手工填写',
        }),
        ('档案基本信息', {
            'fields': (
                'employee_no', 'real_name', 'gender', 'birth_date', 'id_card',
                'phone', 'email', 'education', 'political_status',
                'graduate_school', 'major', 'native_place', 'address',
            ),
        }),
        ('任职信息', {
            'fields': (
                'department', 'position', 'salary_level', 'employ_status',
                'hire_date', 'probation_end_date', 'regular_date', 'resign_date',
            ),
        }),
        ('权限与角色', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'description': '「角色」即 groups：系统管理员 / HR 专员·经理 / 普通职工（FR-SYS-01）',
        }),
        ('重要日期', {'fields': ('last_login', 'date_joined')}),
        ('其他', {'fields': ('is_deleted',)}),
    )

    # 新增员工时展示的字段组。
    # username 不出现在这里：它由工号自动同步，新增时无需填写
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('employee_no', 'real_name', 'gender', 'id_card', 'password1', 'password2'),
            'description': '登录名将自动使用工号',
        }),
    )
