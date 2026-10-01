"use client";

import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ReceiptModal } from "@/components/receipt";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  Notice,
  Select,
  cx,
} from "@/components/ui";
import { type Schemas, api, call, newId } from "@/lib/api";
import { centsToInput, ksh, qty as fmtQty, toCents } from "@/lib/format";
import { useCustomers, useProducts, useRefreshAll } from "@/lib/queries";
import { useSession } from "@/lib/use-session";

type Product = Schemas["ProductOut"];
type Method = "cash" | "mpesa" | "credit";
// unitPrice is what the customer pays per unit (KSh), bargained within the item's price range.
type CartLine = { product: Product; qty: string; unitPrice: string };
type Tender = { method: Method; amount: string; code: string };

const METHOD_LABELS: Record<Method, string> = { cash: "Cash", mpesa: "M-Pesa", credit: "Credit" };

function lineAmounts(line: CartLine) {
  const q = Number(line.qty) || 0;
  const gross = Math.round(q * line.product.price_cents);
  const unit = toCents(line.unitPrice);
  // The backend prices every line at the list price; a bargained price travels as a discount.
  const net = unit === null ? gross : Math.round(q * unit);
  const discount = gross - net;
  const invalid = unit === null || unit < 0 || unit > line.product.price_cents;
  const belowFloor = q > 0 && unit !== null && unit < line.product.floor_price_cents;
  return { q, gross, discount, net, belowFloor, invalid };
}

export default function PosPage() {
  const session = useSession();
  const products = useProducts();
  const customers = useCustomers();
  const refreshAll = useRefreshAll();

  const [search, setSearch] = useState("");
  const [cart, setCart] = useState<CartLine[]>([]);
  const [tenders, setTenders] = useState<Tender[]>([{ method: "cash", amount: "", code: "" }]);
  const [customerId, setCustomerId] = useState("");
  const [floorReason, setFloorReason] = useState("");
  const [creditReason, setCreditReason] = useState("");
  // One id per cart: resubmitting after a network error cannot create a second sale.
  const [saleId, setSaleId] = useState(newId);
  const [receiptFor, setReceiptFor] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    const list = products.data ?? [];
    return term
      ? list.filter((p) => p.name.toLowerCase().includes(term) || p.sku.toLowerCase().includes(term))
      : list;
  }, [products.data, search]);

  const totals = useMemo(() => {
    const lines = cart.map(lineAmounts);
    const total = lines.reduce((sum, l) => sum + l.net, 0);
    const paid = tenders.reduce((sum, t) => sum + (toCents(t.amount || "0") ?? 0), 0);
    const cash = tenders
      .filter((t) => t.method === "cash")
      .reduce((sum, t) => sum + (toCents(t.amount || "0") ?? 0), 0);
    return { total, paid, change: Math.max(0, paid - total), due: Math.max(0, total - paid), cash };
  }, [cart, tenders]);

  const add = (product: Product) => {
    setCart((lines) => {
      const existing = lines.find((l) => l.product.id === product.id);
      if (existing) {
        return lines.map((l) =>
          l === existing ? { ...l, qty: String((Number(l.qty) || 0) + 1) } : l,
        );
      }
      return [...lines, { product, qty: "1", unitPrice: centsToInput(product.price_cents) }];
    });
  };
  const updateLine = (index: number, patch: Partial<CartLine>) =>
    setCart((lines) => lines.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  const updateTender = (index: number, patch: Partial<Tender>) =>
    setTenders((ts) => ts.map((t, i) => (i === index ? { ...t, ...patch } : t)));

  const reset = () => {
    setCart([]);
    setTenders([{ method: "cash", amount: "", code: "" }]);
    setCustomerId("");
    setFloorReason("");
    setCreditReason("");
    setSaleId(newId());
    sale.reset();
  };

  const sale = useMutation({
    mutationFn: () =>
      call(
        api.POST("/sales", {
          body: {
            id: saleId,
            customer_id: customerId || null,
            lines: cart.map((l) => ({
              product_id: l.product.id,
              qty: l.qty,
              discount_cents: lineAmounts(l).discount,
            })),
            payments: tenders
              .filter((t) => (toCents(t.amount || "0") ?? 0) > 0)
              .map((t) => ({
                method: t.method,
                amount_cents: toCents(t.amount) ?? 0,
                mpesa_code: t.method === "mpesa" ? t.code : null,
              })),
            floor_override_reason: floorReason || null,
            credit_override_reason: creditReason || null,
          },
        }),
      ),
    onSuccess: (result) => {
      setReceiptFor(result.id);
      refreshAll();
    },
  });

  const errorText = sale.error instanceof Error ? sale.error.message : "";
  const needsFloorReason = errorText.includes("floor_override_reason") || floorReason !== "";
  const needsCreditReason = errorText.includes("credit_override_reason") || creditReason !== "";
  const hasCredit = tenders.some((t) => t.method === "credit" && (toCents(t.amount || "0") ?? 0) > 0);
  const invalidLine = cart.some((l) => !(Number(l.qty) > 0) || lineAmounts(l).invalid);
  const canCharge = cart.length > 0 && !invalidLine && totals.due === 0 && !sale.isPending;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_26rem]">
      <Card title="Products">
        <Input
          placeholder="Search by name or SKU / scan barcode"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => {
            // A barcode scanner types the SKU then Enter.
            if (e.key === "Enter" && filtered.length === 1) {
              add(filtered[0]);
              setSearch("");
            }
          }}
          autoFocus
        />
        {products.isPending ? (
          <Loading />
        ) : filtered.length === 0 ? (
          <Empty>No products match.</Empty>
        ) : (
          <ul className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
            {filtered.map((p) => {
              const out = Number(p.qty_on_hand) <= 0;
              return (
                <li key={p.id}>
                  <button
                    onClick={() => add(p)}
                    disabled={out}
                    className={cx(
                      "h-full w-full rounded-md p-3 text-left ring-1 ring-gray-200 transition",
                      out ? "cursor-not-allowed bg-gray-50 opacity-60" : "bg-white hover:ring-emerald-500",
                    )}
                  >
                    <span className="block text-sm font-medium">{p.name}</span>
                    <span className="num block text-sm text-emerald-800">{ksh(p.price_cents)}</span>
                    <span className="num block text-xs text-gray-500">min {ksh(p.floor_price_cents)}</span>
                    <span className="block text-xs text-gray-500">
                      {out ? "Out of stock" : `${fmtQty(p.qty_on_hand)} ${p.uom} in stock`}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card
        title="Current sale"
        actions={
          cart.length > 0 && (
            <Button variant="ghost" size="sm" onClick={reset}>
              Clear
            </Button>
          )
        }
      >
        {cart.length === 0 ? (
          <Empty>Tap a product to start a sale.</Empty>
        ) : (
          <ul className="-mt-1 divide-y divide-gray-100">
            {cart.map((line, i) => {
              const a = lineAmounts(line);
              return (
                <li key={line.product.id} className="py-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{line.product.name}</p>
                      <p className="num text-xs text-gray-500">
                        Range {ksh(line.product.floor_price_cents)} – {ksh(line.product.price_cents)}
                      </p>
                    </div>
                    <p className="num text-sm font-medium">{ksh(a.net)}</p>
                  </div>
                  <div className="mt-1.5 flex items-center gap-2">
                    <Input
                      aria-label="Quantity"
                      className="w-20"
                      inputMode="decimal"
                      value={line.qty}
                      onChange={(e) => updateLine(i, { qty: e.target.value })}
                    />
                    <span className="text-xs text-gray-500">×</span>
                    <Input
                      aria-label="Price each (KSh)"
                      title="Price each (KSh): bargain within the range"
                      className="w-28"
                      inputMode="decimal"
                      value={line.unitPrice}
                      onChange={(e) => updateLine(i, { unitPrice: e.target.value })}
                    />
                    {a.invalid ? (
                      <Badge tone="red">
                        {toCents(line.unitPrice) === null ? "Enter a price" : "Above selling price"}
                      </Badge>
                    ) : (
                      a.belowFloor && <Badge tone="amber">Below minimum</Badge>
                    )}
                    <button
                      onClick={() => setCart((lines) => lines.filter((_, j) => j !== i))}
                      className="ml-auto text-xs text-gray-400 hover:text-red-600"
                    >
                      Remove
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <div className="mt-3 flex items-baseline justify-between border-t border-gray-200 pt-3">
          <span className="text-sm font-medium">Total</span>
          <span className="num text-2xl font-semibold">{ksh(totals.total)}</span>
        </div>

        <div className="mt-4 space-y-3">
          <Field label="Customer" hint={hasCredit ? "Required for credit." : "Optional."}>
            <Select value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
              <option value="">Walk-in customer</option>
              {customers.data?.filter((c) => c.active).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} — available {ksh(c.available_credit_cents)}
                  {c.overdue_cents > 0 ? " (overdue)" : ""}
                </option>
              ))}
            </Select>
          </Field>

          <div className="space-y-2">
            <p className="text-sm font-medium text-gray-700">Payment</p>
            {tenders.map((t, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <Select
                  aria-label="Payment method"
                  className="w-28"
                  value={t.method}
                  onChange={(e) => updateTender(i, { method: e.target.value as Method })}
                >
                  {(Object.keys(METHOD_LABELS) as Method[]).map((m) => (
                    <option key={m} value={m}>
                      {METHOD_LABELS[m]}
                    </option>
                  ))}
                </Select>
                <Input
                  aria-label="Amount (KSh)"
                  placeholder="Amount"
                  className="w-28"
                  inputMode="decimal"
                  value={t.amount}
                  onChange={(e) => updateTender(i, { amount: e.target.value })}
                />
                {t.method === "mpesa" && (
                  <Input
                    aria-label="M-Pesa code"
                    placeholder="M-Pesa code"
                    className="w-32 uppercase"
                    value={t.code}
                    onChange={(e) => updateTender(i, { code: e.target.value })}
                  />
                )}
                {tenders.length > 1 && (
                  <button
                    onClick={() => setTenders((ts) => ts.filter((_, j) => j !== i))}
                    className="text-xs text-gray-400 hover:text-red-600"
                  >
                    Remove
                  </button>
                )}
              </div>
            ))}
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={totals.due === 0}
                onClick={() => {
                  // Put the remaining amount on the last payment row.
                  const last = tenders.length - 1;
                  const current = toCents(tenders[last].amount || "0") ?? 0;
                  updateTender(last, { amount: centsToInput(current + totals.due) });
                }}
              >
                Fill remaining {totals.due > 0 && ksh(totals.due)}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setTenders((ts) => [...ts, { method: "mpesa", amount: "", code: "" }])}
              >
                Split payment
              </Button>
            </div>
          </div>

          {totals.change > 0 && (
            <Notice tone="green">
              Change due: <strong className="num">{ksh(totals.change)}</strong>
            </Notice>
          )}

          {session?.role === "owner" && needsFloorReason && (
            <Field label="Reason for selling below the price floor">
              <Input value={floorReason} onChange={(e) => setFloorReason(e.target.value)} />
            </Field>
          )}
          {session?.role === "owner" && needsCreditReason && (
            <Field label="Reason for overriding the credit check">
              <Input value={creditReason} onChange={(e) => setCreditReason(e.target.value)} />
            </Field>
          )}

          <ErrorText error={sale.error} />

          <Button size="lg" className="w-full" disabled={!canCharge} onClick={() => sale.mutate()}>
            {sale.isPending ? "Posting…" : `Charge ${ksh(totals.total)}`}
          </Button>
        </div>
      </Card>

      {receiptFor && (
        <ReceiptModal
          saleId={receiptFor}
          onClose={() => {
            setReceiptFor(null);
            reset();
          }}
          closeLabel="New sale"
        />
      )}
    </div>
  );
}
