"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { type FormEvent, type KeyboardEvent, useMemo, useState } from "react";
import { MinPriceEditor } from "@/components/products/min-price-editor";
import {
  PRICING_MODES,
  type PricingMode,
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
  Select,
  Table,
  Td,
  Th,
  cx,
} from "@/components/ui";
import { type Schemas, api, call, newId } from "@/lib/api";
import { centsToInput, ksh, pct, qty, toCents } from "@/lib/format";
import { useProducts, useRefreshAll } from "@/lib/queries";
import { useSession } from "@/lib/use-session";

type Product = Schemas["ProductOut"];

export function AvailableStock() {
  const session = useSession();
  const isOwner = session?.role === "owner";
  const [includeInactive, setIncludeInactive] = useState(false);
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [editingMins, setEditingMins] = useState(false);
  const products = useProducts(isOwner && includeInactive);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    const list = products.data ?? [];
    return term
      ? list.filter(
          (p) =>
            p.name.toLowerCase().includes(term) ||
            p.sku.toLowerCase().includes(term) ||
            (p.category ?? "").toLowerCase().includes(term),
        )
      : list;
  }, [products.data, search]);

  const totalValue = filtered.reduce((sum, p) => sum + p.stock_value_cents, 0);

  return (
    <div className="space-y-4">
      {isOwner && <PriceSuggestions />}

      {editingMins && products.data ? (
        <MinPriceEditor
          products={products.data.filter((p) => p.active)}
          onDone={() => setEditingMins(false)}
        />
      ) : (
        <Card
          title={`${filtered.length} products · stock value ${ksh(totalValue)}`}
          actions={
            isOwner && (
              <label className="flex items-center gap-2 text-sm text-gray-600">
                <input
                  type="checkbox"
                  checked={includeInactive}
                  onChange={(e) => setIncludeInactive(e.target.checked)}
                />
                Show inactive
              </label>
            )
          }
        >
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Input
              placeholder="Search by name, SKU or category"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="min-w-52 flex-1"
            />
            {isOwner && (
              <>
                <Button variant="secondary" onClick={() => setEditingMins(true)} disabled={editingMins}>
                  Set minimum prices
                </Button>
                <Button onClick={() => setCreating(true)}>New product</Button>
              </>
            )}
          </div>
          {products.isPending ? (
            <Loading />
          ) : products.error ? (
            <ErrorText error={products.error} />
          ) : filtered.length === 0 ? (
            <Empty>{search ? "No products match." : "No products yet."}</Empty>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Product</Th>
                  <Th right>BP (avg cost)</Th>
                  <Th right>Sell price</Th>
                  <Th right>Margin</Th>
                  <Th right>On hand</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map((p) => (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <Td>
                      <Link href={`/products/${p.id}`} className="font-medium text-gray-900 hover:text-emerald-700">
                        {p.name}
                      </Link>
                      <span className="block text-xs text-gray-500">
                        {p.sku}
                        {p.category ? ` · ${p.category}` : ""}
                      </span>
                      {(p.below_floor || isLowStock(p) || !p.active) && (
                        <span className="mt-0.5 flex flex-wrap gap-1">
                          {!p.active && <Badge>Inactive</Badge>}
                          {isLowStock(p) && <Badge tone="amber">Low stock</Badge>}
                          {p.below_floor && <Badge tone="red">Below minimum</Badge>}
                        </span>
                      )}
                    </Td>
                    <Td right>{ksh(p.wac_cents)}</Td>
                    <PriceCell p={p} isOwner={isOwner} />
                    <Td right>{pct(p.margin)}</Td>
                    <Td right>
                      {qty(p.qty_on_hand)} <span className="text-xs text-gray-500">{p.uom}</span>
                      <span className="block text-xs text-gray-500">{ksh(p.stock_value_cents)}</span>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}

      {creating && <NewProductModal onClose={() => setCreating(false)} />}
    </div>
  );
}

/** Sell price cell: owners click to type a new price; the margin updates from it. */
function PriceCell({ p, isOwner }: { p: Product; isOwner: boolean }) {
  const refreshAll = useRefreshAll();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [initial, setInitial] = useState(0);

  const save = useMutation({
    mutationFn: (cents: number) =>
      call(
        api.PUT("/products/{product_id}/pricing", {
          params: { path: { product_id: p.id } },
          body: {
            pricing_mode: "manual",
            price_cents: cents,
            target_value: null,
            reason: "Edited on the Stock page",
          },
        }),
      ),
    onSuccess: () => {
      refreshAll();
      setEditing(false);
    },
  });

  const start = () => {
    setInitial(p.price_cents);
    setValue(centsToInput(p.price_cents));
    setEditing(true);
  };
  const commit = (v: string) => {
    if (save.isPending) return;
    const cents = toCents(v);
    if (cents === null || cents < 0 || cents === initial) return setEditing(false);
    save.mutate(cents);
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") commit(value);
    if (e.key === "Escape") setEditing(false);
  };

  if (!isOwner) {
    return (
      <Td right>
        <span className="font-medium">{ksh(p.price_cents)}</span>
      </Td>
    );
  }

  if (editing) {
    const cents = toCents(value);
    const invalid = cents === null || cents < 0;
    const liveMargin = !invalid && cents !== null && p.wac_cents > 0 ? (cents - p.wac_cents) / cents : null;
    const belowCost = cents !== null && !invalid && cents < p.wac_cents;
    return (
      <Td right>
        <div className="flex justify-end">
          <div>
            <Input
              autoFocus
              inputMode="decimal"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={onKey}
              onBlur={() => commit(value)}
              className="w-24 text-right"
            />
            <span
              className={cx(
                "block text-xs",
                invalid || belowCost ? "text-red-600" : "text-gray-500",
              )}
            >
              {invalid
                ? "Enter an amount in KSh."
                : belowCost
                  ? "Below cost"
                  : liveMargin !== null
                    ? `margin ${pct(liveMargin)}`
                    : "No cost yet"}
            </span>
          </div>
        </div>
      </Td>
    );
  }

  return (
    <Td right>
      <button
        type="button"
        onClick={start}
        title="Click to change the price"
        className="rounded px-1 text-right hover:bg-emerald-50"
      >
        <span className="block font-medium">{ksh(p.price_cents)}</span>
        <span className="block text-xs text-gray-500">
          {p.min_price_cents === null ? `min ${ksh(p.floor_price_cents)} (auto)` : `min ${ksh(p.min_price_cents)}`}
        </span>
      </button>
    </Td>
  );
}

function PriceSuggestions() {
  const refreshAll = useRefreshAll();
  const products = useProducts(true);
  const suggestions = useQuery({
    queryKey: ["price-suggestions", "pending"],
    queryFn: () => call(api.GET("/price-suggestions", { params: { query: { status: "pending" } } })),
  });
  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) =>
      approve
        ? call(api.POST("/price-suggestions/{suggestion_id}/approve", { params: { path: { suggestion_id: id } } }))
        : call(api.POST("/price-suggestions/{suggestion_id}/reject", { params: { path: { suggestion_id: id } } })),
    onSuccess: refreshAll,
  });

  if (!suggestions.data?.length) return null;
  const names = new Map((products.data ?? []).map((p) => [p.id, p.name]));

  return (
    <Card title="Price suggestions">
      <p className="mb-3 text-sm text-gray-600">
        Costs moved by more than the repricing threshold. Approve to change the price, or reject to keep it.
      </p>
      <ErrorText error={decide.error} />
      <ul className="divide-y divide-gray-100">
        {suggestions.data.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 py-2">
            <div>
              <Link href={`/products/${s.product_id}`} className="text-sm font-medium hover:text-emerald-700">
                {names.get(s.product_id) ?? "Product"}
              </Link>
              <p className="num text-sm">
                {ksh(s.price_at_suggestion)} → <strong>{ksh(s.suggested_price)}</strong>
              </p>
              <p className="num text-xs text-gray-500">
                Cost {ksh(s.previous_wac)} → {ksh(s.trigger_wac)}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: s.id, approve: false })}
              >
                Reject
              </Button>
              <Button size="sm" disabled={decide.isPending} onClick={() => decide.mutate({ id: s.id, approve: true })}>
                Approve
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function NewProductModal({ onClose }: { onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const [form, setForm] = useState({
    sku: "",
    name: "",
    category: "",
    uom: "pcs",
    supplier_name: "",
    price: "",
    pricing_mode: "manual" as PricingMode,
    target: "",
    reorder_point: "0",
    lead_time_days: "0",
  });
  const [localError, setLocalError] = useState<string | null>(null);
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));

  const create = useMutation({
    mutationFn: (body: Schemas["ProductCreate"]) =>
      call(api.POST("/products", { body })),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    const price = toCents(form.price || "0");
    if (price === null || price < 0) return setLocalError("Enter a valid price in KSh.");
    let target: string | null = null;
    if (form.pricing_mode !== "manual") {
      target = percentToFraction(form.target);
      if (target === null) return setLocalError("Enter the target as a percentage, e.g. 25.");
    }
    create.mutate({
      id: newId(),
      sku: form.sku.trim() || null,
      name: form.name.trim(),
      category: form.category.trim() || null,
      uom: form.uom.trim() || "pcs",
      supplier_name: null,
      price_cents: price,
      pricing_mode: form.pricing_mode,
      target_value: target,
      reorder_point: form.reorder_point || "0",
      lead_time_days: Number(form.lead_time_days) || 0,
    });
  };

  const mode = PRICING_MODES.find((m) => m.value === form.pricing_mode);

  return (
    <Modal open onClose={onClose} title="New product">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Barcode / SKU" hint="Optional: generated if left empty.">
            <Input value={form.sku} onChange={(e) => set({ sku: e.target.value })} />
          </Field>
          <Field label="Unit">
            <Input value={form.uom} onChange={(e) => set({ uom: e.target.value })} placeholder="pcs, kg, L" />
          </Field>
        </div>
        <Field label="Name">
          <Input value={form.name} onChange={(e) => set({ name: e.target.value })} required autoFocus />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Category">
            <Input value={form.category} onChange={(e) => set({ category: e.target.value })} />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Pricing" hint={mode?.hint}>
            <Select value={form.pricing_mode} onChange={(e) => set({ pricing_mode: e.target.value as PricingMode })}>
              {PRICING_MODES.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
          </Field>
          {form.pricing_mode === "manual" ? (
            <Field label="Selling price (KSh)">
              <Input inputMode="decimal" value={form.price} onChange={(e) => set({ price: e.target.value })} />
            </Field>
          ) : (
            <Field label={`${modeLabel(form.pricing_mode)} (%)`}>
              <Input inputMode="decimal" value={form.target} onChange={(e) => set({ target: e.target.value })} />
            </Field>
          )}
        </div>
        {form.pricing_mode !== "manual" && (
          <Field
            label="Starting price (KSh, optional)"
            hint="There is no cost yet. The first delivery will suggest a price from your target."
          >
            <Input inputMode="decimal" value={form.price} onChange={(e) => set({ price: e.target.value })} />
          </Field>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Reorder point" hint="Low-stock alert at or below this.">
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
        <ErrorText error={localError ?? create.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Saving…" : "Create product"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
