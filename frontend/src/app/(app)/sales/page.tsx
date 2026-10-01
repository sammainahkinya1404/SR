"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { SaleStatusBadge } from "@/components/sales/status-badge";
import {
  Card,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  PageHeader,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { api, call } from "@/lib/api";
import { dateTime, ksh } from "@/lib/format";
import { useCustomers } from "@/lib/queries";

const METHOD_LABELS: Record<string, string> = { cash: "Cash", mpesa: "M-Pesa", credit: "Credit" };

/** The API filters by UTC timestamp; a Kenyan date starts at 00:00 EAT. */
function startOfKenyanDay(date: string) {
  return date ? new Date(`${date}T00:00:00+03:00`).toISOString() : undefined;
}

export default function SalesPage() {
  const [since, setSince] = useState("");
  const customers = useCustomers();
  const sales = useQuery({
    queryKey: ["sales", { since }],
    queryFn: () =>
      call(
        api.GET("/sales", {
          params: { query: { since: startOfKenyanDay(since), limit: 200 } },
        }),
      ),
  });

  const customerNames = useMemo(
    () => new Map((customers.data ?? []).map((c) => [c.id, c.name])),
    [customers.data],
  );

  return (
    <>
      <PageHeader title="Sales" description="Most recent first. Open a sale for its receipt and returns." />
      <Card
        title="Recent sales"
        actions={
          <Field label="Since" className="flex items-center gap-2 [&>span]:mb-0">
            <Input type="date" value={since} onChange={(e) => setSince(e.target.value)} />
          </Field>
        }
      >
        {sales.isPending ? (
          <Loading />
        ) : sales.error ? (
          <ErrorText error={sales.error} />
        ) : sales.data.length === 0 ? (
          <Empty>No sales yet.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Receipt</Th>
                <Th>Time</Th>
                <Th>Customer</Th>
                <Th>Paid by</Th>
                <Th>Status</Th>
                <Th right>Total</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {sales.data.map((sale) => (
                <tr key={sale.id} className="hover:bg-gray-50">
                  <Td>
                    <Link href={`/sales/${sale.id}`} className="font-medium text-emerald-700 hover:underline">
                      #{sale.receipt_no}
                    </Link>
                  </Td>
                  <Td>{dateTime(sale.ts)}</Td>
                  <Td>{sale.customer_id ? (customerNames.get(sale.customer_id) ?? "Customer") : "—"}</Td>
                  <Td>
                    {[...new Set(sale.payments.map((p) => METHOD_LABELS[p.method] ?? p.method))].join(
                      " + ",
                    ) || "—"}
                  </Td>
                  <Td>
                    <SaleStatusBadge status={sale.status} />
                  </Td>
                  <Td right>{ksh(sale.total)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
