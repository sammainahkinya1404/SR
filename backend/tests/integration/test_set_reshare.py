from tests.integration.conftest import add_user, open_business

PIECES = [("Large plate", 15_000), ("Small plate", 12_000), ("Bowl", 13_000), ("Cup", 9_000)]


def test_resharing_existing_stock_cost_by_price(client):
    """The real case: a dinner set bought for KSh 2,500, entered as 4 items at an equal cost."""
    owner = open_business(client)
    received = client.post(
        "/inventory/receive",
        headers=owner,
        json={"items": [{"name": n, "qty": "6", "bp_cents": 10_420} for n, _ in PIECES]},
    ).json()
    ids = [ln["product_id"] for ln in received["lines"]]
    dinner = client.post(
        "/sets",
        headers=owner,
        json={
            "name": "Dinner set",
            "components": [
                {"product_id": pid, "qty_per_set": "6", "price_cents": price}
                for pid, (_, price) in zip(ids, PIECES, strict=True)
            ],
        },
    ).json()
    before = sum(p["stock_value_cents"] for p in client.get("/products", headers=owner).json())

    resp = client.post(
        f"/sets/{dinner['id']}/reshare-cost", headers=owner, json={"reason": "split by price"}
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["value_cents"] == 4 * 6 * 10_420  # KSh 2,500.80
    # Each piece now costs the same fraction of its price: 2,500.80 / (6 x 490) = 85.06%.
    costs = [c["wac_cents"] for c in out["set"]["components"]]
    assert costs == [12_759, 10_207, 11_058, 7_656]
    ratios = {round(c / p, 3) for c, (_, p) in zip(costs, PIECES, strict=True)}
    assert ratios == {0.851}
    after = sum(p["stock_value_cents"] for p in client.get("/products", headers=owner).json())
    assert abs(after - before) <= 3  # total cost kept, up to rounding cents

    # Ledger replay agrees with the new costs (dashboard stock value uses the movements).
    dashboard = client.get("/dashboard", headers=owner).json()
    assert dashboard["periods"]["today"]["metrics"]["stock_value"]["value"] == after
    moves = client.get(f"/products/{ids[0]}/movements", headers=owner).json()
    assert [(m["type"], m["qty"], m["wac_snapshot"]) for m in moves[-2:]] == [
        ("adjustment", "-6.000", 10_420),
        ("adjustment", "6.000", 12_759),
    ]

    cashier = add_user(client, owner, "cashier")
    denied = client.post(
        f"/sets/{dinner['id']}/reshare-cost", headers=cashier, json={"reason": "x"}
    )
    assert denied.status_code == 403
