"""
报表统计模块视图。

模块结构：
    一、结构统计      性别 / 年龄 / 学历 / 工龄            FR-RPT-01
    二、动态分析      人员流动趋势、离职率                 FR-RPT-02
    三、人员流动统计  在职总数 / 新增 / 辞职               FR-RPT-03

页面与数据接口分离：页面用模板渲染骨架（指标卡、筛选器、图表容器），
图表数据由 JsonResponse 接口异步提供。这样做而不是把数据直接塞进模板，原因：
    1. 切换年份 / 部门时只需重新取数，不必整页刷新；
    2. 同一份聚合结果可以被验证脚本直接调用，不必去解析 HTML。

聚合口径集中在 services.py，本文件只负责 HTTP 编排与权限把关。

@author 王坤尧
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView

from apps.sysconf.models import Department

from .services import (
    age_distribution,
    available_years,
    data_quality_notes,
    department_flow,
    education_distribution,
    flow_series,
    flow_summary,
    gender_distribution,
    recent_resignations,
    structure_overview,
    tenure_distribution,
)


# =============================================================================
# 通用：访问控制与参数解析
# =============================================================================


class ReportAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """报表访问控制。

    报表模块没有数据模型，因此**没有可用的 model permission**——
    Django 的权限是挂在模型的 CRUD 动作上的，没有模型就无从挂起。
    这里复用与行级权限同一套角色判定（Employee.can_view_all）：
    能看到全员数据的角色（系统管理员 / HR 专员）才看得到报表。
    """

    def test_func(self):
        return getattr(self.request.user, 'can_view_all', False)

    def handle_no_permission(self):
        """区分「没登录」与「登录了但权限不够」两种失败。

        未登录：交给 LoginRequiredMixin 重定向到登录页。
        已登录但无权限：直接 403，而不是把人踢去登录页——
        已登录用户看到登录页会以为「登录失效了」，白折腾一遍重新登录，
        然后又被踢回来。

        注意不能简单地写 raise_exception = True：那个属性被
        LoginRequiredMixin 与 UserPassesTestMixin 共用，一旦设上，
        连未登录的访客也会直接收到 403 页面，而不是被引导去登录。
        """
        if self.request.user.is_authenticated:
            raise PermissionDenied(self.get_permission_denied_message())
        return super().handle_no_permission()


def _selected_department(request):
    """解析 ?department= 参数。

    非法值（不存在的 id、非数字）一律当作「全部部门」而不是报错：
    筛选条件多半是用户手改 URL 得来的，没必要为此打断浏览。
    """
    raw = (request.GET.get('department') or '').strip()
    if raw.isdigit():
        return Department.objects.filter(pk=int(raw)).first()
    return None


def _selected_year(request, years):
    """解析 ?year= 参数，缺省或非法时取最新的一年。"""
    raw = (request.GET.get('year') or '').strip()
    if raw.isdigit() and int(raw) in years:
        return int(raw)
    return years[0]


# =============================================================================
# 一、结构统计（FR-RPT-01）
# =============================================================================


class StructureReportView(ReportAccessMixin, TemplateView):
    """结构统计页（FR-RPT-01）。

    指标卡由服务端渲染，4 张图表由接口异步填充——
    指标卡是首屏最该看到的东西，等 JS 回来再显示会白屏一下。
    """

    template_name = 'reporting/structure.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        department = _selected_department(self.request)
        context.update({
            'page_title': '结构统计',
            'departments': Department.objects.order_by('name'),
            'selected_department': department.pk if department else '',
            'department_name': department.name if department else '全公司',
            'overview': structure_overview(department),
        })
        return context


class StructureDataView(ReportAccessMixin, View):
    """结构统计数据接口（FR-RPT-01）。

    一次返回 4 组数据而不是拆成 4 个接口：页面加载时必然全都要，
    拆开就是 4 次往返，而它们的数据量都很小（各几十个数字）。
    """

    def get(self, request):
        department = _selected_department(request)
        return JsonResponse({
            'gender': gender_distribution(department),
            'age': age_distribution(department),
            'education': education_distribution(department),
            'tenure': tenure_distribution(department),
            'overview': structure_overview(department),
        })


# =============================================================================
# 二、动态分析（FR-RPT-02）
# =============================================================================


class TrendReportView(ReportAccessMixin, TemplateView):
    """动态分析页（FR-RPT-02）：人员流动与离职率的年度 / 季度趋势。"""

    template_name = 'reporting/trend.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        years = available_years()
        year = _selected_year(self.request, years)
        context.update({
            'page_title': '动态分析',
            'years': years,
            'selected_year': year,
            'summary': flow_summary(year),
            'notes': data_quality_notes(year),
        })
        return context


class TrendDataView(ReportAccessMixin, View):
    """动态分析数据接口（FR-RPT-02）。

    granularity 参数只接受 month / quarter 两个值，
    其余一律回落到 month——避免把非法值透传给聚合逻辑。
    """

    def get(self, request):
        years = available_years()
        year = _selected_year(request, years)
        granularity = request.GET.get('granularity', 'month')
        if granularity not in ('month', 'quarter'):
            granularity = 'month'
        return JsonResponse(flow_series(year, granularity))


# =============================================================================
# 三、人员流动统计（FR-RPT-03）
# =============================================================================


class TurnoverReportView(ReportAccessMixin, TemplateView):
    """人员流动统计页（FR-RPT-03）。

    对应课程清单的三项：在职人员总数统计、新增人员统计、辞职人员统计。
    与动态分析页的分工：本页回答「现在有多少人、这一年进出多少」，
    动态分析页回答「这个过程是怎么变化的」。
    """

    template_name = 'reporting/turnover.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        years = available_years()
        year = _selected_year(self.request, years)
        department = _selected_department(self.request)
        context.update({
            'page_title': '人员流动统计',
            'years': years,
            'selected_year': year,
            'departments': Department.objects.order_by('name'),
            'selected_department': department.pk if department else '',
            'department_name': department.name if department else '全公司',
            'summary': flow_summary(year, department),
            'resignations': recent_resignations(year),
            'notes': data_quality_notes(year),
        })
        return context


class TurnoverDataView(ReportAccessMixin, View):
    """人员流动统计数据接口（FR-RPT-03）：各部门进出对比。"""

    def get(self, request):
        years = available_years()
        year = _selected_year(request, years)
        return JsonResponse(department_flow(year))
