"""
薪酬管理模块视图。

模块结构：
    一、薪酬体系配置      薪酬级别 / 薪酬标准              FR-SAL-01
    二、津贴与扣减项登记  加班 / 水电 / 计件计时            FR-SAL-03、FR-SAL-02
    三、工资核算与发放    核算、工资档案、发放、我的工资     FR-SAL-02

公式与事务逻辑集中在 services.py，本文件只负责 HTTP 编排与权限把关，
这样公式可以脱离浏览器单独验证。

对应的课程原始功能条目：
    「薪酬级别设置」「加班登记」「水电费登记」「计件工资与计时工资」
    「生成工资档案」「批量发放」「历史薪酬查询」

@author 王坤尧
"""

import re
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from apps.sysconf.models import Department, Employee
from apps.sysconf.scoping import DataScopeMixin

from .forms import (
    OvertimeRecordForm,
    PieceworkRecordForm,
    SalaryCalculateForm,
    SalaryLevelForm,
    SalaryStandardForm,
    UtilityFeeRecordForm,
)
from .models import (
    OvertimeRecord,
    PieceworkRecord,
    SalaryLevel,
    SalaryRecord,
    SalaryStandard,
    UtilityFeeRecord,
)
from .services import SalaryCalculationError, calculate_for_period

# 用于在核算页兜底校验周期字符串，避免非法值（例如 2026-13）被送去拼日期
# 这里必须与表单里的 PERIOD_RE 同样严格：宽松一位，表单校验失败后的重新渲染就会 500
_PERIOD_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


# =============================================================================
# 通用工具
# =============================================================================


def _last_month_period() -> str:
    """返回上个月的薪酬周期字符串。

    默认核算「上个月」是因为当月还没过完、数据不完整；
    这比让每个用户自己回想该填哪个月要省事。
    """
    today = timezone.localdate()
    return (today.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')


def _department_and_children(department) -> list:
    """取某个部门及其所有下级部门的 id 列表。

    只按单个部门过滤会漏掉下级部门的员工；组织树一旦有两层以上，
    漏掉的恰恰是人数最多的基层部门。这里按层向下遍历，直到没有子部门。
    """
    ids = [department.pk]
    frontier = [department.pk]
    while frontier:
        children = list(
            Department.objects.filter(parent_id__in=frontier).values_list('pk', flat=True)
        )
        ids.extend(children)
        frontier = children
    return ids


def _scoped_employees(department=None):
    """本次核算范围内的员工。

    排除「未配置薪酬级别」与「已离职」两类：
    前者算不出基本工资，后者不该再发工资。
    """
    queryset = (
        Employee.objects
        .filter(is_deleted=False, salary_level__isnull=False)
        .exclude(employ_status=Employee.EmployStatus.RESIGNED)
        .select_related('department', 'salary_level')
    )
    if department is not None:
        queryset = queryset.filter(department_id__in=_department_and_children(department))
    return queryset


class SoftDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """通用软删除（由列表页 POST 触发）。

    不做物理删除的原因是这些登记记录是工资的**数据来源**：
    真删掉以后历史工资就再也无法复现，审计时说不清楚。
    软删除后列表与核算查询都会把它排除，效果等同删除，但可以回退。
    """

    model = None
    success_url_name = None
    success_message = '记录已删除。'

    def post(self, request, pk):
        obj = get_object_or_404(self.model, pk=pk)
        obj.is_deleted = True
        obj.save(update_fields=['is_deleted'])
        messages.success(request, self.success_message)
        return redirect(self.success_url_name)


class FormPageMixin:
    """为新增 / 编辑表单页补齐统一的页面上下文。

    把这三个键抽出来的原因：五个模块的新增与编辑视图共 10 处都要传它们，
    任何一处写漏，模板就会渲染出一个没有标题、取消按钮指向错误页面的表单。
    """

    page_title = ''
    form_hint = ''
    cancel_url = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = self.page_title
        context['form_hint'] = self.form_hint
        context['cancel_url'] = self.cancel_url
        return context


# =============================================================================
# 一、薪酬体系配置（FR-SAL-01）
# =============================================================================


class SalaryLevelListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """薪酬级别列表（FR-SAL-01）。"""

    model = SalaryLevel
    template_name = 'salary/level_list.html'
    context_object_name = 'levels'
    paginate_by = 15
    permission_required = 'salary.view_salarylevel'

    def get_queryset(self):
        # 【聚合】用 annotate 把在岗人数算在查询集上，而不是在模板里查字典：
        # Django 模板不支持「以变量为键」的字典取值，写成 dict 就得配自定义过滤器，
        # 而一条 annotate 就能解决，且只发一次 SQL。
        # 末尾的 order_by('code') 不能省：annotate 会置起 GROUP BY，
        # Django 便不再采信 Meta.ordering，分页会报 UnorderedObjectListWarning。
        queryset = SalaryLevel.objects.annotate(
            employee_count=Count(
                'employees', filter=Q(employees__is_deleted=False)
            )
        ).order_by('code')

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(name__icontains=keyword) | Q(code__icontains=keyword)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filters'] = {'q': self.request.GET.get('q', '')}
        return context


class SalaryLevelCreateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, CreateView):
    """新增薪酬级别（FR-SAL-01）。"""

    model = SalaryLevel
    form_class = SalaryLevelForm
    template_name = 'salary/form.html'
    permission_required = 'salary.add_salarylevel'
    success_url = reverse_lazy('salarylevel-list')
    page_title = '新增薪酬级别'
    form_hint = '级别编码需唯一；基本工资是工资公式中的第一项。'
    cancel_url = 'salarylevel-list'

    def form_valid(self, form):
        messages.success(self.request, f'薪酬级别「{form.instance.name}」已建立。')
        return super().form_valid(form)


class SalaryLevelUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, UpdateView):
    """编辑薪酬级别（FR-SAL-01）。"""

    model = SalaryLevel
    form_class = SalaryLevelForm
    template_name = 'salary/form.html'
    permission_required = 'salary.change_salarylevel'
    success_url = reverse_lazy('salarylevel-list')
    form_hint = '调整基本工资只影响之后核算的工资，已生成的工资档案金额不变。'
    cancel_url = 'salarylevel-list'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑薪酬级别：{self.object.name}'
        return context

    def form_valid(self, form):
        messages.success(self.request, '薪酬级别已更新。')
        return super().form_valid(form)


class SalaryLevelDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """删除薪酬级别（FR-SAL-01）。"""

    model = SalaryLevel
    template_name = 'salary/confirm_delete.html'
    permission_required = 'salary.delete_salarylevel'
    success_url = reverse_lazy('salarylevel-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '删除薪酬级别'
        context['object_label'] = str(self.object)
        context['warning'] = '若仍有员工使用该级别，删除会被拒绝，请先把这些员工改到其它级别。'
        context['cancel_url'] = 'salarylevel-list'
        return context

    def form_valid(self, form):
        messages.success(self.request, '薪酬级别已删除。')
        return super().form_valid(form)


class SalaryStandardListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """薪酬标准列表（FR-SAL-01、FR-SYS-02）。"""

    model = SalaryStandard
    template_name = 'salary/standard_list.html'
    context_object_name = 'standards'
    paginate_by = 15
    permission_required = 'salary.view_salarystandard'

    def get_queryset(self):
        # 按生效日期倒序：最上面一条就是当前正在执行的标准
        return SalaryStandard.objects.order_by('-effective_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current'] = (
            SalaryStandard.objects.filter(is_active=True)
            .order_by('-effective_date')
            .first()
        )
        return context


class SalaryStandardCreateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, CreateView):
    """新增薪酬标准（FR-SAL-01）。"""

    model = SalaryStandard
    form_class = SalaryStandardForm
    template_name = 'salary/form.html'
    permission_required = 'salary.add_salarystandard'
    success_url = reverse_lazy('salarystandard-list')
    page_title = '新增薪酬标准'
    form_hint = (
        '标准按生效日期版本化：核算某月工资时取「生效日期不晚于该月」的最新一条。'
        '调整标准请新增一条，不要修改历史记录，否则过去月份的工资将无法复算。'
    )
    cancel_url = 'salarystandard-list'

    def form_valid(self, form):
        messages.success(self.request, f'{form.instance.effective_date} 起生效的标准已建立。')
        return super().form_valid(form)


class SalaryStandardUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, UpdateView):
    """编辑薪酬标准（FR-SAL-01）。"""

    model = SalaryStandard
    form_class = SalaryStandardForm
    template_name = 'salary/form.html'
    permission_required = 'salary.change_salarystandard'
    success_url = reverse_lazy('salarystandard-list')
    form_hint = '若该日期之后已有核算结果，修改标准不会自动重算，需到「工资核算」页重算。'
    cancel_url = 'salarystandard-list'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑标准：{self.object.effective_date} 起生效'
        return context

    def form_valid(self, form):
        messages.success(self.request, '薪酬标准已更新。')
        return super().form_valid(form)


class SalaryStandardDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """删除薪酬标准（FR-SAL-01）。"""

    model = SalaryStandard
    template_name = 'salary/confirm_delete.html'
    permission_required = 'salary.delete_salarystandard'
    success_url = reverse_lazy('salarystandard-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '删除薪酬标准'
        context['object_label'] = str(self.object)
        context['warning'] = '删除后该时段将回落到上一条标准；若这是唯一一条，工资核算会直接失败。'
        context['cancel_url'] = 'salarystandard-list'
        return context

    def form_valid(self, form):
        messages.success(self.request, '薪酬标准已删除。')
        return super().form_valid(form)


# =============================================================================
# 二、津贴与扣减项登记（FR-SAL-03、FR-SAL-02）
# =============================================================================


class OvertimeRecordListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """加班登记列表（FR-SAL-03）。"""

    model = OvertimeRecord
    template_name = 'salary/overtime_list.html'
    context_object_name = 'records'
    paginate_by = 20
    permission_required = 'salary.view_overtimerecord'

    def get_queryset(self):
        queryset = (
            OvertimeRecord.objects
            .filter(is_deleted=False)
            .select_related('employee', 'employee__department')
        )

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(employee__real_name__icontains=keyword)
                | Q(employee__employee_no__icontains=keyword)
            )

        period = self.request.GET.get('salary_period', '').strip()
        if period:
            queryset = queryset.filter(salary_period=period)

        overtime_type = self.request.GET.get('overtime_type', '').strip()
        if overtime_type:
            queryset = queryset.filter(overtime_type=overtime_type)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type_choices'] = OvertimeRecord.OvertimeType.choices
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'salary_period': self.request.GET.get('salary_period', ''),
            'overtime_type': self.request.GET.get('overtime_type', ''),
        }
        return context


class OvertimeRecordCreateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, CreateView):
    """加班登记（FR-SAL-03）。"""

    model = OvertimeRecord
    form_class = OvertimeRecordForm
    template_name = 'salary/form.html'
    permission_required = 'salary.add_overtimerecord'
    success_url = reverse_lazy('overtime-list')
    page_title = '加班登记'
    form_hint = '所属薪酬周期由加班日期自动推导；加班费 = 基本工资 ÷ 月标准工时 × 倍率 × 时长。'
    cancel_url = 'overtime-list'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(
            self.request,
            f'已登记「{form.instance.employee.real_name}」'
            f'{form.instance.overtime_date} 加班 {form.instance.hours} 小时。',
        )
        return super().form_valid(form)


class OvertimeRecordUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, UpdateView):
    """编辑加班登记（FR-SAL-03）。"""

    model = OvertimeRecord
    form_class = OvertimeRecordForm
    template_name = 'salary/form.html'
    permission_required = 'salary.change_overtimerecord'
    success_url = reverse_lazy('overtime-list')
    page_title = '编辑加班登记'
    form_hint = '修改后需到「工资核算」页重算该周期，否则工资档案仍是旧值。'
    cancel_url = 'overtime-list'

    def form_valid(self, form):
        messages.success(self.request, '加班记录已更新。')
        return super().form_valid(form)


class OvertimeRecordDeleteView(SoftDeleteView):
    """删除加班登记（软删除）。"""

    model = OvertimeRecord
    success_url_name = 'overtime-list'
    success_message = '加班记录已删除。'
    permission_required = 'salary.delete_overtimerecord'


class UtilityFeeRecordListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """水电费登记列表（FR-SAL-03）。"""

    model = UtilityFeeRecord
    template_name = 'salary/utility_list.html'
    context_object_name = 'records'
    paginate_by = 20
    permission_required = 'salary.view_utilityfeerecord'

    def get_queryset(self):
        queryset = (
            UtilityFeeRecord.objects
            .filter(is_deleted=False)
            .select_related('employee', 'employee__department')
        )

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(employee__real_name__icontains=keyword)
                | Q(employee__employee_no__icontains=keyword)
            )

        period = self.request.GET.get('salary_period', '').strip()
        if period:
            queryset = queryset.filter(salary_period=period)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'salary_period': self.request.GET.get('salary_period', ''),
        }
        return context


class UtilityFeeRecordCreateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, CreateView):
    """水电费登记（FR-SAL-03）。"""

    model = UtilityFeeRecord
    form_class = UtilityFeeRecordForm
    template_name = 'salary/form.html'
    permission_required = 'salary.add_utilityfeerecord'
    success_url = reverse_lazy('utilityfee-list')
    page_title = '水电费登记'
    form_hint = '同一员工同一周期只允许一条记录；重复登记请先编辑原记录。'
    cancel_url = 'utilityfee-list'

    def form_valid(self, form):
        messages.success(
            self.request,
            f'已登记「{form.instance.employee.real_name}」'
            f'{form.instance.salary_period} 水电费，合计扣款 {form.instance.total_fee} 元。',
        )
        return super().form_valid(form)


class UtilityFeeRecordUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, UpdateView):
    """编辑水电费登记（FR-SAL-03）。"""

    model = UtilityFeeRecord
    form_class = UtilityFeeRecordForm
    template_name = 'salary/form.html'
    permission_required = 'salary.change_utilityfeerecord'
    success_url = reverse_lazy('utilityfee-list')
    page_title = '编辑水电费登记'
    form_hint = '修改后需到「工资核算」页重算该周期，否则工资档案仍是旧值。'
    cancel_url = 'utilityfee-list'

    def form_valid(self, form):
        messages.success(self.request, '水电费记录已更新。')
        return super().form_valid(form)


class UtilityFeeRecordDeleteView(SoftDeleteView):
    """删除水电费登记（软删除）。"""

    model = UtilityFeeRecord
    success_url_name = 'utilityfee-list'
    success_message = '水电费记录已删除。'
    permission_required = 'salary.delete_utilityfeerecord'


class PieceworkRecordListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """计件 / 计时产量列表（FR-SAL-02）。"""

    model = PieceworkRecord
    template_name = 'salary/piecework_list.html'
    context_object_name = 'records'
    paginate_by = 20
    permission_required = 'salary.view_pieceworkrecord'

    def get_queryset(self):
        queryset = (
            PieceworkRecord.objects
            .filter(is_deleted=False)
            .select_related('employee', 'employee__department')
        )

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(employee__real_name__icontains=keyword)
                | Q(employee__employee_no__icontains=keyword)
                | Q(product_name__icontains=keyword)
            )

        period = self.request.GET.get('salary_period', '').strip()
        if period:
            queryset = queryset.filter(salary_period=period)

        work_mode = self.request.GET.get('work_mode', '').strip()
        if work_mode:
            queryset = queryset.filter(work_mode=work_mode)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mode_choices'] = PieceworkRecord.WorkMode.choices
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'salary_period': self.request.GET.get('salary_period', ''),
            'work_mode': self.request.GET.get('work_mode', ''),
        }
        return context


class PieceworkRecordCreateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, CreateView):
    """产量登记（FR-SAL-02）。"""

    model = PieceworkRecord
    form_class = PieceworkRecordForm
    template_name = 'salary/form.html'
    permission_required = 'salary.add_pieceworkrecord'
    success_url = reverse_lazy('piecework-list')
    page_title = '计件 / 计时产量登记'
    form_hint = '计件填「数量 / 单价」，计时填「工时 / 时薪」；小计由系统自动计算。'
    cancel_url = 'piecework-list'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(
            self.request,
            f'已登记「{form.instance.employee.real_name}」的产量，'
            f'小计 {form.instance.amount} 元。',
        )
        return super().form_valid(form)


class PieceworkRecordUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FormPageMixin, UpdateView):
    """编辑产量登记（FR-SAL-02）。"""

    model = PieceworkRecord
    form_class = PieceworkRecordForm
    template_name = 'salary/form.html'
    permission_required = 'salary.change_pieceworkrecord'
    success_url = reverse_lazy('piecework-list')
    page_title = '编辑产量登记'
    form_hint = '修改后需到「工资核算」页重算该周期，否则工资档案仍是旧值。'
    cancel_url = 'piecework-list'

    def form_valid(self, form):
        messages.success(self.request, '产量记录已更新。')
        return super().form_valid(form)


class PieceworkRecordDeleteView(SoftDeleteView):
    """删除产量记录（软删除）。"""

    model = PieceworkRecord
    success_url_name = 'piecework-list'
    success_message = '产量记录已删除。'
    permission_required = 'salary.delete_pieceworkrecord'


# =============================================================================
# 三、工资核算与发放（FR-SAL-02）
# =============================================================================


class SalaryRecordListView(LoginRequiredMixin, PermissionRequiredMixin, DataScopeMixin, ListView):
    """工资档案列表（FR-SAL-02）。

    同时是「历史薪酬查询」的入口。行级权限：普通职工只能看到自己的工资条。
    """

    model = SalaryRecord
    template_name = 'salary/record_list.html'
    context_object_name = 'records'
    paginate_by = 20
    permission_required = 'salary.view_salaryrecord'

    def get_queryset(self):
        queryset = self.scope_queryset(
            SalaryRecord.objects
            .filter(is_deleted=False)
            .select_related('employee', 'employee__department')
        )

        period = self.request.GET.get('salary_period', '').strip()
        if period:
            queryset = queryset.filter(salary_period=period)

        pay_status = self.request.GET.get('pay_status', '').strip()
        if pay_status:
            queryset = queryset.filter(pay_status=pay_status)

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(employee__real_name__icontains=keyword)
                | Q(employee__employee_no__icontains=keyword)
            )

        department = self.request.GET.get('department', '').strip()
        if department.isdigit():
            queryset = queryset.filter(employee__department_id=int(department))

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = SalaryRecord.PayStatus.choices
        context['departments'] = Department.objects.order_by('name')
        context['filters'] = {
            'salary_period': self.request.GET.get('salary_period', ''),
            'pay_status': self.request.GET.get('pay_status', ''),
            'q': self.request.GET.get('q', ''),
            'department': self.request.GET.get('department', ''),
        }

        # 【汇总】对当前筛选结果整体（而非分页后的一页）做聚合，
        # 供财务核对「本周期共多少人、合计多少钱」
        aggregate = self.get_queryset().aggregate(
            total_net=Sum('net_pay'), total_people=Count('id')
        )
        context['summary'] = {
            'total_net': aggregate['total_net'] or 0,
            'total_people': aggregate['total_people'] or 0,
            # 只有能看全员的角色（HR / 管理员）才给出发放按钮的显示依据
            'can_pay': getattr(self.request.user, 'can_view_all', False),
        }
        return context


class SalaryRecordDetailView(LoginRequiredMixin, PermissionRequiredMixin, DataScopeMixin, DetailView):
    """工资条明细（FR-SAL-02）。

    普通职工访问他人的工资条会直接 404（而不是 403）——
    用 404 是为了不泄露「这条记录存在」这一信息。
    """

    model = SalaryRecord
    template_name = 'salary/record_detail.html'
    context_object_name = 'record'
    permission_required = 'salary.view_salaryrecord'

    def get_queryset(self):
        return self.scope_queryset(
            SalaryRecord.objects.select_related(
                'employee', 'employee__department', 'employee__position',
                'employee__salary_level',
            )
        )


class SalaryCalculateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """工资核算页（FR-SAL-02）。

    同一个页面承担「首次核算」与「重算」两件事：
    核算逻辑本身是幂等的，重复执行只会覆盖待发放的记录，因此不需要两套入口。
    """

    permission_required = 'salary.add_salaryrecord'

    def _context(self, form):
        """构造页面上下文；表单校验失败时也要能正常渲染，故做了兜底。"""
        raw_period = str(form['salary_period'].value() or '')
        period = raw_period if _PERIOD_RE.match(raw_period) else _last_month_period()

        department = None
        raw_department = str(form['department'].value() or '')
        if raw_department.isdigit():
            department = Department.objects.filter(pk=int(raw_department)).first()

        return {
            'form': form,
            'page_title': '工资核算',
            'period': period,
            'standard': SalaryStandard.get_for_period(period),
            'preview_count': _scoped_employees(department).count(),
            'existing_count': SalaryRecord.objects.filter(
                salary_period=period, is_deleted=False
            ).count(),
        }

    def get(self, request):
        form = SalaryCalculateForm(initial={'salary_period': _last_month_period()})
        return render(request, 'salary/calculate.html', self._context(form))

    def post(self, request):
        form = SalaryCalculateForm(request.POST)
        if not form.is_valid():
            return render(request, 'salary/calculate.html', self._context(form))

        period = form.cleaned_data['salary_period']
        department = form.cleaned_data['department']
        employees = _scoped_employees(department).order_by('employee_no')

        try:
            stats, _standard, note = calculate_for_period(period, employees)
        except SalaryCalculationError as exc:
            # 前置条件不满足（例如没有可用标准）属于用户可自行修正的问题，
            # 用页面提示而非抛出 500
            messages.error(request, str(exc))
            return render(request, 'salary/calculate.html', self._context(form))

        message = (
            f'已核算 {period} 的工资：新增 {stats["created"]} 条、'
            f'更新 {stats["updated"]} 条'
        )
        if stats['skipped']:
            message += f'、跳过已发放 {stats["skipped"]} 条'
        message += '。'
        if note:
            message += f'（{note}）'
        messages.success(request, message)

        return redirect(f"{reverse('salaryrecord-list')}?salary_period={period}")


@login_required
@permission_required('salary.change_salaryrecord', raise_exception=True)
def salary_pay(request):
    """批量发放工资（FR-SAL-02）。

    只发放「待发放」的记录；提交了选中项则按选中发放，未选中则发放整个周期。
    """
    if request.method != 'POST':
        return redirect('salaryrecord-list')

    period = (request.POST.get('salary_period') or '').strip()
    selected = request.POST.getlist('record_ids')

    queryset = SalaryRecord.objects.filter(
        pay_status=SalaryRecord.PayStatus.DRAFT, is_deleted=False
    )
    if selected:
        queryset = queryset.filter(pk__in=selected)
    elif period:
        queryset = queryset.filter(salary_period=period)
    else:
        messages.error(request, '请先选择要发放的工资记录。')
        return redirect('salaryrecord-list')

    # 【事务】update() 编译为单条 UPDATE 语句，要么全部生效要么全部不变，
    # 无需再包 transaction.atomic()，比逐条 save() 更快也更不容易写出半截状态
    count = queryset.update(
        pay_status=SalaryRecord.PayStatus.PAID, paid_at=timezone.now()
    )

    if count:
        messages.success(
            request,
            f'已发放 {count} 条工资记录；这些记录金额已锁定，重算时会被自动跳过。',
        )
    else:
        messages.warning(request, '没有可发放的记录（选中的记录可能已经是「已发放」状态）。')

    if period:
        return redirect(f"{reverse('salaryrecord-list')}?salary_period={period}")
    return redirect('salaryrecord-list')


class MySalaryListView(LoginRequiredMixin, ListView):
    """我的工资（FR-SAL-02 历史薪酬查询的职工自助入口）。

    不加 PermissionRequiredMixin：任何登录用户都有权查看自己的工资条，
    而查询集已硬性限定为当前登录用户，不存在越权读取他人数据的可能。
    """

    model = SalaryRecord
    template_name = 'salary/my_salary.html'
    context_object_name = 'records'
    paginate_by = 12

    def get_queryset(self):
        return (
            SalaryRecord.objects
            .filter(employee=self.request.user, is_deleted=False)
            .order_by('-salary_period')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 累计已发到手金额：职工最想先看到的数字
        context['paid_total'] = sum(
            record.net_pay or 0
            for record in SalaryRecord.objects.filter(
                employee=self.request.user,
                is_deleted=False,
                pay_status=SalaryRecord.PayStatus.PAID,
            )
        )
        return context
