"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { OwnerOnly } from "@/components/app-shell";
import { Badge, Button, Card, Empty, ErrorText, Loading, Notice, PageHeader } from "@/components/ui";
import { api, call } from "@/lib/api";
import { dateTime } from "@/lib/format";

const TYPE_LABELS: Record<string, string> = {
  below_break_even: "Below break-even",
  low_stock: "Low stock",
  slow_moving: "Slow-moving",
  thin_margin: "Thin margin",
  low_cash: "Low cash",
  credit_risk: "Credit risk",
  drawings: "Drawings over profit",
};

// These alerts are about one product: link to it.
const PRODUCT_TYPES = new Set(["low_stock", "slow_moving", "thin_margin"]);

const STATUS_TONE = { open: "amber", acknowledged: "blue", resolved: "green" } as const;

export default function AlertsPage() {
  return (
    <OwnerOnly>
      <Alerts />
    </OwnerOnly>
  );
}

function Alerts() {
  const queryClient = useQueryClient();
  const [includeResolved, setIncludeResolved] = useState(false);
  const alerts = useQuery({
    queryKey: ["alerts", { includeResolved }],
    queryFn: () =>
      call(api.GET("/alerts", { params: { query: { include_resolved: includeResolved } } })),
  });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["alerts"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const run = useMutation({
    mutationFn: () => call(api.POST("/alerts/run")),
    onSuccess: refresh,
  });
  const acknowledge = useMutation({
    mutationFn: (alertId: string) =>
      call(api.POST("/alerts/{alert_id}/acknowledge", { params: { path: { alert_id: alertId } } })),
    onSuccess: refresh,
  });

  return (
    <>
      <PageHeader
        title="Alerts"
        description="Checks run nightly, and low stock is checked after every sale and delivery."
        actions={
          <Button onClick={() => run.mutate()} disabled={run.isPending}>
            {run.isPending ? "Checking…" : "Run checks now"}
          </Button>
        }
      />

      <div className="space-y-4">
        {run.data && (
          <Notice tone="green">
            Checks complete: {run.data.opened} new, {run.data.resolved} resolved,{" "}
            {run.data.active.length} active.
          </Notice>
        )}
        <ErrorText error={run.error ?? acknowledge.error} />

        <Card
          title={includeResolved ? "All alerts" : "Active alerts"}
          actions={
            <label className="flex items-center gap-2 text-sm text-gray-600">
              <input
                type="checkbox"
                checked={includeResolved}
                onChange={(e) => setIncludeResolved(e.target.checked)}
                className="accent-emerald-700"
              />
              Show resolved
            </label>
          }
        >
          {alerts.isPending ? (
            <Loading />
          ) : alerts.error ? (
            <ErrorText error={alerts.error} />
          ) : alerts.data.length === 0 ? (
            <Empty>Nothing needs your attention.</Empty>
          ) : (
            <ul className="-my-2 divide-y divide-gray-100">
              {alerts.data.map((a) => (
                <li key={a.id} className="flex flex-wrap items-start justify-between gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold">{TYPE_LABELS[a.type] ?? a.type}</span>
                      <Badge tone={STATUS_TONE[a.status as keyof typeof STATUS_TONE] ?? "gray"}>
                        {a.status}
                      </Badge>
                    </div>
                    <p className="mt-1 text-sm text-gray-700">{a.message}</p>
                    <p className="mt-1 text-xs text-gray-500">
                      Raised {dateTime(a.created_at)}
                      {a.resolved_at && ` · resolved ${dateTime(a.resolved_at)}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {PRODUCT_TYPES.has(a.type) && a.entity_id && (
                      <Link
                        href={`/products/${a.entity_id}`}
                        className="text-sm text-emerald-700 hover:underline"
                      >
                        View product
                      </Link>
                    )}
                    {a.status === "open" && (
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={acknowledge.isPending}
                        onClick={() => acknowledge.mutate(a.id)}
                      >
                        Acknowledge
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <p className="text-xs text-gray-500">
          Acknowledged alerts stay listed until the problem clears, then they resolve on their own.
          Thresholds are in Settings.
        </p>
      </div>
    </>
  );
}
