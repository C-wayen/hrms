"""
报表统计模块的 Admin 配置。

本模块不含模型：所有报表均由其他模块的数据实时聚合而成
（通过 Django ORM 的 annotate/aggregate + JsonResponse 供 ECharts 渲染），
因此没有可注册的模型。

对应文档：HRMS/code_artifact.md（SRS V1.1）

@author 王坤尧
"""

# 本模块无需注册任何模型
