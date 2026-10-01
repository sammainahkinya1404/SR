import datetime as dt
import uuid

import pytest

from app import jobs
from app.db import tenant_session
from app.domain.clock import business_today
from app.services.actor import Actor, Role
from app.services.expenses import post_due_recurring
from tests.integration.conftest import add_user, open_business

ZERO_COSTS = {"transport": 0, "duty": 0, "packaging": 0, "other": 0}


@pytest.fixture
def shop(client):
    """Rice: 10 in stock at WAC KSh 100, price KSh 150. Two sold for cash: KSh 300 in the drawer,
    KSh 100 gross profit."""
    owner = open_business(client)
    rice = client.post(
        "/products", headers=owner, json={"sku": "RICE", "name": "Rice", "price_cents": 15_000}
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
    sale = client.post(
        "/sales",
        headers=owner,
        json={
            "lines": [{"product_id": rice["id"], "qty": "2"}],
            "payments": [{"method": "cash", "amount_cents": 30_000}],
        },
    )
    assert sale.status_code == 201, sale.text
    accounts = {a["type"]: a["id"] for a in client.get("/accounts", headers=owner).json()}
    categories = {
        c["name"]: c["id"] for c in client.get("/expense-categories", headers=owner).json()
    }
    return {
        "owner": owner,
        "cashier": add_user(client, owner, "cashier"),
        "rice": rice["id"],
        "accounts": accounts,
        "categories": categories,
    }


def balances(client, shop):
    return {
        a["type"]: a["balance_cents"] for a in client.get("/accounts", headers=shop["owner"]).json()
    }


def profit(client, shop):
    return client.get("/profit-to-date", headers=shop["owner"]).json()


def expense(client, shop, category, amount, account="cash", **extra):
    return client.post(
        "/expenses",
        headers=shop["owner"],
        json={
            "category_id": shop["categories"][category],
            "amount_cents": amount,
            "account_id": shop["accounts"][account],
            **extra,
        },
    )


def test_default_categories_are_seeded(client, shop):
    cats = client.get("/expense-categories", headers=shop["owner"]).json()
    assert len(cats) == 12
    assert {c["name"] for c in cats if c["system"]} == {"Stock loss", "Cash shortage", "Bad debt"}
    assert {c["name"] for c in cats if c["is_fixed"]} == {
        "Rent",
        "Salaries",
        "Electricity",
        "Internet",
    }


def test_expense_leaves_the_account_and_a_reversal_restores_it(client, shop):
    assert expense(client, shop, "Stock loss", 100).status_code == 422  # system category
    assert (
        client.post(
            "/expenses",
            headers=shop["cashier"],
            json={
                "category_id": shop["categories"]["Transport"],
                "amount_cents": 5_000,
                "account_id": shop["accounts"]["cash"],
            },
        ).status_code
        == 403
    )

    spent = expense(client, shop, "Transport", 5_000, note="boda to supplier").json()
    assert spent["is_fixed"] is False
    assert balances(client, shop)["cash"] == 25_000
    assert profit(client, shop) == {
        "gross_profit": 10_000,
        "operating_expenses": 5_000,
        "net_profit": 5_000,
        "drawings": 0,
    }

    reversal = client.post(
        f"/expenses/{spent['id']}/reverse", headers=shop["owner"], json={"reason": "duplicate"}
    )
    assert reversal.status_code == 201
    assert (reversal.json()["amount"], reversal.json()["reverses_id"]) == (-5_000, spent["id"])
    assert balances(client, shop)["cash"] == 30_000
    assert profit(client, shop)["operating_expenses"] == 0
    again = client.post(
        f"/expenses/{spent['id']}/reverse", headers=shop["owner"], json={"reason": "x"}
    )
    assert again.status_code == 409


def test_recurring_expense_posts_each_occurrence_once_and_catches_up(client, shop):
    rent = client.post(
        "/recurring-expenses",
        headers=shop["owner"],
        json={
            "category_id": shop["categories"]["Rent"],
            "amount_cents": 2_000_000,
            "account_id": shop["accounts"]["bank"],
            "frequency": "monthly",
            "day": 31,
            "start_date": "2026-01-15",
        },
    ).json()
    assert rent["next_due"] == "2026-01-31"

    business_id = uuid.UUID(shop["owner"]["X-Business-Id"])
    actor = Actor(uuid.UUID(shop["owner"]["X-User-Id"]), business_id, Role.OWNER)
    with tenant_session(business_id) as session:
        posted = post_due_recurring(session, actor, today=dt.date(2026, 3, 31))
        assert [e.date for e in posted] == [
            dt.date(2026, 1, 31),
            dt.date(2026, 2, 28),
            dt.date(2026, 3, 31),
        ]
    with tenant_session(business_id) as session:
        assert post_due_recurring(session, actor, today=dt.date(2026, 3, 31)) == []

    rents = client.get(
        "/expenses", headers=shop["owner"], params={"category_id": shop["categories"]["Rent"]}
    ).json()
    assert len(rents) == 3 and all(e["is_fixed"] and e["source"] == "recurring" for e in rents)
    assert balances(client, shop)["bank"] == -6_000_000
    listed = client.get("/recurring-expenses", headers=shop["owner"]).json()
    assert listed[0]["next_due"] == "2026-04-30"

    # Pausing and resuming restarts from today instead of back-posting the gap.
    for active in (False, True):
        client.patch(
            f"/recurring-expenses/{rent['id']}", headers=shop["owner"], json={"active": active}
        )
    resumed = client.get("/recurring-expenses", headers=shop["owner"]).json()[0]
    assert dt.date.fromisoformat(resumed["next_due"]) >= business_today()


def test_run_endpoint_and_nightly_job_post_what_is_due_today(client, shop):
    today = business_today()
    client.post(
        "/recurring-expenses",
        headers=shop["owner"],
        json={
            "category_id": shop["categories"]["Salaries"],
            "amount_cents": 50_000,
            "account_id": shop["accounts"]["cash"],
            "frequency": "weekly",
            "day": today.weekday(),
        },
    )
    assert len(client.post("/recurring-expenses/run", headers=shop["owner"]).json()) == 1
    assert client.post("/recurring-expenses/run", headers=shop["owner"]).json() == []
    assert jobs.post_recurring() == 0  # already posted for today

    other = open_business(client, "Other")
    other_cash = client.get("/accounts", headers=other).json()
    salaries = next(
        c["id"]
        for c in client.get("/expense-categories", headers=other).json()
        if c["name"] == "Salaries"
    )
    client.post(
        "/recurring-expenses",
        headers=other,
        json={
            "category_id": salaries,
            "amount_cents": 10_000,
            "account_id": next(a["id"] for a in other_cash if a["type"] == "cash"),
            "frequency": "weekly",
            "day": today.weekday(),
        },
    )
    assert jobs.post_recurring() == 1  # only the other business had anything due


def test_transfer_moves_money_and_posts_the_fee_as_an_expense(client, shop):
    same = {"from_account_id": shop["accounts"]["cash"], "to_account_id": shop["accounts"]["cash"]}
    assert (
        client.post(
            "/transfers", headers=shop["owner"], json={**same, "amount_cents": 1}
        ).status_code
        == 422
    )
    resp = client.post(
        "/transfers",
        headers=shop["owner"],
        json={
            "from_account_id": shop["accounts"]["cash"],
            "to_account_id": shop["accounts"]["bank"],
            "amount_cents": 20_000,
            "fee_cents": 300,
        },
    )
    assert resp.status_code == 201, resp.text
    assert balances(client, shop) == {"bank": 20_000, "cash": 9_700, "mpesa": 0}
    fees = client.get(
        "/expenses",
        headers=shop["owner"],
        params={"category_id": shop["categories"]["M-Pesa charges"]},
    ).json()
    assert [(e["amount"], e["source"]) for e in fees] == [(300, "transfer_fee")]


def test_capital_and_drawings_are_never_profit_or_expenses(client, shop):
    capital = {"account_id": shop["accounts"]["bank"], "amount_cents": 100_000}
    assert client.post("/capital", headers=shop["owner"], json=capital).status_code == 201
    assert client.post("/capital", headers=shop["owner"], json=capital).status_code == 409
    assert balances(client, shop)["bank"] == 100_000

    first = client.post(
        "/drawings",
        headers=shop["owner"],
        json={"account_id": shop["accounts"]["cash"], "amount_cents": 4_000},
    ).json()
    assert first["warning"] is None
    second = client.post(
        "/drawings",
        headers=shop["owner"],
        json={"account_id": shop["accounts"]["cash"], "amount_cents": 7_000},
    ).json()
    assert (second["drawings_to_date"], second["net_profit_to_date"]) == (11_000, 10_000)
    assert "exceed net profit" in second["warning"]

    assert profit(client, shop) == {
        "gross_profit": 10_000,
        "operating_expenses": 0,
        "net_profit": 10_000,
        "drawings": 11_000,
    }
    assert client.get("/expenses", headers=shop["owner"]).json() == []
    assert balances(client, shop)["cash"] == 30_000 - 11_000


def test_cash_up_posts_shortages_as_expenses_and_overages_to_the_account(client, shop):
    cash_id, mpesa_id = shop["accounts"]["cash"], shop["accounts"]["mpesa"]
    no_reason = client.post(
        "/cash-ups", headers=shop["owner"], json={"account_id": cash_id, "counted_cents": 29_500}
    )
    assert no_reason.status_code == 422

    short = client.post(
        "/cash-ups",
        headers=shop["owner"],
        json={"account_id": cash_id, "counted_cents": 29_500, "explanation": "coins short"},
    ).json()
    assert (short["expected"], short["counted"], short["variance"]) == (30_000, 29_500, -500)
    assert balances(client, shop)["cash"] == 29_500
    shortage = client.get(
        "/expenses",
        headers=shop["owner"],
        params={"category_id": shop["categories"]["Cash shortage"]},
    ).json()
    assert [(e["amount"], e["source"]) for e in shortage] == [(500, "cash_shortage")]

    again = client.post(
        "/cash-ups", headers=shop["owner"], json={"account_id": cash_id, "counted_cents": 29_500}
    )
    assert again.status_code == 409

    over = client.post(
        "/cash-ups",
        headers=shop["owner"],
        json={"account_id": mpesa_id, "counted_cents": 100, "explanation": "unrecorded sale"},
    ).json()
    assert over["variance"] == 100
    assert balances(client, shop)["mpesa"] == 100
    ledger = client.get(f"/accounts/{mpesa_id}/ledger", headers=shop["owner"]).json()
    assert [(e["type"], e["amount"]) for e in ledger] == [("cash_up_overage", 100)]

    exact = client.post(
        "/cash-ups",
        headers=shop["owner"],
        json={"account_id": shop["accounts"]["bank"], "counted_cents": 0},
    )
    assert exact.status_code == 201
    assert (
        client.post(
            "/cash-ups", headers=shop["cashier"], json={"account_id": cash_id, "counted_cents": 0}
        ).status_code
        == 403
    )


def test_stock_write_offs_become_expenses_or_drawings_automatically(client, shop):
    def write_off(kind, qty="1"):
        return client.post(
            "/stock-adjustments",
            headers=shop["owner"],
            json={"product_id": shop["rice"], "type": kind, "qty": qty, "reason": "test"},
        )

    damaged = write_off("damage").json()
    assert (damaged["value_cents"], damaged["drawing"]) == (10_000, None)
    loss = client.get(f"/expenses/{damaged['expense_id']}", headers=shop["owner"]).json()
    assert (loss["amount"], loss["account_id"], loss["source"]) == (10_000, None, "stock_loss")

    eaten = write_off("owner_consumption").json()
    assert eaten["expense_id"] is None
    assert (eaten["drawing"]["entry"]["amount"], eaten["drawing"]["entry"]["account_id"]) == (
        10_000,
        None,
    )

    assert write_off("theft", "7").status_code == 422  # only 6 left
    product = client.get(f"/products/{shop['rice']}", headers=shop["owner"]).json()
    assert product["qty_on_hand"] == "6.000"
    movements = client.get(f"/products/{shop['rice']}/movements", headers=shop["owner"]).json()
    assert [m["type"] for m in movements[-2:]] == ["damage", "owner_consumption"]
    assert balances(client, shop)["cash"] == 30_000  # no money moved
    assert profit(client, shop) == {
        "gross_profit": 10_000,
        "operating_expenses": 10_000,
        "net_profit": 0,
        "drawings": 10_000,
    }
