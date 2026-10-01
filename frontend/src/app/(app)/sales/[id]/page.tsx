"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { ReceiptModal, ReceiptText } from "@/components/receipt";
import { SaleStatusBadge } from "@/components/sales/status-badge";
import {
  Button,
  Card,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  Modal,
  PageHeader,
  Select,
  Stat,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { type Schemas, api, call, newId } from "@/lib/api";
import { dateTime, ksh, qty } from "@/lib/format";
import { useCustomers, useProducts, useRefreshAll } from "@/lib/queries";
import { useSession } from "@/lib/use-session";

const METHOD_LABELS: Record<string, string> = { cash: "Cash", mpesa: "M-Pesa", credit: "Credit" };

export default function SaleDetailPage() {
  const { id } = useParams<{ id: string }>();
  const session = useSession();
  const isOwner = session?.role === "owner";
  const products = useProducts(true);
  const customers = useCustomers();
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [returnOpen, setReturnOpen] = useState(false);

  const sale = useQuery({
    queryKey: ["sale", id],
    queryFn: () => call(api.GET("/sales/{sale_id}", { params: { path: { sale_id: id } } })),
  });
  const returns = useQuery({
    queryKey: ["sale-returns", id],
    queryFn: () => call(api.GET("/sales/{sale_id}/returns", { params: { path: { sale_id: id } } })),
  });

  const names = useMemo(
    () => new Map((products.data ?? []).map((p) => [p.id, p.name])),
    [products.data],
  );

  if (sale.isPending) return <Loading />;
  if (sale.error) return <ErrorText error={sale.error} />;
  const s = sale.data;
  const customer = customers.data?.find((c) => c.id === s.customer_id);
  const returnable = s.lines.some((l) => Number(l.qty) > Number(l.returned_qty));

  return (
    <>
      <PageHeader
        title={`Sale #${s.receipt_no}`}
        description={
          <>
            {dateTime(s.ts)} · <SaleStatusBadge status={s.status} />
            {customer && (
              <>
                {" "}
                · Customer{" "}
                <Link href={`/customers/${customer.id}`} className="text-emerald-700 hover:underline">
                  {customer.name}
                </Link>
              </>
            )}
          </>
        }
        actions={
          <>
            <Link href="/sales" className="text-sm text-gray-600 hover:underline">
              All sales
            </Link>
            <Button variant="secondary" onClick={() => setReceiptOpen(true)}>
              Receipt
            </Button>
            {isOwner && returnable && <Button onClick={() => setReturnOpen(true)}>Return items</Button>}
          </>
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Total" value={ksh(s.total)} sub={s.discount_total ? `Discount ${ksh(s.discount_total)}` : undefined} />
        <Stat label="Change given" value={ksh(s.change_given)} />
        {isOwner && <Stat label="Cost of goods" value={ksh(s.cogs)} />}
        {isOwner && <Stat label="Gross profit" value={ksh(s.gross_profit)} />}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-4">
          <Card title="Items">
            <Table>
              <thead>
                <tr>
                  <Th>Product</Th>
                  <Th right>Qty</Th>
                  <Th right>Returned</Th>
                  <Th right>Price</Th>
                  <Th right>Discount</Th>
                  <Th right>Total</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {s.lines.map((line) => (
                  <tr key={line.id}>
                    <Td>{names.get(line.product_id) ?? "Product"}</Td>
                    <Td right>{qty(line.qty)}</Td>
                    <Td right>{Number(line.returned_qty) ? qty(line.returned_qty) : "—"}</Td>
                    <Td right>{ksh(line.unit_price)}</Td>
                    <Td right>{line.discount ? ksh(line.discount) : "—"}</Td>
                    <Td right>{ksh(line.line_total)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>

          <Card title="Payments">
            {s.payments.length === 0 ? (
              <Empty>No payment (zero total).</Empty>
            ) : (
              <ul className="divide-y divide-gray-100 text-sm">
                {s.payments.map((p, i) => (
                  <li key={i} className="flex justify-between py-2">
                    <span>
                      {METHOD_LABELS[p.method] ?? p.method}
                      {p.mpesa_code && <span className="ml-2 font-mono text-xs text-gray-500">{p.mpesa_code}</span>}
                    </span>
                    <span className="num">{ksh(p.amount)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Returns">
            {returns.isPending ? (
              <Loading />
            ) : returns.error ? (
              <ErrorText error={returns.error} />
            ) : returns.data.length === 0 ? (
              <Empty>No returns.</Empty>
            ) : (
              <ul className="divide-y divide-gray-100 text-sm">
                {returns.data.map((r) => (
                  <li key={r.id} className="py-2">
                    <div className="flex justify-between">
                      <span className="font-medium">
                        {dateTime(r.ts)} · refunded via {METHOD_LABELS[r.refund_method] ?? r.refund_method}
                        {r.refund_reference && <span className="ml-1 font-mono text-xs">({r.refund_reference})</span>}
                      </span>
                      <span className="num">{ksh(r.refund_total)}</span>
                    </div>
                    <p className="text-xs text-gray-500">
                      {r.lines
                        .map((l) => {
                          const line = s.lines.find((x) => x.id === l.sale_line_id);
                          return `${qty(l.qty)} × ${line ? (names.get(line.product_id) ?? "item") : "item"}`;
                        })
                        .join(", ")}{" "}
                      — {r.reason}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <Card title="Receipt">
          <ReceiptText saleId={s.id} />
        </Card>
      </div>

      {receiptOpen && <ReceiptModal saleId={s.id} onClose={() => setReceiptOpen(false)} />}
      {returnOpen && (
        <ReturnModal
          sale={s}
          names={names}
          onClose={() => setReturnOpen(false)}
        />
      )}
    </>
  );
}

function ReturnModal({
  sale,
  names,
  onClose,
}: {
  sale: Schemas["SaleOut"];
  names: Map<string, string>;
  onClose: () => void;
}) {
  const refreshAll = useRefreshAll();
  const [qtys, setQtys] = useState<Record<string, string>>({});
  const [method, setMethod] = useState<"cash" | "mpesa" | "credit">(sale.customer_id ? "credit" : "cash");
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");
  const [returnId] = useState(newId);

  const lines = sale.lines
    .map((l) => ({ line: l, remaining: Number(l.qty) - Number(l.returned_qty) }))
    .filter((x) => x.remaining > 0);
  const chosen = lines
    .map(({ line }) => ({ sale_line_id: line.id, qty: qtys[line.id] ?? "" }))
    .filter((l) => Number(l.qty) > 0);
  const tooMany = lines.some(({ line, remaining }) => Number(qtys[line.id] || 0) > remaining);

  const submit = useMutation({
    mutationFn: () =>
      call(
        api.POST("/sales/{sale_id}/returns", {
          params: { path: { sale_id: sale.id } },
          body: {
            id: returnId,
            lines: chosen,
            refund_method: method,
            refund_reference: reference || null,
            reason,
          },
        }),
      ),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });

  return (
    <Modal open onClose={onClose} title={`Return items from #${sale.receipt_no}`}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          submit.mutate();
        }}
      >
        <ul className="divide-y divide-gray-100">
          {lines.map(({ line, remaining }) => (
            <li key={line.id} className="flex items-center justify-between gap-3 py-2">
              <div className="min-w-0 text-sm">
                <p className="truncate font-medium">{names.get(line.product_id) ?? "Product"}</p>
                <p className="text-xs text-gray-500">Up to {remaining} can be returned</p>
              </div>
              <Input
                aria-label="Quantity to return"
                className="w-24"
                inputMode="decimal"
                placeholder="0"
                value={qtys[line.id] ?? ""}
                onChange={(e) => setQtys((q) => ({ ...q, [line.id]: e.target.value }))}
              />
            </li>
          ))}
        </ul>
        <Field label="Refund as">
          <Select value={method} onChange={(e) => setMethod(e.target.value as typeof method)}>
            <option value="cash">Cash</option>
            <option value="mpesa">M-Pesa</option>
            {sale.customer_id && <option value="credit">Reduce the customer&apos;s credit balance</option>}
          </Select>
        </Field>
        {method === "mpesa" && (
          <Field label="M-Pesa reversal code (optional)">
            <Input value={reference} onChange={(e) => setReference(e.target.value)} />
          </Field>
        )}
        <Field label="Reason">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} required />
        </Field>
        {tooMany && <ErrorText error="A quantity is more than can be returned." />}
        <ErrorText error={submit.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={chosen.length === 0 || tooMany || !reason || submit.isPending}>
            {submit.isPending ? "Posting…" : "Post return"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
