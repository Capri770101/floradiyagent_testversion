"""cli.py —— 本地调试 CLI（typer）。

无 API 也能快速试用设计能力、跑知识库检索、做回归：
    python cli.py design "母亲节给妈妈买束花"
    python cli.py knowledge --domain pairing --query "看望生病住院的朋友"
    python cli.py revise --plan plan.json --feedback "便宜点"
    python cli.py tools
    python cli.py chat --message "帮我设计一束送妈妈的生日花"

依赖：typer（已装在开发 venv；如需复现 `pip install typer`）。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from agent.knowledge import query_knowledge
from agent.tools import design_diy_plan, get_tool_specs, revise_diy_plan

app = typer.Typer(help='Flora DIY 智能体本地调试 CLI', add_completion=False)

def _dump(obj: object) -> None:
    typer.echo(json.dumps(obj, ensure_ascii=False, indent=2))

@app.command()
def design(requirements: str=typer.Argument(..., help='用户 DIY 需求描述')) -> None:
    """基于知识库设计一份结构化 DIY 方案（含插花步骤/养护/贺卡/预算明细）。"""
    _dump(design_diy_plan(requirements))

@app.command()
def knowledge(domain: str=typer.Option('all', '--domain', '-d', help='flower|style|pairing|budget|packaging|scene|shop|all'), query: str=typer.Option(..., '--query', '-q', help='关键词或自然语言（多词触发向量语义召回）')) -> None:
    """检索知识库（向量混合检索）。"""
    _dump(query_knowledge(domain, query))

@app.command()
def revise(plan: str=typer.Option(..., '--plan', '-p', help='方案 JSON 文件路径或 JSON 字符串'), feedback: str=typer.Option(..., '--feedback', '-f', help='自然语言反馈，如 便宜点/不要康乃馨')) -> None:
    """基于已有方案 + 反馈生成下一版（version 递增、parent_id 可追溯）。"""
    path = Path(plan)
    plan_str = path.read_text(encoding='utf-8') if path.is_file() else plan
    _dump(json.loads(asyncio.run(revise_diy_plan(plan_str, feedback))))

@app.command('tools')
def list_tools() -> None:
    """列出已注册工具。"""
    for t in get_tool_specs():
        typer.echo(f'- {t.name}: {t.description}')

@app.command()
def chat(message: str=typer.Option(..., '--message', '-m', help='用户消息'), user_id: str=typer.Option('cli-user', '--user-id'), session_id: str=typer.Option(None, '--session')) -> None:
    """与智能体对话（需配置 LLM_API_KEY；未配置时 call_llm 直接报错，已无 Mock 引擎兜底）。"""
    from agent.agent import ReActAgent
    agent = ReActAgent()
    result = asyncio.run(agent.arun(user_id, message, session_id, 'user', None))
    _dump(result.model_dump())

@app.command('make-admin')
def make_admin(username: str=typer.Argument(..., help='要授予管理员角色的用户名')) -> None:
    """把指定用户名提升为 admin（管理后台 / 系统信息编辑权限）。"""
    from backend.security import set_user_role
    from backend.storage.db import get_conn
    conn = get_conn()
    row = conn.execute('SELECT id, nickname, role FROM users WHERE username=?', (username,)).fetchone()
    if not row:
        typer.secho(f'用户不存在: {username}（先注册再授权）', fg=typer.colors.RED)
        raise typer.Exit(1)
    if set_user_role(row['id'], 'admin'):
        typer.secho(f"已授予 admin: {username}（{row['nickname'] or row['id']}）", fg=typer.colors.GREEN)
    else:
        typer.secho('授权失败', fg=typer.colors.RED)
        raise typer.Exit(1)

@app.command('set-role')
def set_role(username: str=typer.Argument(..., help='用户名'), role: str=typer.Argument(..., help='user | merchant | admin')) -> None:
    """设置用户角色（user / merchant / admin）。"""
    from backend.security import set_user_role
    from backend.storage.db import get_conn
    conn = get_conn()
    row = conn.execute('SELECT id, nickname FROM users WHERE username=?', (username,)).fetchone()
    if not row:
        typer.secho(f'用户不存在: {username}', fg=typer.colors.RED)
        raise typer.Exit(1)
    try:
        set_user_role(row['id'], role)
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(1) from exc
    typer.secho(f'{username} 角色已设为 {role}', fg=typer.colors.GREEN)

@app.command('bind-merchant')
def bind_merchant(username: str=typer.Argument(..., help='商家用户名'), shop_id: str=typer.Argument(..., help='店铺 id，如 S001')) -> None:
    """把商家绑定到店铺（商家后台按此隔离数据；一个商家可绑多家店）。"""
    from backend.storage import catalog
    from backend.storage.db import _run_async, get_conn
    conn = get_conn()
    row = conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    if not row:
        typer.secho(f'用户不存在: {username}', fg=typer.colors.RED)
        raise typer.Exit(1)
    if not _run_async(asyncio.run(catalog.merchant_bind(row['id'], shop_id))):
        typer.secho(f'店铺不存在: {shop_id}（用 python cli.py list-shops 查看）', fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f'已绑定 {username} → {shop_id}', fg=typer.colors.GREEN)

@app.command('unbind-merchant')
def unbind_merchant(username: str=typer.Argument(..., help='商家用户名'), shop_id: str=typer.Argument(..., help='店铺 id，如 S001')) -> None:
    """解除商家与店铺的绑定。"""
    from backend.storage import catalog
    from backend.storage.db import _run_async, get_conn
    conn = get_conn()
    row = conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    if not row:
        typer.secho(f'用户不存在: {username}', fg=typer.colors.RED)
        raise typer.Exit(1)
    if not _run_async(asyncio.run(catalog.merchant_unbind(row['id'], shop_id))):
        typer.secho(f'{username} 与 {shop_id} 之间没有绑定', fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f'已解除 {username} → {shop_id}', fg=typer.colors.GREEN)

@app.command('merchant-shops')
def merchant_shops_list(username: str=typer.Argument(..., help='商家用户名')) -> None:
    """查看商家当前绑定的店铺。"""
    from backend.storage import catalog
    from backend.storage.db import _run_async, get_conn
    conn = get_conn()
    row = conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
    if not row:
        typer.secho(f'用户不存在: {username}', fg=typer.colors.RED)
        raise typer.Exit(1)
    shops = _run_async(asyncio.run(catalog.merchant_shops(row['id'])))
    if not shops:
        typer.secho(f'{username} 尚未绑定任何店铺', fg=typer.colors.YELLOW)
        return
    for s in shops:
        typer.echo(f"- {s['id']}  {s['name']}")

@app.command('list-shops')
def list_shops() -> None:
    """列出全部店铺（id + 名称），供 bind-merchant 使用。"""
    from backend.storage.db import get_conn
    rows = get_conn().execute('SELECT id, name FROM shops ORDER BY created_at').fetchall()
    for r in rows:
        typer.echo(f"- {r['id']}  {r['name']}")
if __name__ == '__main__':
    app()
