"""下单技能（Skill）：模块化独立实现，自动注册为 create_order 工具。

职责边界：
- 组装订单数据、写入 orders 表、返回订单信息与小程序跳转参数；
- 不调用微信支付（支付由小程序下单页承接）；
- 对用户角色做最小权限校验（预留商家/管理员的动作扩展点）。
"""
import logging

from runtime import get_runtime
from tools import register_tool

logger = logging.getLogger(__name__)


def create_order(plan_type: str = "existing", plan_id: str = "", plan_name: str = "",
                 price: float = 0.0, shop_id: str = "", quantity: int = 1) -> dict:
    """组装并保存订单，返回订单信息 + 小程序支付页跳转参数。"""
    rt = get_runtime()
    user_id = rt.user_id.get()
    role = rt.user_role.get()

    # 权限预留：普通用户可下单；商家/管理员动作后续在此扩展
    if role != "user":
        logger.warning("角色 %s 调用下单，当前仅普通用户允许", role)

    if not plan_name or price <= 0 or not shop_id:
        return {"error": "下单参数不完整：需提供 plan_name、price、shop_id"}

    order = rt.memory.create_order(
        user_id=user_id, plan_type=plan_type, plan_name=plan_name,
        price=price, quantity=max(1, quantity), shop_id=shop_id,
    )
    logger.info("订单已创建 %s (user=%s, shop=%s)", order["order_id"], user_id, shop_id)
    return {
        **order,
        "page_path": "/pages/order/confirm/index",  # 小程序下单确认页路由（按最终小程序调整）
        "params": {"order_id": order["order_id"]},
    }


register_tool(
    "create_order",
    "用户最终确认方案与店铺后调用：创建订单，返回订单号、金额信息以及小程序支付页跳转参数（页面路径 page_path 与参数 params）。",
    {
        "type": "object",
        "properties": {
            "plan_type": {"type": "string", "description": "方案类型：existing 商家预设 / diy 定制", "enum": ["existing", "diy"]},
            "plan_id": {"type": "string", "description": "方案 ID（可空）"},
            "plan_name": {"type": "string", "description": "方案名称"},
            "price": {"type": "number", "description": "单价（元）"},
            "shop_id": {"type": "string", "description": "用户选择的店铺 ID"},
            "quantity": {"type": "integer", "description": "数量，默认 1"},
        },
        "required": ["plan_type", "plan_name", "price", "shop_id"],
    },
    create_order,
)