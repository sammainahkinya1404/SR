import uuid

import pytest

from tests.integration.conftest import add_user, open_business

ZERO_COSTS = {"transport": 0, "duty": 0, "packaging": 0, "other": 0}


@pytest.fixture
def shop(client):
    """A business with rice in stock: 10 units at WAC KSh 100, selling at KSh 150 (floor 110)."""
    owner = open_business(client)
    rice = client.post(
        "/products", headers=owner, json={"sku": "RICE", "name": "Rice 1kg", "price_cents": 15_000}
    ).json()
    batch = client.post(
        "/stock-in-batches",
        headers=owner,
        json={
            "date": "2026-09-29",
            "lines": [{"product_id": rice["id"], "qty": "10", "bp_cents": 10_000}],
            "costs": ZERO_COSTS,
        },
    ).json()
    client.post(f"/stock-in-batches/{batch['id']}/post", headers=owner)
    return {"owner": owner, "cashier": add_user(client, owner, "cashier"), "rice": rice["id"]}


def sell(client, headers, product_id, qty="1", discount=0, payments=None, **extra):
    body = {
        "lines": [{"product_id": product_id, "qty": qty, "discount_cents": discount}],
        "payments": payments if payments is not None else [],
        **extra,
    }
    return client.post("/sales", headers=headers, json=body)


def balances(client, owner):
    return {a["type"]: a["balance_cents"] for a in client.get("/accounts", headers=owner).json()}


def on_hand(client, owner, product_id):
    return client.get(f"/products/{product_id}", headers=owner).json()["qty_on_hand"]


def test_cash_sale_snapshots_cost_moves_stock_and_cash(client, shop):
    resp = sell(
        client,
        shop["cashier"],
        shop["rice"],
        qty="2",
        discount=1_000,
        payments=[{"method": "cash", "amount_cents": 30_000}],
    )
    assert resp.status_code == 201, resp.text
    sale = resp.json()
    assert sale["receipt_no"] == "000001"
    assert (sale["subtotal"], sale["discount_total"], sale["total"]) == (30_000, 1_000, 29_000)
    assert (sale["cogs"], sale["gross_profit"], sale["change_given"]) == (20_000, 9_000, 1_000)
    assert sale["lines"][0]["wac_snapshot"] == 10_000

    assert on_hand(client, shop["owner"], shop["rice"]) == "8.000"
    assert balances(client, shop["owner"]) == {"bank": 0, "cash": 29_000, "mpesa": 0}
    movements = client.get(f"/products/{shop['rice']}/movements", headers=shop["owner"]).json()
    assert (movements[-1]["type"], movements[-1]["qty"], movements[-1]["unit_cost"]) == (
        "sale",
        "-2.000",
        10_000,
    )

    receipt = client.get(f"/sales/{sale['id']}/receipt", headers=shop["cashier"]).json()
    assert "Receipt 000001" in receipt["text"] and "290.00" in receipt["text"]

    second = sell(
        client, shop["cashier"], shop["rice"], payments=[{"method": "cash", "amount_cents": 15_000}]
    )
    assert second.json()["receipt_no"] == "000002"


def test_split_mpesa_and_cash_payment(client, shop):
    resp = sell(
        client,
        shop["cashier"],
        shop["rice"],
        payments=[
            {"method": "mpesa", "amount_cents": 10_000, "mpesa_code": " sib2xk7q9m "},
            {"method": "cash", "amount_cents": 5_000},
        ],
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["payments"][0]["mpesa_code"] == "SIB2XK7Q9M"
    assert balances(client, shop["owner"]) == {"bank": 0, "cash": 5_000, "mpesa": 10_000}

    reused = sell(
        client,
        shop["cashier"],
        shop["rice"],
        payments=[{"method": "mpesa", "amount_cents": 15_000, "mpesa_code": "SIB2XK7Q9M"}],
    )
    assert reused.status_code == 409


@pytest.mark.parametrize(
    "payments",
    [
        [{"method": "cash", "amount_cents": 14_999}],  # underpaid
        [{"method": "mpesa", "amount_cents": 16_000, "mpesa_code": "AAAAAAAAAA"}],  # M-Pesa change
        [{"method": "mpesa", "amount_cents": 15_000}],  # no code
        [{"method": "mpesa", "amount_cents": 15_000, "mpesa_code": "SHORT"}],  # bad code
        [{"method": "credit", "amount_cents": 15_000}],  # phase 4
    ],
)
def test_bad_tenders_are_rejected_and_nothing_is_posted(client, shop, payments):
    assert sell(client, shop["cashier"], shop["rice"], payments=payments).status_code == 422
    assert on_hand(client, shop["owner"], shop["rice"]) == "10.000"
    assert balances(client, shop["owner"]) == {"bank": 0, "cash": 0, "mpesa": 0}


def test_retrying_a_sale_is_idempotent(client, shop):
    body = {
        "id": str(uuid.uuid4()),
        "lines": [{"product_id": shop["rice"], "qty": "1"}],
        "payments": [{"method": "cash", "amount_cents": 15_000}],
    }
    first = client.post("/sales", headers=shop["cashier"], json=body)
    again = client.post("/sales", headers=shop["cashier"], json=body)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["receipt_no"] == again.json()["receipt_no"]
    assert on_hand(client, shop["owner"], shop["rice"]) == "9.000"


def test_cannot_sell_more_than_on_hand(client, shop):
    resp = sell(
        client,
        shop["cashier"],
        shop["rice"],
        qty="11",
        payments=[{"method": "cash", "amount_cents": 165_000}],
    )
    assert resp.status_code == 422
    assert "not enough stock" in resp.json()["detail"]


def test_selling_below_the_floor_needs_the_owner_and_a_reason(client, shop):
    below = {"discount": 5_000, "payments": [{"method": "cash", "amount_cents": 10_000}]}
    assert sell(client, shop["cashier"], shop["rice"], **below).status_code == 403
    assert sell(client, shop["owner"], shop["rice"], **below).status_code == 422
    resp = sell(
        client, shop["owner"], shop["rice"], floor_override_reason="damaged packaging", **below
    )
    assert resp.status_code == 201
    assert resp.json()["lines"][0]["floor_override"] is True
    # A discount that stays above the floor is fine for a cashier.
    ok = sell(
        client,
        shop["cashier"],
        shop["rice"],
        discount=4_000,
        payments=[{"method": "cash", "amount_cents": 11_000}],
    )
    assert ok.status_code == 201


def test_partial_then_full_return_reverses_stock_and_cash(client, shop):
    sale = sell(
        client,
        shop["cashier"],
        shop["rice"],
        qty="3",
        discount=1_000,
        payments=[{"method": "cash", "amount_cents": 44_000}],
    ).json()
    line_id = sale["lines"][0]["id"]

    def ret(headers, qty):
        return client.post(
            f"/sales/{sale['id']}/returns",
            headers=headers,
            json={
                "lines": [{"sale_line_id": line_id, "qty": qty}],
                "refund_method": "cash",
                "reason": "spoilt",
            },
        )

    assert ret(shop["cashier"], "1").status_code == 403

    first = ret(shop["owner"], "1").json()
    assert (first["refund_total"], first["cogs_reversed"]) == (14_667, 10_000)
    assert (
        client.get(f"/sales/{sale['id']}", headers=shop["owner"]).json()["status"]
        == "partially_returned"
    )
    assert on_hand(client, shop["owner"], shop["rice"]) == "8.000"

    rest = ret(shop["owner"], "2").json()
    assert rest["refund_total"] == 44_000 - 14_667  # the last return takes the remainder
    after = client.get(f"/sales/{sale['id']}", headers=shop["owner"]).json()
    assert (after["status"], after["refunded_total"]) == ("returned", 44_000)
    assert after["lines"][0]["returned_qty"] == "3.000"

    assert ret(shop["owner"], "1").status_code == 422  # nothing left to return
    assert on_hand(client, shop["owner"], shop["rice"]) == "10.000"
    assert balances(client, shop["owner"])["cash"] == 0
    movements = client.get(f"/products/{shop['rice']}/movements", headers=shop["owner"]).json()
    assert [(m["type"], m["unit_cost"]) for m in movements[-2:]] == [
        ("return", 10_000),
        ("return", 10_000),
    ]


def test_sales_and_balances_stay_within_the_business(client, shop):
    sale = sell(
        client, shop["cashier"], shop["rice"], payments=[{"method": "cash", "amount_cents": 15_000}]
    ).json()
    other = open_business(client, "Other")
    assert client.get(f"/sales/{sale['id']}", headers=other).status_code == 404
    assert client.get("/sales", headers=other).json() == []
    assert balances(client, other) == {"bank": 0, "cash": 0, "mpesa": 0}
    assert client.get("/accounts", headers=shop["cashier"]).status_code == 403
