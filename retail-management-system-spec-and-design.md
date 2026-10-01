# Retail Business Management System — SR

Functional Specification & System Design · v0.2

---

# Part A — Functional Specification

## 1. Overview
- **Purpose:** Track goods, costs, prices, sales, credit, expenses and cash for SR, a single Kenyan retail shop, and show whether the business is actually making money.
- **Single shop:** one installation serves exactly one shop (SR). There is no tenant selection, no multi-shop support, and no second business can be created. Sign-in simply picks a user.
- **Currency:** KSh.
- **Inventory valuation:** Weighted average cost (WAC).
- **Roles:**
  - *Owner:* full access.
  - *Cashier:* sales and stock viewing only; cannot edit prices or cost.
- **Out of scope for v0.1:** supplier/purchase-order management, tax compliance, capital allocation, multi-shop / multi-branch.

## 2. Goods & Inventory
**Product fields:** SKU/barcode, name, category, unit of measure, supplier (text field), BP, landed unit cost, selling price, quantity on hand, reorder point, lead time (days), active flag.

**Stock movements** (append-only ledger): purchase, sale, return, adjustment, damage, theft, owner consumption. Each movement records date, quantity, unit cost, user and reason.

**Requirements:**
- Quantity on hand is always derived from the movement ledger, never edited directly.
- Each stock-in updates WAC: `new WAC = (old qty × old WAC + in qty × landed cost) ÷ (old qty + in qty)`.
- Reorder point: `avg daily sales × lead time + safety stock`.
- Stock value = `qty on hand × WAC`.

**Physical stock count:**
- Staff enter counted quantities. The system shows `variance = system qty − counted qty`, valued at WAC.
- Each variance needs a reason code before posting.
- Posting creates adjustment movements.

## 3. Landed Cost
- **Stock-in batch:** supplier, date, lines (product, qty, BP), and shared costs (transport, duties, packaging, other).
- **Shared-cost allocation** is configurable: by line value (default) or by quantity.
- **Formula:** `landed unit cost = (BP × qty + allocated shared costs) ÷ qty`.
- The batch cannot be posted until all shared costs are either entered or explicitly set to zero.

## 4. Pricing Engine
**Pricing modes per product:**
- *Target margin:* `price = cost ÷ (1 − margin)`.
- *Markup:* `price = cost × (1 + markup)`.
- *Manual.*

**Display rule:** Margin and markup are always shown side by side, both calculated from WAC:
- `margin = (P − C) ÷ P`
- `markup = (P − C) ÷ C`

**Rounding:** configurable (e.g. to the nearest KSh 5 or 10).

**Minimum price floor:**
- A default floor applies (e.g. WAC + 10%).
- Only the owner can sell below the floor, and each override is logged.

**Automatic repricing:** When WAC changes by more than a threshold (default 5%), the system flags the product with a suggested new price. The owner approves or rejects the suggestion.

**Price history:** old price, new price, date, user and reason are recorded for every change.

## 5. Sales / POS
- **Sale lines:** product, qty, unit price, discount.
- **Payment methods:** cash, M-Pesa (with transaction code), credit, or split payment.
- **Captured on every line:** COGS (`qty × WAC at time of sale`) and gross profit (`revenue − COGS`).
- **Returns and refunds:** each links to the original sale and reverses its stock and cash entries.
- **Receipts:** printable or shareable via SMS/WhatsApp.
- **Offline mode:** sales are queued and synced when connection returns.

## 6. Customer Credit
- **Customer fields:** name, phone, ID (optional), credit limit, payment terms (days).
- **Blocking rules:** A credit sale is blocked if it would push the balance over the limit, or if the customer has any overdue balance. The owner can override, and overrides are logged.
- **Repayments:** partial payments are allowed and applied to the oldest invoices first.
- **Ageing buckets:** current, 1–30, 31–60, 61–90, and 90+ days.
- **Reminders:** SMS reminders sent on the due date and when an invoice becomes overdue.
- **Write-offs:** owner only; each write-off is posted as an expense.

## 7. Expenses
- **Fields:** date, category, amount, payment account, fixed/variable flag, note, receipt photo.
- **Default categories:** rent, salaries, electricity, internet, transport, M-Pesa charges, packaging, repairs, other.
- **Recurring expenses:** set up once (e.g. rent) and posted automatically.
- **Automatic losses:** stock losses from damage, theft and count variances are posted as expenses without manual entry.

## 8. Cash & Drawings
- **Accounts:** cash drawer, M-Pesa till, and bank.
- **Transactions:** every sale, repayment, expense, transfer and drawing posts to an account.
- **Owner drawings** are recorded separately and never counted as an expense. The system warns when drawings exceed net profit to date.
- **Daily cash-up:**
  - Expected balance is compared with the counted balance for each account.
  - Any variance must be explained and is posted.
- **Opening capital:** a one-time owner contribution entry.

## 9. Profitability & Break-even
**Core figures:**
- `Net profit = gross profit − operating expenses`, calculated per day, week and month.
- `Break-even (monthly) = fixed costs ÷ average gross margin %`.
- `Break-even (daily) = monthly break-even ÷ trading days`.

**Stock turnover:**
- `Turnover = COGS ÷ average stock value`
- `Days of stock = average stock value ÷ average daily COGS`

**Product ranking:** products ranked by gross profit, units sold, turnover and GMROI (`gross profit ÷ average stock value`).

## 10. Dashboard
**Seven metrics** (today, this week and this month, each with a trend): daily sales, gross margin %, operating expenses, net profit, stock value, cash balance, stock turnover.

**Alerts:**

| Alert | Default trigger |
|---|---|
| Below break-even | Month-to-date sales under pro-rata break-even |
| Low stock | Qty ≤ reorder point |
| Slow-moving | No sale in 30 days, or days of stock > 90 |
| Thin margin | Product margin below target |
| Low cash | Cash below X days of fixed costs |
| Credit risk | Total overdue > X% of sales |
| Drawings | Drawings > net profit to date |
| Stock variance | Count variance > X% |

## 11. Cross-cutting requirements
- **Audit log:** every change to price, cost, stock or cash is recorded with user, timestamp, old value and new value.
- **Corrections:** no hard deletes; errors are fixed by posting reversals.
- **Exports:** CSV/Excel for all reports.
- **Platforms:** mobile-first, with Android POS support.

---

# Part B — System Design

## 1. Architecture
```
Android POS app / Web dashboard (PWA)
        │  HTTPS (REST + sync API)
        ▼
API service (FastAPI)
   ├── Domain services: inventory, pricing, sales, credit, expenses, cash, reports
   ├── Sync service (offline queue ingestion)
   └── Auth + audit
        │
        ├── PostgreSQL (primary store, ledgers)
        ├── Redis (job queue, cache)
        └── Worker (scheduled jobs, SMS, alerts, metric snapshots)
External: M-Pesa Daraja API, SMS gateway (Africa's Talking)
```
- **Deployment:** a modular monolith, not microservices. At SME scale it is simpler to run and cheaper to host.
- **Tenancy:** single-tenant. The system serves one shop (SR) per installation. There is no tenant dimension in the API, no per-tenant isolation, and no multi-tenant features are planned.

## 2. Stack
| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| DB | PostgreSQL 16 |
| Jobs | Celery + Redis (or RQ for a lighter setup) |
| POS client | React Native + SQLite (offline-first) |
| Owner dashboard | React PWA |
| Reports/exports | Pandas → CSV/XLSX |
| Hosting | One VPS or managed cloud, Dockerised, daily DB backups |

## 3. Core design rules
- **Ledgers, not balances:** stock, cash and credit are append-only ledgers. Balances are derived from them or cached in views.
- **Corrections:** errors are fixed with reversal entries. Nothing is ever updated in place or hard-deleted.
- **Money:** stored as integer cents in `BIGINT`, never as floats.
- **Cost snapshots:** each stock movement and sale line stores the WAC at the time it was posted, so historical profit never changes.
- **Client IDs:** clients generate UUIDs for all records, so offline sync can safely replay without creating duplicates.
- **Domain events:** each posting emits an event (`SalePosted`, `StockReceived`, etc.) that drives alerts and metric updates.

## 4. Data model (key tables)
| Table | Key fields |
|---|---|
| `businesses` | a single row: shop name (SR) and settings (rounding, floor %, reprice threshold, trading days) |
| `users` | id, role (owner/cashier), pin_hash |
| `products` | id, sku, name, category, uom, supplier_name, wac, price, pricing_mode, target_value, reorder_point, lead_time_days |
| `stock_movements` | id, product_id, type, qty, unit_cost, ref_type, ref_id, reason, user_id, ts |
| `stock_in_batches` | id, supplier_name, date, allocation_method, status |
| `stock_in_lines` | batch_id, product_id, qty, bp, allocated_cost, landed_unit_cost |
| `batch_costs` | batch_id, type (transport/duty/packaging/other), amount |
| `price_history` | product_id, old_price, new_price, reason, user_id, ts |
| `price_suggestions` | product_id, suggested_price, trigger_wac, status |
| `sales` | id, receipt_no, customer_id, total, status, device_id, ts |
| `sale_lines` | sale_id, product_id, qty, unit_price, discount, wac_snapshot, cogs, gross_profit |
| `payments` | sale_id, method (cash/mpesa/credit), amount, mpesa_code |
| `customers` | id, name, phone, credit_limit, terms_days |
| `credit_ledger` | customer_id, type (charge/repayment/writeoff), amount, due_date, sale_id |
| `expenses` | id, category, amount, account_id, fixed_flag, recurring_id, receipt_url |
| `accounts` | id, type (cash/mpesa/bank), name |
| `cash_ledger` | account_id, type, amount, ref_type, ref_id, ts |
| `cash_ups` | account_id, date, expected, counted, variance, explanation |
| `stock_counts` / `count_lines` | product_id, system_qty, counted_qty, variance_value, reason |
| `metric_snapshots` | date, sales, cogs, gp, opex, net_profit, stock_value, cash, turnover |
| `alerts` | type, entity_id, message, status, ts |
| `audit_log` | entity, entity_id, field, old, new, user_id, ts |

## 5. Key flows
**Stock-in posting**
1. Validate that all shared costs are entered or explicitly zero.
2. Allocate shared costs across the batch lines.
3. Compute landed unit cost for each line.
4. Insert stock movements.
5. Update WAC.
6. If WAC changed by more than the threshold, create a price suggestion.

**Sale posting**
1. Check the price floor and the customer's credit limit.
2. Snapshot WAC onto each line and compute COGS and gross profit.
3. Insert stock movements (type: sale).
4. Record payments: cash and M-Pesa go to the cash ledger, credit goes to the credit ledger.

**Stock count**
1. Freeze the system quantities at the moment the count starts.
2. Staff enter counted quantities.
3. Each variance gets a reason code.
4. Post adjustment movements and the matching loss expense.

**Daily cash-up**
1. Compute the expected balance per account from the cash ledger.
2. Compare it with the counted balance.
3. Post any variance along with its explanation.

**M-Pesa**
- Customers pay by Daraja STK Push, or the till's C2B confirmation webhook matches incoming payments.
- Unmatched payments go to a suspense queue for the owner to assign.

## 6. Offline sync
- The POS keeps local copies of products, prices, customers and credit balances, plus a queue of unsent sales.
- **Push:** the client sends its queued events in batches, and the server applies them idempotently using the client UUIDs.
- **Pull:** the client fetches changes since its last sync cursor (`updated_at` + id).
- **Conflicts:**
  - The server is authoritative for price, WAC and credit limits.
  - An offline sale that pushes stock negative, or a customer over their limit, is still accepted but flagged for owner review.

## 7. Scheduled jobs
| Job | When |
|---|---|
| Post recurring expenses | Daily 00:05 |
| Credit ageing + SMS reminders | Daily 08:00 |
| Low stock / slow-moving / thin-margin checks | Daily |
| Metric snapshot + break-even check | Nightly |
| Low cash / drawings > profit check | Nightly |
| DB backup | Nightly |

## 8. Reporting layer
- **Dashboard:** reads `metric_snapshots`, with today's figures computed live.
- **Heavy reports** (turnover, GMROI, ageing) run on SQL views or materialised views, refreshed nightly.
- **Exports:** every report can be exported as CSV or XLSX.

## 9. Security
- **Scope:** all data belongs to the single shop; there is no cross-tenant data access surface.
- **Authentication:**
  - Owners log in with phone + OTP.
  - Cashiers use a device-bound PIN.
  - Sessions use JWT with short-lived access tokens.
- **Permissions:** role checks are enforced in the service layer, not only in the UI.
- **Owner-only actions:** price floor overrides, write-offs and posting stock counts. Each is audited.
- **Encryption:** TLS in transit; encrypted backups at rest.

## 10. Build phases
1. Products, stock-in with landed cost, WAC, pricing engine.
2. POS (online first), payments, receipts.
3. Expenses, cash accounts, drawings, cash-up.
4. Customer credit, ageing, SMS reminders.
5. Metrics, break-even, dashboard, alerts.
6. Offline sync and M-Pesa integration.
