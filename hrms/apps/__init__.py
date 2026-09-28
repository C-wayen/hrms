"""
HRMS 业务应用包。

本包下按 SRS 第 4 章的模块划分组织 7 个 Django 应用：

    sysconf     模块 6 系统设置与安全   FR-SYS-01 ~ FR-SYS-03
    personnel   模块 1 人事管理         FR-PER-01 ~ FR-PER-04
    training    模块 2 培训管理         FR-TRN-01 ~ FR-TRN-02
    salary      模块 3 薪酬管理         FR-SAL-01 ~ FR-SAL-03
    pubquery    模块 4 公共查询         FR-QRY-01 ~ FR-QRY-02
    reporting   模块 5 报表统计         FR-RPT-01 ~ FR-RPT-03（纯聚合查询，无模型）
    assistant   加分项 智能应答机器人   FR-AI-01  ~ FR-AI-02

@author 王坤尧
"""
