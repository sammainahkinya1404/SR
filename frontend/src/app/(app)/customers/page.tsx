"use client";

import { useMutation } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
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
  PageHeader,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { api, call, newId } from "@/lib/api";
import { ksh, toCents } from "@/lib/format";
import { useCustomers, useRefreshAll } from "@/lib/queries";
import { useSession } from "@/lib/use-session";

export default function CustomersPage() {
  const session = useSession();
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);
  const customers = useCustomers(search.trim());

  return (
    <>
      <PageHeader
        title="Customers"
        description="Credit customers, their balances and what is overdue."
        actions={session?.role === "owner" && <Button onClick={() => setAdding(true)}>Add customer</Button>}
      />
      <Card>
        <Input
          placeholder="Search by name or phone"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="mb-3"
        />
        {customers.isPending ? (
          <Loading />
        ) : customers.error ? (
          <ErrorText error={customers.error} />
        ) : customers.data.length === 0 ? (
          <Empty>{search ? "No customers match." : "No customers yet."}</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Phone</Th>
                <Th right>Balance</Th>
                <Th right>Overdue</Th>
                <Th right>Available</Th>
                <Th right>Limit</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {customers.data.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50">
                  <Td>
                    <Link href={`/customers/${c.id}`} className="font-medium text-emerald-700 hover:underline">
                      {c.name}
                    </Link>
                    {!c.active && (
                      <span className="ml-2">
                        <Badge>Inactive</Badge>
                      </span>
                    )}
                  </Td>
                  <Td>{c.phone ?? "—"}</Td>
                  <Td right>{ksh(c.balance_cents)}</Td>
                  <Td right className={c.overdue_cents > 0 ? "font-medium text-red-600" : ""}>
                    {c.overdue_cents > 0 ? ksh(c.overdue_cents) : "—"}
                  </Td>
                  <Td right>{ksh(c.available_credit_cents)}</Td>
                  <Td right>{ksh(c.credit_limit_cents)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {adding && <AddCustomerModal onClose={() => setAdding(false)} />}
    </>
  );
}

function AddCustomerModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const refreshAll = useRefreshAll();
  const [id] = useState(newId);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [idNumber, setIdNumber] = useState("");
  const [limit, setLimit] = useState("0");
  const [terms, setTerms] = useState("30");
  const limitCents = toCents(limit || "0");

  const create = useMutation({
    mutationFn: () =>
      call(
        api.POST("/customers", {
          body: {
            id,
            name,
            phone: phone || null,
            id_number: idNumber || null,
            credit_limit_cents: limitCents ?? 0,
            terms_days: Number(terms),
          },
        }),
      ),
    onSuccess: (customer) => {
      refreshAll();
      router.push(`/customers/${customer.id}`);
    },
  });

  return (
    <Modal open onClose={onClose} title="Add customer">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Phone" hint="Needed for SMS reminders.">
            <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" />
          </Field>
          <Field label="ID number (optional)">
            <Input value={idNumber} onChange={(e) => setIdNumber(e.target.value)} />
          </Field>
          <Field label="Credit limit (KSh)" hint="0 = no credit without an override.">
            <Input value={limit} onChange={(e) => setLimit(e.target.value)} inputMode="decimal" />
          </Field>
          <Field label="Payment terms (days)">
            <Input type="number" min={0} max={365} value={terms} onChange={(e) => setTerms(e.target.value)} />
          </Field>
        </div>
        {limitCents === null && <ErrorText error="Enter a valid credit limit." />}
        <ErrorText error={create.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!name || limitCents === null || create.isPending}>
            Add customer
          </Button>
        </div>
      </form>
    </Modal>
  );
}
