"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
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
  Notice,
  PageHeader,
  Select,
  Stat,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { type Schemas, api, call, newId } from "@/lib/api";
import { centsToInput, date, dateTime, ksh, toCents } from "@/lib/format";
import { useRefreshAll } from "@/lib/queries";
import { useSession } from "@/lib/use-session";

const BUCKETS = ["current", "1-30", "31-60", "61-90", "90+"] as const;
const BUCKET_TONES = {
  current: "green",
  "1-30": "amber",
  "31-60": "amber",
  "61-90": "red",
  "90+": "red",
} as const;
const ENTRY_LABELS: Record<string, string> = {
  charge: "Credit sale",
  repayment: "Repayment",
  writeoff: "Write-off",
  credit_note: "Return (credit note)",
};

export default function CustomerPage() {
  const { id } = useParams<{ id: string }>();
  const session = useSession();
  const isOwner = session?.role === "owner";
  const [editing, setEditing] = useState(false);
  const [writingOff, setWritingOff] = useState(false);

  const customer = useQuery({
    queryKey: ["customer", id],
    queryFn: () => call(api.GET("/customers/{customer_id}", { params: { path: { customer_id: id } } })),
  });
  const statement = useQuery({
    queryKey: ["customer-statement", id],
    queryFn: () =>
      call(api.GET("/customers/{customer_id}/statement", { params: { path: { customer_id: id } } })),
    enabled: isOwner,
  });

  if (customer.isPending) return <Loading />;
  if (customer.error) return <ErrorText error={customer.error} />;
  const c = customer.data;

  return (
    <>
      <PageHeader
        title={c.name}
        description={
          <>
            {c.phone ?? "No phone"} · {c.terms_days}-day terms
            {!c.active && (
              <>
                {" "}
                · <Badge>Inactive</Badge>
              </>
            )}
          </>
        }
        actions={
          <>
            <Link href="/customers" className="text-sm text-gray-600 hover:underline">
              All customers
            </Link>
            {isOwner && (
              <>
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  Edit
                </Button>
                {c.balance_cents > 0 && (
                  <Button variant="danger" onClick={() => setWritingOff(true)}>
                    Write off
                  </Button>
                )}
              </>
            )}
          </>
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Balance owed" value={ksh(c.balance_cents)} />
        <Stat
          label="Overdue"
          value={<span className={c.overdue_cents > 0 ? "text-red-600" : ""}>{ksh(c.overdue_cents)}</span>}
        />
        <Stat label="Available credit" value={ksh(c.available_credit_cents)} />
        <Stat label="Credit limit" value={ksh(c.credit_limit_cents)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <RepaymentCard customer={c} />
        {isOwner && (
          <div className="space-y-4">
            {statement.isPending ? (
              <Loading />
            ) : statement.error ? (
              <ErrorText error={statement.error} />
            ) : (
              <Statement statement={statement.data} />
            )}
          </div>
        )}
      </div>

      {editing && <EditCustomerModal customer={c} onClose={() => setEditing(false)} />}
      {writingOff && <WriteOffModal customer={c} onClose={() => setWritingOff(false)} />}
    </>
  );
}

function RepaymentCard({ customer }: { customer: Schemas["CustomerOut"] }) {
  const refreshAll = useRefreshAll();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<"cash" | "mpesa">("cash");
  const [code, setCode] = useState("");
  const [note, setNote] = useState("");
  const [repaymentId, setRepaymentId] = useState(newId);
  const [done, setDone] = useState<number | null>(null);
  const cents = toCents(amount || "");

  const repay = useMutation({
    mutationFn: () =>
      call(
        api.POST("/customers/{customer_id}/repayments", {
          params: { path: { customer_id: customer.id } },
          body: {
            id: repaymentId,
            amount_cents: cents ?? 0,
            method,
            mpesa_code: method === "mpesa" ? code : null,
            note: note || null,
          },
        }),
      ),
    onSuccess: () => {
      setDone(cents);
      setAmount("");
      setCode("");
      setNote("");
      setRepaymentId(newId());
      refreshAll();
    },
  });

  return (
    <Card title="Take a repayment">
      {customer.balance_cents <= 0 ? (
        <Empty>Nothing is owed.</Empty>
      ) : (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            setDone(null);
            repay.mutate();
          }}
        >
          <Field label="Amount (KSh)" hint="Applied to the oldest invoices first.">
            <div className="flex gap-2">
              <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" required />
              <Button variant="secondary" onClick={() => setAmount(centsToInput(customer.balance_cents))}>
                Full
              </Button>
            </div>
          </Field>
          <Field label="Paid by">
            <Select value={method} onChange={(e) => setMethod(e.target.value as "cash" | "mpesa")}>
              <option value="cash">Cash</option>
              <option value="mpesa">M-Pesa</option>
            </Select>
          </Field>
          {method === "mpesa" && (
            <Field label="M-Pesa code">
              <Input value={code} onChange={(e) => setCode(e.target.value)} className="uppercase" required />
            </Field>
          )}
          <Field label="Note (optional)">
            <Input value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          {done !== null && <Notice tone="green">Repayment of {ksh(done)} recorded.</Notice>}
          <ErrorText error={repay.error} />
          <Button type="submit" className="w-full" disabled={!cents || cents <= 0 || repay.isPending}>
            Record repayment
          </Button>
        </form>
      )}
    </Card>
  );
}

function Statement({ statement }: { statement: Schemas["StatementOut"] }) {
  const ageing = statement.ageing as Record<string, number>;
  return (
    <>
      <Card title="Ageing">
        <div className="grid grid-cols-5 gap-2 text-center">
          {BUCKETS.map((b) => (
            <div key={b} className="rounded-md bg-gray-50 p-2">
              <p className="text-xs text-gray-500">{b === "current" ? "Not yet due" : `${b} days`}</p>
              <p className="num text-sm font-semibold">{ksh(ageing[b] ?? 0, false)}</p>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Open invoices">
        {statement.open_invoices.length === 0 ? (
          <Empty>No open invoices.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Receipt</Th>
                <Th>Date</Th>
                <Th>Due</Th>
                <Th>Age</Th>
                <Th right>Amount</Th>
                <Th right>Outstanding</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {statement.open_invoices.map((inv) => (
                <tr key={inv.charge_id}>
                  <Td>
                    {inv.sale_id ? (
                      <Link href={`/sales/${inv.sale_id}`} className="text-emerald-700 hover:underline">
                        #{inv.receipt_no ?? "—"}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td>{dateTime(inv.date)}</Td>
                  <Td>{date(inv.due_date)}</Td>
                  <Td>
                    <Badge tone={BUCKET_TONES[inv.bucket as keyof typeof BUCKET_TONES] ?? "gray"}>
                      {inv.days_overdue > 0 ? `${inv.days_overdue} days overdue` : "Not yet due"}
                    </Badge>
                  </Td>
                  <Td right>{ksh(inv.amount)}</Td>
                  <Td right>{ksh(inv.outstanding)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card title="History">
        {statement.entries.length === 0 ? (
          <Empty>No credit activity yet.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>When</Th>
                <Th>What</Th>
                <Th>Detail</Th>
                <Th right>Amount</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {[...statement.entries].reverse().map((e) => (
                <tr key={e.id}>
                  <Td>{dateTime(e.ts)}</Td>
                  <Td>{ENTRY_LABELS[e.type] ?? e.type}</Td>
                  <Td className="text-gray-500">
                    {e.mpesa_code ?? e.note ?? (e.due_date ? `Due ${date(e.due_date)}` : "")}
                  </Td>
                  <Td right className={e.amount < 0 ? "text-emerald-700" : ""}>
                    {ksh(e.amount)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}

function EditCustomerModal({ customer, onClose }: { customer: Schemas["CustomerOut"]; onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const [name, setName] = useState(customer.name);
  const [phone, setPhone] = useState(customer.phone ?? "");
  const [limit, setLimit] = useState(centsToInput(customer.credit_limit_cents));
  const [terms, setTerms] = useState(String(customer.terms_days));
  const [active, setActive] = useState(customer.active);
  const limitCents = toCents(limit || "0");

  const save = useMutation({
    mutationFn: () =>
      call(
        api.PATCH("/customers/{customer_id}", {
          params: { path: { customer_id: customer.id } },
          body: {
            name,
            phone: phone || null,
            credit_limit_cents: limitCents ?? undefined,
            terms_days: Number(terms),
            active,
          },
        }),
      ),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });

  return (
    <Modal open onClose={onClose} title="Edit customer">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>
        <Field label="Phone">
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Credit limit (KSh)">
            <Input value={limit} onChange={(e) => setLimit(e.target.value)} inputMode="decimal" />
          </Field>
          <Field label="Payment terms (days)">
            <Input type="number" min={0} max={365} value={terms} onChange={(e) => setTerms(e.target.value)} />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          Active (can buy on credit)
        </label>
        <p className="text-xs text-gray-500">Limit and terms changes are recorded in the audit log.</p>
        <ErrorText error={save.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={limitCents === null || save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function WriteOffModal({ customer, onClose }: { customer: Schemas["CustomerOut"]; onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const [amount, setAmount] = useState(centsToInput(customer.balance_cents));
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [writeOffId] = useState(newId);
  const cents = toCents(amount || "");

  const writeOff = useMutation({
    mutationFn: () =>
      call(
        api.POST("/customers/{customer_id}/write-offs", {
          params: { path: { customer_id: customer.id } },
          body: { id: writeOffId, amount_cents: cents ?? 0, reason },
        }),
      ),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });

  return (
    <Modal open onClose={onClose} title={`Write off debt: ${customer.name}`}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          writeOff.mutate();
        }}
      >
        <Notice>
          The amount is removed from what {customer.name} owes (oldest invoices first) and recorded as a
          &quot;Bad debt&quot; expense, which lowers profit. This cannot be undone.
        </Notice>
        <Field label="Amount (KSh)" hint={`Owed: ${ksh(customer.balance_cents)}`}>
          <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" required />
        </Field>
        <Field label="Reason">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} required />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
          I understand this is permanent.
        </label>
        <ErrorText error={writeOff.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="danger"
            disabled={!confirmed || !reason || !cents || cents <= 0 || writeOff.isPending}
          >
            Write off {cents ? ksh(cents) : ""}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
