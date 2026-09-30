"""
公共查询模块视图。

关联需求：FR-QRY-01 多维检索、FR-QRY-02 通知套红与打印

@author 王坤尧
"""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, UpdateView

from apps.sysconf.models import Department, Employee, Position

from .forms import NotificationDocForm
from .models import NotificationDoc


def _years_ago(years: int) -> date:
    """返回 N 年前的今天，用于把「工龄 ≥ N 年」翻译成 hire_date 条件。

    2 月 29 日在平年不存在，此时退到 2 月 28 日，避免抛 ValueError。
    """
    today = timezone.localdate()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


# =============================================================================
# 一、多维检索（FR-QRY-01）
# =============================================================================


# 【权限】Employee 属于 sysconf，不是 personnel——写成 personnel.view_employee
# 是个不存在的权限码，会让 HR 这类非超级管理员一律被拒
@login_required
@permission_required('sysconf.view_employee', raise_exception=True)
def employee_search(request):
    """多维检索：按部门、职位、学历、工龄区间、状态复合查询（FR-QRY-01）。

    与「职工档案」列表页的分工：
        列表页  -> 日常浏览与维护，条件固定、追求点击少
        检索页  -> 临时分析，条件更全、附带结果统计（如各学历人数分布）
    """
    departments = Department.objects.filter(is_active=True).order_by('sort_order', 'code')
    positions = Position.objects.filter(is_active=True).order_by('code')

    filters = {
        'q': request.GET.get('q', '').strip(),
        'department': request.GET.get('department', '').strip(),
        'position': request.GET.get('position', '').strip(),
        'education': request.GET.get('education', '').strip(),
        'status': request.GET.get('status', '').strip(),
        'gender': request.GET.get('gender', '').strip(),
        'min_years': request.GET.get('min_years', '').strip(),
        'max_years': request.GET.get('max_years', '').strip(),
    }

    queryset = Employee.objects.filter(is_deleted=False).select_related(
        'department', 'position', 'salary_level'
    )
    searched = False

    # 只有用户提交过查询才执行筛选，避免初次进入就列全表
    if any(filters.values()):
        searched = True

        if filters['q']:
            queryset = queryset.filter(
                Q(employee_no__icontains=filters['q'])
                | Q(real_name__icontains=filters['q'])
                | Q(phone__icontains=filters['q'])
            )
        if filters['department']:
            queryset = queryset.filter(department_id=filters['department'])
        if filters['position']:
            queryset = queryset.filter(position_id=filters['position'])
        if filters['education']:
            queryset = queryset.filter(education=filters['education'])
        if filters['status']:
            queryset = queryset.filter(employ_status=filters['status'])
        if filters['gender']:
            queryset = queryset.filter(gender=filters['gender'])

        # 工龄换算成入职日期区间：工龄越大，入职日期越早
        if filters['min_years'].isdigit():
            queryset = queryset.filter(hire_date__lte=_years_ago(int(filters['min_years'])))
        if filters['max_years'].isdigit():
            queryset = queryset.filter(hire_date__gte=_years_ago(int(filters['max_years']) + 1))

        queryset = queryset.order_by('employee_no')

    # 结果统计：按学历与部门分组，供 HR 快速看出构成
    education_stats = []
    department_stats = []
    if searched:
        education_labels = dict(Employee.Education.choices)
        education_stats = [
            {'label': education_labels.get(row['education'], '未填写'), 'total': row['total']}
            for row in queryset.values('education').annotate(total=Count('id')).order_by('-total')
        ]
        department_stats = [
            {'label': row['department__name'] or '未分配', 'total': row['total']}
            for row in queryset.values('department__name').annotate(total=Count('id')).order_by('-total')
        ]

    return render(request, 'pubquery/employee_search.html', {
        'departments': departments,
        'positions': positions,
        'education_choices': Employee.Education.choices,
        'status_choices': Employee.EmployStatus.choices,
        'gender_choices': Employee.Gender.choices,
        'filters': filters,
        'results': queryset if searched else Employee.objects.none(),
        'searched': searched,
        'education_stats': education_stats,
        'department_stats': department_stats,
    })


# =============================================================================
# 二、人事变动通知单（FR-QRY-02）
# =============================================================================


def _suggest_doc_no(doc_type: str = 'transfer') -> str:
    """生成建议的通知单编号：类型前缀 + 日期 + 当日序号。

    仅作为表单默认值，用户可改；真正的唯一性由数据库约束保证。
    """
    prefixes = {'transfer': 'DD', 'regular': 'ZZ', 'reward': 'JC', 'resign': 'LZ'}
    today = timezone.localdate()
    base = f'{prefixes.get(doc_type, "TZ")}{today:%Y%m%d}'
    count = NotificationDoc.objects.filter(doc_no__startswith=base).count() + 1
    return f'{base}{count:03d}'


class NotificationDocListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """人事变动通知单列表（FR-QRY-02）。"""

    model = NotificationDoc
    template_name = 'pubquery/notification_list.html'
    context_object_name = 'docs'
    paginate_by = 15
    permission_required = 'pubquery.view_notificationdoc'

    def get_queryset(self):
        queryset = NotificationDoc.objects.select_related(
            'employee', 'employee__department', 'issuer'
        )

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(doc_no__icontains=keyword)
                | Q(title__icontains=keyword)
                | Q(employee__real_name__icontains=keyword)
            )

        doc_type = self.request.GET.get('doc_type', '').strip()
        if doc_type:
            queryset = queryset.filter(doc_type=doc_type)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type_choices'] = NotificationDoc.DocType.choices
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'doc_type': self.request.GET.get('doc_type', ''),
        }
        return context


class NotificationDocCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """生成人事变动通知单（FR-QRY-02）。"""

    model = NotificationDoc
    form_class = NotificationDocForm
    template_name = 'pubquery/notification_form.html'
    permission_required = 'pubquery.add_notificationdoc'
    success_url = reverse_lazy('notification-list')

    def get_initial(self):
        initial = super().get_initial()
        initial['issue_date'] = timezone.localdate()
        initial['doc_no'] = _suggest_doc_no()
        # 从调动记录跳转过来时带上关联，便于自动带出前后岗位信息
        transfer_id = self.request.GET.get('transfer')
        if transfer_id:
            initial['related_transfer'] = transfer_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '生成人事通知单'
        return context

    def form_valid(self, form):
        # 签发人默认记为当前用户，避免手选到别人
        if not form.instance.issuer_id:
            form.instance.issuer = self.request.user
        messages.success(self.request, f'通知单「{form.instance.doc_no}」已生成。')
        return super().form_valid(form)


class NotificationDocUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """编辑人事变动通知单（FR-QRY-02）。"""

    model = NotificationDoc
    form_class = NotificationDocForm
    template_name = 'pubquery/notification_form.html'
    permission_required = 'pubquery.change_notificationdoc'
    success_url = reverse_lazy('notification-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑通知单：{self.object.doc_no}'
        return context

    def form_valid(self, form):
        messages.success(self.request, '通知单已更新。')
        return super().form_valid(form)


@login_required
@permission_required('pubquery.view_notificationdoc', raise_exception=True)
def notification_print(request, pk):
    """通知单套红打印页（FR-QRY-02）。

    实现方式：**浏览器打印**而非服务端生成 PDF。
    理由：不引入 reportlab / weasyprint 这类依赖，答辩环境无需额外安装；
    且打印样式可控（@media print），用户可「打印到 PDF」或直接走打印机。
    """
    doc = get_object_or_404(
        NotificationDoc.objects.select_related(
            'employee', 'employee__department', 'employee__position',
            'issuer', 'related_transfer',
        ),
        pk=pk,
    )
    return render(request, 'pubquery/notification_print.html', {'doc': doc})
