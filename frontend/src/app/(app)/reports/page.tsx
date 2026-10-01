"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { OwnerOnly } from "@/components/app-shell";
import {
  Button,
  Card,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  PageHeader,
  Select,
  Stat,
  Table,
  Td,
  Th,
  cx,
} from "@/components/ui";
import { api, call, download } from "@/lib/api";
import { date, ksh, pct, qty, ratio, todayKenya } from "@/lib/format";

type Tab = "profit" | "products" | "ageing" | "daily";
const TABS: { key: Tab; label: string }[] = [
  { key: "profit", label: "Profit" },
  { key: "products", label: "Product ranking" },
  { key: "ageing", label: "Credit ageing" },
  { key: "daily", label: "Daily history" },
];

const BUCKETS = ["current", "1-30", "31-60", "61-90", "90+"] as const;

function daysAgo(n: number): string {
  const d = new Date(`${todayKenya()}T12:00:00+03:00`);
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export default function ReportsPage() {
  const [tab, setTab] = useState<Tab>("profit");
  return (
    <OwnerOnly>
      <PageHeader title="Reports" description="Every report can be exported to CSV or Excel." />
      <div className="mb-4 flex flex-wrap gap-1 rounded-lg bg-gray-200/60 p-1 sm:w-fit">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cx(
              "rounded-md px-3 py-1.5 text-sm font-medium",
              tab === t.key ? "bg-white shadow-sm" : "text-gray-600",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "profit" && <ProfitReport />}
      {tab === "products" && <ProductReport />}
      {tab === "ageing" && <AgeingReport />}
      {tab === "daily" && <DailyReport />}
    </OwnerOnly>
  );
}

function ExportButtons({ path, params }: { path: string; params: Record<string, string | undefined> }) {
  const exporter = useMutation({
    mutationFn: (format: "csv" | "xlsx") => download(path, { ...params, format }),
  });
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="secondary" size="sm" disabled={exporter.isPending} onClick={() => exporter.mutate("csv")}>
        Export CSV
      </Button>
      <Button variant="secondary" size="sm" disabled={exporter.isPending} onClick={() => exporter.mutate("xlsx")}>
        Export Excel
      </Button>
      {exporter.error && <span className="text-xs text-red-600">{exporter.error.message}</span>}
    </div>
  );
}

function DateRange({
  since,
  until,
  onChange,
}: {
  since: string;
  until: string;
  onChange: (since: string, until: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <Field label="From">
        <Input type="date" value={since} max={until} onChange={(e) => onChange(e.target.value, until)} />
      </Field>
      <Field label="To">
        <Input type="date" value={until} min={since} onChange={(e) => onChange(since, e.target.value)} />
      </Field>
    </div>
  );
}

function ProfitReport() {
  const [range, setRange] = useState({ since: daysAgo(29), until: todayKenya() });
  const report = useQuery({
    queryKey: ["reports", "profit", range],
    queryFn: () => call(api.GET("/reports/profit", { params: { query: range } })),
    enabled: !!range.since && !!range.until,
  });
  const t = report.data?.totals;

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <DateRange {...range} onChange={(since, until) => setRange({ since, until })} />
          <ExportButtons path="/reports/profit" params={range} />
        </div>
      </Card>
      {report.isPending ? (
        <Loading />
      ) : report.error ? (
        <ErrorText error={report.error} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Sales (net of refunds)" value={ksh(t?.sales)} />
            <Stat label="Gross profit" value={ksh(t?.gross_profit)} sub={`Margin ${pct(t?.gross_margin)}`} />
            <Stat
              label="Operating expenses"
              value={ksh(t?.operating_expenses)}
              sub={`Fixed ${ksh(t?.fixed_expenses)}`}
            />
            <Stat label="Net profit" value={ksh(t?.net_profit)} />
          </div>
          <Card title="By day">
            <Table>
              <thead>
                <tr>
                  <Th>Date</Th>
                  <Th right>Sales</Th>
                  <Th right>Cost of sales</Th>
                  <Th right>Gross profit</Th>
                  <Th right>Expenses</Th>
                  <Th right>Net profit</Th>
                  <Th right>Stock value</Th>
                  <Th right>Cash</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {[...report.data.days].reverse().map((d) => (
                  <tr key={d.date}>
                    <Td>{date(d.date)}</Td>
                    <Td right>{ksh(d.sales, false)}</Td>
                    <Td right>{ksh(d.cogs, false)}</Td>
                    <Td right>{ksh(d.gross_profit, false)}</Td>
                    <Td right>{ksh(d.opex, false)}</Td>
                    <Td right className={d.net_profit < 0 ? "text-red-600" : undefined}>
                      {ksh(d.net_profit, false)}
                    </Td>
                    <Td right>{ksh(d.stock_value, false)}</Td>
                    <Td right>{ksh(d.cash, false)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </>
      )}
    </div>
  );
}

type RankBy = "gross_profit" | "units" | "turnover" | "gmroi";

function ProductReport() {
  const [range, setRange] = useState({ since: daysAgo(29), until: todayKenya() });
  const [sort, setSort] = useState<RankBy>("gross_profit");
  const params = { ...range, sort };
  const report = useQuery({
    queryKey: ["reports", "products", params],
    queryFn: () => call(api.GET("/reports/products", { params: { query: params } })),
  });

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <DateRange {...range} onChange={(since, until) => setRange({ since, until })} />
            <Field label="Rank by">
              <Select value={sort} onChange={(e) => setSort(e.target.value as RankBy)}>
                <option value="gross_profit">Gross profit</option>
                <option value="units">Units sold</option>
                <option value="turnover">Turnover</option>
                <option value="gmroi">GMROI</option>
              </Select>
            </Field>
          </div>
          <ExportButtons path="/reports/products" params={params} />
        </div>
      </Card>
      <Card title="Products">
        {report.isPending ? (
          <Loading />
        ) : report.error ? (
          <ErrorText error={report.error} />
        ) : report.data.length === 0 ? (
          <Empty>No active products.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>#</Th>
                <Th>Product</Th>
                <Th right>Units</Th>
                <Th right>Sales</Th>
                <Th right>Gross profit</Th>
                <Th right>Avg stock value</Th>
                <Th right>Turnover</Th>
                <Th right>GMROI</Th>
                <Th right>Days of stock</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {report.data.map((r, i) => (
                <tr key={r.product_id}>
                  <Td className="text-gray-500">{i + 1}</Td>
                  <Td>
                    <Link href={`/products/${r.product_id}`} className="font-medium hover:underline">
                      {r.name}
                    </Link>
                    <span className="ml-2 text-xs text-gray-500">{r.sku}</span>
                  </Td>
                  <Td right>{qty(r.units_sold)}</Td>
                  <Td right>{ksh(r.sales, false)}</Td>
                  <Td right>{ksh(r.gross_profit, false)}</Td>
                  <Td right>{ksh(r.average_stock_value, false)}</Td>
                  <Td right>{ratio(r.turnover)}</Td>
                  <Td right>{ratio(r.gmroi)}</Td>
                  <Td right>{r.days_of_stock === null ? "—" : Math.round(Number(r.days_of_stock))}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        <p className="mt-3 text-xs text-gray-500">
          Turnover = cost of sales ÷ average stock value for the period. GMROI = gross profit ÷
          average stock value.
        </p>
      </Card>
    </div>
  );
}

function AgeingReport() {
  const [asOf, setAsOf] = useState(todayKenya());
  const report = useQuery({
    queryKey: ["reports", "ageing", asOf],
    queryFn: () => call(api.GET("/credit/ageing", { params: { query: { as_of: asOf } } })),
    enabled: !!asOf,
  });
  const totals = report.data?.totals as Record<string, number> | undefined;

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <Field label="As of">
            <Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
          </Field>
          <ExportButtons path="/credit/ageing" params={{ as_of: asOf }} />
        </div>
      </Card>
      {report.isPending ? (
        <Loading />
      ) : report.error ? (
        <ErrorText error={report.error} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
            <Stat label="Total owed" value={ksh(report.data.total_cents)} />
            {BUCKETS.map((b) => (
              <Stat key={b} label={b === "current" ? "Not yet due" : `${b} days overdue`} value={ksh(totals?.[b] ?? 0)} />
            ))}
          </div>
          <Card title="By customer">
            {report.data.rows.length === 0 ? (
              <Empty>No customer owes anything.</Empty>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Customer</Th>
                    <Th right>Balance</Th>
                    {BUCKETS.map((b) => (
                      <Th key={b} right>
                        {b === "current" ? "Current" : b}
                      </Th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {report.data.rows.map((r) => {
                    const buckets = r.buckets as Record<string, number>;
                    return (
                      <tr key={r.customer_id}>
                        <Td>
                          <Link href={`/customers/${r.customer_id}`} className="font-medium hover:underline">
                            {r.name}
                          </Link>
                          {r.phone && <span className="ml-2 text-xs text-gray-500">{r.phone}</span>}
                        </Td>
                        <Td right className="font-medium">
                          {ksh(r.balance_cents, false)}
                        </Td>
                        {BUCKETS.map((b) => (
                          <Td
                            key={b}
                            right
                            className={b !== "current" && buckets[b] ? "text-red-600" : "text-gray-500"}
                          >
                            {buckets[b] ? ksh(buckets[b], false) : "—"}
                          </Td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function DailyReport() {
  const [days, setDays] = useState(30);
  const report = useQuery({
    queryKey: ["reports", "daily", days],
    queryFn: () => call(api.GET("/metrics/daily", { params: { query: { days } } })),
  });

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <Field label="Days">
            <Select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[7, 30, 90, 180, 365].map((n) => (
                <option key={n} value={n}>
                  Last {n} days
                </option>
              ))}
            </Select>
          </Field>
          <ExportButtons path="/metrics/daily" params={{ days: String(days) }} />
        </div>
      </Card>
      <Card title="Daily history">
        {report.isPending ? (
          <Loading />
        ) : report.error ? (
          <ErrorText error={report.error} />
        ) : (
          <>
            <SalesBars days={report.data} />
            <Table>
              <thead>
                <tr>
                  <Th>Date</Th>
                  <Th right>Sales</Th>
                  <Th right>Gross profit</Th>
                  <Th right>Expenses</Th>
                  <Th right>Net profit</Th>
                  <Th right>Stock value</Th>
                  <Th right>Cash</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {[...report.data].reverse().map((d) => (
                  <tr key={d.date}>
                    <Td>{date(d.date)}</Td>
                    <Td right>{ksh(d.sales, false)}</Td>
                    <Td right>{ksh(d.gross_profit, false)}</Td>
                    <Td right>{ksh(d.opex, false)}</Td>
                    <Td right className={d.net_profit < 0 ? "text-red-600" : undefined}>
                      {ksh(d.net_profit, false)}
                    </Td>
                    <Td right>{ksh(d.stock_value, false)}</Td>
                    <Td right>{ksh(d.cash, false)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </>
        )}
      </Card>
    </div>
  );
}

/** A small bar chart of daily sales (net profit shown on hover). */
function SalesBars({ days }: { days: { date: string; sales: number; net_profit: number }[] }) {
  const max = Math.max(1, ...days.map((d) => d.sales));
  return (
    <div className="mb-4">
      <div className="flex h-28 items-end gap-px" aria-label="Daily sales">
        {days.map((d) => (
          <div
            key={d.date}
            title={`${date(d.date)}: sales ${ksh(d.sales)}, net profit ${ksh(d.net_profit)}`}
            className="min-w-0 flex-1 rounded-t-sm bg-emerald-600/80 hover:bg-emerald-700"
            style={{ height: `${Math.max(2, (d.sales / max) * 100)}%` }}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-gray-500">
        <span>{date(days[0]?.date)}</span>
        <span>Sales per day</span>
        <span>{date(days[days.length - 1]?.date)}</span>
      </div>
    </div>
  );
}
