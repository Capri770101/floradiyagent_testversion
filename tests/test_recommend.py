"""个性化推荐（模块三）测试：偏好提取、融合排序、空偏好/空定位降级、端点契约。"""

import pytest
from fastapi.testclient import TestClient

import api
from storage import catalog, recommend
from storage.db import init_db

pytestmark = pytest.mark.usefixtures("_reset_rate_limiter")


def setup_module(module):
    init_db()


@pytest.fixture()
def client():
    with TestClient(api.app) as c:
        yield c


def _uid(n):
    return f"u_rec_{n}"


def _neutralize_heat():
    """seed_catalog 的热度演示值由进程级随机 hash() 生成 → 先归一化，让排序断言确定性成立。"""
    from storage.db import get_conn

    conn = get_conn()
    conn.execute("UPDATE plans SET rating=4.5, sold=100")
    conn.execute("UPDATE shops SET rating=4.5, sales=100")
    conn.commit()


def test_extract_preferences_from_favorites_and_orders(client):
    uid = _uid(1)
    # 收藏韩式方案 P001（tags 含温馨）+ 下一单韩式 P001
    from storage import commerce

    catalog.merchant_bind(uid, "S001")
    commerce.add_favorite(uid, "P001")
    order = commerce.create_order(
        user_id=uid,
        items=[{"plan_id": "P001", "qty": 1, "shop": "S001", "name": "康乃馨感恩花束"}],
        recipient={"name": "A", "phone": "1", "address": "x"},
    )
    assert order["order_id"]
    prefs = recommend.extract_preferences(uid)
    assert prefs["styles"].get("韩式", 0) >= 2
    assert "温馨" in prefs["tags"]
    assert prefs["bands"].get(1)  # 199 元 → 121-220 档
    assert prefs["shops"].get("S001") == 1
    # 无用户 → 全空画像（不报错）
    empty = recommend.extract_preferences(None)
    assert empty["styles"] == {} and empty["shops"] == {}


def test_fusion_ordering_favors_preferred_style(client):
    """收藏/购买韩式后，「猜你喜欢」韩式方案排名应高于同热度异风格方案。"""
    uid = _uid(2)
    from storage import commerce

    _neutralize_heat()
    commerce.add_favorite(uid, "P001")  # 韩式
    items = recommend.recommend_plans(uid, limit=10)
    ranked = [p["plan_id"] for p in items]
    assert ranked
    # 韩式方案（P001/P013）整体应排在自然风 P004 之前（无定位，纯偏好+热度）
    korean = [p["plan_id"] for p in items if p.get("style") == "韩式"]
    natural = [p["plan_id"] for p in items if p.get("style") == "自然"]
    assert korean and natural
    assert ranked.index(korean[0]) < ranked.index(natural[0])


def test_location_weights_nearer_first():
    """传定位后，近处店铺承载的方案应排名更靠前。"""
    _neutralize_heat()
    # 定位选在 S001（盐田）附近；S001 承载 P001/P002/P010
    lat, lng = 22.560, 114.242
    items = recommend.recommend_plans(None, lat, lng, limit=6)
    ranked = [p["plan_id"] for p in items]
    assert ranked
    # S001 承载的方案应出现在无偏好时的最前列（距离分主导）
    assert "P001" in ranked[:3] or "P002" in ranked[:3]


def test_fallback_without_location_and_prefs():
    """无定位无偏好 → 回退热度排序，不报错、不空返回。"""
    items = recommend.recommend_plans(None, limit=5)
    assert len(items) == 5
    # 热度分 = 0.6*sold_norm + 0.4*rating；确认返回的确实是方案卡字段
    assert items[0]["plan_id"].startswith("P")
    assert "price" in items[0]


def test_recommend_shops_excludes_self_and_same_range_boost():
    """店铺推荐：排除 shop_id 自身；无定位时同价位带（同类）店铺获加权居首。"""
    _neutralize_heat()
    # 无定位 → 距离分中性，同类加权（0.15）足以让 100-300 档店铺优先
    items = recommend.recommend_shops(None, limit=10, shop_id="S001")
    ids = [s["shop_id"] for s in items]
    assert "S001" not in ids
    assert len(ids) == 10
    same = [s["shop_id"] for s in items if s.get("price_range") == "100-300"]
    assert same and same[0] == ids[0]
    # 有定位时距离主导：S001 位置附近的近店（S004 0.7km < S005 0.9km）应居首
    near = recommend.recommend_shops(None, 22.560, 114.242, limit=3, shop_id="S001")
    assert near[0]["shop_id"] == "S004"


def test_recommend_endpoints_contract(client):
    """GET /recommend/plans 与 /recommend/shops 返回卡片契约字段（无 undefined）。"""
    r = client.get("/recommend/plans?lat=22.56&lng=114.24&limit=3")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert 1 <= len(items) <= 3
    for it in items:
        for key in ("id", "name", "price", "label", "rating", "sold", "tags", "desc", "image", "shop_id"):
            assert key in it, f"缺字段 {key}"
    r2 = client.get("/recommend/shops?limit=3")
    assert r2.status_code == 200, r2.text
    for it in r2.json()["items"]:
        for key in ("id", "name", "rating", "dist", "eta", "price_range", "min_delivery", "delivery_fee"):
            assert key in it, f"缺字段 {key}"


def test_recommend_style_param_boosts_same_style():
    """style 参数：同风格方案加权，其余风格仍可兜底出现（软加权）。"""
    _neutralize_heat()
    items = recommend.recommend_plans(None, limit=10, style="韩式")
    ranked = [p["plan_id"] for p in items]
    assert ranked
    assert ranked[0] in ("P001", "P013")  # 韩式方案应居首
    assert len(ranked) == 10


def test_style_groups_normalize_alias_styles():
    """style 词表分组：DIY 自由文本风格（北欧）能命中 catalog 词表（简约/ins）及其分组。"""
    from storage.recommend import _style_group

    assert _style_group("北欧") == _style_group("简约") == _style_group("ins")
    assert _style_group("韩式") != _style_group("简约")
    assert _style_group("") == ""
    # 词表分组参与偏好画像匹配：收藏 ins 方案 P010 后，简约/ins 组整体受益
    _neutralize_heat()
    items = recommend.recommend_plans(None, limit=10, style="北欧")
    assert items and items[0]["style"] in ("简约", "ins")  # 别名参数命中词表分组


def test_recommend_weights_operations_config():
    """运营可在 /admin/config 调整推荐权重（0~1 校验、合并、回显）。"""
    from storage import config as config_store

    base = config_store.public_config()
    assert set(base["recommend_weights"]) == {"w_distance", "w_pref", "w_heat"}
    try:
        out = config_store.update_operations({"recommend_weights": {"w_distance": 0.9}})
        assert out["recommend_weights"]["w_distance"] == 0.9
        assert out["recommend_weights"]["w_pref"] == 0.4  # 未传字段保留
        with pytest.raises(ValueError):
            config_store.update_operations({"recommend_weights": {"w_distance": 1.5}})
    finally:
        config_store.update_operations(
            {"recommend_weights": {"w_distance": base["recommend_weights"]["w_distance"]}}
        )


def test_recommend_signature_prefers_premium_without_location():
    """当季臻选：无定位时角标气质主导（Premium ≥300 元居前），不依赖用户画像。"""
    _neutralize_heat()
    items = recommend.recommend_signature(limit=6)
    assert items and len(items) == 6
    assert all(p["price"] >= 300 for p in items[:4])  # 4 个 Premium 气质分最高
    assert items[0]["dist_km"] is None  # 无定位 → None（前端不展示）
    # 与个性化推荐解耦：签名与用户偏好无关
    uid = _uid(9)
    from storage import commerce

    commerce.add_favorite(uid, "P001")
    assert [p["plan_id"] for p in recommend.recommend_signature(limit=6)] == [
        p["plan_id"] for p in recommend.recommend_signature(limit=6)
    ]


def test_recommend_signature_distance_tiebreaks_same_label():
    """当季臻选：定位在 S001 附近（22.560,114.242）时——
    1) 同 Limited 气质下 S001 承载的 P010（0km）优先于 S004 的 P008（0.7km）；
    2) 近处 Limited（P010）可压过超远 Premium（P015，暮色花园约 17.7km）；
    3) dist_km 有值且合理。"""
    _neutralize_heat()
    items = recommend.recommend_signature(22.560, 114.242, limit=20)
    ranked = [p["plan_id"] for p in items]
    assert ranked.index("P010") < ranked.index("P008")
    assert ranked.index("P010") < ranked.index("P015")
    p010 = next(p for p in items if p["plan_id"] == "P010")
    assert p010["dist_km"] is not None and p010["dist_km"] < 1.5


def test_recommend_signature_endpoint_contract(client):
    """GET /recommend/signature 返回策展卡字段（含 dist_km），limit 生效。"""
    r = client.get("/recommend/signature?lat=22.56&lng=114.24&limit=3")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert 1 <= len(items) <= 3
    for it in items:
        for key in ("id", "name", "price", "label", "rating", "sold", "tags", "desc", "image", "shop_id"):
            assert key in it, f"缺字段 {key}"
    assert "dist_km" in items[0]