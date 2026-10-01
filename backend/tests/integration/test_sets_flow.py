import pytest

from tests.integration.conftest import add_user, open_business

SIZES = [
    ("Sufuria size 1", 20_000),
    ("Sufuria size 2", 25_000),
    ("Sufuria size 3", 30_000),
    ("Sufuria size 4", 35_000),
    ("Sufuria size 5", 40_000),
]


def create_set(client, headers, name, components, category="Sufuria"):
    return client.post(
        "/sets",
        headers=headers,
        json={"name": name, "category": category, "components": components},
    )


def new_component(name, price, qty="1"):
    return {"name": name, "qty_per_set": qty, "price_cents": price}


def existing_component(product_id, price, qty="1"):
    return {"product_id": product_id, "qty_per_set": qty, "price_cents": price}


@pytest.fixture
def shop(client):
    owner = open_business(client)
    sufuria = create_set(client, owner, "Sufuria set 1-5", [new_component(n, p) for n, p in SIZES])
    assert sufuria.status_code == 201, sufuria.text
    return {"owner": owner, "sufuria": sufuria.json()}


def products_by_name(client, headers):
    return {p["name"]: p for p in client.get("/products", headers=headers).json()}


def test_a_set_defines_separately_priced_items(client, shop):
    s = shop["sufuria"]
    assert s["set_value_cents"] == 150_000
    assert [(c["name"], c["price_cents"], c["qty_on_hand"]) for c in s["components"]] == [
        (n, p, "0.000") for n, p in SIZES
    ]
    items = products_by_name(client, shop["owner"])
    assert items["Sufuria size 3"]["pricing_mode"] == "manual"
    assert items["Sufuria size 3"]["category"] == "Sufuria"


def test_receiving_sets_stocks_every_size_with_cost_shared_by_price(client, shop):
    # 2 sets at KSh 1,200 each (by name, any case), plus KSh 100 transport.
    resp = client.post(
        "/inventory/receive",
        headers=shop["owner"],
        json={
            "items": [{"name": "sufuria SET 1-5", "qty": "2", "bp_cents": 120_000}],
            "transport_cents": 10_000,
        },
    )
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["goods_value_cents"] == 240_000
    assert [(ln["name"], ln["set_name"], ln["qty"], ln["bp_cents"]) for ln in out["lines"]] == [
        (n, "Sufuria set 1-5", "2.000", p * 4 // 5) for n, p in SIZES
    ]
    assert sum(ln["transport_share_cents"] for ln in out["lines"]) == 10_000
    assert all(ln["price_status"] == "unchanged" for ln in out["lines"])  # owner prices stand
    assert products_by_name(client, shop["owner"])["Sufuria size 5"]["qty_on_hand"] == "2.000"
    # Every size earns the same margin before transport: 1 - 1,200 / 1,500 = 20%.
    margins = {
        round((price - ln["bp_cents"]) / price, 4)
        for (_, price), ln in zip(SIZES, out["lines"], strict=True)
    }
    assert margins == {0.2}


def test_a_dinner_set_of_existing_items_with_several_units_each(client, shop):
    owner = shop["owner"]
    parts = [
        client.post("/products", headers=owner, json={"name": n, "price_cents": p}).json()
        for n, p in [
            ("Large plate", 15_000),
            ("Small plate", 12_000),
            ("Bowl", 13_000),
            ("Cup", 9_000),
        ]
    ]
    dinner = create_set(
        client,
        owner,
        "Dinner set",
        [existing_component(p["id"], p["price_cents"], "6") for p in parts],
        category="Dinner Set",
    ).json()
    assert dinner["set_value_cents"] == 6 * (15_000 + 12_000 + 13_000 + 9_000)
    out = client.post(
        "/inventory/receive",
        headers=owner,
        json={"items": [{"set_id": dinner["id"], "qty": "1", "bp_cents": 262_685}]},
    ).json()
    assert [ln["qty"] for ln in out["lines"]] == ["6.000"] * 4
    booked = sum(ln["bp_cents"] * 6 for ln in out["lines"])
    batch = client.get("/stock-in-batches", headers=owner).json()[0]
    # Rounding cents are booked as "other" cost so the delivery totals exactly what was paid.
    assert booked + batch["costs"]["other"] == 262_685


def test_editing_a_set_changes_prices_and_membership(client, shop):
    s = shop["sufuria"]
    comps = [existing_component(c["product_id"], c["price_cents"]) for c in s["components"][:4]]
    comps[0]["price_cents"] = 22_000
    resp = client.put(
        f"/sets/{s['id']}",
        headers=shop["owner"],
        json={"name": "Sufuria set 1-4", "components": comps},
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["name"] == "Sufuria set 1-4"
    assert [c["name"] for c in updated["components"]] == [n for n, _ in SIZES[:4]]
    assert updated["components"][0]["price_cents"] == 22_000
    history = client.get(
        f"/products/{comps[0]['product_id']}/price-history", headers=shop["owner"]
    ).json()
    assert history[-1]["new_price"] == 22_000
    # Size 5 left the set, so it can now join another one.
    size5 = s["components"][4]["product_id"]
    other = create_set(client, shop["owner"], "Big pots", [existing_component(size5, 40_000)])
    assert other.status_code == 201


def test_names_and_membership_are_guarded(client, shop):
    owner = shop["owner"]
    size1 = shop["sufuria"]["components"][0]["product_id"]
    same_as_item = create_set(client, owner, "Sufuria size 1", [new_component("X", 1)])
    assert same_as_item.status_code == 409
    assert (
        client.post("/products", headers=owner, json={"name": "sufuria set 1-5"}).status_code == 409
    )
    taken = create_set(client, owner, "Another", [existing_component(size1, 1)])
    assert taken.status_code == 409 and "already in the set" in taken.json()["detail"]
    cashier = add_user(client, owner, "cashier")
    assert create_set(client, cashier, "Nope", [new_component("Y", 1)]).status_code == 403
    assert len(client.get("/sets", headers=cashier).json()) == 1  # cashiers can see sets


def test_existing_stock_converts_into_a_sets_sizes_keeping_its_cost(client, shop):
    owner = shop["owner"]
    old = client.post(
        "/inventory/receive",
        headers=owner,
        json={"items": [{"name": "Sufuria(1-5)", "qty": "5", "bp_cents": 30_524}]},
    ).json()["lines"][0]
    s = shop["sufuria"]
    before = sum(p["stock_value_cents"] for p in client.get("/products", headers=owner).json())
    resp = client.post(
        f"/sets/{s['id']}/convert-stock",
        headers=owner,
        json={
            "sources": [{"product_id": old["product_id"], "qty": "5"}],
            "targets": [{"product_id": c["product_id"], "qty": "1"} for c in s["components"]],
            "reason": "split the old set item into sizes",
        },
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["value_moved_cents"] == 5 * 30_524
    # KSh 1,526.20 of cost shared by price 200:250:300:350:400.
    assert [c["wac_cents"] for c in out["set"]["components"]] == [
        20_349,
        25_437,
        30_524,
        35_611,
        40_699,
    ]
    assert all(c["qty_on_hand"] == "1.000" for c in out["set"]["components"])
    active = client.get("/products", headers=owner).json()
    assert "Sufuria(1-5)" not in {p["name"] for p in active}  # emptied source is deactivated
    after = sum(p["stock_value_cents"] for p in active)
    assert abs(after - before) <= 2  # value preserved up to rounding cents
    moves = client.get(f"/products/{old['product_id']}/movements", headers=owner).json()
    assert (moves[-1]["type"], moves[-1]["qty"]) == ("adjustment", "-5.000")

    bad_target = client.post(
        f"/sets/{s['id']}/convert-stock",
        headers=owner,
        json={
            "sources": [{"product_id": s["components"][0]["product_id"], "qty": "1"}],
            "targets": [{"product_id": old["product_id"], "qty": "1"}],
            "reason": "x",
        },
    )
    assert bad_target.status_code == 422
