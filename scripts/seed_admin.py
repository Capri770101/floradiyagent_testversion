"""scripts/seed_admin.py —— 创建管理员账号（M0，幂等）。

用法：python scripts/seed_admin.py
环境变量（可选，默认仅演示、上线前必须改）：
- ADMIN_USERNAME  （默认 admin）
- ADMIN_PASSWORD  （默认 admin123456）

已存在同名用户则仅确保 role=admin；不覆盖密码。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from security import register_user, set_user_role  # noqa: E402
from storage.db import get_conn, init_db  # noqa: E402


def main() -> None:
    init_db()
    username = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.environ.get("ADMIN_PASSWORD", "admin123456")
    nickname = "平台管理员"

    conn = get_conn()
    row = conn.execute(
        "SELECT id, role FROM users WHERE username=?", (username,)
    ).fetchone()
    if row:
        if row["role"] != "admin":
            set_user_role(row["id"], "admin")
            print(f"已提权 {username} -> admin")
        else:
            print(f"{username} 已是 admin，跳过")
        return

    uid, _token = register_user(username, password, nickname)
    set_user_role(uid, "admin")
    print(f"已创建管理员 {username} (role=admin)")


if __name__ == "__main__":
    main()
