import datetime as dt
import uuid
from decimal import Decimal

import pytest

from app import jobs
from app.db import tenant_session
from app.domain.clock import business_today
from app.models import Business
from app.services import alerts
from tests.integration.conftest import add_user, open_business

ZERO_COSTS = {"transport": 0, "duty": 0, "packaging": 0, "other": 0}
TODAY = business_today()


def receive(client, owner, lines):
    batch = client.post(
        "/stock-in-batches",
        headers=owner,
        json={"date": "2026-09-29", "lines": lines, "costs": ZERO_COSTS},
    ).json()
    assert client.post(f"/stock-in-batches/{batch['id']}/post", headers=owner).status_code == 200


def sell(client, headers, product_id, qty, amount):
    resp = client.post(
        "/sales",
        headers=headers,
        json={
            "lines": [{"product_id": product_id, "qty": qty}],
            "payments": [{"method": "cash", "amount_cents": amount}],
        },
    )
    assert resp.status_code == 201, resp.text


@pytest.fixture
def shop(client):
    """Rice: 10 in at KSh 100, 2 sold at KSh 150 (GP 100); reorder point 5.
    Sugar: 5 in at KSh 110, priced KSh 120 (8% margin: thin). Transport expense KSh 50."""
    owner = open_business(client)
    product = lambda sku, price, **kw: client.post(  # noqa: E731
        "/products",
        headers=owner,
        json={"sku": sku, "name": sku.title(), "price_cents": price, **kw},
    ).json()["id"]
    rice = product("RICE", 15_000, reorder_point="5")
    sugar = product("SUGAR", 12_000)
    receive(
        client,
        owner,
        [
            {"product_id": rice, "qty": "10", "bp_cents": 10_000},
            {"product_id": sugar, "qty": "5", "bp_cents": 11_000},
        ],
    )
    sell(client, owner, rice, "2", 30_000)
    accounts = {a["type"]: a["id"] for a in client.get("/accounts", headers=owner).json()}
    categories = {
        c["name"]: c["id"] for c in client.get("/expense-categories", headers=owner).json()
    }
    client.post(
        "/expenses",
        headers=owner,
        json={
            "category_id": categories["Transport"],
            "amount_cents": 5_000,
            "account_id": accounts["cash"],
        },
    )
    return {
        "owner": owner,
        "cashier": add_user(client, owner, "cashier"),
        "rice": rice,
        "sugar": sugar,
        "accounts": accounts,
        "categories": categories,
    }


def metric(dashboard, period, name):
    return dashboard["periods"][period]["metrics"][name]


def test_dashboard_shows_the_seven_metrics_with_trends(client, shop):
    d = client.get("/dashboard", headers=shop["owner"]).json()
    assert d["as_of"] == str(TODAY)
    for period in ("today", "week", "month"):
        assert set(d["periods"][period]["metrics"]) == {
            "sales",
            "gross_margin",
            "operating_expenses",
            "net_profit",
            "stock_value",
            "cash_balance",
            "stock_turnover",
        }
    today = {k: v["value"] for k, v in d["periods"]["today"]["metrics"].items()}
    assert (today["sales"], today["operating_expenses"], today["net_profit"]) == (
        30_000,
        5_000,
        5_000,
    )
    assert Decimal(today["gross_margin"]).quantize(Decimal("0.0001")) == Decimal("0.3333")
    # 8 rice at 100 + 5 sugar at 110
    assert today["stock_value"] == 80_000 + 55_000
    assert today["cash_balance"] == 25_000
    assert Decimal(today["stock_turnover"]) == Decimal(20_000) / 135_000

    # Nothing happened yesterday, so there is no trend to compute for flows.
    assert metric(d, "today", "sales")["previous"] == 0
    assert metric(d, "today", "sales")["change"] is None

    products = client.get("/products", headers=shop["owner"]).json()
    assert today["stock_value"] == sum(p["stock_value_cents"] for p in products)


def test_profit_report_and_exports(client, shop):
    report = client.get(
        "/reports/profit", headers=shop["owner"], params={"since": str(TODAY)}
    ).json()
    assert report["totals"] == {
        "sales": 30_000,
        "cogs": 20_000,
        "gross_profit": 10_000,
        "gross_margin": report["totals"]["gross_margin"],
        "operating_expenses": 5_000,
        "fixed_expenses": 0,
        "net_profit": 5_000,
    }
    assert [(d["date"], d["net_profit"], d["cash"]) for d in report["days"]] == [
        (str(TODAY), 5_000, 25_000)
    ]

    csv = client.get(
        "/reports/profit", headers=shop["owner"], params={"since": str(TODAY), "format": "csv"}
    )
    assert csv.headers["content-type"].startswith("text/csv")
    lines = csv.text.strip().splitlines()
    assert lines[0].startswith("date,sales_ksh,cogs_ksh,gross_profit_ksh")
    assert lines[1] == f"{TODAY},300,200,100,50,50,1350,250"

    xlsx = client.get("/reports/products", headers=shop["owner"], params={"format": "xlsx"})
    assert xlsx.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert xlsx.content[:2] == b"PK"  # a zip container

    bad = client.get(
        "/reports/profit",
        headers=shop["owner"],
        params={"since": "2026-12-01", "until": "2026-01-01"},
    )
    assert bad.status_code == 422


def test_product_ranking(client, shop):
    ranks = client.get(
        "/reports/products", headers=shop["owner"], params={"since": str(TODAY)}
    ).json()
    assert [r["sku"] for r in ranks] == ["RICE", "SUGAR"]
    rice = ranks[0]
    assert (rice["units_sold"], rice["gross_profit"], rice["average_stock_value"]) == (
        "2.000",
        10_000,
        80_000,
    )
    assert Decimal(rice["gmroi"]) == Decimal("0.125")
    by_units = client.get(
        "/reports/products", headers=shop["owner"], params={"sort": "units"}
    ).json()
    assert by_units[0]["sku"] == "RICE"


def test_break_even_uses_fixed_costs_and_trailing_margin(client, shop):
    client.post(
        "/recurring-expenses",
        headers=shop["owner"],
        json={
            "category_id": shop["categories"]["Rent"],
            "amount_cents": 1_000_000,
            "account_id": shop["accounts"]["bank"],
            "frequency": "monthly",
            "day": 1,
            "start_date": str(TODAY + dt.timedelta(days=40)),  # scheduled, not yet posted
        },
    )
    be = client.get("/reports/break-even", headers=shop["owner"]).json()
    assert be["monthly_fixed_costs"] == 1_000_000
    assert be["monthly"] == 3_000_000  # KSh 10,000 / (1/3 margin)
    assert be["daily"] == round(3_000_000 / 26)
    assert be["below"] is True


def test_alert_checks_open_update_and_resolve(client, shop):
    run = client.post("/alerts/run", headers=shop["owner"]).json()
    types = {a["type"] for a in run["active"]}
    assert "thin_margin" in types  # sugar: 8.3% against the 20% default target
    assert "low_stock" not in types  # rice: 8 left, reorder point 5
    thin = next(a for a in run["active"] if a["type"] == "thin_margin")
    assert thin["entity_id"] == shop["sugar"] and "8.3%" in thin["message"]

    # Re-running does not duplicate.
    again = client.post("/alerts/run", headers=shop["owner"]).json()
    assert again["opened"] == 0

    # Acknowledged alerts stay until the condition clears, then resolve.
    assert (
        client.post(f"/alerts/{thin['id']}/acknowledge", headers=shop["owner"]).status_code == 200
    )
    assert (
        client.post(f"/alerts/{thin['id']}/acknowledge", headers=shop["owner"]).status_code == 409
    )
    client.put(
        f"/products/{shop['sugar']}/pricing",
        headers=shop["owner"],
        json={"pricing_mode": "manual", "price_cents": 15_000, "reason": "fix margin"},
    )
    after = client.post("/alerts/run", headers=shop["owner"]).json()
    assert after["resolved"] >= 1
    history = client.get("/alerts", headers=shop["owner"], params={"include_resolved": True}).json()
    assert next(a for a in history if a["id"] == thin["id"])["status"] == "resolved"


def test_low_stock_alert_follows_sales_and_deliveries_in_real_time(client, shop):
    sell(client, shop["cashier"], shop["rice"], "3", 45_000)  # 5 left = reorder point
    active = client.get("/alerts", headers=shop["owner"]).json()
    assert [(a["type"], a["entity_id"]) for a in active] == [("low_stock", shop["rice"])]

    receive(client, shop["owner"], [{"product_id": shop["rice"], "qty": "10", "bp_cents": 10_000}])
    assert client.get("/alerts", headers=shop["owner"]).json() == []


def test_business_level_alerts_and_thresholds(client, shop):
    # Rent of KSh 10,000/month: KSh 250 in the bank is far below 7 days of fixed costs, and
    # month-to-date sales are under break-even.
    client.post(
        "/recurring-expenses",
        headers=shop["owner"],
        json={
            "category_id": shop["categories"]["Rent"],
            "amount_cents": 1_000_000,
            "account_id": shop["accounts"]["bank"],
            "frequency": "monthly",
            "day": 1,
            "start_date": str(TODAY + dt.timedelta(days=40)),
        },
    )
    client.post(
        "/drawings",
        headers=shop["owner"],
        json={"account_id": shop["accounts"]["cash"], "amount_cents": 6_000},
    )
    types = {a["type"] for a in client.post("/alerts/run", headers=shop["owner"]).json()["active"]}
    assert {"low_cash", "below_break_even", "drawings"} <= types

    # Setting the low-cash threshold to 0 days clears that alert on the next run.
    settings = client.patch(
        "/settings", headers=shop["owner"], json={"alert_low_cash_days": 0}
    ).json()
    assert settings["alert_low_cash_days"] == 0
    types = {a["type"] for a in client.post("/alerts/run", headers=shop["owner"]).json()["active"]}
    assert "low_cash" not in types
    assert (
        client.patch(
            "/settings", headers=shop["cashier"], json={"alert_low_cash_days": 1}
        ).status_code
        == 403
    )


def test_credit_risk_alert(client, shop, monkeypatch):
    wanjiku = client.post(
        "/customers",
        headers=shop["owner"],
        json={"name": "Wanjiku", "credit_limit_cents": 100_000, "terms_days": 0},
    ).json()
    client.post(
        "/sales",
        headers=shop["owner"],
        json={
            "customer_id": wanjiku["id"],
            "lines": [{"product_id": shop["rice"], "qty": "1"}],
            "payments": [{"method": "credit", "amount_cents": 15_000}],
        },
    )
    business_id = uuid.UUID(shop["owner"]["X-Business-Id"])
    with tenant_session(business_id) as session:
        business = session.get(Business, business_id)
        tomorrow = TODAY + dt.timedelta(days=1)
        # KSh 150 overdue against KSh 450 of sales in the last 30 days: over 10%.
        found = alerts.business_checks(session, business, tomorrow)
    assert "credit_risk" in {c.type for c in found}


def test_slow_moving_alerts(client, shop):
    flour = client.post(
        "/products",
        headers=shop["owner"],
        json={"sku": "FLOUR", "name": "Flour", "price_cents": 20_000},
    ).json()["id"]
    receive(client, shop["owner"], [{"product_id": flour, "qty": "1000", "bp_cents": 10_000}])
    sell(client, shop["owner"], flour, "1", 20_000)

    business_id = uuid.UUID(shop["owner"]["X-Business-Id"])
    with tenant_session(business_id) as session:
        business = session.get(Business, business_id)
        today = {c.entity_id: c.message for c in alerts.slow_moving(session, business, TODAY)}
        later = {
            c.entity_id: c.message
            for c in alerts.slow_moving(session, business, TODAY + dt.timedelta(days=30))
        }
    # Flour sells 1 a month with 999 on hand: far more than 90 days of stock.
    assert "days of stock" in today[uuid.UUID(flour)]
    assert uuid.UUID(shop["sugar"]) not in today
    # A month on, sugar has never sold and rice has not sold for 30 days.
    assert "never sold since delivery in 30 days" in later[uuid.UUID(shop["sugar"])]
    assert "no sale in 30 days" in later[uuid.UUID(shop["rice"])]


def test_snapshots_and_daily_history(client, shop):
    assert jobs.snapshot_metrics() == 7  # one business, last 7 finished days
    assert jobs.snapshot_metrics() == 7  # upsert: no duplicates
    history = client.get("/metrics/daily", headers=shop["owner"], params={"days": 3}).json()
    assert [d["date"] for d in history] == [str(TODAY - dt.timedelta(days=i)) for i in (2, 1, 0)]
    assert (history[-1]["sales"], history[-1]["cash"]) == (30_000, 25_000)
    assert history[0]["sales"] == 0
    opened, _ = jobs.check_alerts()
    assert opened >= 1


def test_reports_are_owner_only_and_per_business(client, shop):
    for path in ("/dashboard", "/reports/profit", "/reports/products", "/alerts", "/metrics/daily"):
        assert client.get(path, headers=shop["cashier"]).status_code == 403
    other = open_business(client, "Other")
    d = client.get("/dashboard", headers=other).json()
    assert metric(d, "month", "sales")["value"] == 0
    assert metric(d, "month", "stock_value")["value"] == 0
    assert client.get("/alerts", headers=other).json() == []


def test_ageing_report_exports(client, shop):
    resp = client.get("/credit/ageing", headers=shop["owner"], params={"format": "csv"})
    assert (
        resp.text.splitlines()[0]
        == "customer,phone,balance_ksh,current_ksh,1-30_ksh,31-60_ksh,61-90_ksh,90+_ksh"
    )
