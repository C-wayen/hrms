"""
系统设置与安全模块视图。

模块结构：
    一、首页仪表盘   指标卡片与待办提醒
    二、组织机构     部门树增删改查                FR-SYS-02
    三、数据字典     枚举值维护                    FR-SYS-02
    四、用户与角色   账号启用 / 角色 / 重置密码     FR-SYS-01、FR-SYS-03
    五、导航菜单     菜单项与可见角色               FR-SYS-03

关联需求：FR-SYS-01 权限控制、FR-SYS-02 基础数据、FR-SYS-03 用户与菜单管理
关联用例：UC-12 用户、菜单与基础数据管理

@author 王坤尧
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.models import Group
from django.db.models import ProtectedError, Q
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.personnel.models import LeaveRequest, RegularizationApply
from apps.sysconf.forms import (
    DataDictForm,
    DepartmentForm,
    EmployeeAccountForm,
    MenuForm,
)
from apps.sysconf.mixins import FormPageMixin
from apps.sysconf.models import DataDict, Department, Employee, Menu


@login_required
def home(request):
    """首页仪表盘。

    展示两类信息，回答「现在公司什么情况」与「我需要处理什么」：
      1. 关键指标卡片：在职人数、实习人数、部门数
      2. 待办提醒：本周生日员工（FR-PER-04）、待审批请假与转正申请
         （FR-PER-03 / FR-PER-02）

    查询均加 select_related，避免模板里访问 employee 时触发 N+1。
    """
    today = timezone.localdate()
    employees = Employee.objects.filter(is_deleted=False)

    stats = {
        'total': employees.count(),
        'on_job': employees.exclude(
            employ_status=Employee.EmployStatus.RESIGNED
        ).count(),
        'intern': employees.filter(employ_status=Employee.EmployStatus.INTERN).count(),
        'departments': Department.objects.filter(is_active=True).count(),
    }

    # 本周生日员工：按月日区间筛选，跨月时用两个条件取并集
    week_end = today + timedelta(days=7)
    if today.month == week_end.month:
        birthday_q = employees.filter(
            birth_date__month=today.month,
            birth_date__day__range=(today.day, week_end.day),
        )
    else:
        birthday_q = employees.filter(
            Q(birth_date__month=today.month, birth_date__day__gte=today.day)
            | Q(birth_date__month=week_end.month, birth_date__day__lte=week_end.day)
        )

    context = {
        'stats': stats,
        'birthdays': birthday_q.select_related('department').order_by('birth_date__day')[:6],
        'pending_leaves': (
            LeaveRequest.objects
            .filter(status=LeaveRequest.LeaveStatus.PENDING, is_deleted=False)
            .select_related('employee', 'employee__department')
            .order_by('start_date')[:6]
        ),
        'pending_regularizations': (
            RegularizationApply.objects
            .filter(status=RegularizationApply.ApplyStatus.PENDING)
            .select_related('employee')
            .order_by('expect_regular_date')[:6]
        ),
        'today': today,
    }
    return render(request, 'home.html', context)


# =============================================================================
# 通用工具
# =============================================================================


def _build_tree(queryset):
    """把「parent 自关联」的查询集组装成 (根节点列表, 子节点映射)。

    部门、菜单都是这个形状，抽出来给两处共用。
    """
    children_map = {}
    roots = []
    for node in queryset:
        if node.parent_id is None:
            roots.append(node)
        else:
            children_map.setdefault(node.parent_id, []).append(node)
    return roots, children_map


def _flatten_tree(roots, children_map, depth=0):
    """深度优先把树摊平成 [(节点, 层级), ...]，供表格按缩进渲染。

    为什么不在模板里递归：模板可以递归 include，但层数一深就难读，
    也难加「本层暂无下级」之类的处理。节点本来只有几十个，
    在视图里一次摊平最省事，模板只需按 depth 加左内边距。
    """
    rows = []
    for node in roots:
        rows.append((node, depth))
        rows.extend(_flatten_tree(children_map.get(node.pk, []), children_map, depth + 1))
    return rows


# =============================================================================
# 二、组织机构（FR-SYS-02）
# =============================================================================


class DepartmentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """组织机构列表（FR-SYS-02 组织机构树形管理）。

    渲染成带缩进的树而不是平铺表格：部门本身就是层级结构，
    平铺开就看不出「谁是谁的上级」了。

    不分页：组织节点通常只有几十个，分页反而会把一个部门和它的下级
    拆到两页，看的人得来回翻才能拼出完整结构。
    """

    model = Department
    template_name = 'sysconf/department_list.html'
    context_object_name = 'departments'
    permission_required = 'sysconf.view_department'

    def get_queryset(self):
        return (
            Department.objects
            .select_related('parent', 'leader')
            .order_by('sort_order', 'code')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        roots, children_map = _build_tree(self.get_queryset())
        rows = _flatten_tree(roots, children_map)
        context['rows'] = rows
        context['total'] = len(rows)
        context['active_count'] = sum(1 for node, _ in rows if node.is_active)
        return context


class DepartmentCreateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, CreateView):
    """新增部门（FR-SYS-02）。"""

    model = Department
    form_class = DepartmentForm
    template_name = 'sysconf/form.html'
    permission_required = 'sysconf.add_department'
    success_url = reverse_lazy('department-list')
    page_title = '新增部门'
    form_hint = '部门编码需唯一；上级部门留空即成为顶级部门。'
    cancel_url = 'department-list'

    def form_valid(self, form):
        messages.success(self.request, f'部门「{form.instance.name}」已建立。')
        return super().form_valid(form)


class DepartmentUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, UpdateView):
    """编辑部门（FR-SYS-02）。"""

    model = Department
    form_class = DepartmentForm
    template_name = 'sysconf/form.html'
    permission_required = 'sysconf.change_department'
    success_url = reverse_lazy('department-list')
    form_hint = '调整上级部门会连同下级一起改变隶属关系；下拉里已排除本部门及其下级，以免成环。'
    cancel_url = 'department-list'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑部门：{self.object.name}'
        return context

    def form_valid(self, form):
        messages.success(self.request, '部门已更新。')
        return super().form_valid(form)


class DepartmentDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """删除部门（FR-SYS-02）。

    部门与下级部门、员工之间是 PROTECT 外键关系，被引用时删除会抛
    ProtectedError。这里把它接住并转成一句人话，而不是让用户撞上 500 页。
    """

    model = Department
    template_name = 'sysconf/confirm_delete.html'
    permission_required = 'sysconf.delete_department'
    success_url = reverse_lazy('department-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '删除部门'
        context['object_label'] = self.object.get_full_path()
        context['warning'] = (
            f'该部门下有 {self.object.children.count()} 个下级部门、'
            f'{self.object.employees.count()} 名员工。'
            '只要还有任一项，删除就会被拒绝——请先转移它们。'
        )
        context['cancel_url'] = 'department-list'
        return context

    def form_valid(self, form):
        # 先取好可读名称：删完之后 self.object 还在内存里，但读起来容易疏忽
        label = self.object.get_full_path()
        response = super().form_valid(form)
        messages.success(self.request, f'部门「{label}」已删除。')
        return response

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        try:
            return super().post(request, *args, **kwargs)
        except ProtectedError:
            messages.error(
                request,
                f'无法删除「{self.object.get_full_path()}」：它下面还有下级部门或员工，'
                '请先转移这些数据。',
            )
            return redirect('department-list')


# =============================================================================
# 三、数据字典（FR-SYS-02）
# =============================================================================


class DataDictListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """数据字典列表（FR-SYS-02）。

    按「类型 → 排序号」排列，同一类型天然连在一起，
    这样「政治面貌」下面有没有混进别的类型一眼就能看出来。
    """

    model = DataDict
    template_name = 'sysconf/datadict_list.html'
    context_object_name = 'dicts'
    paginate_by = 20
    permission_required = 'sysconf.view_datadict'

    def get_queryset(self):
        # 显式 order_by：与 Meta.ordering 一致，但写出来可避免将来加 annotate
        # 时 Django 不再采信 Meta.ordering，分页报 UnorderedObjectListWarning
        queryset = DataDict.objects.order_by('dict_type', 'sort_order', 'dict_key')

        dict_type = self.request.GET.get('dict_type', '').strip()
        if dict_type:
            queryset = queryset.filter(dict_type=dict_type)

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(dict_key__icontains=keyword) | Q(dict_value__icontains=keyword)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filters'] = {
            'dict_type': self.request.GET.get('dict_type', ''),
            'q': self.request.GET.get('q', ''),
        }
        # 已有类型供筛选下拉直接选，不用手敲
        context['dict_types'] = (
            DataDict.objects.values_list('dict_type', flat=True)
            .distinct().order_by('dict_type')
        )
        return context


class DataDictCreateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, CreateView):
    """新增字典项（FR-SYS-02）。"""

    model = DataDict
    form_class = DataDictForm
    template_name = 'sysconf/form.html'
    permission_required = 'sysconf.add_datadict'
    success_url = reverse_lazy('datadict-list')
    page_title = '新增字典项'
    form_hint = '同一「字典类型 + 字典键」只能有一条，重复会被拒绝。'
    cancel_url = 'datadict-list'

    def form_valid(self, form):
        messages.success(
            self.request,
            f'字典项「{form.instance.dict_type} / {form.instance.dict_value}」已建立。',
        )
        return super().form_valid(form)


class DataDictUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, UpdateView):
    """编辑字典项（FR-SYS-02）。"""

    model = DataDict
    form_class = DataDictForm
    template_name = 'sysconf/form.html'
    permission_required = 'sysconf.change_datadict'
    success_url = reverse_lazy('datadict-list')
    form_hint = '改「字典值」只影响以后新填的数据，已经落库的历史值不会跟着变。'
    cancel_url = 'datadict-list'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑字典项：{self.object.dict_value}'
        return context

    def form_valid(self, form):
        messages.success(self.request, '字典项已更新。')
        return super().form_valid(form)


class DataDictDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """删除字典项（FR-SYS-02）。

    物理删除：字典属于配置数据，不在 SRS 约定的软删除范围内
    （那是员工、工资、请假三类），录错了就直接删。
    """

    model = DataDict
    template_name = 'sysconf/confirm_delete.html'
    permission_required = 'sysconf.delete_datadict'
    success_url = reverse_lazy('datadict-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '删除字典项'
        context['object_label'] = f'{self.object.dict_type} / {self.object.dict_value}'
        context['warning'] = '已经用过这个值的历史数据不会受影响，但下拉框里将不再出现该项。'
        context['cancel_url'] = 'datadict-list'
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, '字典项已删除。')
        return response


# =============================================================================
# 四、用户与角色（FR-SYS-01、FR-SYS-03）
# =============================================================================


class EmployeeAccountListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """用户与角色列表（FR-SYS-01、FR-SYS-03、UC-12）。

    只列账号维度的信息：能否登录、能否进后台、属于哪些角色。

    为什么本页没有「新增账号」：账号与档案是同一张表（Employee 继承
    AbstractUser），建账号就是建档，统一走「人事管理 - 新增职工」，
    建完再回本页设密码与角色，避免两处都能建人而字段校验不一致。
    """

    model = Employee
    template_name = 'sysconf/account_list.html'
    context_object_name = 'accounts'
    paginate_by = 20
    permission_required = 'sysconf.view_employee'

    def get_queryset(self):
        queryset = (
            Employee.objects
            .filter(is_deleted=False)
            .select_related('department')
            .prefetch_related('groups')
            .order_by('employee_no')
        )

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(employee_no__icontains=keyword) | Q(real_name__icontains=keyword)
            )

        role = self.request.GET.get('role', '').strip()
        if role:
            queryset = queryset.filter(groups__name=role)

        status = self.request.GET.get('status', '').strip()
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'role': self.request.GET.get('role', ''),
            'status': self.request.GET.get('status', ''),
        }
        context['roles'] = Group.objects.order_by('name')
        context['status_choices'] = [('active', '已启用'), ('inactive', '已停用')]
        return context


class EmployeeAccountUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, UpdateView):
    """编辑账号权限与重置密码（FR-SYS-01、FR-SYS-03）。

    路由名沿用菜单里已配置的 employee-account 命名体系，
    因此这里是 account-update 而不是 employee-update——后者是人事档案。
    """

    model = Employee
    form_class = EmployeeAccountForm
    template_name = 'sysconf/form.html'
    permission_required = 'sysconf.change_employee'
    success_url = reverse_lazy('employee-account')
    form_hint = (
        '这里只管账号：能否登录、是否允许进后台、属于哪些角色、以及重置密码。'
        '姓名与部门等档案字段请到「人事管理 - 职工档案」修改。'
    )
    cancel_url = 'employee-account'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = (
            f'账号设置：{self.object.real_name}（{self.object.employee_no}）'
        )
        context['account'] = self.object
        return context

    def form_valid(self, form):
        # 防止把自己锁在门外：本页是唯一能改后台访问权限的地方，
        # 一旦停用自己或去掉 is_staff，就再也进不来，只能去改数据库
        if self.object == self.request.user:
            problems = []
            if not form.cleaned_data.get('is_active'):
                problems.append('停用自己')
            if not form.cleaned_data.get('is_staff'):
                problems.append('取消自己的后台访问权限')
            if problems:
                form.add_error(
                    None,
                    f'不能{"、".join(problems)}——否则将没有人能再进入本页。',
                )
                return self.form_invalid(form)

        messages.success(self.request, f'「{self.object.real_name}」的账号设置已更新。')
        return super().form_valid(form)


# =============================================================================
# 五、导航菜单（FR-SYS-03）
# =============================================================================


class MenuListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """导航菜单列表（FR-SYS-03、UC-12）。"""

    model = Menu
    template_name = 'sysconf/menu_list.html'
    context_object_name = 'menus'
    permission_required = 'sysconf.view_menu'

    def get_queryset(self):
        return (
            Menu.objects
            .select_related('parent')
            .prefetch_related('visible_roles')
            .order_by('sort_order', 'title')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        roots, children_map = _build_tree(self.get_queryset())
        rows = _flatten_tree(roots, children_map)
        context['rows'] = rows
        context['total'] = len(rows)
        context['active_count'] = sum(1 for node, _ in rows if node.is_active)

        # 标出「配了路由名但页面不存在」的项：它们不会出现在侧边栏（_has_route
        # 会静默过滤）。不在页面上点出来的话，改配置的人只会以为「改完没生效」，
        # 而真正的清单只能靠翻代码——这正是「我的档案」漏了两周的原因。
        broken = set()
        for node, _ in rows:
            if not node.url_name:
                continue
            try:
                reverse(node.url_name)
            except NoReverseMatch:
                broken.add(node.pk)
        context['broken_route_ids'] = broken
        return context


class MenuCreateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, CreateView):
    """新增菜单项（FR-SYS-03）。"""

    model = Menu
    form_class = MenuForm
    template_name = 'sysconf/form.html'
    permission_required = 'sysconf.add_menu'
    success_url = reverse_lazy('menu-list')
    page_title = '新增菜单项'
    form_hint = '新增后侧边栏立即生效；路由尚未实现的菜单项不会显示（避免死链）。'
    cancel_url = 'menu-list'

    def form_valid(self, form):
        messages.success(self.request, f'菜单「{form.instance.title}」已建立。')
        return super().form_valid(form)


class MenuUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, UpdateView):
    """编辑菜单项（FR-SYS-03）。"""

    model = Menu
    form_class = MenuForm
    template_name = 'sysconf/form.html'
    permission_required = 'sysconf.change_menu'
    success_url = reverse_lazy('menu-list')
    form_hint = '改「可见角色」会立刻影响所有已登录用户看到的侧边栏。'
    cancel_url = 'menu-list'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑菜单：{self.object.title}'
        return context

    def form_valid(self, form):
        messages.success(self.request, '菜单已更新。')
        return super().form_valid(form)


class MenuDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """删除菜单项（FR-SYS-03）。

    菜单的 parent 是 CASCADE：删分组会连同子项一起删。
    这一点必须在确认页说清楚，否则用户只会以为少了一个折叠标题。
    """

    model = Menu
    template_name = 'sysconf/confirm_delete.html'
    permission_required = 'sysconf.delete_menu'
    success_url = reverse_lazy('menu-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        child_count = self.object.children.count()
        context['page_title'] = '删除菜单项'
        context['object_label'] = self.object.title
        context['warning'] = (
            f'其下的 {child_count} 个子菜单会被一并删除（菜单是配置数据，不保留历史）。'
            '删除后侧边栏立即少掉这些项。'
            if child_count else
            '删除后侧边栏立即少掉这一项。若它只是暂时不用，把「是否启用」取消勾选更稳妥。'
        )
        context['cancel_url'] = 'menu-list'
        return context

    def form_valid(self, form):
        label = self.object.title
        response = super().form_valid(form)
        messages.success(self.request, f'菜单「{label}」已删除。')
        return response
