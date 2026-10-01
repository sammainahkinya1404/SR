"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { type FormEvent, useMemo, useState } from "react";
import { OwnerOnly } from "@/components/app-shell";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  Table,
  Td,
  Th,
  cx,
} from "@/components/ui";
import { type Schemas, api, call, newId } from "@/lib/api";
import { date as fmtDate, ksh, qty as fmtQty, toCents } from "@/lib/format";
import { useProducts, useRefreshAll } from "@/lib/queries";

type Result = Schemas["ReceiveOut"];
type Method = "by_value" | "by_quantity";
type Row = { key: string; name: string; category: string; qty: string; bp: string };

const emptyRow = (): Row => ({ key: newId(), name: "", category: "", qty: "", bp: "" });

/** Same largest-remainder split as the backend, for the preview only (the server decides). */
function previewShares(rows: { qty: number; bp: number }[], transport: number, method: Method) {
  let weights = rows.map((r) => (method === "by_value" ? r.qty * r.bp : r.qty));
  if (weights.every((w) => w === 0)) weights = rows.map((r) => r.qty);
  const total = weights.reduce((a, b) => a + b, 0);
  if (!total || !transport) return rows.map(() => 0);
  const exact = weights.map((w) => (transport * w) / total);
  const shares = exact.map(Math.floor);
  let left = transport - shares.reduce((a, b) => a + b, 0);
  const order = exact.map((e, i) => [e - shares[i], i] as const).sort((a, b) => b[0] - a[0]);
  for (const [, i] of order) {
    if (left-- <= 0) break;
    shares[i] += 1;
  }
  return shares;
}

export default function AddStock() {
  const [mode, setMode] = useState<"single" | "bulk">("single");
  const [result, setResult] = useState<Result | null>(null);

  return (
    <OwnerOnly>
      {result ? (
        <>
          <div className="mb-3 flex justify-end">
            <Button variant="secondary" onClick={() => setResult(null)}>
              Add more stock
            </Button>
          </div>
          <ResultView result={result} />
        </>
      ) : (
        <>
          <div className="mb-4 flex w-fit gap-1 rounded-lg bg-gray-200/60 p-1">
            {(
              [
                ["single", "Single item"],
                ["bulk", "Bulk order"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setMode(key)}
                className={cx(
                  "rounded-md px-4 py-1.5 text-sm font-medium",
                  mode === key ? "bg-white shadow-sm" : "text-gray-600",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <StockForm key={mode} bulk={mode === "bulk"} onDone={setResult} />
        </>
      )}
      <div className="mt-6">
        <RecentDeliveries />
      </div>
    </OwnerOnly>
  );
}

function StockForm({ bulk, onDone }: { bulk: boolean; onDone: (r: Result) => void }) {
  const products = useProducts(true);
  const refreshAll = useRefreshAll();
  const [rows, setRows] = useState<Row[]>(() => (bulk ? [emptyRow(), emptyRow()] : [emptyRow()]));
  const [transport, setTransport] = useState("");
  const [method, setMethod] = useState<Method>("by_value");
  const [localError, setLocalError] = useState<string | null>(null);
  // One id per delivery: resubmitting after a network error cannot add the stock twice.
  const [deliveryId, setDeliveryId] = useState(newId);

  const sets = useQuery({ queryKey: ["sets"], queryFn: () => call(api.GET("/sets")) });
  const byName = useMemo(
    () => new Map((products.data ?? []).map((p) => [p.name.trim().toLowerCase(), p])),
    [products.data],
  );
  const setsByName = useMemo(
    () => new Map((sets.data ?? []).map((s) => [s.name.trim().toLowerCase(), s])),
    [sets.data],
  );
  const categories = useMemo(
    () => [...new Set((products.data ?? []).map((p) => p.category).filter(Boolean))] as string[],
    [products.data],
  );

  const parsed = rows.map((r) => ({
    qty: Number(r.qty) || 0,
    bp: toCents(r.bp || "0") ?? 0,
    existing: byName.get(r.name.trim().toLowerCase()),
    set: setsByName.get(r.name.trim().toLowerCase()),
  }));
  const transportCents = toCents(transport || "0");
  const shares = previewShares(parsed, transportCents ?? 0, method);
  const goodsValue = parsed.reduce((sum, r) => sum + Math.round(r.qty * r.bp), 0);

  const update = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const save = useMutation({
    mutationFn: (body: Schemas["ReceiveCreate"]) => call(api.POST("/inventory/receive", { body })),
    onSuccess: (r) => {
      setDeliveryId(newId());
      refreshAll();
      onDone(r);
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    const filled = rows.filter((r) => r.name.trim() || r.qty || r.bp);
    if (!filled.length) return setLocalError("Add at least one item.");
    for (const r of filled) {
      if (!r.name.trim()) return setLocalError("Every item needs a name.");
      if (!(Number(r.qty) > 0)) return setLocalError(`Enter a quantity for ${r.name}.`);
      if (toCents(r.bp) === null) return setLocalError(`Enter the buying price for ${r.name}.`);
    }
    if (transportCents === null || transportCents < 0) {
      return setLocalError("Check the transport amount.");
    }
    save.mutate({
      id: deliveryId,
      transport_cents: transportCents,
      allocation_method: method,
      items: filled.map((r) => {
        const key = r.name.trim().toLowerCase();
        const existing = byName.get(key);
        const set = setsByName.get(key);
        const bp = toCents(r.bp) ?? 0;
        if (set) return { set_id: set.id, qty: r.qty, bp_cents: bp };
        return existing
          ? { product_id: existing.id, qty: r.qty, bp_cents: bp }
          : { name: r.name.trim(), category: r.category.trim() || null, qty: r.qty, bp_cents: bp };
      }),
    });
  };

  return (
    <form onSubmit={submit}>
      <datalist id="product-names">
        {sets.data?.map((s) => (
          <option key={s.id} value={s.name}>
            Set of {s.components.length}
          </option>
        ))}
        {products.data?.map((p) => <option key={p.id} value={p.name} />)}
      </datalist>
      <datalist id="categories">
        {categories.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>

      <Card title={bulk ? "Items in this order" : "Item"}>
        <div className="space-y-3">
          {rows.map((row, i) => {
            const p = parsed[i];
            return (
              <div
                key={row.key}
                className={cx(
                  "grid gap-3 sm:grid-cols-12",
                  bulk && i > 0 && "border-t border-gray-100 pt-3",
                )}
              >
                <Field label="Name" className="sm:col-span-4">
                  <Input
                    list="product-names"
                    value={row.name}
                    onChange={(e) => update(i, { name: e.target.value })}
                    placeholder="e.g. Sugar 1kg"
                    autoFocus={i === 0}
                  />
                </Field>
                <Field label="Category" className="sm:col-span-3">
                  <Input
                    list="categories"
                    value={
                      p.set
                        ? (p.set.category ?? "")
                        : p.existing
                          ? (p.existing.category ?? "")
                          : row.category
                    }
                    onChange={(e) => update(i, { category: e.target.value })}
                    disabled={!!p.existing || !!p.set}
                    placeholder="e.g. Dry goods"
                  />
                </Field>
                <Field label={p.set ? "Number of sets" : "Qty"} className="sm:col-span-2">
                  <Input
                    inputMode="decimal"
                    value={row.qty}
                    onChange={(e) => update(i, { qty: e.target.value })}
                  />
                </Field>
                <Field
                  label={p.set ? "Price paid per set (KSh)" : "Buying price / unit (KSh)"}
                  className="sm:col-span-3"
                >
                  <Input
                    inputMode="decimal"
                    value={row.bp}
                    onChange={(e) => update(i, { bp: e.target.value })}
                  />
                </Field>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 sm:col-span-12">
                  {row.name.trim() &&
                    (p.set ? (
                      <span>
                        <Badge tone="green">Set</Badge>{" "}
                        Stocks{" "}
                        {p.set.components
                          .map((c) => `${fmtQty(Number(c.qty_per_set) * (p.qty || 1))} × ${c.name}`)
                          .join(", ")}
                        , cost shared by selling price
                      </span>
                    ) : p.existing ? (
                      <span>
                        Existing item · {fmtQty(p.existing.qty_on_hand)} {p.existing.uom} in stock ·
                        avg cost {ksh(p.existing.wac_cents)}
                      </span>
                    ) : (
                      <Badge tone="blue">New item</Badge>
                    ))}
                  {p.qty > 0 && p.bp > 0 && (
                    <span className="num">
                      Line {ksh(Math.round(p.qty * p.bp))}
                      {shares[i] > 0 &&
                        ` + transport ${ksh(shares[i])} ≈ ${ksh(
                          Math.round((p.qty * p.bp + shares[i]) / p.qty),
                        )} per unit`}
                    </span>
                  )}
                  {bulk && rows.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
                      className="ml-auto text-gray-400 hover:text-red-600"
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>
            );
          })}
          {bulk && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setRows((rs) => [...rs, emptyRow()])}
            >
              Add item
            </Button>
          )}
        </div>
      </Card>

      <Card title="Transport" className="mt-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label={bulk ? "Transport paid for the whole order (KSh)" : "Transport (KSh, optional)"}
            hint="Added to the items' cost, so your selling price covers it."
          >
            <Input
              inputMode="decimal"
              value={transport}
              onChange={(e) => setTransport(e.target.value)}
              placeholder="0"
            />
          </Field>
          {bulk && (
            <fieldset>
              <legend className="mb-1 text-sm font-medium text-gray-700">Share transport</legend>
              <div className="space-y-1.5 text-sm">
                {(
                  [
                    ["by_value", "By value", "Dearer items carry more of it."],
                    ["by_quantity", "By quantity", "Every unit carries the same amount."],
                  ] as const
                ).map(([value, label, hint]) => (
                  <label key={value} className="flex items-start gap-2">
                    <input
                      type="radio"
                      name="method"
                      className="mt-1 accent-emerald-700"
                      checked={method === value}
                      onChange={() => setMethod(value)}
                    />
                    <span>
                      {label} <span className="text-gray-500">— {hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}
        </div>
      </Card>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <p className="num text-sm text-gray-700">
          Goods {ksh(goodsValue)} + transport {ksh(transportCents ?? 0)} ={" "}
          <strong>{ksh(goodsValue + (transportCents ?? 0))}</strong>
        </p>
        <Button type="submit" size="lg" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Add stock"}
        </Button>
      </div>
      <div className="mt-3 space-y-2">
        <ErrorText error={localError} />
        <ErrorText error={save.error} />
      </div>
    </form>
  );
}

const PRICE_STATUS = {
  set: { tone: "green", label: "Priced by engine" },
  suggested: { tone: "amber", label: "New price suggested" },
  unchanged: { tone: "gray", label: "Price unchanged" },
} as const;

function ResultView({ result }: { result: Result }) {
  const suggested = result.lines.some((l) => l.price_status === "suggested");
  return (
    <Card title={`Stock added · ${fmtDate(result.date)}`}>
      <Table>
        <thead>
          <tr>
            <Th>Item</Th>
            <Th right>Qty</Th>
            <Th right>Buying price</Th>
            <Th right>Transport share</Th>
            <Th right>Landed / unit</Th>
            <Th right>Avg cost</Th>
            <Th right>Selling price</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {result.lines.map((l, i) => {
            const status =
              PRICE_STATUS[l.price_status as keyof typeof PRICE_STATUS] ?? PRICE_STATUS.unchanged;
            return (
              <tr key={i}>
                <Td>
                  <Link
                    href={`/products/${l.product_id}`}
                    className="font-medium hover:text-emerald-800"
                  >
                    {l.name}
                  </Link>
                  {l.set_name && <span className="ml-2 text-xs text-gray-500">{l.set_name}</span>}
                  {l.new_product && (
                    <span className="ml-2">
                      <Badge tone="blue">New</Badge>
                    </span>
                  )}
                  {l.category && <span className="ml-2 text-xs text-gray-500">{l.category}</span>}
                </Td>
                <Td right>{fmtQty(l.qty)}</Td>
                <Td right>{ksh(l.bp_cents)}</Td>
                <Td right>{ksh(l.transport_share_cents)}</Td>
                <Td right className="font-medium">
                  {ksh(l.landed_unit_cost_cents)}
                </Td>
                <Td right>{ksh(l.wac_cents)}</Td>
                <Td right>
                  <span className="block">{ksh(l.price_cents)}</span>
                  <Badge tone={status.tone}>{status.label}</Badge>
                </Td>
              </tr>
            );
          })}
        </tbody>
      </Table>
      <p className="num mt-4 text-sm text-gray-700">
        Goods {ksh(result.goods_value_cents)} + transport {ksh(result.transport_cents)} shared{" "}
        {result.allocation_method === "by_value" ? "by value" : "by quantity"}.
      </p>
      {suggested && (
        <p className="mt-2 text-sm">
          Some costs moved: review the new prices on the{" "}
          <Link href="/stock" className="font-medium text-emerald-700 hover:underline">
            Available Stock
          </Link>{" "}
          tab.
        </p>
      )}
    </Card>
  );
}

function RecentDeliveries() {
  const batches = useQuery({
    queryKey: ["stock-in-batches"],
    queryFn: () =>
      call(api.GET("/stock-in-batches", { params: { query: { status: "posted", limit: 15 } } })),
  });
  const products = useProducts(true);
  const names = new Map(products.data?.map((p) => [p.id, p.name]));
  return (
    <Card title="Recent stock added">
      {batches.isPending ? (
        <Loading />
      ) : batches.error ? (
        <ErrorText error={batches.error} />
      ) : batches.data.length === 0 ? (
        <Empty>No stock added yet.</Empty>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Date</Th>
              <Th>Items</Th>
              <Th right>Goods</Th>
              <Th right>Transport</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {batches.data.map((b) => (
              <tr key={b.id}>
                <Td>{fmtDate(b.date)}</Td>
                <Td className="max-w-md truncate">
                  {b.lines
                    .map((l) => `${names.get(l.product_id) ?? "…"} × ${fmtQty(l.qty)}`)
                    .join(", ")}
                </Td>
                <Td right>
                  {ksh(b.lines.reduce((sum, l) => sum + Math.round(Number(l.qty) * l.bp_cents), 0))}
                </Td>
                <Td right>{ksh(b.costs.transport ?? 0)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}
