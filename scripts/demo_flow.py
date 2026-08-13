"""一键演示 / 自测脚本：对运行中的智能体服务按业务流走完整个流程。

用法（需先启动服务）：
    python -m uvicorn api:app --port 8000          # 终端 1
    python scripts/demo_flow.py --auto             # 终端 2：自动走完整下单流程
    python scripts/demo_flow.py                    # 交互模式：自己逐句对话（自动续接会话）
    python scripts/demo_flow.py --once "你好"      # 单条消息
    python scripts/demo_flow.py --user demo --auto # 指定用户
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"


def safe(text) -> str:
    """Windows 控制台为 GBK 时把无法显示的字符替换为 ?，避免打印崩溃。"""
    s = str(text)
    encoding = sys.stdout.encoding or "utf-8"
    try:
        return s.encode(encoding, errors="replace").decode(encoding)
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s.encode("ascii", errors="replace").decode("ascii")


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def print_resp(r: dict, step: str) -> None:
    """打印结构化响应，突出 UI 动作、工具调用链。"""
    print(f"\n[{step}] ui=\x1b[36m{safe(r.get('ui'))}\x1b[0m  session={r.get('session_id')}")
    print(f"  回复: {safe(r.get('reply'))}")
    if r.get("data"):
        print(f"  数据: {safe(json.dumps(r['data'], ensure_ascii=False)[:400])}")
    for t in r.get("tool_calls") or []:
        args = json.dumps(t.get("arguments", {}), ensure_ascii=False)[:100]
        print(f"  工具: {t['name']}({safe(args)}) -> {t['status']}")


def suggest_next(r: dict):
    """根据返回的 UI 动作推荐下一条引导消息，让对话自动收敛到下单。"""
    ui = r.get("ui")
    if ui == "dialog_options":
        return "看下商家现有方案"
    if ui in ("plan_card", "text"):
        return "确认这个方案"
    if ui == "shop_card":
        return "选第一家店下单"
    return None


def wait_task(task_id: str) -> str:
    for _ in range(40):
        t = get(f"/tasks/{task_id}")
        if t["status"] == "done":
            return t.get("result_url") or ""
        if t["status"] == "error":
            return f"任务失败: {t.get('error')}"
        time.sleep(2)
    return "轮询超时"


def run_auto(user: str) -> None:
    post("/chat/reset", {"user_id": user})
    print(f"=== 自动演示开始（user={user}）===")
    session_id, step, done = None, 1, False
    msg = "想给母亲买一束花，预算 200 元，帮我安排一下"
    while not done and step <= 12:
        resp = post("/chat", {"user_id": user, "message": msg, "session_id": session_id})
        session_id = resp.get("session_id") or session_id
        print_resp(resp, f"{step}")
        # 生图任务：提交后轮询拿结果
        task_id = (resp.get("data") or {}).get("task_id")
        if task_id and resp.get("ui") == "text":
            print(f"  [生图任务] 轮询中 task_id={task_id} ...")
            url = wait_task(task_id)
            print(f"  [生图任务] 完成 -> {url[:100]}")
        if resp.get("ui") == "pay_jump":
            oid = (resp.get("data") or {}).get("order_id")
            print(f"\n✅ 全流程走通！订单号 {oid}，支付跳转参数已返回。")
            done = True
            break
        nxt = suggest_next(resp)
        if nxt is None:
            print("\n⚠️ 未识别可推进的 UI 动作（真实模型回复可能偏离），演示在此结束。")
            print("   可改用交互模式继续：python scripts/demo_flow.py")
            done = True
            break
        msg = nxt
        step += 1
        time.sleep(0.3)
    if not done:
        print("\n⚠️ 超过步骤上限未走到 pay_jump，说明模型回复与预期流程有偏差，"
              "切换交互模式逐句观察：python scripts/demo_flow.py")


def run_interactive(user: str) -> None:
    print(f"=== 交互模式（user={user}，输入 exit 退出）===")
    session_id = None
    while True:
        try:
            msg = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if msg.lower() in ("exit", "quit", "q"):
            break
        if not msg:
            continue
        resp = post("/chat", {"user_id": user, "message": msg, "session_id": session_id})
        session_id = resp.get("session_id") or session_id
        print_resp(resp, "回复")


def main() -> None:
    parser = argparse.ArgumentParser(description="花卉选购智能体自测脚本")
    parser.add_argument("--auto", action="store_true", help="自动走完整下单流程")
    parser.add_argument("--once", metavar="MSG", help="发送单条消息后退出")
    parser.add_argument("--user", default="demo-user", help="用户 ID")
    args = parser.parse_args()

    try:
        health = get("/health")
        print(f"服务在线: llm={health.get('llm_backend')} 生图={health.get('image_provider')} "
              f"工具数={len(health.get('skills', []))}")
    except urllib.error.URLError:
        print(f"❌ 无法连接 {BASE}，请先启动服务：python -m uvicorn api:app --port 8000")
        sys.exit(1)

    if args.auto:
        run_auto(args.user)
    elif args.once:
        resp = post("/chat", {"user_id": args.user, "message": args.once})
        print_resp(resp, "单条")
    else:
        run_interactive(args.user)


if __name__ == "__main__":
    main()