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
  Modal,
  Notice,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { type Schemas, api, call, newId } from "@/lib/api";
import { centsToInput, ksh, pct, qty as fmtQty, toCents } from "@/lib/format";
import { useProducts, useRefreshAll } from "@/lib/queries";

type ProductSet = Schemas["SetOut"];
type Product = Schemas["ProductOut"];

export default function SetsPage() {
  const sets = useQuery({ queryKey: ["sets"], queryFn: () => call(api.GET("/sets")) });
  const [editing, setEditing] = useState<ProductSet | "new" | null>(null);
  const [converting, setConverting] = useState<ProductSet | null>(null);
  const [resharing, setResharing] = useState<ProductSet | null>(null);

  return (
    <OwnerOnly>
      <PageHeader
        title="Sets"
        description="Things bought as one set but sold as separate items, like Sufuria sizes 1–5 or a dinner set. Each item has its own price; when a set comes in, its cost is shared by those prices, so every item earns the same margin."
        actions={<Button onClick={() => setEditing("new")}>New set</Button>}
      />
      {sets.isPending ? (
        <Loading />
      ) : sets.error ? (
        <ErrorText error={sets.error} />
      ) : sets.data.length === 0 ? (
        <Card>
          <Empty>No sets yet. Create one, then add it under Add stock by its name.</Empty>
        </Card>
      ) : (
        <div className="space-y-4">
          {sets.data.map((s) => (
            <SetCard
              key={s.id}
              set={s}
              onEdit={() => setEditing(s)}
              onConvert={() => setConverting(s)}
              onReshare={() => setResharing(s)}
            />
          ))}
        </div>
      )}
      {editing && (
        <SetEditor set={editing === "new" ? null : editing} onClose={() => setEditing(null)} />
      )}
      {converting && <ConvertStock set={converting} onClose={() => setConverting(null)} />}
      {resharing && <ReshareCost set={resharing} onClose={() => setResharing(null)} />}
    </OwnerOnly>
  );
}

function SetCard({
  set,
  onEdit,
  onConvert,
  onReshare,
}: {
  set: ProductSet;
  onEdit: () => void;
  onConvert: () => void;
  onReshare: () => void;
}) {
  return (
    <Card
      title={
        <span>
          {set.name}
          {set.category && <span className="ml-2 text-xs font-normal text-gray-500">{set.category}</span>}
        </span>
      }
      actions={
        <>
          <Button variant="secondary" size="sm" onClick={onConvert}>
            Move stock in
          </Button>
          <Button variant="secondary" size="sm" onClick={onReshare}>
            Re-share stock cost
          </Button>
          <Button variant="secondary" size="sm" onClick={onEdit}>
            Edit
          </Button>
        </>
      }
    >
      <Table>
        <thead>
          <tr>
            <Th>Item</Th>
            <Th right>Per set</Th>
            <Th right>Selling price</Th>
            <Th right>Share of set cost</Th>
            <Th right>Avg cost</Th>
            <Th right>Margin</Th>
            <Th right>In stock</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {set.components.map((c) => (
            <tr key={c.product_id}>
              <Td>
                <Link href={`/products/${c.product_id}`} className="font-medium hover:text-emerald-800">
                  {c.name}
                </Link>
              </Td>
              <Td right>{fmtQty(c.qty_per_set)}</Td>
              <Td right>{ksh(c.price_cents)}</Td>
              <Td right>{pct(c.cost_share)}</Td>
              <Td right>{c.wac_cents ? ksh(c.wac_cents) : "—"}</Td>
              <Td right>
                {c.wac_cents && c.price_cents
                  ? pct((c.price_cents - c.wac_cents) / c.price_cents)
                  : "—"}
              </Td>
              <Td right>{fmtQty(c.qty_on_hand)}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <p className="num mt-3 text-sm text-gray-600">
        One full set sells for {ksh(set.set_value_cents)}. Add stock by typing{" "}
        <strong>{set.name}</strong> and the price you paid per set.
      </p>
    </Card>
  );
}

type Row = { key: string; productId: string | null; name: string; qty: string; price: string };

function SetEditor({ set, onClose }: { set: ProductSet | null; onClose: () => void }) {
  const products = useProducts(true);
  const refreshAll = useRefreshAll();
  const [name, setName] = useState(set?.name ?? "");
  const [category, setCategory] = useState(set?.category ?? "");
  const [rows, setRows] = useState<Row[]>(() =>
    set
      ? set.components.map((c) => ({
          key: c.product_id,
          productId: c.product_id,
          name: c.name,
          qty: fmtQty(c.qty_per_set),
          price: centsToInput(c.price_cents),
        }))
      : [0, 1].map(() => ({ key: newId(), productId: null, name: "", qty: "1", price: "" })),
  );
  const [localError, setLocalError] = useState<string | null>(null);
  const [setId] = useState(() => set?.id ?? newId());

  const byName = useMemo(
    () => new Map((products.data ?? []).map((p) => [p.name.trim().toLowerCase(), p])),
    [products.data],
  );
  const update = (i: number, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const values = rows.map((r) => (Number(r.qty) || 0) * (toCents(r.price || "0") ?? 0));
  const total = values.reduce((a, b) => a + b, 0);

  const save = useMutation({
    mutationFn: (body: Schemas["SetUpsert"]) =>
      set
        ? call(api.PUT("/sets/{set_id}", { params: { path: { set_id: set.id } }, body }))
        : call(api.POST("/sets", { body })),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    const filled = rows.filter((r) => r.name.trim() || r.price);
    if (!name.trim()) return setLocalError("Give the set a name.");
    if (!filled.length) return setLocalError("Add the items in the set.");
    for (const r of filled) {
      if (!r.name.trim()) return setLocalError("Every item needs a name.");
      if (!(Number(r.qty) > 0)) return setLocalError(`How many ${r.name} come in one set?`);
      if (!((toCents(r.price) ?? 0) > 0)) return setLocalError(`Give ${r.name} a selling price.`);
    }
    save.mutate({
      id: setId,
      name: name.trim(),
      category: category.trim() || null,
      components: filled.map((r) => {
        const existing = r.productId ?? byName.get(r.name.trim().toLowerCase())?.id ?? null;
        const base = { qty_per_set: r.qty, price_cents: toCents(r.price) ?? 0 };
        return existing ? { ...base, product_id: existing } : { ...base, name: r.name.trim() };
      }),
    });
  };

  return (
    <Modal open onClose={onClose} title={set ? `Edit ${set.name}` : "New set"}>
      <form onSubmit={submit} className="space-y-4">
        <datalist id="set-item-names">
          {products.data?.map((p) => <option key={p.id} value={p.name} />)}
        </datalist>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Set name" hint="What you type under Add stock.">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sufuria set 1-5" autoFocus />
          </Field>
          <Field label="Category">
            <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. Sufuria" />
          </Field>
        </div>

        <div>
          <p className="mb-2 text-sm font-medium text-gray-700">Items in one set</p>
          <div className="space-y-2">
            <div className="grid grid-cols-12 gap-2 text-xs text-gray-500">
              <span className="col-span-6">Item (size or piece)</span>
              <span className="col-span-2">Qty per set</span>
              <span className="col-span-3">Selling price (KSh)</span>
            </div>
            {rows.map((r, i) => (
              <div key={r.key} className="grid grid-cols-12 items-center gap-2">
                <Input
                  className="col-span-6 w-full"
                  list="set-item-names"
                  aria-label="Item name"
                  value={r.name}
                  disabled={!!r.productId}
                  onChange={(e) => update(i, { name: e.target.value })}
                  placeholder="e.g. Sufuria size 1"
                />
                <Input
                  className="col-span-2 w-full"
                  aria-label="Qty per set"
                  inputMode="decimal"
                  value={r.qty}
                  onChange={(e) => update(i, { qty: e.target.value })}
                />
                <Input
                  className="col-span-3 w-full"
                  aria-label="Selling price"
                  inputMode="decimal"
                  value={r.price}
                  onChange={(e) => update(i, { price: e.target.value })}
                />
                <button
                  type="button"
                  onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}
                  className="col-span-1 text-xs text-gray-400 hover:text-red-600"
                  aria-label={`Remove ${r.name || "item"}`}
                >
                  ✕
                </button>
                {total > 0 && values[i] > 0 && (
                  <span className="col-span-12 -mt-1 text-xs text-gray-500">
                    Carries {pct(values[i] / total)} of the set&apos;s cost
                  </span>
                )}
              </div>
            ))}
          </div>
          <Button
            variant="secondary"
            size="sm"
            className="mt-2"
            onClick={() =>
              setRows((rs) => [...rs, { key: newId(), productId: null, name: "", qty: "1", price: "" }])
            }
          >
            Add item
          </Button>
        </div>

        <p className="num text-sm text-gray-700">A full set sells for {ksh(Math.round(total))}.</p>
        {set && <Notice>Removing an item takes it out of the set; the item itself and its stock stay.</Notice>}
        <ErrorText error={localError} />
        <ErrorText error={save.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save set"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** Move stock already on hand (e.g. an old "Sufuria(1-5)" item) into the set's items. */
function ConvertStock({ set, onClose }: { set: ProductSet; onClose: () => void }) {
  const products = useProducts();
  const refreshAll = useRefreshAll();
  const members = new Set(set.components.map((c) => c.product_id));
  const candidates = (products.data ?? []).filter(
    (p) => !members.has(p.id) && Number(p.qty_on_hand) > 0,
  );
  const [sourceId, setSourceId] = useState("");
  const [sourceQty, setSourceQty] = useState("");
  const [targetQty, setTargetQty] = useState<Record<string, string>>(() =>
    Object.fromEntries(set.components.map((c) => [c.product_id, ""])),
  );
  const [reason, setReason] = useState("");
  const source: Product | undefined = candidates.find((p) => p.id === sourceId);

  const value = source ? Math.round((Number(sourceQty) || 0) * source.wac_cents) : 0;
  const weights = set.components.map((c) => (Number(targetQty[c.product_id]) || 0) * c.price_cents);
  const weightTotal = weights.reduce((a, b) => a + b, 0);
  const targets = set.components.filter((c) => Number(targetQty[c.product_id]) > 0);

  const convert = useMutation({
    mutationFn: () =>
      call(
        api.POST("/sets/{set_id}/convert-stock", {
          params: { path: { set_id: set.id } },
          body: {
            sources: [{ product_id: sourceId, qty: sourceQty }],
            targets: targets.map((c) => ({ product_id: c.product_id, qty: targetQty[c.product_id] })),
            reason,
            deactivate_emptied_sources: true,
          },
        }),
      ),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });

  return (
    <Modal open onClose={onClose} title={`Move stock into ${set.name}`}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          convert.mutate();
        }}
      >
        <p className="text-sm text-gray-600">
          Take stock recorded under another item (like an old &quot;Sufuria(1-5)&quot; line) and
          put it on the set&apos;s items. Its total cost moves with it, shared by selling price.
        </p>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Take from" className="col-span-2">
            <Select value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
              <option value="">Choose an item…</option>
              {candidates.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({fmtQty(p.qty_on_hand)} in stock, cost {ksh(p.wac_cents)})
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Qty">
            <Input
              inputMode="decimal"
              value={sourceQty}
              onChange={(e) => setSourceQty(e.target.value)}
              placeholder={source ? fmtQty(source.qty_on_hand) : ""}
            />
          </Field>
        </div>

        <div>
          <p className="mb-2 text-sm font-medium text-gray-700">Put onto</p>
          <div className="space-y-2">
            {set.components.map((c, i) => (
              <div key={c.product_id} className="flex items-center gap-3 text-sm">
                <span className="flex-1">{c.name}</span>
                <span className="num text-xs text-gray-500">{ksh(c.price_cents)}</span>
                <Input
                  aria-label={`Qty of ${c.name}`}
                  className="w-20"
                  inputMode="decimal"
                  value={targetQty[c.product_id]}
                  onChange={(e) => setTargetQty((t) => ({ ...t, [c.product_id]: e.target.value }))}
                />
                <span className="num w-28 text-right text-xs text-gray-500">
                  {weightTotal > 0 && weights[i] > 0
                    ? `≈ ${ksh(Math.round((value * weights[i]) / weightTotal / Number(targetQty[c.product_id])))} each`
                    : ""}
                </span>
              </div>
            ))}
          </div>
        </div>

        <Field label="Reason">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. split into sizes" />
        </Field>
        {source && (
          <p className="num text-sm text-gray-700">
            Moving {ksh(value)} of cost from {source.name}.
            {Number(sourceQty) === Number(source.qty_on_hand) && (
              <span className="ml-1">
                <Badge>{source.name} will be hidden once empty</Badge>
              </span>
            )}
          </p>
        )}
        <ErrorText error={convert.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={!source || !(Number(sourceQty) > 0) || !targets.length || !reason.trim() || convert.isPending}
          >
            Move stock
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** Re-share the cost of the set's stock on hand across its items by selling price. */
function ReshareCost({ set, onClose }: { set: ProductSet; onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const [reason, setReason] = useState("cost shared by selling price");
  const stocked = set.components.filter((c) => Number(c.qty_on_hand) > 0);
  const value = stocked.reduce((sum, c) => sum + Math.round(Number(c.qty_on_hand) * c.wac_cents), 0);
  const weight = stocked.reduce((sum, c) => sum + Number(c.qty_on_hand) * c.price_cents, 0);
  const reshare = useMutation({
    mutationFn: () =>
      call(
        api.POST("/sets/{set_id}/reshare-cost", {
          params: { path: { set_id: set.id } },
          body: { reason },
        }),
      ),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });
  return (
    <Modal open onClose={onClose} title={`Re-share cost: ${set.name}`}>
      <div className="space-y-4">
        <p className="text-sm text-gray-600">
          The {ksh(value)} of stock on hand keeps its total cost; each item&apos;s cost is re-worked
          from its selling price, so every item earns the same margin.
        </p>
        {stocked.length === 0 ? (
          <Notice>None of this set&apos;s items are in stock.</Notice>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Item</Th>
                <Th right>In stock</Th>
                <Th right>Price</Th>
                <Th right>Cost now</Th>
                <Th right>Cost after</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {stocked.map((c) => (
                <tr key={c.product_id}>
                  <Td>{c.name}</Td>
                  <Td right>{fmtQty(c.qty_on_hand)}</Td>
                  <Td right>{ksh(c.price_cents)}</Td>
                  <Td right>{ksh(c.wac_cents)}</Td>
                  <Td right className="font-medium">
                    {weight > 0 ? ksh(Math.round((value * c.price_cents) / weight)) : "—"}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        <Field label="Reason">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorText error={reshare.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => reshare.mutate()}
            disabled={!stocked.length || !reason.trim() || reshare.isPending}
          >
            Re-share cost
          </Button>
        </div>
      </div>
    </Modal>
  );
}
