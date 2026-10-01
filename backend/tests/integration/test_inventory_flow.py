import math
import uuid

import pytest

from app import db
from tests.integration.conftest import add_user, open_business


def receive(client, headers, items, transport=0, method="by_value", **extra):
    return client.post(
        "/inventory/receive",
        headers=headers,
        json={"items": items, "transport_cents": transport, "allocation_method": method, **extra},
    )


BULK = [
    {"name": "Soda 500ml", "category": "Drinks", "qty": "20", "bp_cents": 5_000},  # value 100,000
    {"name": "Bread", "category": "Bakery", "qty": "10", "bp_cents": 2_500},  # value 25,000
]


@pytest.mark.parametrize(
    "method, shares, landed",
    [
        ("by_value", [2_400, 600], [5_120, 2_560]),  # transport split 100,000 : 25,000
        ("by_quantity", [2_000, 1_000], [5_100, 2_600]),  # split 20 : 10 units
    ],
)
def test_bulk_order_shares_transport_and_creates_new_items(client, method, shares, landed):
    owner = open_business(client)
    resp = receive(client, owner, BULK, transport=3_000, method=method)
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert (out["goods_value_cents"], out["transport_cents"]) == (125_000, 3_000)
    assert [ln["transport_share_cents"] for ln in out["lines"]] == shares
    assert [ln["landed_unit_cost_cents"] for ln in out["lines"]] == landed
    assert all(ln["new_product"] and ln["price_status"] == "set" for ln in out["lines"])

    products = {p["name"]: p for p in client.get("/products", headers=owner).json()}
    soda = products["Soda 500ml"]
    assert (soda["category"], soda["qty_on_hand"], soda["wac_cents"]) == (
        "Drinks",
        "20.000",
        landed[0],
    )
    assert soda["sku"].startswith("ITEM-")
    # Priced by the engine: cost / (1 - 20% default margin), rounded up to the next KSh 5.
    assert soda["pricing_mode"] == "target_margin"
    assert soda["price_cents"] == math.ceil(landed[0] / 0.8 / 500) * 500
    history = client.get(f"/products/{soda['id']}/price-history", headers=owner).json()
    assert [h["reason"] for h in history] == ["initial price from the pricing rule"]


def test_single_item_and_restocking_by_name(client):
    owner = open_business(client)
    first = receive(
        client,
        owner,
        [{"name": "Sugar 1kg", "category": "Dry goods", "qty": "10", "bp_cents": 15_000}],
    )
    assert first.json()["lines"][0]["transport_share_cents"] == 0
    price = first.json()["lines"][0]["price_cents"]

    # Same name, any case/spacing: adds to the existing item. Cost barely moves: price stands.
    again = receive(
        client, owner, [{"name": "  sugar 1KG ", "qty": "10", "bp_cents": 15_200}]
    ).json()["lines"][0]
    assert (again["new_product"], again["wac_cents"], again["price_status"]) == (
        False,
        15_100,
        "unchanged",
    )
    assert again["price_cents"] == price

    # A big cost rise raises a suggestion for the owner instead of changing the price.
    jump = receive(client, owner, [{"name": "Sugar 1kg", "qty": "20", "bp_cents": 20_000}]).json()[
        "lines"
    ][0]
    assert (jump["price_status"], jump["price_cents"]) == ("suggested", price)
    assert len(client.get("/price-suggestions", headers=owner).json()) == 1
    assert len(client.get("/products", headers=owner).json()) == 1


def test_the_same_new_name_twice_in_one_order_is_one_item(client):
    owner = open_business(client)
    items = [
        {"name": "Rice", "qty": "5", "bp_cents": 10_000},
        {"name": "rice", "qty": "5", "bp_cents": 12_000},
    ]
    out = receive(client, owner, items).json()
    assert [ln["new_product"] for ln in out["lines"]] == [True, True]
    assert out["lines"][0]["product_id"] == out["lines"][1]["product_id"]
    [rice] = client.get("/products", headers=owner).json()
    assert (rice["qty_on_hand"], rice["wac_cents"]) == ("10.000", 11_000)


def test_existing_item_by_id_and_guards(client):
    owner = open_business(client)
    item = client.post(
        "/products", headers=owner, json={"name": "Soap", "price_cents": 8_000}
    ).json()
    body = {
        "id": str(uuid.uuid4()),
        "items": [{"product_id": item["id"], "qty": "3", "bp_cents": 5_000}],
    }
    assert client.post("/inventory/receive", headers=owner, json=body).status_code == 201
    assert client.post("/inventory/receive", headers=owner, json=body).status_code == 409  # retry
    assert receive(client, owner, [{"qty": "1", "bp_cents": 1}]).status_code == 422  # no name/id
    cashier = add_user(client, owner, "cashier")
    assert receive(client, cashier, [{"name": "X", "qty": "1", "bp_cents": 1}]).status_code == 403


def test_product_names_are_unique_and_skus_optional(client):
    owner = open_business(client)
    first = client.post("/products", headers=owner, json={"name": "Cooking Oil 1L"}).json()
    assert first["sku"] == "ITEM-0001"
    dup = client.post("/products", headers=owner, json={"name": "cooking oil 1l"})
    assert dup.status_code == 409


def test_single_shop_setup(client, monkeypatch):
    monkeypatch.setenv("SINGLE_SHOP", "true")
    db.get_settings.cache_clear()
    assert client.get("/setup").json() == {
        "configured": False,
        "business_id": None,
        "business_name": None,
        "users": [],
    }
    owner = open_business(client, "Mama Mboga")
    again = client.post("/businesses", json={"name": "Second", "owner_name": "X"})
    assert again.status_code == 409 and "Mama Mboga" in again.json()["detail"]
    add_user(client, owner, "cashier")
    setup = client.get("/setup").json()
    assert (setup["configured"], setup["business_name"], setup["business_id"]) == (
        True,
        "Mama Mboga",
        owner["X-Business-Id"],
    )
    assert [(u["name"], u["role"]) for u in setup["users"]] == [
        ("Owner", "owner"),
        ("cashier", "cashier"),
    ]
