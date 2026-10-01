import pytest

from tests.integration.conftest import add_user, open_business


@pytest.fixture
def shop(client):
    """Two items at cost KSh 100 (automatic floor KSh 110), selling at KSh 150 and KSh 200."""
    owner = open_business(client)
    out = client.post(
        "/inventory/receive",
        headers=owner,
        json={
            "items": [
                {"name": "Karai", "qty": "10", "bp_cents": 10_000},
                {"name": "Sufuria", "qty": "10", "bp_cents": 10_000},
            ]
        },
    ).json()
    ids = [ln["product_id"] for ln in out["lines"]]
    for pid, price in zip(ids, (15_000, 20_000), strict=True):
        client.put(
            f"/products/{pid}/pricing",
            headers=owner,
            json={"pricing_mode": "manual", "price_cents": price, "reason": "set"},
        )
    return {
        "owner": owner,
        "cashier": add_user(client, owner, "cashier"),
        "karai": ids[0],
        "sufuria": ids[1],
    }


def set_min(client, headers, *items):
    return client.put(
        "/products/min-prices",
        headers=headers,
        json={"items": [{"product_id": p, "min_price_cents": m} for p, m in items]},
    )


def sell_at(client, headers, product_id, unit_price, list_price=15_000, **extra):
    """Sell one unit at a bargained price: the POS sends the difference as a discount."""
    return client.post(
        "/sales",
        headers=headers,
        json={
            "lines": [
                {"product_id": product_id, "qty": "1", "discount_cents": list_price - unit_price}
            ],
            "payments": [{"method": "cash", "amount_cents": unit_price}],
            **extra,
        },
    )


def test_minimums_are_set_in_bulk_and_define_the_range(client, shop):
    resp = set_min(client, shop["owner"], (shop["karai"], 12_000), (shop["sufuria"], 17_500))
    assert resp.status_code == 200
    assert [
        (p["min_price_cents"], p["floor_price_cents"], p["price_cents"]) for p in resp.json()
    ] == [
        (12_000, 12_000, 15_000),
        (17_500, 17_500, 20_000),
    ]
    # Clearing a minimum brings back the automatic floor (cost + 10%).
    karai = client.get(f"/products/{shop['karai']}", headers=shop["owner"]).json()
    assert karai["auto_floor_price_cents"] == 11_000  # still known while a minimum is set
    cleared = set_min(client, shop["owner"], (shop["karai"], None)).json()[0]
    assert (cleared["min_price_cents"], cleared["floor_price_cents"]) == (None, 11_000)


def test_cashiers_can_bargain_within_the_range_only(client, shop):
    set_min(client, shop["owner"], (shop["karai"], 12_000))
    assert sell_at(client, shop["cashier"], shop["karai"], 12_000).status_code == 201  # at the min
    below = sell_at(client, shop["cashier"], shop["karai"], 11_500)  # above cost+10%, below min
    assert below.status_code == 403
    assert "Karai (min KSh 120.00)" in below.json()["detail"]
    ok = sell_at(
        client, shop["owner"], shop["karai"], 11_500, floor_override_reason="loyal customer"
    )
    assert ok.status_code == 201 and ok.json()["lines"][0]["floor_override"] is True


def test_minimum_must_sit_within_the_range(client, shop):
    too_high = set_min(client, shop["owner"], (shop["karai"], 15_001))
    assert too_high.status_code == 422 and "above the selling price" in too_high.json()["detail"]
    unpriced = client.post("/products", headers=shop["owner"], json={"name": "New"}).json()
    assert set_min(client, shop["owner"], (unpriced["id"], 100)).status_code == 422
    assert set_min(client, shop["cashier"], (shop["karai"], 12_000)).status_code == 403
    # All-or-nothing: one bad item leaves the others unchanged.
    assert (
        set_min(
            client, shop["owner"], (shop["sufuria"], 18_000), (shop["karai"], 99_999)
        ).status_code
        == 422
    )
    sufuria = client.get(f"/products/{shop['sufuria']}", headers=shop["owner"]).json()
    assert sufuria["min_price_cents"] is None


def test_lowering_the_price_below_the_minimum_brings_the_minimum_down(client, shop):
    set_min(client, shop["owner"], (shop["karai"], 14_000))
    after = client.put(
        f"/products/{shop['karai']}/pricing",
        headers=shop["owner"],
        json={"pricing_mode": "manual", "price_cents": 13_000, "reason": "promotion"},
    ).json()
    assert (after["price_cents"], after["min_price_cents"]) == (13_000, 13_000)
