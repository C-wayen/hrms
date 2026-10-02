# HRMS UML 建模清单（Visual Paradigm 绘制与导出用）

> 配套文档：`HRMS/code_artifact.md` 第 6 章（SRS V1.3）
> 图号规则：**图 6-1 ~ 图 6-15**，与 SRS 章节号绑定
> 建模工具：
>
> 代码语言：Python（Entity & Interface）
>
> 本文件是**画图时的对照清单**：每张图画什么、每个类有哪些属性、关系基数是多少、
> 有几个接口、图上的类对应哪张数据表。SRS 第 6 章另有同一套图的 Mermaid 草稿。

---

## 0. 先做这一步：验证导出链路 ⚠️

**课程硬要求是「用建模工具生成代码框架」，所以「能不能导出 Python」必须先验证，再画剩下的图。**
整个项目里只有这一环依赖外部工具的版本能力，一旦 CE 版不具备代码生成功能，越晚发现代价越大。

建议顺序：

1. 先只画**薪酬域的 3 个类**（`SalaryLevel`、`SalaryStandard`、`SalaryRecord`）做最小验证；
2. 立刻尝试导出 Python，确认能否成功、产物形态是否可用；
3. 通过后再补齐其余 21 个类与 14 张图。

若 CE 版的代码生成入口不可用（社区版与商业版在代码工程能力上存在差异），按顺序尝试：

- 在 VP 中查看是否有教育/试用授权可临时启用代码生成；
- 或改用同样支持 UML → Python 代码生成的工具（StarUML、Modelio、Papyrus）建模，**图纸风格保持与本文一致**，并在报告中说明所用工具；
- 最次方案：用 VP CE 正常建模并导出图片，Python 框架按 §9 的接口清单与 §3 的实体清单手工落成 `HRMS/uml/generated/`，报告中如实说明该目录为按模型转写的框架。

> 三条路都能满足「由模型生成代码框架」的实质要求，但**必须尽早选定**，不要等到验收前才发现。

---

## 1. 图总览（15 张）

| 图号 | 图种 | 图名 | 覆盖用例 | 覆盖 FR | VPP 图名 |
|---|---|---|---|---|---|
| 图 6-1 | 用例图 | 系统用例总图 | UC-01 ~ UC-13 | 全部 19 条 | `6-1 用例图` |
| 图 6-2 | 类图 | 核心域（组织机构与员工） | — | FR-SYS-01/02/03、FR-PER-01 | `6-2 类图-核心域` |
| 图 6-3 | 类图 | 人事域 | — | FR-PER-01/02/03 | `6-3 类图-人事域` |
| 图 6-4 | 类图 | 薪酬域 | — | FR-SAL-01/02/03 | `6-4 类图-薪酬域` |
| 图 6-5 | 类图 | 支撑域（培训 / 通知 / 智能助手） | — | FR-TRN-01/02、FR-QRY-02、FR-AI-01/02 | `6-5 类图-支撑域` |
| 图 6-6 | 包图 | 应用模块划分与依赖 | — | — | `6-6 包图` |
| 图 6-7 | 时序图 | 工资核算与发放（含事务回滚与发放锁定） | UC-02 | FR-SAL-01、FR-SAL-02 | `6-7 时序图-工资核算与发放` |
| 图 6-8 | 时序图 | 请假申请与审批（含跨模块写入考勤） | UC-05 | FR-PER-03 | `6-8 时序图-请假审批与考勤联动` |
| 图 6-9 | 时序图 | 职工档案查询与行级数据范围控制 | UC-01 | FR-PER-01、FR-QRY-01 | `6-9 时序图-档案查询与行级权限` |
| 图 6-10 | 活动图 | 请假申请与审批流程 | UC-05 | FR-PER-03 | `6-10 活动图-请假审批` |
| 图 6-11 | 活动图 | 转正申请与审批流程 | UC-06 | FR-PER-02 | `6-11 活动图-转正审批` |
| 图 6-12 | 活动图 | 智能问答三级降级判定 | UC-04 | FR-AI-01、FR-AI-02 | `6-12 活动图-智能问答降级` |
| 图 6-13 | 状态图 | 员工在职状态 | UC-06、UC-07 | FR-PER-02 | `6-13 状态图-员工在职状态` |
| 图 6-14 | 状态图 | 工资档案发放状态 | UC-02 | FR-SAL-02 | `6-14 状态图-工资发放状态` |
| 图 6-15 | 部署图 | 网络版部署结构 | — | 约束 C-02（网络版非单机） | `6-15 部署图` |

**为什么是 15 张而不是课程要求的 4 张**：课程的「四个图」是最低要求（覆盖四种图种），
不是上限。本项目用「同类多场景 + 补部署图与状态图」的方式，
让每张图各讲一个不同的技术点（事务 / 跨模块 / 权限 / 降级 / 状态机 / 部署），
避免四张图全是 CRUD。

---

## 2. 图 6-1 用例图

### 参与者（3 个）

| 参与者 | 说明 |
|---|---|
| 系统管理员 | 全部权限，含系统设置与用户管理 |
| HR 专员 / 经理 | 人事、薪酬、培训、报表的操作权限；系统设置只读 |
| 普通职工 | 自助：查本人档案与工资、提交请假、智能问答 |

### 用例（13 个，UC-01 ~ UC-13）

| 用例编号 | 用例名称 | 参与者 | 对应 FR |
|---|---|---|---|
| UC-01 | 职工档案查询与检索 | 普通职工（限本人）、HR、管理员 | FR-PER-01、FR-QRY-01 |
| UC-02 | 薪酬体系配置与工资核算发放 | HR、管理员 | FR-SAL-01、FR-SAL-02 |
| UC-03 | 系统权限配置 | 管理员 | FR-SYS-01 |
| UC-04 | AI 机器人问答 | 全部角色 | FR-AI-01、FR-AI-02 |
| UC-05 | 考勤、请假与奖罚管理 | 普通职工（发起）、HR、管理员 | FR-PER-03 |
| UC-06 | 转正申请与审批 | 普通职工（申请）、HR、管理员 | FR-PER-02 |
| UC-07 | 社保缴纳记录维护 | HR、管理员 | FR-PER-02 |
| UC-08 | 培训计划与成绩登记 | HR、管理员 | FR-TRN-01、FR-TRN-02 |
| UC-09 | 加班与水电费登记 | HR、管理员 | FR-SAL-03 |
| UC-10 | 人事变动通知单打印 | HR、管理员 | FR-QRY-02 |
| UC-11 | 报表统计分析 | HR、管理员 | FR-RPT-01、FR-RPT-02、FR-RPT-03 |
| UC-12 | 用户、菜单与基础数据管理 | 管理员 | FR-SYS-02、FR-SYS-03 |
| UC-13 | 员工生日关怀 | HR、管理员 | FR-PER-04 |

> UC-01 ~ UC-05 沿用原编号与语义（仅 UC-01、UC-02、UC-05 的名称做了扩展），
> UC-06 ~ UC-13 为新增。**这样代码里已有的 44 处 `UC-0x` 注释无需改动。**

### 关系

- 三个参与者与各自用例之间用**关联**（直线）；
- 可选：在图上标出「普通职工」与「HR 专员」对 UC-01 的**泛化**（HR 是职工的特化），
  以及 UC-01 被 UC-09、UC-11 **包含**（`<<include>>`）——如时间紧可省略，不影响完整性。

---

## 3. 图 6-2 ~ 图 6-5 类图（24 个类）

### 通用约定

- 类名、属性名、方法名**一律英文，与 `hrms/apps/*/models.py` 逐字一致**（中文只作为说明）；
- 每个类保留 **5 ~ 8 个关键属性**（主键、业务标识、状态、关键金额/日期），不列 `created_at` 等审计字段；
- 跨包关联用**引用类**表示（只画类名、不展开属性），避免每张图蔓延成全网。

### 图 6-2 核心域 —— `apps.sysconf`（5 类）

| 类名 | 关键属性 | 关键方法 |
|---|---|---|
| `Department` | `code`、`name`、`parent`、`leader`、`sort_order`、`is_active` | `get_full_path()` |
| `Position` | `code`、`name`、`level`、`is_active` | — |
| `DataDict` | `dict_type`、`dict_key`、`dict_value`、`sort_order`、`is_active` | — |
| `Menu` | `title`、`url_name`、`icon`、`sort_order`、`is_active` | — |
| `Employee` | `employee_no`、`real_name`、`gender`、`birth_date`、`education`、`employ_status`、`hire_date`、`resign_date` | `can_view_all()`、`age`、`service_years` |

**关系**

| 关系 | 基数 | 说明 |
|---|---|---|
| `Employee` — `Department` | `*` → `1` | 员工所属部门（`related_name='employees'`） |
| `Employee` — `Position` | `*` → `0..1` | 员工岗位 |
| `Employee` — `Group`（Django 内置） | `*` → `*` | 角色，经 `sysconf_employee_groups` 关联表 |
| `Department` — `Department` | `1` → `0..*` | 自关联树（`parent` / `children`） |
| `Department` — `Employee` | `1` → `0..1` | 部门负责人（`leader`） |
| `Menu` — `Menu` | `1` → `0..*` | 菜单树（`parent` / `children`） |
| `Menu` — `Group` | `*` → `*` | 可见角色，经 `sysconf_menu_visible_roles` |

> `Employee` 继承 Django 的 `AbstractUser`，图上用**泛化**箭头指向 `AbstractUser`
> （可放在核心域图的右上角，标 `<<external>>`）。`Group`、`Permission` 同理。

### 图 6-3 人事域 —— `apps.personnel`（7 类）

| 类名 | 关键属性 | 关键方法 |
|---|---|---|
| `TransferRecord` | `transfer_type`、`effective_date`、`reason`、`before_department`、`after_department`、`doc_no` | — |
| `Certificate` | `name`、`category`、`cert_no`、`issuing_authority`、`issue_date`、`expire_date` | — |
| `SocialInsurance` | `period`、`insurance_base`、`pension_personal`、`personal_total`、`company_total` | — |
| `RegularizationApply` | `apply_date`、`original_status`、`expect_regular_date`、`status`、`approver`、`approved_at` | `approve()` |
| `Attendance` | `work_date`、`status`、`check_in`、`check_out`、`work_hours` | — |
| `LeaveRequest` | `leave_type`、`start_date`、`end_date`、`days`、`status`、`approver` | — |
| `RewardPunish` | `record_type`、`happen_date`、`title`、`amount`、`description` | — |

**关系**：7 个类均以 `Employee` 为一端，基数为 `*` → `1`（引用类 `Employee` 只画类名）。
其中 `TransferRecord` 另有 4 条指向 `Department` / `Position` 的 `*` → `0..1`（原部门、新部门、原岗位、新岗位）。

> `SocialInsurance.personal_total` 是工资公式中「社保自负部分」的数据来源（Q1 口径），
> 建议在该属性旁加注 `{from FR-SAL-02}`；`RewardPunish.amount` 同理（奖罚净额的来源）。

### 图 6-4 薪酬域 —— `apps.salary`（6 类）

| 类名 | 关键属性 | 关键方法 |
|---|---|---|
| `SalaryLevel` | `code`、`name`、`base_salary`、`post_allowance`、`is_active` | — |
| `SalaryStandard` | `effective_date`、`overtime_workday_rate`、`monthly_work_hours`、`water_price`、`electricity_price`、`social_insurance_ratio` | `get_for_period(period)` |
| `OvertimeRecord` | `overtime_date`、`overtime_type`、`hours`、`reason`、`salary_period` | — |
| `UtilityFeeRecord` | `salary_period`、`water_usage`、`water_fee`、`electricity_usage`、`electricity_fee`、`total_fee` | — |
| `PieceworkRecord` | `salary_period`、`work_date`、`work_mode`、`quantity`、`unit_price`、`hours`、`hourly_rate`、`amount` | — |
| `SalaryRecord` | `salary_period`、`base_salary`、`piecework_amount`、`overtime_amount`、`reward_punish_amount`、`utility_deduction`、`social_deduction`、`net_pay`、`pay_status` | `calculate_net_pay()`、`aggregate_reward_punish()` |

**关系**：`Employee` `1` → `0..*` 四类登记记录（`OvertimeRecord` / `UtilityFeeRecord` / `PieceworkRecord` / `SalaryRecord`）；
`Employee` `*` → `0..1` `SalaryLevel`（跨包引用核心域）。

> `SalaryRecord` 是**核算结果的快照**：各金额字段在核算时一次算好落库，不随标准调整而变动。
> 建议在图上该类的注释框里写明这条，它是这张图最容易被追问的设计点。

### 图 6-5 支撑域（6 类）

| 类名 | 所属 app | 关键属性 | 关键方法 |
|---|---|---|---|
| `Course` | training | `code`、`name`、`course_type`、`instructor`、`duration_hours`、`is_active` | — |
| `TrainingPlan` | training | `name`、`start_date`、`end_date`、`location`、`planned_headcount`、`status` | — |
| `TrainingRecord` | training | `attend_status`、`score`、`certificate_no` | — |
| `NotificationDoc` | pubquery | `doc_no`、`doc_type`、`title`、`content`、`issue_date`、`issuer` | — |
| `FaqItem` | assistant | `question`、`answer`、`keywords`、`category`、`hit_count`、`is_active` | `keyword_list()` |
| `ChatLog` | assistant | `question`、`answer`、`source`、`elapsed_ms` | — |

**关系**：`Course` `1` → `0..*` `TrainingPlan`；`TrainingPlan` `1` → `0..*` `TrainingRecord`；
`Employee` `1` → `0..*` `TrainingRecord` / `NotificationDoc` / `ChatLog`；
`TrainingPlan` `*` → `*` `Department`（面向部门，经 `training_trainingplan_target_departments`）；
`ChatLog` `*` → `0..1` `FaqItem`（命中的知识条目）。

> **课程与计划必须分表**：课程是可复用的知识资产，计划是一次办班活动，
> 成绩挂在计划上才能区分「同一门课不同期」。这条要写进图的说明。

---

## 4. 图 6-6 包图

用**包图**（或带包符号的类图）表达模块划分与依赖方向：

| 包（app） | 职责 | 依赖 |
|---|---|---|
| `apps.sysconf` | 组织机构、岗位、数据字典、菜单、员工（含权限判定） | 不依赖其他业务包 |
| `apps.personnel` | 调动、证书、社保、转正、考勤、请假、奖罚 | → `sysconf` |
| `apps.salary` | 薪酬级别与标准、加班/水电/计件登记、工资档案 | → `sysconf`、`personnel` |
| `apps.training` | 课程、培训计划、成绩 | → `sysconf` |
| `apps.pubquery` | 通知单 | → `sysconf`、`personnel` |
| `apps.reporting` | 报表聚合（**无模型**，纯服务层） | → `sysconf`、`personnel`、`salary` |
| `apps.assistant` | FAQ 与问答记录、应答服务 | → `sysconf`、`personnel`、`salary` |

依赖箭头统一指向 `sysconf`（其他包都依赖核心域）。建议在图上用一句注释标出
**`apps.reporting` 没有自己的表**——它是唯一无模型的 app，这解释了为什么类图里没有 reporting 的类。

---

## 5. 图 6-7 ~ 图 6-9 时序图

**参与者一律用真实类名**，不使用「前端 / 服务 / 数据库」这类泛化角色，这样与类图对得上。

### 图 6-7 工资核算与发放（UC-02）

| 生命线 | 说明 |
|---|---|
| `:HR 专员` | 参与者 |
| `SalaryCalculateView` | 核算页视图 |
| `SalaryStandard` | 取适用标准 |
| `SalaryCalculationService` | 核算服务（`apps/salary/services.py`） |
| `RewardPunish` / `Attendance` / `SocialInsurance` | 跨模块取数（引用类） |
| `SalaryRecord` | 工资档案实体 |
| `MySQL 8.0` | 数据库 |

主流程：提交周期 → `get_for_period()` → 逐员工 `build_salary_record()` → `calculate_net_pay()` → 事务写入。

必须画的两个 `alt` 分支（这是本系统真实实现的规则，图上有、代码里有）：

- `alt` **事务回滚**：任一条写入失败则整批回滚，不产生半截工资记录；
- `alt` **已发放锁定**：`pay_status == paid` 的记录跳过重算，金额不变。

随后是批量发放：`SalaryRecord.pay_status` 由 `draft` 更新为 `paid` 并写入 `paid_at`。
建议在图上标一句「核算幂等：同一员工同一周期只更新不新增」。

### 图 6-8 请假申请与审批（UC-05）

| 生命线 | 说明 |
|---|---|
| `:普通职工` / `:HR 专员` | 参与者 |
| `LeaveCreateView` | 提交申请 |
| `LeaveRequestForm` | 服务端校验 |
| `LeaveRequest` | 请假实体 |
| `leave_approve()` | 审批视图 |
| `Attendance` | 考勤实体 |
| `MySQL 8.0` | 数据库 |

关键点：审批通过后**在同一事务内**按日循环 `Attendance.update_or_create()` 写入考勤。
图上务必画出这个「一次审批 → 多条考勤」的一对多写入，并标注 `transaction.atomic()`
——这是本系统唯一带跨模块写操作的流程，也是这张图的价值所在。

### 图 6-9 职工档案查询与行级数据范围控制（UC-01）

| 生命线 | 说明 |
|---|---|
| `:HR 专员` / `:普通职工` | 参与者 |
| `EmployeeListView` | 档案列表视图 |
| `PermissionRequiredMixin` | 模型级权限校验（`sysconf.view_employee`） |
| `DataScopeMixin` | 行级数据范围（`apps/sysconf/scoping.py`） |
| `Employee.can_view_all()` | 角色判定 |
| `MySQL 8.0` | 数据库 |

用 `alt` 画两条路径：能看全员 → 不加过滤；否则 → `filter(employee=当前登录用户)`。
在图上加一句注释：「他人工资条返回 404 而非 403，避免泄露记录是否存在」。

---

## 6. 图 6-10 ~ 图 6-12 活动图

### 图 6-10 请假申请与审批（UC-05）
与图 6-8 互补：时序图看**调用链**，活动图看**审批分支**。
节点：填写表单 → 校验（否 → 返回修改）→ 提交（待审批）→ 审批意见分叉（驳回 / 通过）→ 通过则写入考勤 → 通知 → 结束。

### 图 6-11 转正申请与审批（UC-06）
节点：发起申请 → 记录申请时状态（实习 / 试用）→ 部门意见 → HR 审批 →（通过）系统自动将
`Employee.employ_status` 置为「正式」并写入 `regular_date` → 通知。
**必须画出「审批通过后自动改档案状态」这一步**，它说明转正结果不需要人工二次修改。

### 图 6-12 智能问答三级降级判定（UC-04）
这是判定分支最密集的一张图，按实现的判定顺序画：

```
接收提问
  ├─ 含他人姓名？ ──是──▶ 拒绝（只能查本人）
  └─否─▶ 含「个人信号」词（我/本人/还剩/余额…）？
            ├─是─▶ 意图识别命中？ ──是──▶ 查询本人数据（数据模板）
            └─否─▶ 进入 FAQ 匹配
                      ├─命中─▶ 返回制度答案（规则库）
                      └─未命中─▶ 云 API 可用？
                                    ├─可用─▶ 调用 DeepSeek 返回
                                    └─不可用/超时─▶ 离线兜底 + 追问建议
```

建议在图上标注：**「个人数据一律查库回答，不经过大模型」**——这是本模块最重要的设计取舍。

---

## 7. 图 6-13 ~ 图 6-14 状态图

### 图 6-13 员工在职状态（UC-06、UC-07）

| 状态 | 取值 | 进入条件 |
|---|---|---|
| 实习 | `intern` | 入职登记 |
| 试用 | `probation` | 转试用 |
| 正式 | `regular` | **转正审批通过**（自动写入） |
| 离职 | `resigned` | 办理离职，填写 `resign_date` |

转移上标注触发事件。建议在图上注明离职状态的两处联动：
① 离职后不再参与工资核算（`exclude(employ_status=RESIGNED)`）；
② 报表按 `resign_date` 统计离职趋势，而**不是**按 `is_deleted`——
因为 `is_deleted` 同时覆盖「误录入作废」，两者语义不同。

### 图 6-14 工资档案发放状态（UC-02）

| 状态 | 取值 | 说明 |
|---|---|---|
| 待发放 | `draft` | 可重算；重算为**更新**而非新增（幂等） |
| 已发放 | `paid` | 金额锁定，重算时跳过 |

转移：`draft --发放（写 paid_at）--> paid`；`draft --重算--> draft`（自环，标注「原地更新」）。
建议加注：「已发放不参与任何重算」——工资条是财务凭证。

---

## 8. 图 6-15 部署图

三节点（对应课程「不能做成单机版，须为网络版」的硬约束）：

| 节点 | 构造型 | 部署内容 | 说明 |
|---|---|---|---|
| 客户端 | `«device»` | 浏览器（Chrome / Edge） | 无需安装客户端，B/S 架构 |
| 应用服务器 | `«execution environment»` | Django 5.2 LTS + **WSGI 容器** → 业务逻辑层 / 数据访问层 | 开发期以 `runserver` 承载 WSGI 角色 |
| 数据库服务器 | `«device»` | MySQL 8.0（InnoDB、utf8mb4） | **独立部署**，可被多个应用实例并发访问 |

连接关系标注协议：客户端 → 应用服务器为 **HTTP/HTTPS**；应用服务器 → 数据库为 **TCP 3306**。

建议在图中加一条注释：「生产环境可将 WSGI 容器替换为 gunicorn 并前置 Nginx；
本图描述的是本系统的实际运行形态，数据库与应用进程分离，满足网络版要求。」

---

## 9. Interface 清单（4 个，`<<interface>>`）

课程要求导出的是 **Entity & Interface**。Entity 即 §3 的 24 个类；
Interface 从现有服务层抽取，与代码一一对应：

### `ISalaryService` ← `apps/salary/services.py`

| 方法 | 签名 |
|---|---|
| `calculate_for_period` | `(salary_period: str, employees=None) -> tuple` |
| `build_salary_record` | `(employee, salary_period: str, standard) -> SalaryRecord` |
| `calculate_overtime_amount` | `(records, base_salary, standard) -> Decimal` |
| `resolve_social_deduction` | `(employee, salary_period: str, base_salary, standard) -> tuple` |
| `attendance_summary` | `(employee, salary_period: str) -> str` |

### `IReportService` ← `apps/reporting/services.py`

| 方法 | 签名 |
|---|---|
| `gender_distribution` | `(department=None) -> list` |
| `age_distribution` | `(department=None) -> list` |
| `education_distribution` | `(department=None) -> list` |
| `tenure_distribution` | `(department=None) -> list` |
| `headcount_at` | `(day: date, department=None) -> int` |
| `flow_series` | `(year: int, granularity: str = 'month') -> dict` |
| `flow_summary` | `(year: int, department=None) -> dict` |
| `department_flow` | `(year: int) -> dict` |

### `IAssistantService` ← `apps/assistant/services.py`

| 方法 | 签名 |
|---|---|
| `answer_question` | `(employee, question: str, allow_cloud: bool = None) -> Answer` |
| `match_intent` | `(question: str) -> Intent | None` |
| `match_faq` | `(question: str) -> tuple` |
| `ask_cloud` | `(question: str) -> str | None` |
| `annual_leave_quota` | `(employee, year: int = None) -> int` |
| `annual_leave_used` | `(employee, year: int = None) -> Decimal` |

### `IAuthService` ← `apps/sysconf/scoping.py`

| 方法 | 签名 |
|---|---|
| `can_view_all` | `(employee) -> bool` |
| `scope_queryset` | `(queryset, user) -> QuerySet` |
| `department_and_children_ids` | `(department) -> list` |

> 在类图上，让 `SalaryCalculationService` 等服务类**实现**对应接口（虚线空心三角箭头），
> 接口与实现类放在同一张图或包图的相邻位置。

---

## 10. 类图 ↔ `models.py` ↔ 数据表 对照表

数据库现有 **35 张表** = 业务实体表 24 张 + 多对多关联表 4 张（合计 **28 张业务表**，
与 SRS 5.2 的口径一致）+ Django 框架内置表 7 张（`auth_*` / `django_*`，不纳入类图）。

| 类图（图 6-x） | 类名 | 源文件 | 数据表 |
|---|---|---|---|
| 6-2 | `Department` | `apps/sysconf/models.py` | `sysconf_department` |
| 6-2 | `Position` | `apps/sysconf/models.py` | `sysconf_position` |
| 6-2 | `DataDict` | `apps/sysconf/models.py` | `sysconf_datadict` |
| 6-2 | `Menu` | `apps/sysconf/models.py` | `sysconf_menu` |
| 6-2 | `Employee` | `apps/sysconf/models.py` | `sysconf_employee` |
| 6-3 | `TransferRecord` | `apps/personnel/models.py` | `personnel_transferrecord` |
| 6-3 | `Certificate` | `apps/personnel/models.py` | `personnel_certificate` |
| 6-3 | `SocialInsurance` | `apps/personnel/models.py` | `personnel_socialinsurance` |
| 6-3 | `RegularizationApply` | `apps/personnel/models.py` | `personnel_regularizationapply` |
| 6-3 | `Attendance` | `apps/personnel/models.py` | `personnel_attendance` |
| 6-3 | `LeaveRequest` | `apps/personnel/models.py` | `personnel_leaverequest` |
| 6-3 | `RewardPunish` | `apps/personnel/models.py` | `personnel_rewardpunish` |
| 6-4 | `SalaryLevel` | `apps/salary/models.py` | `salary_salarylevel` |
| 6-4 | `SalaryStandard` | `apps/salary/models.py` | `salary_salarystandard` |
| 6-4 | `OvertimeRecord` | `apps/salary/models.py` | `salary_overtimerecord` |
| 6-4 | `UtilityFeeRecord` | `apps/salary/models.py` | `salary_utilityfeerecord` |
| 6-4 | `PieceworkRecord` | `apps/salary/models.py` | `salary_pieceworkrecord` |
| 6-4 | `SalaryRecord` | `apps/salary/models.py` | `salary_salaryrecord` |
| 6-5 | `Course` | `apps/training/models.py` | `training_course` |
| 6-5 | `TrainingPlan` | `apps/training/models.py` | `training_trainingplan` |
| 6-5 | `TrainingRecord` | `apps/training/models.py` | `training_trainingrecord` |
| 6-5 | `NotificationDoc` | `apps/pubquery/models.py` | `pubquery_notificationdoc` |
| 6-5 | `FaqItem` | `apps/assistant/models.py` | `assistant_faqitem` |
| 6-5 | `ChatLog` | `apps/assistant/models.py` | `assistant_chatlog` |

**多对多关联表（4 张，图上以关联关系表示，不单独画类）**

| 关联 | 关联表 |
|---|---|
| `Employee` ↔ `Group` | `sysconf_employee_groups` |
| `Employee` ↔ `Permission` | `sysconf_employee_user_permissions` |
| `Menu` ↔ `Group` | `sysconf_menu_visible_roles` |
| `TrainingPlan` ↔ `Department` | `training_trainingplan_target_departments` |

**Django 框架内置表（7 张，不纳入类图）**
`auth_group`、`auth_group_permissions`、`auth_permission`、`django_admin_log`、
`django_content_type`、`django_migrations`、`django_session`

> 这张对照表建议同时放进综合实践报告的「详细设计」一节——
> 它能直接证明「UML 类图不是另画一套，而是与代码、数据库三者一致」。

---

## 11. 目录与命名约定

```
HRMS/uml/
├── HRMS.vpp                 # Visual Paradigm 工程（进 git，课程要检查）
├── images/                  # 导出的图片，按图号命名
│   ├── 6-1-use-case.png
│   ├── 6-2-class-sysconf.png
│   ├── ...
│   └── 6-15-deployment.png
├── generated/               # VPP 导出的 Python Entity & Interface 框架
└── README.md                # 本文件
```

命名规则：

- VPP 图名与导出文件名**都带图号前缀**（`6-2-...`），保证 VPP 工程里的图序与 SRS 章节一致；
- 图片导出 PNG（`images/`），导出代码入库（`generated/`）；
- 若导出的 Python 类名与 §3 表格不一致，**以 §3 为准**并修正 VPP 模型，不要反过来改代码——
  代码是已经跑通并通过 143 项验证的实现。

---

## 12. 完成后的核对清单

- [ ] 15 张图全部在 VPP 中建完，图名与 §1 表格一致
- [ ] 24 个类名与属性名与 `models.py` 逐字一致
- [ ] 4 个 `<<interface>>` 已建，且与服务类之间有实现关系
- [ ] 部署图为三节点并标注 HTTP / TCP 3306
- [ ] 导出 Python 框架到 `generated/`，导出图片到 `images/`
- [ ] `HRMS.vpp` 已保存并提交 git
- [ ] SRS 第 6 章图清单表的「状态」列全部改为「已完成」
