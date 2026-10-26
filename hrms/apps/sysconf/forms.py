"""
系统设置模块表单。

关联需求：FR-SYS-01 权限控制、FR-SYS-02 基础数据、FR-SYS-03 用户与菜单管理

@author 王坤尧
"""

from django import forms
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password

from .models import DataDict, Department, Employee, Menu
from .scoping import department_and_children_ids


def apply_bootstrap(form) -> None:
    """统一为控件加上 Bootstrap 样式类，保证与其它模块观感一致。"""
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, (forms.Select, forms.SelectMultiple)):
            widget.attrs.setdefault('class', 'form-select')
        elif isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault('class', 'form-check-input')
        else:
            widget.attrs.setdefault('class', 'form-control')


def _menu_subtree_ids(menu) -> list:
    """取某菜单自身及其所有下级菜单的 id。

    用来把「上级菜单」下拉里的自己和自己的后代排除掉。不排除的话组织树会成环：
    菜单 A 的上级设成自己的后代 B，侧边栏遍历父子关系时就绕不出来了。
    """
    ids, frontier = [menu.pk], [menu.pk]
    while frontier:
        children = list(
            Menu.objects.filter(parent_id__in=frontier).values_list('pk', flat=True)
        )
        ids.extend(children)
        frontier = children
    return ids


# =============================================================================
# 一、组织机构（FR-SYS-02）
# =============================================================================


class DepartmentForm(forms.ModelForm):
    """部门表单（FR-SYS-02 组织机构树形管理）。"""

    class Meta:
        model = Department
        fields = ['code', 'name', 'parent', 'leader', 'sort_order', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            # 上级部门不能选自己或自己的后代（department_and_children_ids 返回的
            # 正是「自身 + 全部下级」），否则部门树成环，get_full_path() 只能靠
            # 20 层 guard 兜底，页面上会显示成一条诡异的长路径
            self.fields['parent'].queryset = Department.objects.exclude(
                pk__in=department_and_children_ids(self.instance)
            )

        # 负责人只列在职员工：已离职的人不该再被指为部门负责人
        self.fields['leader'].queryset = (
            Employee.objects
            .filter(is_deleted=False)
            .exclude(employ_status=Employee.EmployStatus.RESIGNED)
            .order_by('employee_no')
        )
        self.fields['leader'].label_from_instance = (
            lambda e: f'{e.real_name}（{e.employee_no}）'
        )

        apply_bootstrap(self)


# =============================================================================
# 二、数据字典（FR-SYS-02）
# =============================================================================


class DataDictForm(forms.ModelForm):
    """数据字典表单（FR-SYS-02）。"""

    class Meta:
        model = DataDict
        fields = [
            'dict_type', 'dict_key', 'dict_value',
            'sort_order', 'is_active', 'remark',
        ]
        help_texts = {
            'dict_type': '如「政治面貌」「请假类型」。已有类型见列表页，'
                         '请沿用已有写法，否则会分裂出两个同义类型',
        }


# =============================================================================
# 三、用户与角色（FR-SYS-01、FR-SYS-03）
# =============================================================================


class EmployeeAccountForm(forms.ModelForm):
    """用户账号与角色表单（FR-SYS-01、FR-SYS-03）。

    只暴露「账号」维度的字段。姓名、部门、岗位等档案字段属于人事管理，
    在这里改会绕过 FR-PER-01 的调动记录，因此本表单不碰它们。

    is_superuser 同样不在此：超级管理员是系统的最后一道门，
    日常授权用「角色」就够了，不该在日常界面上被随手勾选。
    """

    groups = forms.ModelMultipleChoiceField(
        label='角色',
        queryset=Group.objects.all().order_by('name'),
        required=False,
        widget=forms.SelectMultiple(attrs={'size': 6}),
        help_text='角色决定可见的菜单与功能权限，对应 FR-SYS-01 的 RBAC',
    )

    new_password1 = forms.CharField(
        label='新密码',
        required=False,
        widget=forms.PasswordInput,
        help_text='留空表示不修改密码；填写则至少 8 位',
    )
    new_password2 = forms.CharField(
        label='确认新密码',
        required=False,
        widget=forms.PasswordInput,
    )

    class Meta:
        model = Employee
        fields = ['is_active', 'is_staff', 'groups']

    def clean(self):
        cleaned = super().clean()
        first = cleaned.get('new_password1')
        second = cleaned.get('new_password2')

        if first or second:
            if first != second:
                self.add_error('new_password2', '两次输入的密码不一致。')
            else:
                # 走 Django 的密码强度校验（settings.AUTH_PASSWORD_VALIDATORS）。
                # 未配置校验器时该调用是空操作，不会误报
                try:
                    validate_password(first, self.instance)
                except forms.ValidationError as exc:
                    self.add_error('new_password1', exc)
        return cleaned

    def save(self, commit=True):
        employee = super().save(commit=False)
        password = self.cleaned_data.get('new_password1')
        if password:
            # set_password 会做哈希；直接赋值会把明文写进库
            employee.set_password(password)
        if commit:
            employee.save()
            self.save_m2m()
        return employee


# =============================================================================
# 四、导航菜单（FR-SYS-03）
# =============================================================================


class MenuForm(forms.ModelForm):
    """导航菜单表单（FR-SYS-03）。

    url_name 是「路由名」而非 URL 路径：菜单靠 reverse(url_name) 反查地址，
    这样改了路由前缀也不必回头改菜单配置。
    """

    class Meta:
        model = Menu
        fields = [
            'title', 'url_name', 'parent', 'icon',
            'sort_order', 'is_active', 'visible_roles',
        ]
        help_texts = {
            'url_name': '路由名，如 employee-list；分组型菜单留空（它只是折叠开关）',
            'icon': 'Bootstrap Icons 类名，如 bi-people',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            # 上级菜单不能选自己或自己的后代，否则菜单树成环
            self.fields['parent'].queryset = Menu.objects.exclude(
                pk__in=_menu_subtree_ids(self.instance)
            )

        self.fields['visible_roles'].required = False
        self.fields['visible_roles'].widget.attrs['size'] = 6
        apply_bootstrap(self)
