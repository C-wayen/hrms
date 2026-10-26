# HRMS — Human Resource Management System

English | [简体中文](./README.md)

HRMS is a web-based Human Resource Management System built with **Django 5.2 LTS + MySQL 8.0**. It covers personnel, payroll, training, public queries, reporting, system configuration, and an AI assistant. Role-based access control (RBAC) and row-level data scoping are built in, making the project suitable for teaching and demonstration purposes.

## Features

| Module | Highlights |
| --- | --- |
| Dashboard | Headcount, department count, pending approvals, and birthdays this week |
| Personnel | Employee records, regularization applications and approvals, social insurance, attendance, leave requests and approvals, rewards and punishments, employee care |
| Payroll | Salary levels and standards, overtime / utility fee / piecework records, batch payroll calculation, payroll records, payment locking, my salary |
| Training | Course library, training plans, training records and scores |
| Public Query | Multi-dimensional employee search, notification printing |
| Reporting | Workforce structure (gender / age / education / tenure), trend analysis, turnover statistics (ECharts) |
| System Settings | Organization tree, data dictionaries, users and roles, navigation menus and visible roles |
| My Workspace | My profile, my salary, my leave requests, change password |
| AI Assistant | Policy FAQ, personal data lookup, three-level fallback between rule mode and cloud API |

## Tech Stack

- **Backend**: Python 3.12, Django 5.2.17 LTS
- **Database**: MySQL 8.0 (`utf8mb4`, strict mode) via PyMySQL
- **Configuration**: python-dotenv for `.env`
- **Frontend**: Django templates + Bootstrap 5.3.3 + Bootstrap Icons 1.11.3 + ECharts 5 (vendored locally, no frontend build step)
- **Authentication**: Django Auth with a custom user model (`sysconf.Employee`), Group permissions, and view-level data scoping

## Project Structure

```text
HRMS/
├── README.md                 Chinese documentation
├── README.en.md              English documentation
└── hrms/
    ├── manage.py
    ├── requirements.txt
    ├── .env.example          Environment variable template
    ├── config/               Global settings and root URL configuration
    │   ├── settings.py
    │   ├── urls.py
    │   ├── asgi.py
    │   └── wsgi.py
    ├── apps/
    │   ├── sysconf/          Users / roles / departments / dictionaries / menus / dashboard
    │   ├── personnel/        Personnel management
    │   ├── salary/           Payroll management
    │   ├── training/         Training management
    │   ├── pubquery/         Public queries
    │   ├── reporting/        Reporting
    │   └── assistant/        AI assistant
    ├── scripts/              Database setup, seed data, and end-to-end verification scripts
    ├── static/               Stylesheets, chart scripts, and vendored frontend assets
    └── templates/            Global layout, shared partials, and module templates
```

## Quick Start

### 1. Prerequisites

- Python 3.12+
- MySQL 8.0+
- Git

### 2. Clone and install dependencies

```bash
git clone https://github.com/C-wayen/hrms.git
cd hrms/hrms
```

Create and activate a virtual environment (conda also works):

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
# Windows PowerShell
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

Edit `.env` and fill in at least `DB_PASSWORD`, `SUPERUSER_PASSWORD`, and `DJANGO_SECRET_KEY`.

| Variable | Description |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django secret key; always use a random value in production |
| `DJANGO_DEBUG` | `True` for development, must be `False` in production |
| `DJANGO_ALLOWED_HOSTS` | Allowed domain names / IPs, comma-separated |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | MySQL database name and credentials |
| `DB_HOST` / `DB_PORT` | MySQL host and port, default `127.0.0.1:3306` |
| `AI_PROVIDER` | `rules` (default, offline rule mode) or `cloud` (DeepSeek) |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` | Required for cloud mode |
| `AI_REQUEST_TIMEOUT` | Cloud request timeout in seconds; falls back to rule mode on timeout |
| `SUPERUSER_*` | Information used to create the initial superuser |

Generate a secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### 4. Initialize the database and seed data

Run the following commands from the `hrms/` directory:

```bash
# Create the database if it does not exist
python scripts/init_db.py

# Apply migrations
python manage.py migrate

# Create the superuser (credentials are read from .env)
python scripts/create_superuser.py

# Seed roles, departments, dictionaries, salary data, menus, FAQs, and demo data (idempotent)
python scripts/init_data.py
```

### 5. Start the development server

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and sign in with the superuser account from `.env`.

## Roles and Permissions

The seed script creates three roles and assigns permissions by module:

| Role | Scope |
| --- | --- |
| System Administrator | All business modules and system settings |
| HR Specialist / Manager | Personnel, payroll, training, public queries, reporting, AI assistant; read-only system settings, but can maintain employee records |
| Employee | Submit leave requests, view their own profile / salary / leave records, use the AI assistant, and change their password; no access to the full employee list |

Additional row-level scoping is enforced in views. For example, employees can only see their own leave requests, salary, and attendance data.

## Verification Scripts

The scripts under `hrms/scripts/` provide repeatable end-to-end checks. They use the Django test client to call views and verify database results directly, so no running server is required. Migrations and `init_data.py` must have completed first.

| Script | What it verifies |
| --- | --- |
| `scripts/verify_sysconf.py` | CRUD for departments, dictionaries, users and roles, and navigation menus |
| `scripts/verify_salary.py` | Payroll formulas, transaction consistency, payment locking, and row-level permissions |
| `scripts/verify_reporting.py` | Definitions and API data for structure, trend, and turnover reports |
| `scripts/verify_assistant.py` | FAQ matching, personal data lookup, access denial, and offline fallback |
| `scripts/verify_menu_permissions.py` | Consistency between visible menu items and actual page permissions for each role |

Example:

```bash
python scripts/verify_sysconf.py
python scripts/verify_salary.py
python scripts/verify_reporting.py
python scripts/verify_assistant.py
python scripts/verify_menu_permissions.py
```

## AI Assistant Configuration

The assistant processes questions in this order:

1. Detect personal-data intent and query the database directly, returning only the asker's own data;
2. Fall back to the FAQ knowledge base;
3. If neither matches and `AI_PROVIDER=cloud`, call the DeepSeek API. Timeouts or errors automatically fall back to rule mode.

The default `AI_PROVIDER=rules` works without internet access and is suitable for offline demos. To enable cloud mode, set `DEEPSEEK_API_KEY` in `.env` and change `AI_PROVIDER` to `cloud`.

## Deployment Notes

- Set `DJANGO_DEBUG` to `False` and use a random `DJANGO_SECRET_KEY`;
- Configure `DJANGO_ALLOWED_HOSTS` correctly;
- Run `python manage.py collectstatic` to collect static files;
- Deploy behind a production WSGI server (Gunicorn / uWSGI) and a reverse proxy such as Nginx. The WSGI entry point is `config.wsgi:application`;
- Use a dedicated database account instead of root;
- Run `python manage.py check --deploy` before going live.

## Security Notes

- Database passwords, the Django secret key, and API keys live only in `.env`, which is ignored by Git;
- All forms are protected by CSRF, and passwords use Django's built-in hashing and strength validators;
- Business views check both authentication and model permissions;
- Change every initial password before using the system in production.

## Troubleshooting

**Cannot connect to MySQL?**

Make sure MySQL is running, the credentials in `.env` are correct, and `python scripts/init_db.py` has been executed. MySQL 8 uses `caching_sha2_password` by default; if the driver reports an authentication error, install `cryptography` or adjust the account's authentication plugin.

**The navigation menu is empty.**

Menus are database-driven. Make sure `python scripts/init_data.py` has been executed and the current account has been assigned a role.

**Static assets return 404.**

In development, make sure `DEBUG=True` and start the app with `python manage.py runserver`. In production, run `collectstatic` first and serve static files through the web server.
