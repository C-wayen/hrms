"""创建 HRMS 超级管理员账号。

账号信息（含密码）一律从项目根目录的 .env 读取，不写进代码，
也不提交到版本库。

对应 FR-SYS-01 权限控制：超级管理员是整个 RBAC 体系的起点，
创建后可在 /admin/ 中继续建立「系统管理员 / HR 专员·经理 / 普通职工」三个角色。

用法：
    & 'D:\\rj\\conda_env\\envs\\aip\\python.exe' scripts\\create_superuser.py
"""

import os
import sys
from pathlib import Path

# 把项目根目录加入模块搜索路径，否则 config.settings 无法导入
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402  必须在设置环境变量之后导入

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(BASE_DIR / '.env')

Employee = get_user_model()


def main() -> int:
    employee_no = os.getenv('SUPERUSER_EMPLOYEE_NO', 'ADMIN001')
    password = os.getenv('SUPERUSER_PASSWORD', '')

    if not password:
        print('[!] .env 中的 SUPERUSER_PASSWORD 为空。')
        print(f'    请先编辑 {BASE_DIR / ".env"} 填写登录密码，再运行本脚本。')
        return 1

    if Employee.objects.filter(employee_no=employee_no).exists():
        print(f'[i] 工号为「{employee_no}」的账号已存在，无需重复创建。')
        return 0

    # Employee 的 REQUIRED_FIELDS 要求四个业务字段，一并从 .env 取。
    # username 传工号——本模型「工号即账号」，save() 也会自动同步，
    # 但 UserManager 的签名仍要求显式传入
    Employee.objects.create_superuser(
        username=employee_no,
        password=password,
        real_name=os.getenv('SUPERUSER_REAL_NAME', '系统管理员'),
        employee_no=employee_no,
        id_card=os.getenv('SUPERUSER_ID_CARD', '110101199001011234'),
        gender=os.getenv('SUPERUSER_GENDER', 'M'),
    )

    print(f'[OK] 超级管理员创建成功，工号即登录名：{employee_no}')
    print('     登录地址：http://127.0.0.1:8000/admin/')
    print('     建议登录后在「修改密码」中更换 .env 里的初始密码')
    return 0


if __name__ == '__main__':
    sys.exit(main())
