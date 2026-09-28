"""创建 HRMS 数据库（若不存在）。

连接信息一律从项目根目录的 .env 读取，密码不写在代码里、不提交到版本库。
用法：
    & 'D:\\rj\\conda_env\\envs\\aip\\python.exe' scripts\\init_db.py
"""

import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def main() -> int:
    db_name = os.getenv("DB_NAME", "hrms")
    password = os.getenv("DB_PASSWORD", "")

    if not password:
        print("[!] .env 中的 DB_PASSWORD 为空。")
        print(f"    请先编辑 {BASE_DIR / '.env'} 填写 MySQL root 密码，再运行本脚本。")
        return 1

    conn_kwargs = {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": password,
        "charset": "utf8mb4",
    }

    try:
        conn = pymysql.connect(**conn_kwargs)
    except pymysql.MySQLError as exc:
        print(f"[x] 连接 MySQL 失败：{exc}")
        print(f"    目标：{conn_kwargs['user']}@{conn_kwargs['host']}:{conn_kwargs['port']}")
        return 1

    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.execute("SELECT VERSION()")
            version = cur.fetchone()[0]

            cur.execute(
                "SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME "
                "FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
                (db_name,),
            )
            row = cur.fetchone()
            charset, collation = row if row else ("?", "?")
    finally:
        conn.close()

    print(f"[OK] MySQL {version} 连接成功")
    print(f"[OK] 数据库 `{db_name}` 就绪")
    print(f"     字符集 {charset} / 排序规则 {collation}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
