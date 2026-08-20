"""review.py —— 内容机审（阶段5 内容审核体系：机审兜底）。

契约：
- settings.content_review_enabled=False（dev 默认）→ 直接放行，不影响开发联调。
- True 时上架图片先过内容安全 API，违规抛 ReviewError（调用方转 400 拦截上传）。
- 真实接入：把 _review_remote 换成目标内容安全服务（智谱 / 阿里云内容安全等）实现即可，
  返回值固定为 (ok: bool, reason: str)；当前为占位实现（放行 + warning），
  上线前只需替换本模块，无需改动上传端点。
"""

from __future__ import annotations

import logging

from backend.config import settings

logger = logging.getLogger("api")


class ReviewError(Exception):
    """内容审核不通过。message 为给调用方展示的违规原因。"""


def review_image(data: bytes) -> None:
    """审核图片二进制内容；违规抛 ReviewError，通过则静默返回。

    content_review_enabled=False 时零开销直接放行（dev 默认）。
    """
    if not settings.content_review_enabled:
        return
    ok, reason = _review_remote(data)
    if not ok:
        raise ReviewError(reason or "内容审核未通过")


def _review_remote(data: bytes) -> tuple[bool, str]:
    """调用真实内容安全 API（占位实现）。

    TODO(上线前)：按 settings.content_review_url / content_review_api_key 实现，
    将图片（或先压缩/抽样）提交到目标服务，按返回判定违规并给出原因文案。
    """
    logger.warning(
        "content_review_enabled=true 但未接入真实内容安全 API（%s），当前放行",
        settings.content_review_url or "未配置 CONTENT_REVIEW_URL",
    )
    return True, ""
