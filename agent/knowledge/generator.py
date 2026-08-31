"""knowledge/generator.py —— LLM 知识生成器。

使用 LLM 自动生成花卉知识库条目，支持：
- 花材信息生成
- 搭配方案生成
- 场景信息生成
- 风格信息生成
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger('knowledge.generator')


async def _call_llm(prompt: str, system: str = '') -> str:
    """调用 LLM 生成内容。"""
    try:
        from agent.engine.llm import call_llm
        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})
        return await call_llm(messages)
    except Exception as e:
        logger.error('[generator] LLM 调用失败: %s', e)
        return ''


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """从 LLM 响应中解析 JSON。"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试从 markdown 代码块中提取
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试找到第一个 { 到最后一个 }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


async def generate_flower(flower_name: str) -> dict[str, Any] | None:
    """使用 LLM 生成花材信息。

    Args:
        flower_name: 花材名称（如 "向日葵"、"郁金香"）

    Returns:
        符合 FlowerBase 模型的字典，失败返回 None
    """
    system = """你是花卉知识专家。请根据花材名称生成完整的花材信息。
返回 JSON 格式，包含以下字段：
- name: 花材名称
- aliases: 别名数组
- flower_language: 花语数组
- colors: 常见颜色数组
- season: 花期数组（如 ["春季", "夏季"]）
- price_tier: 价格档位（"低"/"中"/"高"）
- category: 分类（"主花"/"配花"/"叶材"）
- care_tips: 养护建议
- pairing_notes: 搭配建议
- tags: 标签数组

只返回 JSON，不要其他内容。"""

    prompt = f"请生成「{flower_name}」的详细花材信息。"
    response = await _call_llm(prompt, system)

    if not response:
        return None

    data = _parse_json_response(response)
    if not data:
        logger.warning('[generator] 无法解析 LLM 响应: %s', response[:200])
        return None

    # 验证必要字段
    if 'name' not in data:
        data['name'] = flower_name

    # 设置默认值
    data.setdefault('aliases', [])
    data.setdefault('flower_language', [])
    data.setdefault('colors', [])
    data.setdefault('season', ['四季'])
    data.setdefault('price_tier', '中')
    data.setdefault('category', '主花')
    data.setdefault('care_tips', '')
    data.setdefault('pairing_notes', '')
    data.setdefault('tags', [])

    return data


async def generate_pairing(name: str, occasion: str = '', style: str = '') -> dict[str, Any] | None:
    """使用 LLM 生成搭配方案。

    Args:
        name: 搭配方案名称
        occasion: 适用场景（可选）
        style: 适用风格（可选）

    Returns:
        符合 PairingCreate 模型的字典，失败返回 None
    """
    system = """你是花艺搭配专家。请根据要求生成花艺搭配方案。
返回 JSON 格式，包含以下字段：
- name: 方案名称
- description: 搭配描述
- occasion_ids: 适用场景 ID 数组
- style_ids: 适用风格 ID 数组
- season: 适用季节数组
- tags: 标签数组
- flowers: 花材列表，每项包含 flower_id, flower_type (main/support/leaf), quantity_min, quantity_max

只返回 JSON，不要其他内容。"""

    context = f"方案名称：{name}"
    if occasion:
        context += f"\n适用场景：{occasion}"
    if style:
        context += f"\n适用风格：{style}"

    prompt = f"请生成以下搭配方案的详细信息：\n{context}"
    response = await _call_llm(prompt, system)

    if not response:
        return None

    data = _parse_json_response(response)
    if not data:
        logger.warning('[generator] 无法解析 LLM 响应: %s', response[:200])
        return None

    # 验证必要字段
    if 'name' not in data:
        data['name'] = name

    data.setdefault('description', '')
    data.setdefault('occasion_ids', [])
    data.setdefault('style_ids', [])
    data.setdefault('season', [])
    data.setdefault('tags', [])
    data.setdefault('flowers', [])

    return data


async def generate_occasion(name: str, description: str = '') -> dict[str, Any] | None:
    """使用 LLM 生成场景信息。

    Args:
        name: 场景名称（如 "母亲节"、"生日"）
        description: 场景描述（可选）

    Returns:
        符合 OccasionCreate 模型的字典，失败返回 None
    """
    system = """你是花卉场景专家。请根据场景名称生成详细的场景信息。
返回 JSON 格式，包含以下字段：
- name: 场景名称
- description: 场景描述
- keywords: 关键词数组（用于检索）
- suggested_flowers: 推荐花材名称数组
- tags: 标签数组

只返回 JSON，不要其他内容。"""

    prompt = f"请生成「{name}」场景的详细信息。"
    if description:
        prompt += f"\n场景描述：{description}"

    response = await _call_llm(prompt, system)

    if not response:
        return None

    data = _parse_json_response(response)
    if not data:
        logger.warning('[generator] 无法解析 LLM 响应: %s', response[:200])
        return None

    # 验证必要字段
    if 'name' not in data:
        data['name'] = name

    data.setdefault('description', description or '')
    data.setdefault('keywords', [])
    data.setdefault('suggested_flowers', [])
    data.setdefault('tags', [])

    return data


async def generate_style(name: str, description: str = '') -> dict[str, Any] | None:
    """使用 LLM 生成风格信息。

    Args:
        name: 风格名称（如 "韩式"、"日式"）
        description: 风格描述（可选）

    Returns:
        符合 StyleCreate 模型的字典，失败返回 None
    """
    system = """你是花艺设计风格专家。请根据风格名称生成详细的风格信息。
返回 JSON 格式，包含以下字段：
- name: 风格名称
- description: 风格描述
- color_scheme: 配色方案数组
- flower_types: 常用花材类型数组
- keywords: 关键词数组（用于检索）
- tags: 标签数组

只返回 JSON，不要其他内容。"""

    prompt = f"请生成「{name}」花艺风格的详细信息。"
    if description:
        prompt += f"\n风格描述：{description}"

    response = await _call_llm(prompt, system)

    if not response:
        return None

    data = _parse_json_response(response)
    if not data:
        logger.warning('[generator] 无法解析 LLM 响应: %s', response[:200])
        return None

    # 验证必要字段
    if 'name' not in data:
        data['name'] = name

    data.setdefault('description', description or '')
    data.setdefault('color_scheme', [])
    data.setdefault('flower_types', [])
    data.setdefault('keywords', [])
    data.setdefault('tags', [])

    return data


async def batch_generate_flowers(flower_names: list[str]) -> list[dict[str, Any]]:
    """批量生成花材信息。

    Args:
        flower_names: 花材名称列表

    Returns:
        生成的花材信息列表（已过滤失败项）
    """
    results = []
    for name in flower_names:
        data = await generate_flower(name)
        if data:
            results.append(data)
            logger.info('[generator] 生成花材成功: %s', name)
        else:
            logger.warning('[generator] 生成花材失败: %s', name)
    return results
