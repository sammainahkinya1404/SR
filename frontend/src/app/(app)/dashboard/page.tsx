"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { OwnerOnly } from "@/components/app-shell";
import { Badge, Card, Empty, ErrorText, Loading, PageHeader, Stat, cx } from "@/components/ui";
import { type Schemas, api, call } from "@/lib/api";
import { date, ksh, pct, ratio } from "@/lib/format";

type PeriodKey = "today" | "week" | "month";
type MetricValue = Schemas["MetricValue"];

const PERIODS: { key: PeriodKey; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "week", label: "This week" },
  { key: "month", label: "This month" },
];

// How each of the seven dashboard metrics is shown, and whether "up" is good news.
const METRICS: {
  key: string;
  label: string;
  format: (v: MetricValue["value"]) => string;
  upIsGood: boolean;
}[] = [
  { key: "sales", label: "Sales", format: (v) => ksh(num(v)), upIsGood: true },
  { key: "gross_margin", label: "Gross margin", format: (v) => pct(v), upIsGood: true },
  { key: "operating_expenses", label: "Expenses", format: (v) => ksh(num(v)), upIsGood: false },
  { key: "net_profit", label: "Net profit", format: (v) => ksh(num(v)), upIsGood: true },
  { key: "stock_value", label: "Stock value", format: (v) => ksh(num(v)), upIsGood: true },
  { key: "cash_balance", label: "Cash balance", format: (v) => ksh(num(v)), upIsGood: true },
  { key: "stock_turnover", label: "Stock turnover", format: (v) => ratio(v), upIsGood: true },
];

function num(v: MetricValue["value"]): number | null {
  return v === null || v === undefined ? null : Number(v);
}

function Trend({ change, upIsGood }: { change: string | null | undefined; upIsGood: boolean }) {
  if (change === null || change === undefined) return <span>No comparison</span>;
  const value = Number(change);
  if (value === 0) return <span>No change</span>;
  const up = value > 0;
  const good = up === upIsGood;
  return (
    <span className={cx("font-medium", good ? "text-emerald-700" : "text-red-600")}>
      {up ? "▲" : "▼"} {pct(Math.abs(value))}
    </span>
  );
}

export default function DashboardPage() {
  return (
    <OwnerOnly>
      <Dashboard />
    </OwnerOnly>
  );
}

function Dashboard() {
  const [period, setPeriod] = useState<PeriodKey>("today");
  const dashboard = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => call(api.GET("/dashboard")),
    refetchInterval: 60_000,
  });

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={dashboard.data && `As of ${date(dashboard.data.as_of)}`}
        actions={
          <>
            <Link
              href="/pos"
              className="rounded-md bg-emerald-700 px-3.5 py-2 text-sm font-medium text-white hover:bg-emerald-800"
            >
              Sell (POS)
            </Link>
            <Link
              href="/stock?tab=add"
              className="rounded-md bg-white px-3.5 py-2 text-sm font-medium text-gray-800 ring-1 ring-gray-300 hover:bg-gray-50"
            >
              Add stock
            </Link>
          </>
        }
      />

      {dashboard.isPending ? (
        <Loading />
      ) : dashboard.error ? (
        <ErrorText error={dashboard.error} />
      ) : (
        <div className="space-y-6">
          <div>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex gap-1 rounded-lg bg-gray-200/60 p-1">
                {PERIODS.map((p) => (
                  <button
                    key={p.key}
                    onClick={() => setPeriod(p.key)}
                    className={cx(
                      "rounded-md px-3 py-1.5 text-sm font-medium",
                      period === p.key ? "bg-white shadow-sm" : "text-gray-600",
                    )}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <PeriodCaption period={dashboard.data.periods[period]} />
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {METRICS.map((m) => {
                const value = dashboard.data.periods[period]?.metrics[m.key];
                return (
                  <Stat
                    key={m.key}
                    label={m.label}
                    value={m.format(value?.value ?? null)}
                    sub={
                      <>
                        <Trend change={value?.change} upIsGood={m.upIsGood} />
                        <span className="ml-1">(was {m.format(value?.previous ?? null)})</span>
                      </>
                    }
                  />
                );
              })}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <BreakEvenCard breakEven={dashboard.data.break_even} />
            <Card
              title="Alerts"
              actions={
                <Link href="/alerts" className="text-sm text-emerald-700 hover:underline">
                  View all
                </Link>
              }
            >
              {dashboard.data.alerts.length === 0 ? (
                <Empty>No active alerts.</Empty>
              ) : (
                <ul className="-my-2 divide-y divide-gray-100">
                  {dashboard.data.alerts.slice(0, 6).map((a) => (
                    <li key={a.id} className="flex items-start gap-2 py-2 text-sm">
                      <Badge tone={a.status === "open" ? "amber" : "gray"}>
                        {a.type.replaceAll("_", " ")}
                      </Badge>
                      <span className="text-gray-700">{a.message}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

function PeriodCaption({ period }: { period: Schemas["PeriodOut"] | undefined }) {
  if (!period) return null;
  const span = (a: string, b: string) => (a === b ? date(a) : `${date(a)} – ${date(b)}`);
  return (
    <p className="text-xs text-gray-500">
      {span(period.start, period.end)} vs {span(period.compared_to_start, period.compared_to_end)}
    </p>
  );
}

function BreakEvenCard({ breakEven }: { breakEven: Schemas["BreakEvenOut"] }) {
  const target = breakEven.pro_rata_target;
  const progress =
    target && target > 0 ? Math.min(100, (breakEven.month_to_date_sales / target) * 100) : null;
  return (
    <Card
      title="Break-even"
      actions={
        target !== null &&
        target !== undefined && (
          <Badge tone={breakEven.below ? "red" : "green"}>
            {breakEven.below ? "Below break-even" : "On track"}
          </Badge>
        )
      }
    >
      {breakEven.monthly === null || breakEven.monthly === undefined ? (
        <Empty>
          Break-even needs fixed costs and a positive gross margin. Set up rent and salaries as
          recurring expenses and record some sales.
        </Empty>
      ) : (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs text-gray-500">Monthly</dt>
              <dd className="num font-semibold">{ksh(breakEven.monthly)}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Per trading day</dt>
              <dd className="num font-semibold">{ksh(breakEven.daily)}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Fixed costs / month</dt>
              <dd className="num font-semibold">{ksh(breakEven.monthly_fixed_costs)}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-500">Gross margin (30 days)</dt>
              <dd className="num font-semibold">{pct(breakEven.gross_margin)}</dd>
            </div>
          </dl>
          {progress !== null && (
            <div>
              <div className="mb-1 flex justify-between text-xs text-gray-600">
                <span>Month-to-date sales {ksh(breakEven.month_to_date_sales)}</span>
                <span>Target so far {ksh(target)}</span>
              </div>
              <div className="h-2.5 overflow-hidden rounded-full bg-gray-100">
                <div
                  className={cx("h-full rounded-full", breakEven.below ? "bg-amber-500" : "bg-emerald-600")}
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
