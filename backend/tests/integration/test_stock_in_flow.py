from tests.integration.conftest import add_user, open_business


def _product(client, owner, sku, **extra):
    resp = client.post("/products", headers=owner, json={"sku": sku, "name": sku, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _batch(client, owner, lines, costs):
    resp = client.post(
        "/stock-in-batches",
        headers=owner,
        json={"date": "2026-09-29", "lines": lines, "costs": costs},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_stock_in_landed_cost_wac_and_repricing(client):
    owner = open_business(client)
    rice = _product(client, owner, "RICE", price_cents=12_000)
    sugar = _product(client, owner, "SUGAR", pricing_mode="target_margin", target_value="0.25")

    batch = _batch(
        client,
        owner,
        lines=[
            {"product_id": rice["id"], "qty": "10", "bp_cents": 10_000},  # value 100,000
            {"product_id": sugar["id"], "qty": "20", "bp_cents": 2_500},  # value 50,000
        ],
        costs={"transport": 3_000, "duty": 0, "packaging": 0},
    )
    assert batch["missing_costs"] == ["other"]

    # Posting is blocked until every shared cost is entered or explicitly zero.
    resp = client.post(f"/stock-in-batches/{batch['id']}/post", headers=owner)
    assert resp.status_code == 422
    resp = client.put(
        f"/stock-in-batches/{batch['id']}/costs/other", headers=owner, json={"amount_cents": 0}
    )
    assert resp.json()["missing_costs"] == []

    posted = client.post(f"/stock-in-batches/{batch['id']}/post", headers=owner).json()
    assert posted["status"] == "posted"
    # 3,000 shared split by value 2:1, then (BP x qty + allocated) / qty.
    lines = [(ln["allocated_cost_cents"], ln["landed_unit_cost_cents"]) for ln in posted["lines"]]
    assert lines == [(2_000, 10_200), (1_000, 2_550)]

    rice_now = client.get(f"/products/{rice['id']}", headers=owner).json()
    assert rice_now["wac_cents"] == 10_200
    assert rice_now["qty_on_hand"] == "10.000"
    assert rice_now["stock_value_cents"] == 102_000

    # Posting twice is refused.
    assert client.post(f"/stock-in-batches/{batch['id']}/post", headers=owner).status_code == 409

    # Sugar is target-margin priced: 2,550 / 0.75 = 3,400 -> nearest KSh 5 = 3,500.
    # Rice is manual with no previous cost, so there is no margin to preserve and no suggestion.
    pending = client.get("/price-suggestions", headers=owner).json()
    assert [(s["product_id"], s["suggested_price"]) for s in pending] == [(sugar["id"], 3_500)]

    approved = client.post(f"/price-suggestions/{pending[0]['id']}/approve", headers=owner)
    assert approved.json()["status"] == "approved"
    sugar_now = client.get(f"/products/{sugar['id']}", headers=owner).json()
    assert sugar_now["price_cents"] == 3_500
    history = client.get(f"/products/{sugar['id']}/price-history", headers=owner).json()
    assert [(h["old_price"], h["new_price"]) for h in history] == [(0, 3_500)]

    # Second delivery of rice at a higher cost: WAC (10 x 10,200 + 10 x 12,000) / 20 = 11,100,
    # an 8.8% move. Manual price keeps its 15% margin: 11,100 / 0.85 = 13,059 -> up to 13,500.
    zero = {"transport": 0, "duty": 0, "packaging": 0, "other": 0}
    batch2 = _batch(
        client, owner, [{"product_id": rice["id"], "qty": "10", "bp_cents": 12_000}], zero
    )
    client.post(f"/stock-in-batches/{batch2['id']}/post", headers=owner)

    rice_now = client.get(f"/products/{rice['id']}", headers=owner).json()
    assert rice_now["wac_cents"] == 11_100
    assert rice_now["qty_on_hand"] == "20.000"
    movements = client.get(f"/products/{rice['id']}/movements", headers=owner).json()
    assert [(m["type"], m["unit_cost"], m["wac_snapshot"]) for m in movements] == [
        ("purchase", 10_200, 10_200),
        ("purchase", 12_000, 11_100),
    ]
    pending = client.get("/price-suggestions", headers=owner).json()
    assert [(s["product_id"], s["suggested_price"]) for s in pending] == [(rice["id"], 13_500)]


def test_rule_based_pricing_uses_wac_and_rounding(client):
    owner = open_business(client)
    item = _product(client, owner, "SOAP")
    zero = {"transport": 0, "duty": 0, "packaging": 0, "other": 0}
    batch = _batch(client, owner, [{"product_id": item["id"], "qty": "4", "bp_cents": 8_000}], zero)
    client.post(f"/stock-in-batches/{batch['id']}/post", headers=owner)

    resp = client.put(
        f"/products/{item['id']}/pricing",
        headers=owner,
        json={"pricing_mode": "markup", "target_value": "0.3", "reason": "new policy"},
    )
    body = resp.json()
    assert body["price_cents"] == 10_500  # 8,000 x 1.3 = 10,400 -> nearest KSh 5
    assert body["floor_price_cents"] == 8_800
    assert not body["below_floor"]


def test_deliveries_can_be_listed_by_status(client):
    owner = open_business(client)
    item = _product(client, owner, "SOAP")
    zero = {"transport": 0, "duty": 0, "packaging": 0, "other": 0}
    line = [{"product_id": item["id"], "qty": "1", "bp_cents": 100}]
    posted = _batch(client, owner, line, zero)
    client.post(f"/stock-in-batches/{posted['id']}/post", headers=owner)
    draft = _batch(client, owner, line, {})

    drafts = client.get("/stock-in-batches", headers=owner, params={"status": "draft"}).json()
    assert [(b["id"], b["missing_costs"]) for b in drafts] == [
        (draft["id"], ["transport", "duty", "packaging", "other"])
    ]
    assert len(client.get("/stock-in-batches", headers=owner).json()) == 2
    cashier = {**owner, "X-User-Id": add_user(client, owner, "cashier")["X-User-Id"]}
    assert client.get("/stock-in-batches", headers=cashier).status_code == 403
