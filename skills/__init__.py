"""技能（Skill）自动发现：skills/ 下每个模块自描述、自注册到工具注册表。

新增技能只需：在此目录新建模块 -> 调用 register_tool 注册。启动时自动加载。
"""
import importlib
import logging
import pkgutil

logger = logging.getLogger(__name__)


def load_skills() -> None:
    """扫描并导入 skills 包内所有非下划线开头的模块（模块自身完成注册）。"""
    for module in pkgutil.iter_modules(__path__):
        if module.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module.name}")
        logger.info("技能已加载: %s", module.name)