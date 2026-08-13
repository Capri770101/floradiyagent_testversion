"""结构化 UI 协议：/chat 响应统一定义，是小程序前端渲染的开发契约。

ui 取值与 data 结构约定（已注入系统提示词，供模型遵循）：
- text            : data 为空，纯文本回复
- dialog_options  : data = {"question": str, "options": [{"label": str, "value": str}]}
- plan_card       : data = {"plan_id","name","price","desc","effect_image_url",
                            "merchant_name","plan_type"("existing"|"diy")}
- shop_card       : data = {"shops":[{shop_id,name,address,distance_km,price_range,rating}],
                            "question": str}
- order_card      : data = {"order_id","plan_type","plan_name","quantity","total_price","shop_id"}
- pay_jump        : data = {"order_id","page_path","params": {…}}（跳转小程序下单页）
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

UI_TEXT = "text"
UI_DIALOG = "dialog_options"
UI_PLAN_CARD = "plan_card"
UI_SHOP_CARD = "shop_card"
UI_ORDER_CARD = "order_card"
UI_PAY_JUMP = "pay_jump"

ALL_UI: List[str] = [
    UI_TEXT, UI_DIALOG, UI_PLAN_CARD, UI_SHOP_CARD, UI_ORDER_CARD, UI_PAY_JUMP,
]


class ToolCallRecord(BaseModel):
    """本轮请求中工具调用的审计记录。"""
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result: str = ""
    status: str = "ok"  # ok | error


class ChatResponse(BaseModel):
    """POST /chat 统一响应结构。"""
    user_id: str
    reply: str
    ui: str = UI_TEXT
    data: Dict[str, Any] = Field(default_factory=dict)
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    session_id: str = ""


class ErrorResponse(BaseModel):
    """统一错误结构。"""
    code: int
    message: str