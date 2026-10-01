"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
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
import { centsToInput, date, ksh, toCents, todayKenya } from "@/lib/format";
import { useAccounts, useCategories, useRefreshAll } from "@/lib/queries";

type Category = Schemas["CategoryOut"];

const SOURCES: Record<string, { label: string; tone: "gray" | "green" | "amber" | "red" | "blue" }> = {
  manual: { label: "Manual", tone: "gray" },
  recurring: { label: "Recurring", tone: "blue" },
  stock_loss: { label: "Stock loss", tone: "amber" },
  cash_shortage: { label: "Cash shortage", tone: "amber" },
  bad_debt: { label: "Bad debt", tone: "red" },
  transfer_fee: { label: "Transfer fee", tone: "gray" },
  reversal: { label: "Reversal", tone: "green" },
};
const REVERSIBLE = new Set(["manual", "recurring"]);
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function daysAgo(days: number) {
  const d = new Date(`${todayKenya()}T12:00:00+03:00`);
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export default function ExpensesPage() {
  return (
    <OwnerOnly>
      <Expenses />
    </OwnerOnly>
  );
}

function Expenses() {
  const categories = useCategories();
  const accounts = useAccounts();
  const [since, setSince] = useState(daysAgo(29));
  const [until, setUntil] = useState(todayKenya());
  const [categoryFilter, setCategoryFilter] = useState("");
  const [reversing, setReversing] = useState<Schemas["ExpenseOut"] | null>(null);
  const [addingCategory, setAddingCategory] = useState(false);

  const expenses = useQuery({
    queryKey: ["expenses", { since, until, categoryFilter }],
    queryFn: () =>
      call(
        api.GET("/expenses", {
          params: {
            query: {
              since: since || undefined,
              until: until || undefined,
              category_id: categoryFilter || undefined,
            },
          },
        }),
      ),
  });

  const categoryNames = useMemo(
    () => new Map((categories.data ?? []).map((c) => [c.id, c.name])),
    [categories.data],
  );
  const accountNames = useMemo(
    () => new Map((accounts.data ?? []).map((a) => [a.id, a.name])),
    [accounts.data],
  );
  const reversed = useMemo(
    () => new Set((expenses.data ?? []).map((e) => e.reverses_id).filter(Boolean)),
    [expenses.data],
  );
  const total = (expenses.data ?? []).reduce((sum, e) => sum + e.amount, 0);

  return (
    <>
      <PageHeader
        title="Expenses"
        description="Everything the shop spends. Mistakes are fixed by reversing, never by editing."
        actions={
          <Button variant="secondary" onClick={() => setAddingCategory(true)}>
            Add category
          </Button>
        }
      />
      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <div className="space-y-4">
          <RecordExpense categories={categories.data ?? []} />
        </div>
        <div className="space-y-4">
          <Card
            title="Expenses"
            actions={<span className="num text-sm text-gray-600">Total {ksh(total)}</span>}
          >
            <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
              <Field label="From">
                <Input type="date" value={since} onChange={(e) => setSince(e.target.value)} />
              </Field>
              <Field label="To">
                <Input type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
              </Field>
              <Field label="Category">
                <Select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
                  <option value="">All</option>
                  {categories.data?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            {expenses.isPending ? (
              <Loading />
            ) : expenses.error ? (
              <ErrorText error={expenses.error} />
            ) : expenses.data.length === 0 ? (
              <Empty>No expenses in this range.</Empty>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Date</Th>
                    <Th>Category</Th>
                    <Th>Paid from</Th>
                    <Th>Note</Th>
                    <Th>Source</Th>
                    <Th right>Amount</Th>
                    <Th />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {expenses.data.map((e) => {
                    const source = SOURCES[e.source] ?? { label: e.source, tone: "gray" as const };
                    const canReverse = REVERSIBLE.has(e.source) && !reversed.has(e.id);
                    return (
                      <tr key={e.id}>
                        <Td>{date(e.date)}</Td>
                        <Td>
                          {categoryNames.get(e.category_id) ?? "—"}
                          {e.is_fixed && <span className="ml-1 text-xs text-gray-500">(fixed)</span>}
                        </Td>
                        <Td>{e.account_id ? (accountNames.get(e.account_id) ?? "—") : "No cash moved"}</Td>
                        <Td className="max-w-56 truncate text-gray-600">
                          {e.receipt_url ? (
                            <a href={e.receipt_url} target="_blank" rel="noreferrer" className="text-emerald-700 hover:underline">
                              {e.note || "Receipt"}
                            </a>
                          ) : (
                            (e.note ?? "")
                          )}
                        </Td>
                        <Td>
                          <Badge tone={source.tone}>{source.label}</Badge>
                          {reversed.has(e.id) && (
                            <span className="ml-1">
                              <Badge>Reversed</Badge>
                            </span>
                          )}
                        </Td>
                        <Td right className={e.amount < 0 ? "text-emerald-700" : ""}>
                          {ksh(e.amount)}
                        </Td>
                        <Td right>
                          {canReverse && (
                            <Button variant="ghost" size="sm" onClick={() => setReversing(e)}>
                              Reverse
                            </Button>
                          )}
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            )}
          </Card>
          <RecurringCard categories={categories.data ?? []} />
        </div>
      </div>
      {reversing && <ReverseModal expense={reversing} onClose={() => setReversing(null)} />}
      {addingCategory && <AddCategoryModal onClose={() => setAddingCategory(false)} />}
    </>
  );
}

function RecordExpense({ categories }: { categories: Category[] }) {
  const accounts = useAccounts();
  const refreshAll = useRefreshAll();
  const choosable = categories.filter((c) => !c.system && c.active);
  const [id, setId] = useState(newId);
  const [day, setDay] = useState(todayKenya());
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [accountId, setAccountId] = useState("");
  const [fixed, setFixed] = useState<boolean | null>(null);
  const [note, setNote] = useState("");
  const [receiptUrl, setReceiptUrl] = useState("");
  const [saved, setSaved] = useState(false);

  const category = choosable.find((c) => c.id === categoryId);
  const isFixed = fixed ?? category?.is_fixed ?? false;
  const cents = toCents(amount || "");
  const account = accountId || accounts.data?.find((a) => a.type === "cash")?.id || "";

  const record = useMutation({
    mutationFn: () =>
      call(
        api.POST("/expenses", {
          body: {
            id,
            date: day,
            category_id: categoryId,
            amount_cents: cents ?? 0,
            account_id: account,
            is_fixed: isFixed,
            note: note || null,
            receipt_url: receiptUrl || null,
          },
        }),
      ),
    onSuccess: () => {
      setSaved(true);
      setId(newId());
      setAmount("");
      setNote("");
      setReceiptUrl("");
      setFixed(null);
      refreshAll();
    },
  });

  return (
    <Card title="Record an expense">
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          setSaved(false);
          record.mutate();
        }}
      >
        <Field label="Date">
          <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} required />
        </Field>
        <Field label="Category">
          <Select
            value={categoryId}
            onChange={(e) => {
              setCategoryId(e.target.value);
              setFixed(null);
            }}
            required
          >
            <option value="">Choose…</option>
            {choosable.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Amount (KSh)">
          <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" required />
        </Field>
        <Field label="Paid from">
          <Select value={account} onChange={(e) => setAccountId(e.target.value)} required>
            {accounts.data?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({ksh(a.balance_cents)})
              </option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={isFixed} onChange={(e) => setFixed(e.target.checked)} />
          Fixed cost (counts toward break-even)
        </label>
        <Field label="Note (optional)">
          <Input value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <Field label="Receipt link (optional)" hint="Photo upload comes later; paste a link for now.">
          <Input value={receiptUrl} onChange={(e) => setReceiptUrl(e.target.value)} type="url" />
        </Field>
        {saved && <Notice tone="green">Expense recorded.</Notice>}
        {amount && cents === null && <ErrorText error="Enter a valid amount." />}
        <ErrorText error={record.error} />
        <Button
          type="submit"
          className="w-full"
          disabled={!categoryId || !cents || cents <= 0 || !account || record.isPending}
        >
          Record expense
        </Button>
      </form>
    </Card>
  );
}

function ReverseModal({ expense, onClose }: { expense: Schemas["ExpenseOut"]; onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const [reason, setReason] = useState("");
  const reverse = useMutation({
    mutationFn: () =>
      call(
        api.POST("/expenses/{expense_id}/reverse", {
          params: { path: { expense_id: expense.id } },
          body: { reason },
        }),
      ),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });
  return (
    <Modal open onClose={onClose} title="Reverse expense">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          reverse.mutate();
        }}
      >
        <p className="text-sm text-gray-700">
          This posts a reversal of {ksh(expense.amount)} dated today
          {expense.account_id ? " and puts the money back in the account" : ""}. The original stays on record.
        </p>
        <Field label="Reason">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} required autoFocus />
        </Field>
        <ErrorText error={reverse.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="danger" disabled={!reason || reverse.isPending}>
            Reverse
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function RecurringCard({ categories }: { categories: Category[] }) {
  const refreshAll = useRefreshAll();
  const accounts = useAccounts();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Schemas["RecurringOut"] | null>(null);
  const [posted, setPosted] = useState<number | null>(null);
  const recurring = useQuery({
    queryKey: ["recurring-expenses"],
    queryFn: () => call(api.GET("/recurring-expenses")),
  });
  const run = useMutation({
    mutationFn: () => call(api.POST("/recurring-expenses/run")),
    onSuccess: (items) => {
      setPosted(items.length);
      refreshAll();
    },
  });
  const toggle = useMutation({
    mutationFn: (item: Schemas["RecurringOut"]) =>
      call(
        api.PATCH("/recurring-expenses/{recurring_id}", {
          params: { path: { recurring_id: item.id } },
          body: { active: !item.active },
        }),
      ),
    onSuccess: () => refreshAll(),
  });

  const names = new Map(categories.map((c) => [c.id, c.name]));
  const accountNames = new Map((accounts.data ?? []).map((a) => [a.id, a.name]));
  const schedule = (r: Schemas["RecurringOut"]) =>
    r.frequency === "monthly" ? `Monthly on day ${r.day}` : `Weekly on ${WEEKDAYS[r.day]}`;

  return (
    <Card
      title="Recurring expenses"
      actions={
        <>
          <Button variant="secondary" size="sm" onClick={() => run.mutate()} disabled={run.isPending}>
            Post due now
          </Button>
          <Button size="sm" onClick={() => setCreating(true)}>
            Add
          </Button>
        </>
      }
    >
      {posted !== null && (
        <div className="mb-3">
          <Notice tone="green">
            {posted === 0 ? "Nothing was due." : `Posted ${posted} expense${posted === 1 ? "" : "s"}.`}
          </Notice>
        </div>
      )}
      <ErrorText error={run.error ?? toggle.error} />
      {recurring.isPending ? (
        <Loading />
      ) : recurring.error ? (
        <ErrorText error={recurring.error} />
      ) : recurring.data.length === 0 ? (
        <Empty>Set up rent, salaries and other regular costs once; they post automatically.</Empty>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Category</Th>
              <Th>Schedule</Th>
              <Th>From</Th>
              <Th>Next due</Th>
              <Th right>Amount</Th>
              <Th />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {recurring.data.map((r) => (
              <tr key={r.id} className={r.active ? "" : "text-gray-400"}>
                <Td>
                  {names.get(r.category_id) ?? "—"}
                  {r.note && <span className="ml-1 text-xs text-gray-500">{r.note}</span>}
                </Td>
                <Td>{schedule(r)}</Td>
                <Td>{accountNames.get(r.account_id) ?? "—"}</Td>
                <Td>{r.active ? date(r.next_due) : <Badge>Paused</Badge>}</Td>
                <Td right>{ksh(r.amount)}</Td>
                <Td right>
                  <Button variant="ghost" size="sm" onClick={() => setEditing(r)}>
                    Amount
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => toggle.mutate(r)} disabled={toggle.isPending}>
                    {r.active ? "Pause" : "Resume"}
                  </Button>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {creating && <CreateRecurringModal categories={categories} onClose={() => setCreating(false)} />}
      {editing && <EditRecurringModal item={editing} onClose={() => setEditing(null)} />}
    </Card>
  );
}

function CreateRecurringModal({ categories, onClose }: { categories: Category[]; onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const accounts = useAccounts();
  const choosable = categories.filter((c) => !c.system && c.active);
  const [id] = useState(newId);
  const [categoryId, setCategoryId] = useState("");
  const [amount, setAmount] = useState("");
  const [accountId, setAccountId] = useState("");
  const [frequency, setFrequency] = useState<"monthly" | "weekly">("monthly");
  const [day, setDay] = useState("1");
  const [startDate, setStartDate] = useState(todayKenya());
  const [note, setNote] = useState("");
  const cents = toCents(amount || "");
  const account = accountId || accounts.data?.find((a) => a.type === "bank")?.id || "";

  const create = useMutation({
    mutationFn: () =>
      call(
        api.POST("/recurring-expenses", {
          body: {
            id,
            category_id: categoryId,
            amount_cents: cents ?? 0,
            account_id: account,
            frequency,
            day: Number(day),
            start_date: startDate || null,
            note: note || null,
          },
        }),
      ),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });

  return (
    <Modal open onClose={onClose} title="Add recurring expense">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <div className="grid grid-cols-2 gap-3">
          <Field label="Category">
            <Select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} required>
              <option value="">Choose…</option>
              {choosable.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Amount (KSh)">
            <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" required />
          </Field>
          <Field label="Frequency">
            <Select
              value={frequency}
              onChange={(e) => {
                setFrequency(e.target.value as "monthly" | "weekly");
                setDay(e.target.value === "monthly" ? "1" : "0");
              }}
            >
              <option value="monthly">Monthly</option>
              <option value="weekly">Weekly</option>
            </Select>
          </Field>
          <Field label={frequency === "monthly" ? "Day of month" : "Day of week"} hint={frequency === "monthly" ? "31 posts on the last day of short months." : undefined}>
            {frequency === "monthly" ? (
              <Input type="number" min={1} max={31} value={day} onChange={(e) => setDay(e.target.value)} />
            ) : (
              <Select value={day} onChange={(e) => setDay(e.target.value)}>
                {WEEKDAYS.map((w, i) => (
                  <option key={w} value={i}>
                    {w}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Paid from">
            <Select value={account} onChange={(e) => setAccountId(e.target.value)}>
              {accounts.data?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Starting">
            <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </Field>
        </div>
        <Field label="Note (optional)">
          <Input value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <ErrorText error={create.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!categoryId || !cents || cents <= 0 || !account || create.isPending}>
            Add
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function EditRecurringModal({ item, onClose }: { item: Schemas["RecurringOut"]; onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const [amount, setAmount] = useState(centsToInput(item.amount));
  const cents = toCents(amount || "");
  const save = useMutation({
    mutationFn: () =>
      call(
        api.PATCH("/recurring-expenses/{recurring_id}", {
          params: { path: { recurring_id: item.id } },
          body: { amount_cents: cents ?? undefined },
        }),
      ),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });
  return (
    <Modal open onClose={onClose} title="Change recurring amount">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label="Amount (KSh)" hint="Applies from the next posting. To change the schedule, add a new one and pause this.">
          <Input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" autoFocus />
        </Field>
        <ErrorText error={save.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!cents || cents <= 0 || save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function AddCategoryModal({ onClose }: { onClose: () => void }) {
  const refreshAll = useRefreshAll();
  const [id] = useState(newId);
  const [name, setName] = useState("");
  const [fixed, setFixed] = useState(false);
  const create = useMutation({
    mutationFn: () => call(api.POST("/expense-categories", { body: { id, name, is_fixed: fixed } })),
    onSuccess: () => {
      refreshAll();
      onClose();
    },
  });
  return (
    <Modal open onClose={onClose} title="Add expense category">
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
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={fixed} onChange={(e) => setFixed(e.target.checked)} />
          Fixed cost by default
        </label>
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
