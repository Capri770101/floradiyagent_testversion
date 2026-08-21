"""scripts/generate_plan_images.py —— 按 描述 批量生成真实商品图与店铺图。

用法（后端运行中亦可，直接调智谱接口不经过 uvicorn）：
    python scripts/generate_plan_images.py            # 全部商品 + 店铺
    python scripts/generate_plan_images.py P001 P003  # 指定商品（不含店铺）
    python scripts/generate_plan_images.py --shops    # 仅店铺图

流程：
- 商品：遍历 plans 表 -> 名称+描述+标签 组 prompt -> CogView 出图 ->
  落盘 data/generated/plan_{id}.{ext} -> 回写 plans.effect_image_url
- 店铺：遍历 shops 表 -> 头图 cover（宽幅 1344x768 门面横幅）+
  店面图 logo（方图门头）-> 回写 shops.cover / logo / image
单张失败不中断，保留原图并告警；扩展名变化时旧文件一并清理。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.storage import tasks  # noqa: E402
from backend.storage.db import get_conn, init_db  # noqa: E402


def build_prompt(name: str, desc: str, tags: str) -> str:
    tag_txt = tags.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
    return (
        f"鲜花电商产品图：{name}。{desc}"
        f"关键词：{tag_txt}。"
        "浅米色纯净背景，柔和自然光，居中构图，花材新鲜饱满带水珠，"
        "高清写实商业摄影，无文字无水印。"
    )


def _cleanup_old(old_url: str, new_url: str) -> None:
    """扩展名变化时清理旧落盘文件。"""
    if old_url and old_url != new_url and old_url.startswith("/generated/"):
        old_file = tasks._ensure_generated_dir() / Path(old_url).name
        if old_file.exists() and old_file.name != Path(new_url).name:
            old_file.unlink(missing_ok=True)


def gen_plans(conn, only: set[str]) -> None:
    rows = conn.execute(
        "SELECT id, name, price, desc, tags, effect_image_url FROM plans ORDER BY id"
    ).fetchall()
    if only:
        rows = [r for r in rows if r["id"] in only]
    print(f"待出图商品 {len(rows)} 个")
    ok = fail = 0
    for r in rows:
        pid = r["id"]
        old_url = r["effect_image_url"] or ""
        prompt = build_prompt(r["name"], r["desc"] or "", r["tags"] or "")
        try:
            new_url = tasks._image_client_submit_zhipu(prompt, f"plan_{pid}")
        except Exception as exc:  # noqa: BLE001
            fail += 1
            print(f"  x {pid} {r['name']}: 出图失败（保留原图 {old_url}）：{exc}")
            continue
        with conn:
            conn.execute(
                "UPDATE plans SET effect_image_url=? WHERE id=?", (new_url, pid)
            )
        _cleanup_old(old_url, new_url)
        ok += 1
        print(f"  + {pid} {r['name']}: {new_url}")
    print(f"商品图完成：成功 {ok} / 失败 {fail}")


def gen_shops(conn) -> None:
    """为每家店生成头图（cover，宽幅）与店面图（logo，方图）。"""
    rows = conn.execute(
        "SELECT id, name, intro, address, cover, logo FROM shops ORDER BY id"
    ).fetchall()
    print(f"待出图店铺 {len(rows)} 家")
    for s in rows:
        sid = s["id"]
        base = (
            f"花店「{s['name']}」店面实拍：{s['intro'] or '温馨花艺工作室'}，"
            f"位于{s['address'] or '街边'}。"
        )
        jobs = [
            (
                "cover",
                "1344x768",
                base + "宽幅门头横幅视角，木质招牌，门口陈列鲜花绿植，暖色灯光，"
                "清新文艺氛围，高清写实商业摄影，无文字无水印。",
            ),
            (
                "logo",
                "1024x1024",
                base + "方形门头特写构图，招牌旁悬挂花束装饰，柔和自然光，"
                "温馨精致，高清写实摄影，无文字无水印。",
            ),
        ]
        for field, size, prompt in jobs:
            old_url = s[field] or ""
            try:
                new_url = tasks._image_client_submit_zhipu(
                    prompt, f"shop_{sid}_{field}", size=size
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  x {sid} {field}: 出图失败（保留原图 {old_url}）：{exc}")
                continue
            with conn:
                if field == "cover":
                    conn.execute(
                        "UPDATE shops SET cover=?, image=? WHERE id=?",
                        (new_url, new_url, sid),
                    )
                else:
                    conn.execute("UPDATE shops SET logo=? WHERE id=?", (new_url, sid))
            _cleanup_old(old_url, new_url)
            print(f"  + {sid} {s['name']} {field}: {new_url}")


def main() -> None:
    init_db()
    only = {a.upper() for a in sys.argv[1:] if not a.startswith("-")}
    conn = get_conn()
    if "--shops" not in sys.argv:
        gen_plans(conn, only)
    if "--shops" in sys.argv or not only:
        gen_shops(conn)


if __name__ == "__main__":
    main()
