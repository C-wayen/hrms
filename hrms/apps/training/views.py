"""
培训管理模块视图。

关联需求：FR-TRN-01 课程与方案管理、FR-TRN-02 专项培训

@author 王坤尧
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from .forms import CourseForm, TrainingPlanForm, TrainingRecordForm
from .models import Course, TrainingPlan, TrainingRecord


# =============================================================================
# 一、培训课程库（FR-TRN-01）
# =============================================================================


class CourseListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """培训课程列表（FR-TRN-01）。"""

    model = Course
    template_name = 'training/course_list.html'
    context_object_name = 'courses'
    paginate_by = 15
    permission_required = 'training.view_course'

    def get_queryset(self):
        queryset = Course.objects.all()

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(name__icontains=keyword)
                | Q(code__icontains=keyword)
                | Q(instructor__icontains=keyword)
            )

        course_type = self.request.GET.get('course_type', '').strip()
        if course_type:
            queryset = queryset.filter(course_type=course_type)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['type_choices'] = Course.CourseType.choices
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'course_type': self.request.GET.get('course_type', ''),
        }
        return context


class CourseCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """新增培训课程（FR-TRN-01）。"""

    model = Course
    form_class = CourseForm
    template_name = 'training/course_form.html'
    permission_required = 'training.add_course'
    success_url = reverse_lazy('course-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增培训课程'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'课程「{form.instance.name}」已建立。')
        return super().form_valid(form)


class CourseUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """编辑培训课程（FR-TRN-01）。"""

    model = Course
    form_class = CourseForm
    template_name = 'training/course_form.html'
    permission_required = 'training.change_course'
    success_url = reverse_lazy('course-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑课程：{self.object.name}'
        return context

    def form_valid(self, form):
        messages.success(self.request, '课程信息已更新。')
        return super().form_valid(form)


# =============================================================================
# 二、培训计划（FR-TRN-01）
# =============================================================================


class TrainingPlanListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """内部培训计划列表（FR-TRN-01）。"""

    model = TrainingPlan
    template_name = 'training/plan_list.html'
    context_object_name = 'plans'
    paginate_by = 15
    permission_required = 'training.view_trainingplan'

    def get_queryset(self):
        # select_related 规避模板访问 course/organizer 时的 N+1
        queryset = TrainingPlan.objects.select_related('course', 'organizer')

        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(status=status)

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(name__icontains=keyword) | Q(course__name__icontains=keyword)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = TrainingPlan.PlanStatus.choices
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'status': self.request.GET.get('status', ''),
        }
        return context


class TrainingPlanCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """制定培训计划（FR-TRN-01）。"""

    model = TrainingPlan
    form_class = TrainingPlanForm
    template_name = 'training/plan_form.html'
    permission_required = 'training.add_trainingplan'
    success_url = reverse_lazy('trainingplan-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '制定培训计划'
        return context

    def form_valid(self, form):
        # 负责人默认为当前用户，不强制选择
        if not form.instance.organizer_id:
            form.instance.organizer = self.request.user
        messages.success(self.request, f'培训计划「{form.instance.name}」已建立。')
        return super().form_valid(form)


class TrainingPlanUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """编辑培训计划（FR-TRN-01）。"""

    model = TrainingPlan
    form_class = TrainingPlanForm
    template_name = 'training/plan_form.html'
    permission_required = 'training.change_trainingplan'
    success_url = reverse_lazy('trainingplan-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑计划：{self.object.name}'
        return context

    def form_valid(self, form):
        messages.success(self.request, '培训计划已更新。')
        return super().form_valid(form)


# =============================================================================
# 三、培训记录与成绩（FR-TRN-02）
# =============================================================================


class TrainingRecordListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """培训记录与成绩列表（FR-TRN-02）。"""

    model = TrainingRecord
    template_name = 'training/record_list.html'
    context_object_name = 'records'
    paginate_by = 15
    permission_required = 'training.view_trainingrecord'

    def get_queryset(self):
        queryset = TrainingRecord.objects.select_related(
            'employee', 'employee__department', 'plan', 'plan__course'
        )

        keyword = self.request.GET.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(
                Q(employee__real_name__icontains=keyword)
                | Q(employee__employee_no__icontains=keyword)
                | Q(plan__name__icontains=keyword)
            )

        attend_status = self.request.GET.get('attend_status', '').strip()
        if attend_status:
            queryset = queryset.filter(attend_status=attend_status)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = TrainingRecord.AttendStatus.choices
        context['filters'] = {
            'q': self.request.GET.get('q', ''),
            'attend_status': self.request.GET.get('attend_status', ''),
        }
        return context


class TrainingRecordCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """登记培训记录与成绩（FR-TRN-02）。"""

    model = TrainingRecord
    form_class = TrainingRecordForm
    template_name = 'training/record_form.html'
    permission_required = 'training.add_trainingrecord'
    success_url = reverse_lazy('trainingrecord-list')

    def get_initial(self):
        initial = super().get_initial()
        # 从培训计划页点「登记成绩」跳过来时带上计划
        plan_id = self.request.GET.get('plan')
        if plan_id:
            initial['plan'] = plan_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '登记培训记录'
        return context

    def form_valid(self, form):
        messages.success(
            self.request,
            f'已登记「{form.instance.employee.real_name}」的培训记录。',
        )
        return super().form_valid(form)


class TrainingRecordUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """编辑培训记录与成绩（FR-TRN-02）。"""

    model = TrainingRecord
    form_class = TrainingRecordForm
    template_name = 'training/record_form.html'
    permission_required = 'training.change_trainingrecord'
    success_url = reverse_lazy('trainingrecord-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'编辑记录：{self.object.employee.real_name}'
        return context

    def form_valid(self, form):
        messages.success(self.request, '培训记录已更新。')
        return super().form_valid(form)
