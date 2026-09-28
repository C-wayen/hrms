"""
人事管理模块视图。

关联需求：FR-PER-01 职工档案管理、FR-QRY-01 多维检索
对应用例：UC-01 职工查询

@author 王坤尧
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from apps.sysconf.models import Department, Employee
from apps.sysconf.scoping import DataScopeMixin

from .forms import (
    AttendanceForm,
    EmployeeForm,
    LeaveApproveForm,
    LeaveRequestForm,
    RegularizationApplyForm,
    RegularizationApproveForm,
    RewardPunishForm,
    SocialInsuranceForm,
)
from .models import (
    Attendance,
    LeaveRequest,
    RegularizationApply,
    RewardPunish,
    SocialInsurance,
)


class EmployeeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """职工档案列表（FR-PER-01）。

    同时承担 FR-QRY-01「多维检索」在档案上的落地：支持按关键字、
    部门、在职状态三个维度组合筛选。
    """

    model = Employee
    template_name = 'personnel/employee_list.html'
    context_object_name = 'employees'
    paginate_by = 15
    permission_required = 'personnel.view_employee'

    def get_queryset(self):
        # 软删除的档案不出现在列表；select_related 规避模板访问外键时的 N+1
        queryset = (
            Employee.objects
            .filter(is_deleted=False)
            .select_related('department', 'position', 'salary_level')
            .order_by('employee_no')
        )

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(employee_no__icontains=keyword)
                | Q(real_name__icontains=keyword)
                | Q(phone__icontains=keyword)
            )

        department = self.request.GET.get('department', '').strip()
        if department:
            queryset = queryset.filter(department_id=department)

        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(employ_status=status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['departments'] = (
            Department.objects.filter(is_active=True).order_by('sort_order', 'code')
        )
        context['status_choices'] = Employee.EmployStatus.choices
        # 回传当前筛选条件：一是让筛选表单保持状态，二是分页链接需要带上它们
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'department': self.request.GET.get('department', ''),
            'status': self.request.GET.get('status', ''),
        }
        context['total'] = self.get_queryset().count()
        return context


class EmployeeDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """职工档案详情（UC-01）。

    一并带出证书与调动历史，避免模板里逐个访问触发 N+1。
    """

    model = Employee
    template_name = 'personnel/employee_detail.html'
    context_object_name = 'employee'
    permission_required = 'personnel.view_employee'

    def get_queryset(self):
        return (
            Employee.objects
            .select_related('department', 'position', 'salary_level')
            .prefetch_related('certificates', 'transfer_records')
        )


class EmployeeCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """新增职工档案（FR-PER-01）。"""

    model = Employee
    form_class = EmployeeForm
    template_name = 'personnel/employee_form.html'
    permission_required = 'personnel.add_employee'
    success_url = reverse_lazy('employee-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增职工档案'
        return context

    def form_valid(self, form):
        # 新档案默认不可登录：账号开通与密码设置属于「用户管理」（FR-SYS-03），
        # 这样 HR 建档时不会顺手设出弱口令
        form.instance.set_unusable_password()
        messages.success(self.request, f'职工「{form.instance.real_name}」档案已建立。')
        return super().form_valid(form)


class EmployeeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """编辑职工档案（FR-PER-01）。

    权限：仅 HR 专员·经理与系统管理员可访问（FR-SYS-01）。
    """

    model = Employee
    form_class = EmployeeForm
    template_name = 'personnel/employee_form.html'
    permission_required = 'personnel.change_employee'
    success_url = reverse_lazy('employee-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑档案：{self.object.real_name}'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'职工「{form.instance.real_name}」档案已更新。')
        return super().form_valid(form)


class EmployeeDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """删除职工档案（软删除）。

    不物理删除：离职档案需要长期保留供工资、报表追溯（SRS 5.2 的软删除约定）。
    同时停用登录账号——档案留着，但不应再能登录系统。
    """

    permission_required = 'personnel.delete_employee'

    def post(self, request, pk):
        employee = get_object_or_404(Employee, pk=pk, is_deleted=False)
        employee.is_deleted = True
        employee.is_active = False
        employee.save(update_fields=['is_deleted', 'is_active'])
        messages.success(
            request,
            f'已删除职工「{employee.real_name}」的档案，其登录账号同时停用。',
        )
        return redirect('employee-list')


# =============================================================================
# 二、转正申请审批流（FR-PER-02）
# =============================================================================


class RegularizationListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """转正申请列表（FR-PER-02）。"""

    model = RegularizationApply
    template_name = 'personnel/regularization_list.html'
    context_object_name = 'applies'
    paginate_by = 15
    permission_required = 'personnel.view_regularizationapply'

    def get_queryset(self):
        # 不过滤 employee__is_deleted：已删除档案的申请仍需留档可查
        queryset = RegularizationApply.objects.select_related(
            'employee', 'employee__department', 'approver'
        )
        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = RegularizationApply.ApplyStatus.choices
        context['filters'] = {'status': self.request.GET.get('status', '')}
        # 待审批数量放在页头，HR 一眼能看到手头积压了多少
        context['pending_count'] = RegularizationApply.objects.filter(
            status=RegularizationApply.ApplyStatus.PENDING
        ).count()
        return context


class RegularizationCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """发起转正申请（FR-PER-02）。"""

    model = RegularizationApply
    form_class = RegularizationApplyForm
    template_name = 'personnel/regularization_form.html'
    permission_required = 'personnel.add_regularizationapply'
    success_url = reverse_lazy('regularization-list')

    def get_initial(self):
        initial = super().get_initial()
        # 默认申请日期为今天，减少手工输入
        initial['apply_date'] = timezone.localdate()
        # 从员工档案页点「发起转正」跳转过来时带上该员工
        employee_id = self.request.GET.get('employee')
        if employee_id:
            initial['employee'] = employee_id
        return initial

    def form_valid(self, form):
        messages.success(
            self.request,
            f'已为「{form.instance.employee.real_name}」提交转正申请，等待 HR 审批。',
        )
        return super().form_valid(form)


@login_required
@permission_required('personnel.change_regularizationapply', raise_exception=True)
def regularization_approve(request, pk):
    """审批转正申请（FR-PER-02）。

    通过时在**同一事务内**更新员工档案状态，原因：
    若「改申请状态」与「改员工状态」分两次提交，中途失败就会留下
    「申请已通过、员工仍是实习」的脏数据，报表统计也会跟着错。
    """
    apply_obj = get_object_or_404(
        RegularizationApply.objects.select_related('employee'), pk=pk
    )

    # 已处理的申请不允许再次审批，否则会重复改写员工状态
    if apply_obj.status != RegularizationApply.ApplyStatus.PENDING:
        messages.error(request, '该申请已被处理，不能重复审批。')
        return redirect('regularization-list')

    if request.method == 'POST':
        form = RegularizationApproveForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']

            with transaction.atomic():
                apply_obj.hr_opinion = form.cleaned_data['hr_opinion']
                apply_obj.approver = request.user
                apply_obj.approved_at = timezone.now()

                if action == 'approve':
                    apply_obj.status = RegularizationApply.ApplyStatus.APPROVED
                    employee = apply_obj.employee
                    employee.employ_status = Employee.EmployStatus.REGULAR
                    employee.regular_date = apply_obj.expect_regular_date
                    employee.probation_end_date = apply_obj.expect_regular_date
                    employee.save()
                    messages.success(
                        request,
                        f'已通过「{employee.real_name}」的转正申请，'
                        f'档案状态同步为「正式」，转正日期 {employee.regular_date}。',
                    )
                else:
                    apply_obj.status = RegularizationApply.ApplyStatus.REJECTED
                    messages.warning(
                        request,
                        f'已驳回「{apply_obj.employee.real_name}」的转正申请。',
                    )

                apply_obj.save()

            return redirect('regularization-list')
    else:
        form = RegularizationApproveForm(
            initial={'hr_opinion': apply_obj.hr_opinion}
        )

    return render(
        request,
        'personnel/regularization_approve.html',
        {'apply': apply_obj, 'form': form},
    )


# =============================================================================
# 三、社保管理（FR-PER-02）
# =============================================================================


class SocialInsuranceListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """社保缴纳记录列表（FR-PER-02）。"""

    model = SocialInsurance
    template_name = 'personnel/socialinsurance_list.html'
    context_object_name = 'records'
    paginate_by = 15
    permission_required = 'personnel.view_socialinsurance'

    def get_queryset(self):
        queryset = SocialInsurance.objects.select_related(
            'employee', 'employee__department'
        )

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(employee__real_name__icontains=keyword)
                | Q(employee__employee_no__icontains=keyword)
            )

        period = self.request.GET.get('period', '').strip()
        if period:
            queryset = queryset.filter(period=period)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'period': self.request.GET.get('period', ''),
        }
        # 已有周期列表，供筛选下拉直接选，不用手敲 YYYY-MM
        context['periods'] = (
            SocialInsurance.objects.values_list('period', flat=True)
            .distinct()
            .order_by('-period')
        )
        # 本页合计，方便财务核对
        records = self.get_queryset()
        context['total_personal'] = sum(r.personal_total for r in records)
        context['total_company'] = sum(r.company_total for r in records)
        return context


class SocialInsuranceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """新增社保缴纳记录（FR-PER-02）。"""

    model = SocialInsurance
    form_class = SocialInsuranceForm
    template_name = 'personnel/socialinsurance_form.html'
    permission_required = 'personnel.add_socialinsurance'
    success_url = reverse_lazy('socialinsurance-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增社保记录'
        return context

    def form_valid(self, form):
        # 合计由模型 save() 自动汇总，这里只提示
        messages.success(
            self.request,
            f'已为「{form.instance.employee.real_name}」登记 {form.instance.period} 的社保记录。',
        )
        return super().form_valid(form)


class SocialInsuranceUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """编辑社保缴纳记录（FR-PER-02）。"""

    model = SocialInsurance
    form_class = SocialInsuranceForm
    template_name = 'personnel/socialinsurance_form.html'
    permission_required = 'personnel.change_socialinsurance'
    success_url = reverse_lazy('socialinsurance-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑社保记录：{self.object.employee.real_name} {self.object.period}'
        return context

    def form_valid(self, form):
        messages.success(self.request, '社保记录已更新。')
        return super().form_valid(form)


class SocialInsuranceDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """删除社保缴纳记录。

    采用物理删除：社保记录不在 SRS 约定的软删除范围内（那是员工、
    工资、请假三类），录入错误时应当直接更正或删除。
    """

    permission_required = 'personnel.delete_socialinsurance'

    def post(self, request, pk):
        record = get_object_or_404(SocialInsurance, pk=pk)
        label = f'{record.employee.real_name} {record.period}'
        record.delete()
        messages.success(request, f'已删除社保记录：{label}')
        return redirect('socialinsurance-list')


# =============================================================================
# 四、考勤、请假与奖罚（FR-PER-03）
# =============================================================================


class AttendanceListView(LoginRequiredMixin, PermissionRequiredMixin, DataScopeMixin, ListView):
    """考勤记录列表（FR-PER-03）。"""

    model = Attendance
    template_name = 'personnel/attendance_list.html'
    context_object_name = 'attendances'
    paginate_by = 20
    permission_required = 'personnel.view_attendance'

    def get_queryset(self):
        queryset = self.scope_queryset(
            Attendance.objects.select_related('employee', 'employee__department')
        )

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(employee__real_name__icontains=keyword)
                | Q(employee__employee_no__icontains=keyword)
            )

        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(status=status)

        work_date = self.request.GET.get('work_date', '').strip()
        if work_date:
            queryset = queryset.filter(work_date=work_date)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Attendance.AttendanceStatus.choices
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'status': self.request.GET.get('status', ''),
            'work_date': self.request.GET.get('work_date', ''),
        }
        return context


class AttendanceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """新增考勤记录（FR-PER-03）。"""

    model = Attendance
    form_class = AttendanceForm
    template_name = 'personnel/attendance_form.html'
    permission_required = 'personnel.add_attendance'
    success_url = reverse_lazy('attendance-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增考勤记录'
        return context

    def form_valid(self, form):
        messages.success(self.request, '考勤记录已保存。')
        return super().form_valid(form)


class AttendanceUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """编辑考勤记录（FR-PER-03）。"""

    model = Attendance
    form_class = AttendanceForm
    template_name = 'personnel/attendance_form.html'
    permission_required = 'personnel.change_attendance'
    success_url = reverse_lazy('attendance-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑考勤：{self.object.employee.real_name} {self.object.work_date}'
        return context

    def form_valid(self, form):
        messages.success(self.request, '考勤记录已更新。')
        return super().form_valid(form)


class LeaveListView(LoginRequiredMixin, PermissionRequiredMixin, DataScopeMixin, ListView):
    """请假申请列表（FR-PER-03、UC-05）。

    HR / 管理员看到全部；普通职工只看得到自己的申请
    （因为也要兼作「我的请假」入口）。
    """

    model = LeaveRequest
    template_name = 'personnel/leave_list.html'
    context_object_name = 'leaves'
    paginate_by = 15
    permission_required = 'personnel.view_leaverequest'

    def get_queryset(self):
        queryset = self.scope_queryset(
            LeaveRequest.objects
            .filter(is_deleted=False)
            .select_related('employee', 'employee__department', 'approver')
        )

        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(status=status)

        leave_type = self.request.GET.get('leave_type', '').strip()
        if leave_type:
            queryset = queryset.filter(leave_type=leave_type)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = LeaveRequest.LeaveStatus.choices
        context['type_choices'] = LeaveRequest.LeaveType.choices
        context['filters'] = {
            'status': self.request.GET.get('status', ''),
            'leave_type': self.request.GET.get('leave_type', ''),
        }
        context['can_view_all'] = getattr(self.request.user, 'can_view_all', False)
        context['pending_count'] = self.scope_queryset(
            LeaveRequest.objects.filter(status=LeaveRequest.LeaveStatus.PENDING, is_deleted=False)
        ).count()
        return context


class LeaveCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """提交请假申请（FR-PER-03、UC-05）。"""

    model = LeaveRequest
    form_class = LeaveRequestForm
    template_name = 'personnel/leave_form.html'
    permission_required = 'personnel.add_leaverequest'
    success_url = reverse_lazy('leave-list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # 把当前用户传给表单，用于限制「普通职工只能给自己请假」
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        # 默认申请人就是自己，符合普通职工的使用习惯
        initial['employee'] = self.request.user.pk
        return initial

    def form_valid(self, form):
        messages.success(self.request, '请假申请已提交，等待审批。')
        return super().form_valid(form)


@login_required
@permission_required('personnel.change_leaverequest', raise_exception=True)
def leave_approve(request, pk):
    """请假审批（FR-PER-03、UC-05）。

    与转正审批的关键差异：**通过后还要写入考勤记录**，
    对应 SRS 6.4 活动图中的「写入考勤记录，联动薪酬计算」节点。
    两个动作在同一事务内完成，避免出现「请假已通过、考勤却没记录」。
    """
    leave = get_object_or_404(
        LeaveRequest.objects.select_related('employee'), pk=pk, is_deleted=False
    )

    if leave.status != LeaveRequest.LeaveStatus.PENDING:
        messages.error(request, '该申请已被处理，不能重复审批。')
        return redirect('leave-list')

    if request.method == 'POST':
        form = LeaveApproveForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']

            with transaction.atomic():
                leave.approve_opinion = form.cleaned_data['approve_opinion']
                leave.approver = request.user
                leave.approved_at = timezone.now()

                if action == 'approve':
                    leave.status = LeaveRequest.LeaveStatus.APPROVED

                    # 逐日写入考勤记录：请假区间内每天一条「请假」状态的考勤，
                    # 薪酬核算时据此扣除未出勤天数
                    current = leave.start_date
                    while current <= leave.end_date:
                        Attendance.objects.update_or_create(
                            employee=leave.employee,
                            work_date=current,
                            defaults={
                                'status': Attendance.AttendanceStatus.LEAVE,
                                'remark': f'请假：{leave.get_leave_type_display()}',
                            },
                        )
                        current += timedelta(days=1)

                    messages.success(
                        request,
                        f'已通过「{leave.employee.real_name}」的请假申请，'
                        f'考勤记录已同步（{leave.start_date} ~ {leave.end_date}）。',
                    )
                else:
                    leave.status = LeaveRequest.LeaveStatus.REJECTED
                    messages.warning(
                        request, f'已驳回「{leave.employee.real_name}」的请假申请。'
                    )

                leave.save()

            return redirect('leave-list')
    else:
        form = LeaveApproveForm()

    return render(
        request, 'personnel/leave_approve.html', {'leave': leave, 'form': form}
    )


class RewardPunishListView(LoginRequiredMixin, PermissionRequiredMixin, DataScopeMixin, ListView):
    """奖罚登记列表（FR-PER-03）。"""

    model = RewardPunish
    template_name = 'personnel/rewardpunish_list.html'
    context_object_name = 'records'
    paginate_by = 15
    permission_required = 'personnel.view_rewardpunish'

    def get_queryset(self):
        queryset = self.scope_queryset(
            RewardPunish.objects.select_related('employee', 'employee__department', 'operator')
        )
        record_type = self.request.GET.get('record_type', '').strip()
        if record_type:
            queryset = queryset.filter(record_type=record_type)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type_choices'] = RewardPunish.RecordType.choices
        context['filters'] = {'record_type': self.request.GET.get('record_type', '')}
        return context


class RewardPunishCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """新增奖罚记录（FR-PER-03）。"""

    model = RewardPunish
    form_class = RewardPunishForm
    template_name = 'personnel/rewardpunish_form.html'
    permission_required = 'personnel.add_rewardpunish'
    success_url = reverse_lazy('rewardpunish-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增奖罚记录'
        return context

    def form_valid(self, form):
        # 登记人自动记为当前用户，不让手工选择
        form.instance.operator = self.request.user
        messages.success(self.request, '奖罚记录已登记。')
        return super().form_valid(form)


class RewardPunishUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """编辑奖罚记录（FR-PER-03）。"""

    model = RewardPunish
    form_class = RewardPunishForm
    template_name = 'personnel/rewardpunish_form.html'
    permission_required = 'personnel.change_rewardpunish'
    success_url = reverse_lazy('rewardpunish-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑奖罚：{self.object.title}'
        return context

    def form_valid(self, form):
        messages.success(self.request, '奖罚记录已更新。')
        return super().form_valid(form)


# =============================================================================
# 五、员工关怀（FR-PER-04）
# =============================================================================


@login_required
@permission_required('personnel.view_employee', raise_exception=True)
def birthday_list(request):
    """员工关怀：生日提醒与统计（FR-PER-04）。

    设计说明：**不为生日建表**——它完全由 Employee.birth_date 派生。
    若单独存一份「生日提醒记录」，就得每天同步一次，反而容易与档案不一致。

    同时给出全年各月的生日人数分布，便于 HR 提前安排当月关怀活动。
    """
    today = timezone.localdate()
    week_end = today + timedelta(days=7)

    employees = (
        Employee.objects
        .filter(is_deleted=False, birth_date__isnull=False)
        .select_related('department', 'position')
    )

    # 本周生日：今天起 7 天内。跨月时拆成两个区间取并集，否则会漏掉下月的头几天
    if today.month == week_end.month:
        week_condition = Q(
            birth_date__month=today.month,
            birth_date__day__range=(today.day, week_end.day),
        )
    else:
        week_condition = (
            Q(birth_date__month=today.month, birth_date__day__gte=today.day)
            | Q(birth_date__month=week_end.month, birth_date__day__lte=week_end.day)
        )

    today_people = employees.filter(
        birth_date__month=today.month, birth_date__day=today.day
    )
    week_people = employees.filter(week_condition).order_by('birth_date__day')
    month_people = employees.filter(birth_date__month=today.month).order_by('birth_date__day')

    # 全年各月生日人数：按月份分组聚合，一次查询取全
    monthly_rows = (
        employees.values('birth_date__month')
        .annotate(total=Count('id'))
        .order_by('birth_date__month')
    )
    monthly_map = {row['birth_date__month']: row['total'] for row in monthly_rows}
    month_distribution = [
        {
            'month': month,
            'label': f'{month} 月',
            'total': monthly_map.get(month, 0),
            # 条形宽度百分比，模板里直接用，避免在模板中做除法
            'percent': 0,
        }
        for month in range(1, 13)
    ]
    peak = max([item['total'] for item in month_distribution] or [1]) or 1
    for item in month_distribution:
        item['percent'] = round(item['total'] / peak * 100)

    return render(request, 'personnel/birthday_list.html', {
        'today': today,
        'week_end': week_end,
        'today_people': today_people,
        'week_people': week_people,
        'month_people': month_people,
        'month_distribution': month_distribution,
    })

