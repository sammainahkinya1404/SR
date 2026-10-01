"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import {
  PRICING_MODES,
  type PricingMode,
  fractionToPercent,
  isLowStock,
  modeLabel,
  percentToFraction,
} from "@/components/products/pricing";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  Modal,
  Notice,
  PageHeader,
  Select,
  Stat,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { type Schemas, api, call, newId } from "@/lib/api";
import { centsToInput, dateTime, ksh, pct, qty, toCents } from "@/lib/format";
import { useRefreshAll } from "@/lib/queries";
import { useSession } from "@/lib/use-session";

type Product = Schemas["ProductOut"];

const MOVEMENT_LABELS: Record<string, string> = {
  purchase: "Delivery",
  sale: "Sale",
  return: "Return",
  adjustment: "Adjustment",
  damage: "Damaged",
  theft: "Theft",
  owner_consumption: "Owner use",
};

export default function ProductPage() {
  const { id } = useParams<{ id: string }>();
  const session = useSession();
  const isOwner = session?.role === "owner";
  const [modal, setModal] = useState<"edit" | "pricing" | "min-price" | "write-off" | null>(null);

  const product = useQuery({
    queryKey: ["product", id],
    queryFn: () => call(api.GET("/products/{product_id}", { params: { path: { product_id: id } } })),
  });
  const movements = useQuery({
    queryKey: ["product", id, "movements"],
    queryFn: () =>
      call(api.GET("/products/{product_id}/movements", { params: { path: { product_id: id } } })),
  });
  const history = useQuery({
    queryKey: ["product", id, "price-history"],
    queryFn: () =>
      call(api.GET("/products/{product_id}/price-history", { params: { path: { product_id: id } } })),
    enabled: isOwner,
  });

  if (product.isPending) return <Loading />;
  if (product.error) return <ErrorText error={product.error} />;
  const p = product.data;

  return (
    <div className="space-y-4">
      <Link href="/stock" className="text-sm text-emerald-700 hover:underline">
        ← Stock
      </Link>
      <PageHeader
        title={p.name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span>
              {p.sku}
              {p.category ? ` · ${p.category}` : ""}
            </span>
            {!p.active && <Badge>Inactive</Badge>}
            {isLowStock(p) && <Badge tone="amber">Low stock</Badge>}
            {p.below_floor && <Badge tone="red">Price below minimum</Badge>}
          </span>
        }
        actions={
          isOwner && (
            <>
              <Button variant="secondary" onClick={() => setModal("edit")}>
                Edit details
              </Button>
              <Button variant="secondary" onClick={() => setModal("pricing")}>
                Change price
              </Button>
              <Button variant="secondary" onClick={() => setModal("min-price")}>
                Set minimum price
              </Button>
              <Button variant="secondary" onClick={() => setModal("write-off")}>
                Write off stock
              </Button>
            </>
          )
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Price range"
          value={`${ksh(p.floor_price_cents)} – ${ksh(p.price_cents)}`}
          sub={p.min_price_cents === null ? "Minimum is automatic (cost + floor %)" : "Minimum set by owner"}
        />
        <Stat label="Cost (WAC)" value={ksh(p.wac_cents)} sub={modeLabel(p.pricing_mode)} />
        <Stat label="Margin / markup" value={pct(p.margin)} sub={`Markup ${pct(p.markup)}`} />
        <Stat
          label="On hand"
          value={`${qty(p.qty_on_hand)} ${p.uom}`}
          sub={`Worth ${ksh(p.stock_value_cents)} · reorder at ${qty(p.reorder_point)}`}
        />
      </div>

      <Card title="Stock movements">
        {movements.isPending ? (
          <Loading />
        ) : movements.error ? (
          <ErrorText error={movements.error} />
        ) : movements.data.length === 0 ? (
          <Empty>No stock has moved yet.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>When</Th>
                <Th>Type</Th>
                <Th right>Qty</Th>
                <Th right>Unit cost</Th>
                <Th right>WAC after</Th>
                <Th>Reason</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {[...movements.data].reverse().map((m) => (
                <tr key={m.id}>
                  <Td>{dateTime(m.ts)}</Td>
                  <Td>{MOVEMENT_LABELS[m.type] ?? m.type}</Td>
                  <Td right className={Number(m.qty) < 0 ? "text-red-700" : "text-emerald-700"}>
                    {Number(m.qty) > 0 ? "+" : ""}
                    {qty(m.qty)}
                  </Td>
                  <Td right>{ksh(m.unit_cost)}</Td>
                  <Td right>{ksh(m.wac_snapshot)}</Td>
                  <Td className="max-w-xs truncate text-gray-600">{m.reason ?? ""}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {isOwner && (
        <Card title="Price history">
          {history.isPending ? (
            <Loading />
          ) : history.error ? (
            <ErrorText error={history.error} />
          ) : history.data.length === 0 ? (
            <Empty>The price has not changed.</Empty>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>When</Th>
                  <Th right>Old</Th>
                  <Th right>New</Th>
                  <Th>Reason</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {[...history.data].reverse().map((h, i) => (
                  <tr key={`${h.ts}-${i}`}>
                    <Td>{dateTime(h.ts)}</Td>
                    <Td right>{ksh(h.old_price)}</Td>
                    <Td right>{ksh(h.new_price)}</Td>
                    <Td className="text-gray-600">{h.reason}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {modal === "edit" && <EditModal product={p} onClose={() => setModal(null)} />}
      {modal === "pricing" && <PricingModal product={p} onClose={() => setModal(null)} />}
      {modal === "min-price" && <MinPriceModal product={p} onClose={() => setModal(null)} />}
      {modal === "write-off" && <WriteOffModal product={p} onClose={() => setModal(null)} />}
    </div>
  );
}

function EditModal({ product, onClose }: { product: Product; onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const [form, setForm] = useState({
    sku: product.sku,
    name: product.name,
    category: product.category ?? "",
    uom: product.uom,
    supplier_name: product.supplier_name ?? "",
    reorder_point: qty(product.reorder_point),
    lead_time_days: String(product.lead_time_days),
    active: product.active,
  });
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));
  const save = useMutation({
    mutationFn: () =>
      call(
        api.PATCH("/products/{product_id}", {
          params: { path: { product_id: product.id } },
          body: {
            sku: form.sku.trim(),
            name: form.name.trim(),
            category: form.category.trim() || null,
            uom: form.uom.trim() || "pcs",
            supplier_name: form.supplier_name.trim() || null,
            reorder_point: form.reorder_point || "0",
            lead_time_days: Number(form.lead_time_days) || 0,
            active: form.active,
          },
        }),
      ),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });

  return (
    <Modal open onClose={onClose} title="Edit product">
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          save.mutate();
        }}
        className="space-y-3"
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label="SKU / barcode">
            <Input value={form.sku} onChange={(e) => set({ sku: e.target.value })} required />
          </Field>
          <Field label="Unit">
            <Input value={form.uom} onChange={(e) => set({ uom: e.target.value })} />
          </Field>
        </div>
        <Field label="Name">
          <Input value={form.name} onChange={(e) => set({ name: e.target.value })} required />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Category">
            <Input value={form.category} onChange={(e) => set({ category: e.target.value })} />
          </Field>
          <Field label="Reorder point">
            <Input
              inputMode="decimal"
              value={form.reorder_point}
              onChange={(e) => set({ reorder_point: e.target.value })}
            />
          </Field>
          <Field label="Lead time (days)">
            <Input
              inputMode="numeric"
              value={form.lead_time_days}
              onChange={(e) => set({ lead_time_days: e.target.value })}
            />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.active} onChange={(e) => set({ active: e.target.checked })} />
          Active (inactive products can&apos;t be sold)
        </label>
        <ErrorText error={save.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function PricingModal({ product, onClose }: { product: Product; onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const [mode, setMode] = useState<PricingMode>(product.pricing_mode);
  const [target, setTarget] = useState(fractionToPercent(product.target_value));
  const [price, setPrice] = useState(centsToInput(product.price_cents));
  const [reason, setReason] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (body: Schemas["PricingUpdate"]) =>
      call(
        api.PUT("/products/{product_id}/pricing", {
          params: { path: { product_id: product.id } },
          body,
        }),
      ),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });

  // Preview the rule-based price (before rounding) from the current WAC.
  const fraction = mode === "manual" ? null : percentToFraction(target);
  const preview =
    fraction === null || product.wac_cents === 0
      ? null
      : mode === "target_margin"
        ? Number(fraction) < 1
          ? Math.round(product.wac_cents / (1 - Number(fraction)))
          : null
        : Math.round(product.wac_cents * (1 + Number(fraction)));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (mode === "manual") {
      const cents = toCents(price);
      if (cents === null || cents < 0) return setLocalError("Enter a valid price in KSh.");
      save.mutate({ pricing_mode: mode, price_cents: cents, target_value: null, reason });
    } else {
      if (fraction === null) return setLocalError("Enter the target as a percentage, e.g. 25.");
      save.mutate({ pricing_mode: mode, target_value: fraction, price_cents: null, reason });
    }
  };

  return (
    <Modal open onClose={onClose} title="Change price">
      <form onSubmit={submit} className="space-y-3">
        <p className="text-sm text-gray-600">
          Current price {ksh(product.price_cents)} · cost {ksh(product.wac_cents)} · floor{" "}
          {ksh(product.floor_price_cents)}
        </p>
        <Field label="Pricing" hint={PRICING_MODES.find((m) => m.value === mode)?.hint}>
          <Select value={mode} onChange={(e) => setMode(e.target.value as PricingMode)}>
            {PRICING_MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </Select>
        </Field>
        {mode === "manual" ? (
          <Field label="New price (KSh)">
            <Input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} required />
          </Field>
        ) : (
          <Field
            label={`${modeLabel(mode)} (%)`}
            hint={
              product.wac_cents === 0
                ? "No cost yet: the first delivery will suggest a price."
                : preview !== null
                  ? `About ${ksh(preview)} before rounding.`
                  : undefined
            }
          >
            <Input inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} required />
          </Field>
        )}
        <Field label="Reason" hint="Recorded in the price history.">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} required />
        </Field>
        <ErrorText error={localError ?? save.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={save.isPending}>
            Save price
          </Button>
        </div>
      </form>
    </Modal>
  );
}

const WRITE_OFF_TYPES: { value: Schemas["WriteOffType"]; label: string; hint: string }[] = [
  { value: "damage", label: "Damaged / expired", hint: "Recorded as a stock-loss expense at cost." },
  { value: "theft", label: "Theft / missing", hint: "Recorded as a stock-loss expense at cost." },
  {
    value: "owner_consumption",
    label: "Taken by the owner",
    hint: "Recorded as an owner drawing at cost, not an expense.",
  },
];

function WriteOffModal({ product, onClose }: { product: Product; onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const [type, setType] = useState<Schemas["WriteOffType"]>("damage");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [id] = useState(newId);
  const writeOff = useMutation({
    mutationFn: () =>
      call(
        api.POST("/stock-adjustments", {
          body: { id, product_id: product.id, type, qty: amount, reason },
        }),
      ),
    onSuccess: refreshAll,
  });

  if (writeOff.data) {
    const r = writeOff.data;
    return (
      <Modal open onClose={onClose} title="Stock written off">
        <div className="space-y-3">
          <Notice tone="green">
            {qty(r.qty)} {product.uom} written off, valued at {ksh(r.value_cents)}.{" "}
            {r.drawing ? "Recorded as an owner drawing." : "Recorded as a stock-loss expense."}
          </Notice>
          {r.drawing?.warning && <Notice>{r.drawing.warning}</Notice>}
          <div className="flex justify-end">
            <Button onClick={onClose}>Done</Button>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal open onClose={onClose} title="Write off stock">
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          writeOff.mutate();
        }}
        className="space-y-3"
      >
        <p className="text-sm text-gray-600">
          {qty(product.qty_on_hand)} {product.uom} on hand at {ksh(product.wac_cents)} each.
        </p>
        <Field label="What happened" hint={WRITE_OFF_TYPES.find((t) => t.value === type)?.hint}>
          <Select value={type} onChange={(e) => setType(e.target.value as Schemas["WriteOffType"])}>
            {WRITE_OFF_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label={`Quantity (${product.uom})`}
          hint={
            Number(amount) > 0 ? `Value about ${ksh(Math.round(Number(amount) * product.wac_cents))}` : undefined
          }
        >
          <Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required />
        </Field>
        <Field label="Reason">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} required />
        </Field>
        <ErrorText error={writeOff.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="danger" disabled={writeOff.isPending || !(Number(amount) > 0)}>
            Write off
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function MinPriceModal({ product, onClose }: { product: Product; onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const [value, setValue] = useState(
    product.min_price_cents === null ? "" : centsToInput(product.min_price_cents),
  );
  const cents = value.trim() === "" ? null : toCents(value);
  const invalid = value.trim() !== "" && (cents === null || cents < 0);
  const aboveMax = cents !== null && cents > product.price_cents;
  const floor = cents ?? product.auto_floor_price_cents;
  const save = useMutation({
    mutationFn: () =>
      call(
        api.PUT("/products/min-prices", {
          body: { items: [{ product_id: product.id, min_price_cents: cents }] },
        }),
      ),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });
  return (
    <Modal open onClose={onClose} title="Minimum price">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <p className="text-sm text-gray-600">
          Cashiers can sell {product.name} anywhere from the minimum up to{" "}
          {ksh(product.price_cents)}. Below the minimum needs the owner.
        </p>
        <Field
          label="Minimum price (KSh)"
          hint={`Leave empty for the automatic minimum (cost + floor %): ${ksh(
            product.auto_floor_price_cents,
          )}.`}
        >
          <Input
            inputMode="decimal"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="automatic"
            autoFocus
          />
        </Field>
        <p className="num text-sm text-gray-700">
          Cost {ksh(product.wac_cents)} · margin at minimum{" "}
          {floor > 0 ? pct((floor - product.wac_cents) / floor) : "—"}
        </p>
        {invalid && <ErrorText error="Enter an amount in KSh." />}
        {aboveMax && <ErrorText error="The minimum can't be above the selling price." />}
        {cents !== null && cents < product.wac_cents && (
          <Notice>This minimum is below cost: a sale at the minimum would lose money.</Notice>
        )}
        <ErrorText error={save.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={invalid || aboveMax || save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  );
}
