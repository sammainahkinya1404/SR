import datetime as dt
import uuid

import pytest

from app import jobs
from app.db import tenant_session
from app.domain.clock import business_today
from app.models import Business
from app.services import reminders
from tests.integration.conftest import add_user, open_business

ZERO_COSTS = {"transport": 0, "duty": 0, "packaging": 0, "other": 0}
TODAY = business_today()


@pytest.fixture
def shop(client):
    """Rice: 20 at WAC KSh 100, price KSh 150. Wanjiku: KSh 500 limit, 30-day terms."""
    owner = open_business(client)
    rice = client.post(
        "/products", headers=owner, json={"sku": "RICE", "name": "Rice", "price_cents": 15_000}
    ).json()
    batch = client.post(
        "/stock-in-batches",
        headers=owner,
        json={
            "date": "2026-09-29",
            "lines": [{"product_id": rice["id"], "qty": "20", "bp_cents": 10_000}],
            "costs": ZERO_COSTS,
        },
    ).json()
    client.post(f"/stock-in-batches/{batch['id']}/post", headers=owner)
    wanjiku = client.post(
        "/customers",
        headers=owner,
        json={
            "name": "Wanjiku",
            "phone": "0712345678",
            "credit_limit_cents": 50_000,
            "terms_days": 30,
        },
    ).json()
    return {
        "owner": owner,
        "cashier": add_user(client, owner, "cashier"),
        "rice": rice["id"],
        "wanjiku": wanjiku["id"],
    }


def credit_sale(client, shop, headers=None, qty="1", credit=None, cash=0, **extra):
    total = int(qty) * 15_000
    payments = [
        {"method": "credit", "amount_cents": credit if credit is not None else total - cash}
    ]
    if cash:
        payments.append({"method": "cash", "amount_cents": cash})
    return client.post(
        "/sales",
        headers=headers or shop["cashier"],
        json={
            "customer_id": shop["wanjiku"],
            "lines": [{"product_id": shop["rice"], "qty": qty}],
            "payments": payments,
            **extra,
        },
    )


def customer(client, shop):
    return client.get(f"/customers/{shop['wanjiku']}", headers=shop["cashier"]).json()


def statement(client, shop):
    return client.get(f"/customers/{shop['wanjiku']}/statement", headers=shop["owner"]).json()


def balances(client, shop):
    return {
        a["type"]: a["balance_cents"] for a in client.get("/accounts", headers=shop["owner"]).json()
    }


def test_credit_sale_raises_an_invoice_instead_of_cash(client, shop):
    resp = credit_sale(client, shop, qty="2")
    assert resp.status_code == 201, resp.text
    sale = resp.json()
    assert sale["customer_id"] == shop["wanjiku"]
    assert sale["payments"] == [{"method": "credit", "amount": 30_000, "mpesa_code": None}]

    c = customer(client, shop)
    assert (c["balance_cents"], c["overdue_cents"], c["available_credit_cents"]) == (
        30_000,
        0,
        20_000,
    )
    assert balances(client, shop)["cash"] == 0
    [invoice] = statement(client, shop)["open_invoices"]
    assert invoice["due_date"] == str(TODAY + dt.timedelta(days=30))
    assert (invoice["outstanding"], invoice["receipt_no"], invoice["bucket"]) == (
        30_000,
        "000001",
        "current",
    )

    receipt = client.get(f"/sales/{sale['id']}/receipt", headers=shop["cashier"]).json()["text"]
    assert "Customer: Wanjiku" in receipt and "Credit" in receipt


def test_split_credit_and_cash(client, shop):
    assert credit_sale(client, shop, credit=10_000, cash=5_000).status_code == 201
    assert customer(client, shop)["balance_cents"] == 10_000
    assert balances(client, shop)["cash"] == 5_000


def test_credit_needs_an_active_customer(client, shop):
    no_customer = client.post(
        "/sales",
        headers=shop["cashier"],
        json={
            "lines": [{"product_id": shop["rice"], "qty": "1"}],
            "payments": [{"method": "credit", "amount_cents": 15_000}],
        },
    )
    assert no_customer.status_code == 422
    client.patch(f"/customers/{shop['wanjiku']}", headers=shop["owner"], json={"active": False})
    assert credit_sale(client, shop).status_code == 422


def test_over_limit_is_blocked_unless_the_owner_overrides(client, shop):
    blocked = credit_sale(client, shop, qty="4")  # KSh 600 against a KSh 500 limit
    assert blocked.status_code == 403
    assert "over the 500.00 limit" in blocked.json()["detail"]
    assert credit_sale(client, shop, headers=shop["owner"], qty="4").status_code == 422
    ok = credit_sale(client, shop, headers=shop["owner"], qty="4", credit_override_reason="regular")
    assert ok.status_code == 201
    assert customer(client, shop)["balance_cents"] == 60_000
    # Nothing is posted by a blocked attempt.
    assert (
        client.get(f"/products/{shop['rice']}", headers=shop["owner"]).json()["qty_on_hand"]
        == "16.000"
    )


def test_overdue_balance_blocks_new_credit(client, shop, monkeypatch):
    credit_sale(client, shop)
    # 31 days later the first invoice is overdue.
    monkeypatch.setattr("app.services.credit.business_today", lambda: TODAY + dt.timedelta(days=31))
    blocked = credit_sale(client, shop)
    assert blocked.status_code == 403
    assert "150.00 is overdue" in blocked.json()["detail"]
    assert customer(client, shop)["overdue_cents"] == 15_000


def test_repayments_clear_the_oldest_invoice_first(client, shop):
    first = credit_sale(client, shop, qty="2").json()  # 30,000
    credit_sale(client, shop)  # 15,000
    repay = client.post(
        f"/customers/{shop['wanjiku']}/repayments",
        headers=shop["cashier"],
        json={"amount_cents": 35_000, "method": "mpesa", "mpesa_code": "rep1234567"},
    )
    assert repay.status_code == 201, repay.text
    assert (repay.json()["amount"], repay.json()["mpesa_code"]) == (-35_000, "REP1234567")

    invoices = statement(client, shop)["open_invoices"]
    assert [(i["sale_id"] == first["id"], i["outstanding"]) for i in invoices] == [(False, 10_000)]
    assert customer(client, shop)["balance_cents"] == 10_000
    assert balances(client, shop)["mpesa"] == 35_000

    reused = client.post(
        f"/customers/{shop['wanjiku']}/repayments",
        headers=shop["cashier"],
        json={"amount_cents": 1_000, "method": "mpesa", "mpesa_code": "REP1234567"},
    )
    assert reused.status_code == 409
    too_much = client.post(
        f"/customers/{shop['wanjiku']}/repayments",
        headers=shop["cashier"],
        json={"amount_cents": 10_001, "method": "cash"},
    )
    assert too_much.status_code == 422


def test_sale_mpesa_code_cannot_be_reused_for_a_repayment(client, shop):
    client.post(
        "/sales",
        headers=shop["cashier"],
        json={
            "lines": [{"product_id": shop["rice"], "qty": "1"}],
            "payments": [{"method": "mpesa", "amount_cents": 15_000, "mpesa_code": "SAL1234567"}],
        },
    )
    credit_sale(client, shop)
    resp = client.post(
        f"/customers/{shop['wanjiku']}/repayments",
        headers=shop["cashier"],
        json={"amount_cents": 1_000, "method": "mpesa", "mpesa_code": "SAL1234567"},
    )
    assert resp.status_code == 409


def test_write_off_is_owner_only_and_becomes_a_bad_debt_expense(client, shop):
    credit_sale(client, shop)
    body = {"amount_cents": 15_000, "reason": "customer relocated"}
    url = f"/customers/{shop['wanjiku']}/write-offs"
    assert client.post(url, headers=shop["cashier"], json=body).status_code == 403
    assert (
        client.post(url, headers=shop["owner"], json={**body, "amount_cents": 15_001}).status_code
        == 422
    )
    assert client.post(url, headers=shop["owner"], json=body).status_code == 201

    assert customer(client, shop)["balance_cents"] == 0
    [bad_debt] = [
        e
        for e in client.get("/expenses", headers=shop["owner"]).json()
        if e["source"] == "bad_debt"
    ]
    assert (bad_debt["amount"], bad_debt["account_id"]) == (15_000, None)
    assert (
        client.get("/profit-to-date", headers=shop["owner"]).json()["net_profit"] == 5_000 - 15_000
    )


def test_returning_goods_from_a_credit_sale_issues_a_credit_note(client, shop):
    older = credit_sale(client, shop).json()
    newer = credit_sale(client, shop, qty="2").json()
    ret = client.post(
        f"/sales/{newer['id']}/returns",
        headers=shop["owner"],
        json={
            "lines": [{"sale_line_id": newer["lines"][0]["id"], "qty": "1"}],
            "refund_method": "credit",
            "reason": "wrong item",
        },
    )
    assert ret.status_code == 201, ret.text
    # The returned sale's own invoice is reduced first, not the older one.
    invoices = {i["sale_id"]: i["outstanding"] for i in statement(client, shop)["open_invoices"]}
    assert invoices == {older["id"]: 15_000, newer["id"]: 15_000}
    assert balances(client, shop)["cash"] == 0

    cash_sale = client.post(
        "/sales",
        headers=shop["cashier"],
        json={
            "lines": [{"product_id": shop["rice"], "qty": "1"}],
            "payments": [{"method": "cash", "amount_cents": 15_000}],
        },
    ).json()
    to_credit = client.post(
        f"/sales/{cash_sale['id']}/returns",
        headers=shop["owner"],
        json={
            "lines": [{"sale_line_id": cash_sale["lines"][0]["id"], "qty": "1"}],
            "refund_method": "credit",
            "reason": "x",
        },
    )
    assert to_credit.status_code == 422


def test_ageing_report(client, shop):
    credit_sale(client, shop, qty="2")
    other = client.post(
        "/customers",
        headers=shop["owner"],
        json={"name": "Otieno", "credit_limit_cents": 100_000, "terms_days": 7},
    ).json()
    client.post(
        "/sales",
        headers=shop["cashier"],
        json={
            "customer_id": other["id"],
            "lines": [{"product_id": shop["rice"], "qty": "1"}],
            "payments": [{"method": "credit", "amount_cents": 15_000}],
        },
    )
    as_of = TODAY + dt.timedelta(days=45)  # Wanjiku 15 days overdue, Otieno 38
    report = client.get(
        "/credit/ageing", headers=shop["owner"], params={"as_of": str(as_of)}
    ).json()
    assert [(r["name"], r["balance_cents"]) for r in report["rows"]] == [
        ("Wanjiku", 30_000),
        ("Otieno", 15_000),
    ]
    assert report["rows"][0]["buckets"]["1-30"] == 30_000
    assert report["rows"][1]["buckets"]["31-60"] == 15_000
    assert report["totals"] == {"current": 0, "1-30": 30_000, "31-60": 15_000, "61-90": 0, "90+": 0}
    assert report["total_cents"] == 45_000
    assert client.get("/credit/ageing", headers=shop["cashier"]).status_code == 403


def test_reminders_are_queued_once_on_the_due_date_and_once_when_overdue(client, shop):
    credit_sale(client, shop)
    no_phone = client.post(
        "/customers",
        headers=shop["owner"],
        json={"name": "No Phone", "credit_limit_cents": 100_000},
    ).json()
    client.post(
        "/sales",
        headers=shop["cashier"],
        json={
            "customer_id": no_phone["id"],
            "lines": [{"product_id": shop["rice"], "qty": "1"}],
            "payments": [{"method": "credit", "amount_cents": 15_000}],
        },
    )
    business_id = uuid.UUID(shop["owner"]["X-Business-Id"])
    due = TODAY + dt.timedelta(days=30)

    def run(today):
        with tenant_session(business_id) as session:
            business = session.get(Business, business_id)
            return [
                (m.kind, m.phone)
                for m in reminders.queue_credit_reminders(session, business, today)
            ]

    assert run(due - dt.timedelta(days=1)) == []
    assert run(due) == [("credit_due", "0712345678")]  # the customer without a phone is skipped
    assert run(due) == []
    assert run(due + dt.timedelta(days=1)) == [("credit_overdue", "0712345678")]
    assert run(due + dt.timedelta(days=9)) == []

    outbox = client.get("/sms-outbox", headers=shop["owner"]).json()
    assert len(outbox) == 2
    assert "was due on" in next(m for m in outbox if m["kind"] == "credit_overdue")["message"]
    assert jobs.credit_reminders() == 0  # nothing is due today in real time


def test_credit_data_stays_within_the_business(client, shop):
    credit_sale(client, shop)
    other = open_business(client, "Other")
    assert client.get(f"/customers/{shop['wanjiku']}", headers=other).status_code == 404
    assert client.get("/customers", headers=other).json() == []
    assert client.get("/credit/ageing", headers=other).json()["total_cents"] == 0
