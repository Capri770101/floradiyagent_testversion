"""knowledge/importer.py —— 知识库导入/同步模块。

支持从多种来源导入知识：
- JSON 文件导入
- LLM 生成导入
- 批量导入
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.storage import knowledge_db as kdb

logger = logging.getLogger('knowledge.importer')

# 知识库 JSON 文件路径
KNOWLEDGE_DIR = Path(__file__).resolve().parent
JSON_FILES = {
    'flowers': KNOWLEDGE_DIR / 'flowers.json',
    'pairings': KNOWLEDGE_DIR / 'pairings.json',
    'occasions': KNOWLEDGE_DIR / 'scenes.json',
    'styles': KNOWLEDGE_DIR / 'styles.json',
    'budget': KNOWLEDGE_DIR / 'budget.json',
    'packaging': KNOWLEDGE_DIR / 'packaging.json',
}


def _load_json(file_path: Path) -> list[dict[str, Any]]:
    """加载 JSON 文件。"""
    if not file_path.exists():
        logger.warning('[importer] 文件不存在: %s', file_path)
        return []

    with open(file_path, encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        logger.warning('[importer] 文件格式错误: %s', file_path)
        return []

    return data


async def import_flowers_from_json(source: str = 'import') -> int:
    """从 JSON 文件导入花材到数据库。

    Args:
        source: 数据来源标记

    Returns:
        成功导入的数量
    """
    data = _load_json(JSON_FILES['flowers'])
    if not data:
        return 0

    count = 0
    for flower in data:
        try:
            # 检查是否已存在
            existing = await kdb.get_flower(flower['id'])
            if existing:
                logger.debug('[importer] 花材已存在，跳过: %s', flower['id'])
                continue

            await kdb.create_flower(flower, source=source)
            count += 1
        except Exception as e:
            logger.error('[importer] 导入花材失败 %s: %s', flower.get('id'), e)

    logger.info('[importer] 花材导入完成: %d 条', count)
    return count


async def import_pairings_from_json(source: str = 'import') -> int:
    """从 JSON 文件导入搭配方案到数据库。"""
    data = _load_json(JSON_FILES['pairings'])
    if not data:
        return 0

    count = 0
    for pairing in data:
        try:
            existing = await kdb.get_pairing(pairing['id'])
            if existing:
                continue

            # 转换格式
            name = pairing.get('name') or pairing.get('condition', pairing['id'])
            description = pairing.get('recommendation', '')

            await kdb.create_pairing({
                'id': pairing['id'],
                'name': name,
                'description': description,
                'occasion_ids': [],
                'style_ids': [],
                'season': [],
                'tags': [pairing.get('type', '')],
            }, source=source)
            count += 1
        except Exception as e:
            logger.error('[importer] 导入搭配方案失败 %s: %s', pairing.get('id'), e)

    logger.info('[importer] 搭配方案导入完成: %d 条', count)
    return count


async def import_occasions_from_json(source: str = 'import') -> int:
    """从 JSON 文件导入场景到数据库。"""
    data = _load_json(JSON_FILES['occasions'])
    if not data:
        return 0

    count = 0
    for occasion in data:
        try:
            existing = await kdb.get_occasion(occasion['id'])
            if existing:
                continue

            await kdb.create_occasion(occasion, source=source)
            count += 1
        except Exception as e:
            logger.error('[importer] 导入场景失败 %s: %s', occasion.get('id'), e)

    logger.info('[importer] 场景导入完成: %d 条', count)
    return count


async def import_styles_from_json(source: str = 'import') -> int:
    """从 JSON 文件导入风格到数据库。"""
    data = _load_json(JSON_FILES['styles'])
    if not data:
        return 0

    count = 0
    for style in data:
        try:
            existing = await kdb.get_style(style['id'])
            if existing:
                continue

            await kdb.create_style(style, source=source)
            count += 1
        except Exception as e:
            logger.error('[importer] 导入风格失败 %s: %s', style.get('id'), e)

    logger.info('[importer] 风格导入完成: %d 条', count)
    return count


async def import_all_from_json(source: str = 'import') -> dict[str, int]:
    """从所有 JSON 文件导入数据。

    Returns:
        各类型导入数量统计
    """
    results = {
        'flowers': await import_flowers_from_json(source),
        'pairings': await import_pairings_from_json(source),
        'occasions': await import_occasions_from_json(source),
        'styles': await import_styles_from_json(source),
    }

    total = sum(results.values())
    logger.info('[importer] 全量导入完成，共 %d 条: %s', total, results)
    return results


async def import_flower_from_llm(flower_name: str) -> dict[str, Any] | None:
    """使用 LLM 生成并导入花材。

    Args:
        flower_name: 花材名称

    Returns:
        生成的花材信息，失败返回 None
    """
    from agent.knowledge.generator import generate_flower

    data = await generate_flower(flower_name)
    if not data:
        return None

    # 检查是否已存在
    flower_id = f'F_{flower_name.upper().replace(" ", "_")}'
    data['id'] = flower_id

    existing = await kdb.get_flower(flower_id)
    if existing:
        logger.info('[importer] 花材已存在，更新: %s', flower_id)
        await kdb.update_flower(flower_id, data, updated_by='llm_generator', reason='LLM 生成更新')
    else:
        await kdb.create_flower(data, created_by='llm_generator', source='llm')
        logger.info('[importer] LLM 生成花材成功: %s', flower_name)

    return data


async def import_flowers_batch_from_llm(flower_names: list[str]) -> list[dict[str, Any]]:
    """批量使用 LLM 生成并导入花材。

    Args:
        flower_names: 花材名称列表

    Returns:
        成功导入的花材信息列表
    """
    from agent.knowledge.generator import batch_generate_flowers

    generated = await batch_generate_flowers(flower_names)
    results = []

    for data in generated:
        try:
            flower_id = f'F_{data["name"].upper().replace(" ", "_")}'
            data['id'] = flower_id

            existing = await kdb.get_flower(flower_id)
            if existing:
                await kdb.update_flower(flower_id, data, updated_by='llm_generator')
            else:
                await kdb.create_flower(data, created_by='llm_generator', source='llm')

            results.append(data)
        except Exception as e:
            logger.error('[importer] 导入 LLM 生成花材失败: %s', e)

    logger.info('[importer] 批量 LLM 导入完成: %d/%d', len(results), len(flower_names))
    return results
