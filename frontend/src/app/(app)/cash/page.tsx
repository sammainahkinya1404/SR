"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
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
  Stat,
  Table,
  Td,
  Th,
  cx,
} from "@/components/ui";
import { type Schemas, api, call, newId } from "@/lib/api";
import { date, dateTime, ksh, toCents, todayKenya } from "@/lib/format";
import { useAccounts, useRefreshAll } from "@/lib/queries";

type Account = Schemas["AccountOut"];

const ENTRY_LABELS: Record<string, string> = {
  sale: "Sale",
  refund: "Refund",
  repayment: "Credit repayment",
  expense: "Expense",
  transfer_out: "Transfer out",
  transfer_in: "Transfer in",
  capital: "Capital",
  drawing: "Drawing",
  cash_up_overage: "Cash-up overage",
};

export default function CashPage() {
  return (
    <OwnerOnly>
      <Cash />
    </OwnerOnly>
  );
}

function Cash() {
  const accounts = useAccounts();
  const [ledgerFor, setLedgerFor] = useState<Account | null>(null);
  const [adding, setAdding] = useState(false);
  const total = (accounts.data ?? []).reduce((sum, a) => sum + a.balance_cents, 0);

  return (
    <>
      <PageHeader
        title="Cash & accounts"
        description="Every sale, repayment, expense, transfer and drawing moves money in one of these accounts."
        actions={
          <Button variant="secondary" onClick={() => setAdding(true)}>
            Add account
          </Button>
        }
      />

      {accounts.isPending ? (
        <Loading />
      ) : accounts.error ? (
        <ErrorText error={accounts.error} />
      ) : (
        <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {accounts.data.map((a) => (
            <button key={a.id} onClick={() => setLedgerFor(a)} className="text-left">
              <Stat
                label={a.name}
                value={<span className={a.balance_cents < 0 ? "text-red-600" : ""}>{ksh(a.balance_cents)}</span>}
                sub={<span className="text-emerald-700">View transactions →</span>}
              />
            </button>
          ))}
          <Stat label="All accounts" value={ksh(total)} />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <CashUpCard accounts={accounts.data ?? []} />
        <TransferCard accounts={accounts.data ?? []} />
        <OwnerMoneyCard accounts={accounts.data ?? []} />
        <CashUpHistory accounts={accounts.data ?? []} />
      </div>

      {ledgerFor && <LedgerModal account={ledgerFor} onClose={() => setLedgerFor(null)} />}
      {adding && <AddAccountModal onClose={() => setAdding(false)} />}
    </>
  );
}

function CashUpCard({ accounts }: { accounts: Account[] }) {
  const refreshAll = useRefreshAll();
  const [accountId, setAccountId] = useState("");
  const [counted, setCounted] = useState("");
  const [explanation, setExplanation] = useState("");
  const [id, setId] = useState(newId);
  const [result, setResult] = useState<Schemas["CashUpOut"] | null>(null);

  const account = accounts.find((a) => a.id === accountId) ?? accounts.find((a) => a.type === "cash");
  const countedCents = toCents(counted || "");
  const variance = account && countedCents !== null ? countedCents - account.balance_cents : null;
  const needsExplanation = variance !== null && variance !== 0;

  const submit = useMutation({
    mutationFn: () =>
      call(
        api.POST("/cash-ups", {
          body: {
            id,
            account_id: account!.id,
            date: todayKenya(),
            counted_cents: countedCents ?? 0,
            explanation: explanation || null,
          },
        }),
      ),
    onSuccess: (r) => {
      setResult(r);
      setCounted("");
      setExplanation("");
      setId(newId());
      refreshAll();
    },
  });

  return (
    <Card title="Daily cash-up">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          setResult(null);
          submit.mutate();
        }}
      >
        <Field label="Account">
          <Select value={account?.id ?? ""} onChange={(e) => setAccountId(e.target.value)}>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Expected (from records)">
            <Input value={account ? ksh(account.balance_cents) : ""} disabled />
          </Field>
          <Field label="Counted (KSh)">
            <Input value={counted} onChange={(e) => setCounted(e.target.value)} inputMode="decimal" required />
          </Field>
        </div>
        {variance !== null && (
          <p
            className={cx(
              "num rounded-md px-3 py-2 text-sm font-medium",
              variance === 0 ? "bg-emerald-50 text-emerald-800" : variance < 0 ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-900",
            )}
          >
            {variance === 0
              ? "Balanced."
              : variance < 0
                ? `Short by ${ksh(-variance)}: recorded as a cash-shortage expense.`
                : `Over by ${ksh(variance)}: added to the account.`}
          </p>
        )}
        {needsExplanation && (
          <Field label="Explanation (required)">
            <Input value={explanation} onChange={(e) => setExplanation(e.target.value)} required />
          </Field>
        )}
        {result && (
          <Notice tone="green">
            Cash-up saved for {result.date}: variance {ksh(result.variance)}.
          </Notice>
        )}
        <ErrorText error={submit.error} />
        <Button
          type="submit"
          className="w-full"
          disabled={!account || countedCents === null || (needsExplanation && !explanation) || submit.isPending}
        >
          Save cash-up
        </Button>
        <p className="text-xs text-gray-500">One cash-up per account per day.</p>
      </form>
    </Card>
  );
}

function TransferCard({ accounts }: { accounts: Account[] }) {
  const refreshAll = useRefreshAll();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [amount, setAmount] = useState("");
  const [fee, setFee] = useState("");
  const [note, setNote] = useState("");
  const [id, setId] = useState(newId);
  const [done, setDone] = useState(false);

  const fromId = from || accounts.find((a) => a.type === "cash")?.id || "";
  const toId = to || accounts.find((a) => a.type === "bank")?.id || "";
  const amountCents = toCents(amount || "");
  const feeCents = toCents(fee || "0");

  const transfer = useMutation({
    mutationFn: () =>
      call(
        api.POST("/transfers", {
          body: {
            id,
            from_account_id: fromId,
            to_account_id: toId,
            amount_cents: amountCents ?? 0,
            fee_cents: feeCents ?? 0,
            note: note || null,
          },
        }),
      ),
    onSuccess: () => {
      setDone(true);
      setAmount("");
      setFee("");
      setNote("");
      setId(newId());
      refreshAll();
    },
  });

  return (
    <Card title="Move money between accounts">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          setDone(false);
          transfer.mutate();
        }}
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label="From">
            <Select value={fromId} onChange={(e) => setFrom(e.target.value)}>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="To">
            <Select value={toId} onChange={(e) => setTo(e.target.value)}>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Amount (KSh)">
            <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" required />
          </Field>
          <Field label="Fee (KSh)" hint="e.g. M-Pesa charges; posted as an expense.">
            <Input value={fee} onChange={(e) => setFee(e.target.value)} inputMode="decimal" />
          </Field>
        </div>
        <Field label="Note (optional)">
          <Input value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {fromId === toId && fromId && <ErrorText error="Choose two different accounts." />}
        {done && <Notice tone="green">Transfer recorded.</Notice>}
        <ErrorText error={transfer.error} />
        <Button
          type="submit"
          className="w-full"
          disabled={!amountCents || amountCents <= 0 || feeCents === null || fromId === toId || transfer.isPending}
        >
          Transfer
        </Button>
      </form>
    </Card>
  );
}

function OwnerMoneyCard({ accounts }: { accounts: Account[] }) {
  const refreshAll = useRefreshAll();
  const [kind, setKind] = useState<"drawing" | "capital">("drawing");
  const [accountId, setAccountId] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [id, setId] = useState(newId);
  const [warning, setWarning] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const profit = useQuery({ queryKey: ["profit-to-date"], queryFn: () => call(api.GET("/profit-to-date")) });
  const entries = useQuery({ queryKey: ["owner-entries"], queryFn: () => call(api.GET("/owner-entries")) });
  const hasCapital = entries.data?.some((e) => e.type === "opening_capital");

  const account = accountId || accounts.find((a) => a.type === "cash")?.id || "";
  const cents = toCents(amount || "");

  const record = useMutation({
    mutationFn: async () => {
      const body = { id, account_id: account, amount_cents: cents ?? 0, note: note || null };
      if (kind === "capital") {
        await call(api.POST("/capital", { body }));
        return null;
      }
      return call(api.POST("/drawings", { body }));
    },
    onSuccess: (result) => {
      setWarning(result?.warning ?? null);
      setSaved(true);
      setAmount("");
      setNote("");
      setId(newId());
      refreshAll();
    },
  });

  return (
    <Card title="Owner capital & drawings">
      {profit.data && (
        <div className="mb-4 grid grid-cols-2 gap-2 text-sm">
          <div className="rounded-md bg-gray-50 p-2">
            <p className="text-xs text-gray-500">Net profit to date</p>
            <p className="num font-semibold">{ksh(profit.data.net_profit)}</p>
          </div>
          <div className="rounded-md bg-gray-50 p-2">
            <p className="text-xs text-gray-500">Drawings to date</p>
            <p className={cx("num font-semibold", profit.data.drawings > profit.data.net_profit && "text-red-600")}>
              {ksh(profit.data.drawings)}
            </p>
          </div>
        </div>
      )}
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          setSaved(false);
          setWarning(null);
          record.mutate();
        }}
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label="Type">
            <Select value={kind} onChange={(e) => setKind(e.target.value as "drawing" | "capital")}>
              <option value="drawing">Drawing (owner takes money)</option>
              <option value="capital" disabled={hasCapital}>
                Opening capital{hasCapital ? " (recorded)" : ""}
              </option>
            </Select>
          </Field>
          <Field label={kind === "capital" ? "Into account" : "From account"}>
            <Select value={account} onChange={(e) => setAccountId(e.target.value)}>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Amount (KSh)" hint="Never counted as an expense or income.">
          <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" required />
        </Field>
        <Field label="Note (optional)">
          <Input value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        {warning && (
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
            ⚠ {warning}
          </p>
        )}
        {saved && !warning && <Notice tone="green">Recorded.</Notice>}
        <ErrorText error={record.error} />
        <Button type="submit" className="w-full" disabled={!cents || cents <= 0 || !account || record.isPending}>
          Record {kind === "capital" ? "opening capital" : "drawing"}
        </Button>
      </form>

      <div className="mt-4 border-t border-gray-100 pt-3">
        <p className="mb-2 text-xs font-semibold tracking-wide text-gray-500 uppercase">History</p>
        {entries.isPending ? (
          <Loading />
        ) : !entries.data?.length ? (
          <Empty>No capital or drawings yet.</Empty>
        ) : (
          <ul className="divide-y divide-gray-100 text-sm">
            {entries.data.map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-2 py-1.5">
                <span>
                  {date(e.date)}{" "}
                  <Badge tone={e.type === "opening_capital" ? "green" : "amber"}>
                    {e.type === "opening_capital" ? "Capital" : e.account_id ? "Drawing" : "Stock taken"}
                  </Badge>
                  {e.note && <span className="ml-1 text-xs text-gray-500">{e.note}</span>}
                </span>
                <span className="num">{ksh(e.amount)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function CashUpHistory({ accounts }: { accounts: Account[] }) {
  const history = useQuery({ queryKey: ["cash-ups"], queryFn: () => call(api.GET("/cash-ups")) });
  const names = new Map(accounts.map((a) => [a.id, a.name]));
  return (
    <Card title="Cash-up history">
      {history.isPending ? (
        <Loading />
      ) : history.error ? (
        <ErrorText error={history.error} />
      ) : history.data.length === 0 ? (
        <Empty>No cash-ups yet.</Empty>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Date</Th>
              <Th>Account</Th>
              <Th right>Expected</Th>
              <Th right>Counted</Th>
              <Th right>Variance</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {history.data.map((c) => (
              <tr key={c.id} title={c.explanation ?? undefined}>
                <Td>{date(c.date)}</Td>
                <Td>{names.get(c.account_id) ?? "—"}</Td>
                <Td right>{ksh(c.expected)}</Td>
                <Td right>{ksh(c.counted)}</Td>
                <Td right className={c.variance < 0 ? "text-red-600" : c.variance > 0 ? "text-amber-700" : ""}>
                  {c.variance === 0 ? "—" : ksh(c.variance)}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}

function LedgerModal({ account, onClose }: { account: Account; onClose: () => void }) {
  const ledger = useQuery({
    queryKey: ["ledger", account.id],
    queryFn: () =>
      call(
        api.GET("/accounts/{account_id}/ledger", {
          params: { path: { account_id: account.id }, query: { limit: 200 } },
        }),
      ),
  });
  return (
    <Modal open onClose={onClose} title={`${account.name}: ${ksh(account.balance_cents)}`}>
      {ledger.isPending ? (
        <Loading />
      ) : ledger.error ? (
        <ErrorText error={ledger.error} />
      ) : ledger.data.length === 0 ? (
        <Empty>No transactions yet.</Empty>
      ) : (
        <ul className="max-h-[60vh] divide-y divide-gray-100 overflow-y-auto text-sm">
          {ledger.data.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-3 py-2">
              <div className="min-w-0">
                <p className="font-medium">{ENTRY_LABELS[e.type] ?? e.type}</p>
                <p className="truncate text-xs text-gray-500">
                  {dateTime(e.ts)}
                  {e.note ? ` · ${e.note}` : ""}
                </p>
              </div>
              <span className={cx("num", e.amount < 0 ? "text-red-600" : "text-emerald-700")}>
                {e.amount > 0 ? "+" : ""}
                {ksh(e.amount)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}

function AddAccountModal({ onClose }: { onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const [id] = useState(newId);
  const [type, setType] = useState<"cash" | "mpesa" | "bank">("bank");
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => call(api.POST("/accounts", { body: { id, type, name } })),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });
  return (
    <Modal open onClose={onClose} title="Add account">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Field label="Type">
          <Select value={type} onChange={(e) => setType(e.target.value as typeof type)}>
            <option value="cash">Cash</option>
            <option value="mpesa">M-Pesa</option>
            <option value="bank">Bank</option>
          </Select>
        </Field>
        <Field label="Name" hint="Sales still settle into the oldest account of each type.">
          <Input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        </Field>
        <ErrorText error={create.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!name || create.isPending}>
            Add
          </Button>
        </div>
      </form>
    </Modal>
  );
}
