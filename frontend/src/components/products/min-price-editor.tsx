"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Badge, Button, Card, ErrorText, Input, Notice, Table, Td, Th } from "@/components/ui";
import { type Schemas, api, call } from "@/lib/api";
import { centsToInput, ksh, pct, toCents } from "@/lib/format";
import { useRefreshAll } from "@/lib/queries";

type Product = Schemas["ProductOut"];

/** Edit the bottom of every item's price range at once. Empty = automatic (cost + floor %). */
export function MinPriceEditor({ products, onDone }: { products: Product[]; onDone: () => void }) {
  const refreshAll = useRefreshAll();
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      products.map((p) => [p.id, p.min_price_cents === null ? "" : centsToInput(p.min_price_cents)]),
    ),
  );
  const [fillPct, setFillPct] = useState("10");

  const parsed = products.map((p) => {
    const raw = values[p.id].trim();
    const cents = raw === "" ? null : toCents(raw);
    return {
      product: p,
      raw,
      cents,
      invalid: raw !== "" && (cents === null || cents < 0),
      aboveMax: cents !== null && cents > p.price_cents,
      belowCost: cents !== null && cents < p.wac_cents,
      changed: (raw === "" ? null : cents) !== p.min_price_cents,
    };
  });
  const changes = parsed.filter((r) => r.changed);
  const blocking = parsed.filter((r) => r.invalid || r.aboveMax);

  const save = useMutation({
    mutationFn: () =>
      call(
        api.PUT("/products/min-prices", {
          body: {
            items: changes.map((r) => ({ product_id: r.product.id, min_price_cents: r.cents })),
          },
        }),
      ),
    onSuccess: () => {
      refreshAll();
      onDone();
    },
  });

  /** Fill empty minimums with a % below the selling price, rounded down to the shilling. */
  const fillEmpty = () => {
    const p = Number(fillPct);
    if (!(p >= 0 && p < 100)) return;
    setValues((v) => {
      const next = { ...v };
      for (const product of products) {
        if (next[product.id].trim() === "" && product.price_cents > 0) {
          const cents = Math.floor((product.price_cents * (100 - p)) / 100 / 100) * 100;
          next[product.id] = centsToInput(cents);
        }
      }
      return next;
    });
  };

  return (
    <Card
      title="Set minimum prices"
      actions={
        <>
          <Button variant="secondary" onClick={onDone}>
            Cancel
          </Button>
          <Button
            onClick={() => save.mutate()}
            disabled={!changes.length || blocking.length > 0 || save.isPending}
          >
            {save.isPending ? "Saving…" : `Save ${changes.length || ""} change${changes.length === 1 ? "" : "s"}`}
          </Button>
        </>
      }
    >
      <p className="mb-3 text-sm text-gray-600">
        Cashiers can sell anywhere between the minimum and the selling price. Below the minimum needs
        the owner. Leave a minimum empty to use the automatic floor (cost + price floor %).
      </p>
      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <span>Fill empty minimums with</span>
        <Input
          aria-label="Percent below selling price"
          className="w-16"
          inputMode="decimal"
          value={fillPct}
          onChange={(e) => setFillPct(e.target.value)}
        />
        <span>% below the selling price</span>
        <Button variant="secondary" size="sm" onClick={fillEmpty}>
          Fill
        </Button>
      </div>

      <Table>
        <thead>
          <tr>
            <Th>Item</Th>
            <Th right>Cost</Th>
            <Th right>Selling price</Th>
            <Th right>Minimum (KSh)</Th>
            <Th right>Margin at minimum</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {parsed.map((r) => {
            const p = r.product;
            const floor = r.cents ?? p.auto_floor_price_cents;
            const margin = floor > 0 ? (floor - p.wac_cents) / floor : null;
            return (
              <tr key={p.id} className={r.changed ? "bg-emerald-50/40" : undefined}>
                <Td>
                  <span className="font-medium">{p.name}</span>
                  {p.category && <span className="ml-2 text-xs text-gray-500">{p.category}</span>}
                </Td>
                <Td right>{ksh(p.wac_cents)}</Td>
                <Td right>{ksh(p.price_cents)}</Td>
                <Td right>
                  <Input
                    aria-label={`Minimum price for ${p.name}`}
                    className="ml-auto w-28 text-right"
                    inputMode="decimal"
                    placeholder={`auto ${centsToInput(p.auto_floor_price_cents)}`}
                    value={values[p.id]}
                    onChange={(e) => setValues((v) => ({ ...v, [p.id]: e.target.value }))}
                  />
                  {r.invalid && <span className="mt-1 block text-xs text-red-600">Not an amount</span>}
                  {r.aboveMax && (
                    <span className="mt-1 block text-xs text-red-600">Above the selling price</span>
                  )}
                </Td>
                <Td right>
                  {pct(margin)}
                  {r.belowCost && (
                    <span className="ml-2">
                      <Badge tone="red">Below cost</Badge>
                    </span>
                  )}
                </Td>
              </tr>
            );
          })}
        </tbody>
      </Table>
      {parsed.some((r) => r.belowCost) && (
        <div className="mt-3">
          <Notice>Some minimums are below cost: cashiers could sell those items at a loss.</Notice>
        </div>
      )}
      <div className="mt-3">
        <ErrorText error={save.error} />
      </div>
    </Card>
  );
}
