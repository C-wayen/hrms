# HRMS 人力资源管理系统

[English](./README.en.md) | 简体中文

HRMS 是一套基于 **Django 5.2 LTS + MySQL 8.0** 的网络版人力资源管理系统。系统覆盖人事、薪酬、培训、公共查询、报表统计、系统设置与智能问答等业务模块，内置基于角色的访问控制（RBAC）与行级数据范围控制，适合作为企业人事管理的教学与演示项目。

## 功能概览

| 模块 | 主要功能 |
| --- | --- |
| 首页仪表盘 | 在职人数、部门数量、待审批事项、本周生日提醒 |
| 人事管理 | 职工档案、转正申请与审批、社保管理、考勤记录、请假申请与审批、奖罚登记、员工关怀 |
| 薪酬管理 | 薪酬级别与标准、加班 / 水电费 / 计件登记、工资批量核算、工资档案、发放锁定、我的工资 |
| 培训管理 | 课程库、培训计划、培训记录与成绩 |
| 公共查询 | 职工多维检索、通知单套红与打印 |
| 报表统计 | 结构统计（性别 / 年龄 / 学历 / 工龄）、动态分析、人员流动统计（ECharts） |
| 系统设置 | 组织机构树、数据字典、用户与角色、导航菜单与可见角色 |
| 我的 | 我的档案、我的工资、我的请假、修改密码 |
| 智能助手 | 制度类 FAQ 问答、个人数据查询、规则模式 / 云 API 三级降级 |

## 技术栈

- **后端**：Python 3.12、Django 5.2.17 LTS
- **数据库**：MySQL 8.0（`utf8mb4`、严格模式），通过 PyMySQL 连接
- **配置**：python-dotenv 读取 `.env`
- **前端**：Django 模板 + Bootstrap 5.3.3 + Bootstrap Icons 1.11.3 + ECharts 5（均已本地化，无需前端构建）
- **鉴权**：Django Auth + 自定义用户模型 `sysconf.Employee` + Group 权限 + 视图层数据范围控制

## 项目结构

```text
HRMS/
├── README.md                 中文说明
├── README.en.md              英文说明
└── hrms/
    ├── manage.py
    ├── requirements.txt
    ├── .env.example          环境变量模板
    ├── config/               全局配置与根路由
    │   ├── settings.py
    │   ├── urls.py
    │   ├── asgi.py
    │   └── wsgi.py
    ├── apps/
    │   ├── sysconf/          用户 / 角色 / 部门 / 字典 / 菜单 / 首页
    │   ├── personnel/        人事管理
    │   ├── salary/           薪酬管理
    │   ├── training/         培训管理
    │   ├── pubquery/         公共查询
    │   ├── reporting/        报表统计
    │   └── assistant/        智能助手
    ├── scripts/              数据库初始化、演示数据与端到端验证脚本
    ├── static/               样式、图表脚本与第三方前端资源
    └── templates/            全局布局、共享 partials 与各模块模板
```

## 快速开始

### 1. 环境要求

- Python 3.12+
- MySQL 8.0+
- Git

### 2. 获取代码并安装依赖

```bash
git clone https://github.com/C-wayen/hrms.git
cd hrms/hrms
```

创建并激活虚拟环境（也可以使用 conda）：

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# Windows PowerShell
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

编辑 `.env`，至少填写 `DB_PASSWORD`、`SUPERUSER_PASSWORD` 与 `DJANGO_SECRET_KEY`。

| 变量 | 说明 |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django 密钥；生产环境务必使用随机值 |
| `DJANGO_DEBUG` | 开发环境为 `True`，上线必须为 `False` |
| `DJANGO_ALLOWED_HOSTS` | 允许访问的域名 / IP，逗号分隔 |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | MySQL 数据库名与账号 |
| `DB_HOST` / `DB_PORT` | MySQL 地址与端口，默认 `127.0.0.1:3306` |
| `AI_PROVIDER` | `rules`（默认，离线规则模式）或 `cloud`（DeepSeek） |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` | 云模式所需配置 |
| `AI_REQUEST_TIMEOUT` | 云模式请求超时（秒），超时自动回落规则模式 |
| `SUPERUSER_*` | 初始化超级管理员所需信息 |

生成密钥：

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 4. 初始化数据库与数据

以下命令均在 `hrms/` 目录下执行：

```bash
# 创建数据库（若不存在）
python scripts/init_db.py

# 应用迁移
python manage.py migrate

# 创建超级管理员（账号信息来自 .env）
python scripts/create_superuser.py

# 写入角色、部门、字典、薪酬、菜单、FAQ 与演示数据（可重复执行）
python scripts/init_data.py
```

### 5. 启动开发服务器

```bash
python manage.py runserver
```

打开 <http://127.0.0.1:8000/>，使用 `.env` 中的超级管理员账号登录。

## 角色与权限

初始化脚本会创建三个角色，并按模块分配权限：

| 角色 | 权限范围 |
| --- | --- |
| 系统管理员 | 全部业务模块与系统设置 |
| HR 专员/经理 | 人事、薪酬、培训、公共查询、报表、智能助手；系统设置只读，但可维护职工档案 |
| 普通职工 | 提交请假、查看本人档案 / 工资 / 请假记录、使用智能助手与自助改密；无全员档案列表权限 |

系统在视图层额外做数据范围控制，例如普通职工只能看到本人的请假、工资与考勤数据。

## 验证脚本

`hrms/scripts/` 下提供可重复执行的端到端验证脚本。它们使用 Django 测试客户端直接请求视图并核对数据库结果，无需启动开发服务器，但需要已完成迁移并执行过 `init_data.py`。

| 脚本 | 验证内容 |
| --- | --- |
| `scripts/verify_sysconf.py` | 组织机构、数据字典、用户与角色、导航菜单的增删改查 |
| `scripts/verify_salary.py` | 工资核算公式、事务一致性、发放锁定与行级权限 |
| `scripts/verify_reporting.py` | 结构、趋势、人员流动三类统计口径与接口数据 |
| `scripts/verify_assistant.py` | FAQ 命中、个人数据查询、越权拒绝与离线降级 |
| `scripts/verify_menu_permissions.py` | 每个角色可见菜单与实际页面权限的一致性 |

运行示例：

```bash
python scripts/verify_sysconf.py
python scripts/verify_salary.py
python scripts/verify_reporting.py
python scripts/verify_assistant.py
python scripts/verify_menu_permissions.py
```

## 智能助手配置

智能助手按以下顺序处理问题：

1. 识别个人数据意图，直接查询数据库并只返回提问者本人的数据；
2. 未命中个人数据时匹配 FAQ 知识库；
3. 前两级均未命中且 `AI_PROVIDER=cloud` 时调用 DeepSeek API，超时或异常自动回落规则模式。

默认 `AI_PROVIDER=rules`，不依赖外网，适合离线演示。需要云模式时在 `.env` 中配置 `DEEPSEEK_API_KEY` 并将 `AI_PROVIDER` 改为 `cloud`。

## 部署提示

- 将 `DJANGO_DEBUG` 设为 `False`，并使用随机 `DJANGO_SECRET_KEY`；
- 正确配置 `DJANGO_ALLOWED_HOSTS`；
- 执行 `python manage.py collectstatic` 收集静态文件；
- 使用生产级 WSGI 服务器（如 Gunicorn / uWSGI）配合 Nginx 部署，入口为 `config.wsgi:application`；
- 数据库使用独立账号，避免直接使用 root；
- 上线前可通过 `python manage.py check --deploy` 检查部署配置。

## 安全说明

- 数据库密码、Django 密钥与 API Key 只保存在 `.env`，该文件已被 Git 忽略；
- 所有表单启用 CSRF 防护，密码使用 Django 自带哈希与强度校验；
- 业务页面同时校验登录状态与模型权限；
- 演示环境中的初始密码应在正式使用前全部更换。

## 常见问题

**无法连接 MySQL？**

确认 MySQL 已启动、`.env` 中的账号密码正确，并且已执行 `python scripts/init_db.py`。MySQL 8 默认使用 `caching_sha2_password`，若驱动报认证相关错误，可安装 `cryptography` 或为账号调整认证插件。

**页面菜单为空？**

导航菜单由数据库驱动。请确认已执行 `python scripts/init_data.py`，并为当前账号分配了对应角色。

**静态资源 404？**

开发模式下确认 `DEBUG=True` 且通过 `python manage.py runserver` 启动；生产环境需先执行 `collectstatic` 并由 Web 服务器托管静态文件。
