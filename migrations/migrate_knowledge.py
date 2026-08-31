"""migrate_knowledge.py —— 将 JSON 知识库迁移到 SQLite。

用法：
    cd flora_diy_agent
    python -m migrations.migrate_knowledge

功能：
1. 创建知识库表结构（如果不存在）
2. 从 JSON 文件导入数据到 SQLite
3. 验证迁移结果
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.storage.db import get_conn, init_db
from backend.storage.models_knowledge import KNOWLEDGE_SCHEMA, KNOWLEDGE_INDEXES

logger = logging.getLogger('migrate')

# JSON 文件路径
KNOWLEDGE_DIR = ROOT / 'agent' / 'knowledge'
JSON_FILES = {
    'flowers': KNOWLEDGE_DIR / 'flowers.json',
    'pairings': KNOWLEDGE_DIR / 'pairings.json',
    'occasions': KNOWLEDGE_DIR / 'scenes.json',
    'styles': KNOWLEDGE_DIR / 'styles.json',
    'budget': KNOWLEDGE_DIR / 'budget.json',
    'packaging': KNOWLEDGE_DIR / 'packaging.json',
}


def create_knowledge_tables() -> None:
    """创建知识库表结构。"""
    logger.info('创建知识库表结构...')
    conn = get_conn()

    # 执行建表语句
    for statement in KNOWLEDGE_SCHEMA.split(';'):
        statement = statement.strip()
        if statement:
            try:
                conn.execute(statement)
            except Exception as e:
                logger.warning(f'执行 SQL 失败: {e}\n{statement}')

    # 创建索引
    for statement in KNOWLEDGE_INDEXES.split(';'):
        statement = statement.strip()
        if statement:
            try:
                conn.execute(statement)
            except Exception as e:
                logger.warning(f'创建索引失败: {e}')

    conn.commit()
    logger.info('知识库表结构创建完成')


def load_json_file(file_path: Path) -> list[dict]:
    """加载 JSON 文件。"""
    if not file_path.exists():
        logger.warning(f'文件不存在: {file_path}')
        return []

    with open(file_path, encoding='utf-8') as f:
        data = json.load(f)

    if not isinstance(data, list):
        logger.warning(f'文件格式错误（期望数组）: {file_path}')
        return []

    return data


def migrate_flowers() -> int:
    """迁移花材数据。"""
    logger.info('迁移花材数据...')
    conn = get_conn()
    data = load_json_file(JSON_FILES['flowers'])

    count = 0
    for flower in data:
        try:
            conn.execute('''
                INSERT OR REPLACE INTO flowers (
                    id, name, aliases, flower_language, colors, season,
                    price_tier, category, pairing_notes, tags,
                    status, created_at, updated_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', datetime('now'), datetime('now'), 1)
            ''', (
                flower['id'],
                flower['name'],
                json.dumps(flower.get('aliases', []), ensure_ascii=False),
                json.dumps(flower.get('flower_language', []), ensure_ascii=False),
                json.dumps(flower.get('colors', []), ensure_ascii=False),
                json.dumps(flower.get('season', []), ensure_ascii=False),
                flower.get('price_tier', '中'),
                flower.get('category', '主花'),
                flower.get('pairing_notes', ''),
                json.dumps(flower.get('tags', []), ensure_ascii=False)
            ))
            count += 1
        except Exception as e:
            logger.error(f'迁移花材失败 {flower.get("id")}: {e}')

    conn.commit()
    logger.info(f'花材迁移完成: {count} 条')
    return count


def migrate_pairings() -> int:
    """迁移搭配方案数据。"""
    logger.info('迁移搭配方案数据...')
    conn = get_conn()
    data = load_json_file(JSON_FILES['pairings'])

    count = 0
    for pairing in data:
        try:
            # pairings.json 使用 condition 作为名称，没有 name 字段
            name = pairing.get('name') or pairing.get('condition', pairing['id'])
            description = pairing.get('recommendation', '')

            conn.execute('''
                INSERT OR REPLACE INTO pairings (
                    id, name, description, occasion_ids, style_ids,
                    budget_min, budget_max, season, tags,
                    use_count, status, created_at, updated_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', datetime('now'), datetime('now'), 1)
            ''', (
                pairing['id'],
                name,
                description,
                json.dumps([], ensure_ascii=False),  # occasion_ids
                json.dumps([], ensure_ascii=False),  # style_ids
                None,  # budget_min
                None,  # budget_max
                json.dumps([], ensure_ascii=False),  # season
                json.dumps([pairing.get('type', '')], ensure_ascii=False)  # tags
            ))

            count += 1
        except Exception as e:
            logger.error(f'迁移搭配方案失败 {pairing.get("id")}: {e}')

    conn.commit()
    logger.info(f'搭配方案迁移完成: {count} 条')
    return count


def migrate_occasions() -> int:
    """迁移场景数据。"""
    logger.info('迁移场景数据...')
    conn = get_conn()
    data = load_json_file(JSON_FILES['occasions'])

    count = 0
    for occasion in data:
        try:
            conn.execute('''
                INSERT OR REPLACE INTO occasions (
                    id, name, description, keywords, suggested_flowers, tags,
                    status, created_at, updated_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', datetime('now'), datetime('now'), 1)
            ''', (
                occasion['id'],
                occasion['name'],
                occasion.get('description', ''),
                json.dumps(occasion.get('keywords', []), ensure_ascii=False),
                json.dumps(occasion.get('suggested_flowers', []), ensure_ascii=False),
                json.dumps(occasion.get('tags', []), ensure_ascii=False)
            ))
            count += 1
        except Exception as e:
            logger.error(f'迁移场景失败 {occasion.get("id")}: {e}')

    conn.commit()
    logger.info(f'场景迁移完成: {count} 条')
    return count


def migrate_styles() -> int:
    """迁移风格数据。"""
    logger.info('迁移风格数据...')
    conn = get_conn()
    data = load_json_file(JSON_FILES['styles'])

    count = 0
    for style in data:
        try:
            conn.execute('''
                INSERT OR REPLACE INTO styles (
                    id, name, description, color_scheme, flower_types, keywords, tags,
                    status, created_at, updated_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', datetime('now'), datetime('now'), 1)
            ''', (
                style['id'],
                style['name'],
                style.get('description', ''),
                json.dumps(style.get('color_scheme', []), ensure_ascii=False),
                json.dumps(style.get('flower_types', []), ensure_ascii=False),
                json.dumps(style.get('keywords', []), ensure_ascii=False),
                json.dumps(style.get('tags', []), ensure_ascii=False)
            ))
            count += 1
        except Exception as e:
            logger.error(f'迁移风格失败 {style.get("id")}: {e}')

    conn.commit()
    logger.info(f'风格迁移完成: {count} 条')
    return count


def verify_migration() -> bool:
    """验证迁移结果。"""
    logger.info('验证迁移结果...')
    conn = get_conn()

    tables = ['flowers', 'pairings', 'pairing_flowers', 'occasions', 'styles']
    for table in tables:
        try:
            result = conn.execute(f'SELECT COUNT(*) FROM {table}')
            # SQLite 返回的是 tuple，第一个元素是计数
            count = result.fetchone()[0] if hasattr(result, 'fetchone') else result[0]
            logger.info(f'{table}: {count} 条记录')
        except Exception as e:
            logger.error(f'验证 {table} 失败: {e}')
            return False

    logger.info('迁移验证通过')
    return True


def main():
    """主函数。"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger.info('开始迁移花卉知识库...')

    # 1. 初始化数据库（创建业务表）
    init_db()

    # 2. 创建知识库表结构
    create_knowledge_tables()

    # 3. 迁移数据
    migrate_flowers()
    migrate_pairings()
    migrate_occasions()
    migrate_styles()

    # 4. 验证
    if verify_migration():
        logger.info('花卉知识库迁移完成！')
    else:
        logger.error('迁移验证失败')
        sys.exit(1)


if __name__ == '__main__':
    main()
