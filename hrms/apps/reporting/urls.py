"""
报表统计模块路由。

路由命名与数据库中的导航菜单 url_name 一一对应（FR-SYS-03），
修改路由名时必须同步更新菜单配置，否则侧边栏会退化为不可点击的「#」。

@author 王坤尧
"""

from django.urls import path

from . import views

urlpatterns = [
    # --- 结构统计（FR-RPT-01）---
    path('structure/', views.StructureReportView.as_view(), name='report-structure'),
    path('structure/data/', views.StructureDataView.as_view(), name='report-structure-data'),

    # --- 动态分析（FR-RPT-02）---
    path('trend/', views.TrendReportView.as_view(), name='report-trend'),
    path('trend/data/', views.TrendDataView.as_view(), name='report-trend-data'),

    # --- 人员流动统计（FR-RPT-03）---
    path('turnover/', views.TurnoverReportView.as_view(), name='report-turnover'),
    path('turnover/data/', views.TurnoverDataView.as_view(), name='report-turnover-data'),
]
