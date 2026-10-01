# Retail backend (FastAPI)

Phases 1-5 of the spec (`../retail-management-system-spec-and-design.md`): products, stock-in with
landed cost, weighted average cost, the pricing engine, the online POS (sales, cash and M-Pesa
payments, returns, receipts), and money management (expenses, recurring expenses, transfers,
opening capital, drawings, daily cash-up, stock write-offs), and customer credit (credit
sales with limits, repayments, write-offs, ageing, SMS reminders queued for sending), and
reporting (dashboard, profit and break-even, product ranking, alerts, CSV/XLSX exports).

Uses SQLite for now (`retail.db` in this folder). The spec targets PostgreSQL later.

## Run it

```sh
cp .env.example .env
uv sync
uv run alembic upgrade head              # creates/updates retail.db
uv run uvicorn app.main:app --reload     # http://localhost:8000/docs
```

Open a business with `POST /businesses`, then send `X-Business-Id` and `X-User-Id` (the returned
`owner_id`) on every other request. This header auth is a dev stub.

## Scheduled jobs

There is no background worker yet. Run jobs from Windows Task Scheduler. All are safe to re-run:

```sh
uv run python -m app.jobs post-recurring     # daily 00:05: posts recurring expenses that are due
uv run python -m app.jobs credit-reminders   # daily 08:00: queues due/overdue SMS reminders
uv run python -m app.jobs snapshot-metrics   # nightly: caches the last 7 days' figures
uv run python -m app.jobs check-alerts       # nightly, after snapshot-metrics
```

## Test and lint

```sh
uv run pytest                    # no setup needed: each test gets a fresh migrated SQLite file
uv run pytest tests/unit         # pure business rules only
uv run ruff check . && uv run ruff format .
```
