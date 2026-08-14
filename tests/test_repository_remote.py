"""RemoteRepository 解析 + build_repository 选择测试（Mock httpx，无真实网络）。

验证「换配置即接入真实后端」：RemoteRepository 把仓库调用透明转成 HTTP 请求，
并正确解析与 Mock 同形状的 JSON；build_repository 按 DATA_SOURCE 正确装配。
"""

from unittest.mock import MagicMock

from storage import catalog as catalog_mod
from storage import repository as repo_mod

FAKE_PLANS = [
    {
        "plan_id": "P001",
        "name": "测试方案",
        "price": 199.0,
        "desc": "x",
        "effect_image_url": "",
        "merchant_name": "m",
        "tags": ["a"],
    }
]
FAKE_SHOPS = [
    {
        "shop_id": "S001",
        "name": "店",
        "distance_km": 1.0,
        "price_range": "100-300",
        "rating": 4.8,
        "plan_ids": ["P001"],
    }
]


class _FakeResp:
    def __init__(self, payload: object) -> None:
        self._p = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._p


class _FakeClient:
    def get(self, url: str, params=None, timeout=None) -> _FakeResp:  # noqa: ANN001
        # 详情接口（含 /{id}）优先于列表接口匹配，避免 /shops/S001 被 /shops 规则误命中
        if "/plans/" in url:
            return _FakeResp(FAKE_PLANS[0])
        if url.endswith("/plans"):
            return _FakeResp(FAKE_PLANS)
        if "/shops/" in url:
            return _FakeResp(FAKE_SHOPS[0])
        if "/shops" in url:
            return _FakeResp(FAKE_SHOPS)
        return _FakeResp({})


def test_remote_repository_parses(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(repo_mod.settings, "data_source", "remote")
    monkeypatch.setattr(repo_mod.settings, "remote_api_base", "https://api.example.com")
    fake_httpx = MagicMock()
    fake_httpx.Client.return_value = _FakeClient()
    monkeypatch.setattr(repo_mod, "httpx", fake_httpx)

    r = repo_mod.RemoteRepository()
    plans = r.search_plans("康乃馨")
    assert plans[0]["plan_id"] == "P001"
    shops = r.list_shops(None, None)
    assert len(shops) == 1
    shop = r.get_shop("S001")
    assert shop["shop_id"] == "S001"
    plan = r.get_plan("P001")
    assert plan["plan_id"] == "P001"


def test_build_repository_remote(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(repo_mod.settings, "data_source", "remote")
    monkeypatch.setattr(repo_mod.settings, "remote_api_base", "https://x.com")
    r = repo_mod.build_repository()
    assert isinstance(r, repo_mod.RemoteRepository)


def test_build_repository_default_db_catalog(monkeypatch) -> None:  # noqa: ANN001
    """默认（mock 配置）走 DB 目录仓储（唯一来源），而非内存 Mock。"""
    monkeypatch.setattr(repo_mod.settings, "data_source", "mock")
    r = repo_mod.build_repository()
    assert isinstance(r, catalog_mod.DBCatalogRepository)


def test_build_repository_remote_missing_base_falls_back(monkeypatch) -> None:  # noqa: ANN001
    """DATA_SOURCE=remote 但缺 base：告警后回退到 DB 目录仓储（仍可用）。"""
    monkeypatch.setattr(repo_mod.settings, "data_source", "remote")
    monkeypatch.setattr(repo_mod.settings, "remote_api_base", "")
    r = repo_mod.build_repository()
    assert isinstance(r, catalog_mod.DBCatalogRepository)
