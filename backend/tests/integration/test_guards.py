"""Permissions, tenant isolation and ledger immutability: the invariants in CLAUDE.md."""

import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

from app.db import tenant_session
from app.models import Product, StockMovement
from tests.integration.conftest import add_user, open_business


def test_cashier_can_view_but_not_change_prices_or_stock(client):
    owner = open_business(client)
    cashier = add_user(client, owner, "cashier")
    product = client.post(
        "/products", headers=owner, json={"sku": "MILK", "name": "Milk", "price_cents": 6_000}
    ).json()

    assert client.get("/products", headers=cashier).status_code == 200
    assert (
        client.post("/products", headers=cashier, json={"sku": "X", "name": "X"}).status_code == 403
    )
    resp = client.put(
        f"/products/{product['id']}/pricing",
        headers=cashier,
        json={"pricing_mode": "manual", "price_cents": 1, "reason": "x"},
    )
    assert resp.status_code == 403
    resp = client.post(
        "/stock-in-batches",
        headers=cashier,
        json={
            "date": "2026-09-29",
            "lines": [{"product_id": product["id"], "qty": "1", "bp_cents": 1}],
        },
    )
    assert resp.status_code == 403


def test_businesses_cannot_see_each_other(client):
    a = open_business(client, "A")
    b = open_business(client, "B")
    product = client.post("/products", headers=a, json={"sku": "S1", "name": "Secret"}).json()

    assert client.get(f"/products/{product['id']}", headers=b).status_code == 404
    assert client.get("/products", headers=b).json() == []
    # A's owner presenting B's business id is not a user of B.
    mixed = {"X-Business-Id": b["X-Business-Id"], "X-User-Id": a["X-User-Id"]}
    assert client.get("/products", headers=mixed).status_code == 401
    # The same SKU is fine in another business.
    assert client.post("/products", headers=b, json={"sku": "S1", "name": "Own"}).status_code == 201


def test_session_cannot_read_or_write_another_business(client):
    a = open_business(client, "A")
    b = open_business(client, "B")
    client.post("/products", headers=a, json={"sku": "S1", "name": "Secret"})
    a_id, b_id = uuid.UUID(a["X-Business-Id"]), uuid.UUID(b["X-Business-Id"])

    with tenant_session(b_id) as session:
        assert session.scalars(select(Product)).all() == []
    with pytest.raises(RuntimeError, match="does not belong"):
        with tenant_session(b_id) as session:
            session.add(Product(business_id=a_id, sku="X", name="X", wac=0, price=0))


def _post_one_delivery(client, owner) -> str:
    product = client.post("/products", headers=owner, json={"sku": "P", "name": "P"}).json()
    zero = {"transport": 0, "duty": 0, "packaging": 0, "other": 0}
    batch = client.post(
        "/stock-in-batches",
        headers=owner,
        json={
            "date": "2026-09-29",
            "lines": [{"product_id": product["id"], "qty": "1", "bp_cents": 100}],
            "costs": zero,
        },
    ).json()
    client.post(f"/stock-in-batches/{batch['id']}/post", headers=owner)
    return product["id"]


@pytest.mark.parametrize(
    "stmt", ["UPDATE stock_movements SET qty = 0", "DELETE FROM stock_movements"]
)
def test_stock_ledger_is_append_only_in_the_database(client, db_url, stmt):
    _post_one_delivery(client, open_business(client))
    engine = create_engine(db_url)
    with engine.connect() as conn, pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text(stmt))
    engine.dispose()


def test_orm_refuses_hard_deletes(client):
    owner = open_business(client)
    _post_one_delivery(client, owner)
    with pytest.raises(RuntimeError, match="hard deletes"):
        with tenant_session(uuid.UUID(owner["X-Business-Id"])) as session:
            session.delete(session.scalars(select(StockMovement)).one())


def test_client_supplied_ids_are_kept_and_duplicates_rejected(client):
    owner = open_business(client)
    pid = str(uuid.uuid4())
    body = {"id": pid, "sku": "EGG", "name": "Eggs"}
    assert client.post("/products", headers=owner, json=body).json()["id"] == pid
    assert client.post("/products", headers=owner, json=body).status_code == 409
