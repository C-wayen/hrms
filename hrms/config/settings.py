"""
人力资源管理系统（HRMS）—— Django 全局配置。

对应文档：HRMS/code_artifact.md（SRS V1.1）
技术栈：Django 5.2 LTS + MySQL 8.0 + PyMySQL（Python 3.12）

@author 王坤尧
"""

import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv

# 【数据库驱动】让 Django 内置的 mysql 后端改用 PyMySQL。
# PyMySQL 是纯 Python 实现，无需 C 编译器，Windows 下比 mysqlclient 好装。
pymysql.install_as_MySQLdb()

# 【路径】项目根目录，即 manage.py 所在目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 【配置注入】从根目录的 .env 读取密钥与数据库账号（该文件不提交到版本库）
load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str = "") -> str:
    """读取环境变量；未配置时回落到默认值。"""
    return os.getenv(key, default)


# =============================================================================
# 一、基础安全配置
# 官方部署检查清单：https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
# =============================================================================

# 【密钥】用于签名 Session 与 CSRF Token。
# 生产环境必须换成随机值：python -c "import secrets;print(secrets.token_urlsafe(50))"
SECRET_KEY = env("DJANGO_SECRET_KEY", "django-insecure-dev-only-fallback-key")

# 【调试开关】正式上线必须为 False，否则会向浏览器泄露源码与配置
DEBUG = env("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")

# 【允许访问的主机】不在此列表的域名/IP 会被拒绝，防御 Host 头攻击
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]


# =============================================================================
# 二、应用注册
# =============================================================================

INSTALLED_APPS = [
    # --- Django 内置应用 ---
    'django.contrib.admin',         # 后台管理站点（承载用户/菜单/数据字典等管理界面）
    'django.contrib.auth',          # 认证与权限：User / Group / Permission，支撑 FR-SYS-01 的 RBAC
    'django.contrib.contenttypes',  # 内容类型框架，权限系统的依赖
    'django.contrib.sessions',      # 会话管理，维持登录状态
    'django.contrib.messages',      # 一次性提示消息
    'django.contrib.staticfiles',   # 静态文件收集与托管

    # --- 业务应用（对应 SRS 第 4 章的 6 大模块 + 1 个加分项）---
    # sysconf 必须最先注册：Employee 作为 AUTH_USER_MODEL，是其他模块的依赖底座
    'apps.sysconf',     # 模块 6 系统设置与安全   FR-SYS-01 ~ FR-SYS-03（Employee 账号在此）
    'apps.salary',      # 模块 3 薪酬管理         FR-SAL-01 ~ FR-SAL-03
    'apps.personnel',   # 模块 1 人事管理         FR-PER-01 ~ FR-PER-04
    'apps.training',    # 模块 2 培训管理         FR-TRN-01 ~ FR-TRN-02
    'apps.pubquery',    # 模块 4 公共查询         FR-QRY-01 ~ FR-QRY-02
    'apps.reporting',   # 模块 5 报表统计         FR-RPT-01 ~ FR-RPT-03（无模型，纯聚合查询）
    'apps.assistant',   # 加分项 智能应答机器人   FR-AI-01  ~ FR-AI-02
]

# 【自定义用户模型】指向 sysconf.Employee。
# 本项目「员工即账号」——Employee 继承 AbstractUser，认证字段与人事档案共用一张表。
# 该设置在首次 migrate 之前一旦确定就不应再改，事后修改必须重建数据库。
AUTH_USER_MODEL = 'sysconf.Employee'

# =============================================================================
# 三、中间件（自下而上：请求时正序执行，响应时逆序返回）
# =============================================================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',          # 安全响应头（HSTS 等）
    'django.contrib.sessions.middleware.SessionMiddleware',   # 会话，依赖缓存/Cookie
    'django.middleware.common.CommonMiddleware',              # URL 规范化、斜杠跳转
    'django.middleware.csrf.CsrfViewMiddleware',              # CSRF 防护，所有表单必须带 Token
    'django.contrib.auth.middleware.AuthenticationMiddleware',  # 为 request 挂载 request.user
    'django.contrib.messages.middleware.MessageMiddleware',   # 跨请求传递提示消息
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # 点击劫持防护
]

# 根路由表，所有 URL 从 config/urls.py 开始分发
ROOT_URLCONF = 'config.urls'

# =============================================================================
# 四、模板引擎
# =============================================================================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # 全局模板目录（各 app 自己的 templates/ 由 APP_DIRS 自动发现）
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',  # 模板中可用 request
                'django.contrib.auth.context_processors.auth',  # 模板中可用 user / perms
                'django.contrib.messages.context_processors.messages',  # 模板中可用 messages
                # 侧边栏菜单：按当前登录用户的角色过滤后注入（FR-SYS-03）
                'apps.sysconf.context_processors.sidebar_menus',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# =============================================================================
# 五、数据库（MySQL 8.0，对应 SRS 5.2「数据库设计与选型说明」）
# 官方文档：https://docs.djangoproject.com/en/5.2/ref/settings/#databases
# =============================================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': env('DB_NAME', 'hrms'),          # 库名
        'USER': env('DB_USER', 'root'),          # 账号
        'PASSWORD': env('DB_PASSWORD'),          # 密码（来自 .env，不入库）
        'HOST': env('DB_HOST', '127.0.0.1'),     # 主机
        'PORT': env('DB_PORT', '3306'),          # 端口
        'OPTIONS': {
            # 字符集必须 utf8mb4，否则存不了 emoji 与部分生僻字
            'charset': 'utf8mb4',
            # 严格模式：非法数据直接报错，而不是静默截断（保证数据质量）
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        # 跑单元测试时自动建 hrms_test 库，同样使用 utf8mb4
        'TEST': {'CHARSET': 'utf8mb4'},
    }
}


# =============================================================================
# 六、密码强度校验（作用于 User.set_password 与 createsuperuser）
# 官方文档：https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        # 密码不能与用户名/邮箱太相似
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        # 最小长度（Django 默认 8 位）
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        # 不得是常见弱口令（如 123456、password）
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        # 不得是纯数字
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# =============================================================================
# 七、国际化与本地化
# 官方文档：https://docs.djangoproject.com/en/5.2/topics/i18n/
# =============================================================================

# 界面语言：简体中文（影响 Django Admin 与内置错误页的文案）
LANGUAGE_CODE = 'zh-hans'

# 时区：东八区（考勤、薪酬周期都依赖它）
TIME_ZONE = 'Asia/Shanghai'

# 启用翻译系统
USE_I18N = True

# 数据库中以 UTC 存储时间戳，模板渲染时自动转为本地时间
USE_TZ = True


# =============================================================================
# 八、静态文件与默认主键
# 官方文档：https://docs.djangoproject.com/en/5.2/howto/static-files/
# =============================================================================

# 浏览器访问静态资源时使用的 URL 前缀
STATIC_URL = 'static/'

# 开发期额外的静态文件目录（Bootstrap、ECharts 等第三方库放在这里）
STATICFILES_DIRS = [BASE_DIR / 'static']

# 执行 collectstatic 后的汇总目录（部署时用，开发期不产生）
STATIC_ROOT = BASE_DIR / 'staticfiles'

# 【用户上传】证书扫描件等用户上传的文件存放于此，与静态资源分开管理
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# 模型主键默认使用 64 位自增整数（避免 32 位溢出，同时与 MySQL BIGINT 对应）
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# =============================================================================
# 九、邮件
# 注意：Django 6.0 起改为 MAILERS 字典；本项目使用 5.2 LTS，必须用 EMAIL_BACKEND。
# 官方文档：https://docs.djangoproject.com/en/5.2/topics/email/
# =============================================================================

# 开发期把邮件输出到控制台，便于调试（对应 FR-PER-04 职工生日提醒）
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


# =============================================================================
# 十、业务配置（HRMS 专有）
# =============================================================================

# 未登录用户访问受保护页面时跳转的路由名（配合 @login_required 使用）
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

# --- 智能应答机器人（FR-AI-01 ~ FR-AI-02）---
# rules = 纯离线规则库 + 意图槽位 + SQL 模板（默认，答辩时不依赖网络）
# cloud = 走 DeepSeek API；请求超时或异常时自动回落 rules 模式并提示「当前为离线问答」
AI_PROVIDER = env('AI_PROVIDER', 'rules')
DEEPSEEK_API_KEY = env('DEEPSEEK_API_KEY')
DEEPSEEK_MODEL = env('DEEPSEEK_MODEL', 'deepseek-chat')
AI_REQUEST_TIMEOUT = int(env('AI_REQUEST_TIMEOUT', '8'))
