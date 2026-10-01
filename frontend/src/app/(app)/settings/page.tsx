"use client";

import {
  type UseMutationResult,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { OwnerOnly, homeFor } from "@/components/app-shell";
import {
  Badge,
  Button,
  Card,
  ErrorText,
  Field,
  Input,
  Loading,
  Notice,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { type Schemas, api, call } from "@/lib/api";
import { centsToInput, toCents } from "@/lib/format";
import { signIn } from "@/lib/sign-in";
import { useSession } from "@/lib/use-session";

type Settings = Schemas["SettingsOut"];

// Fractions are stored 0-1 with 4 decimal places; people enter percentages ("10" = 0.1000).
const PERCENT_FIELDS = [
  ["price_floor_pct", "Minimum price floor", "Selling below WAC + this % needs the owner."],
  ["reprice_threshold_pct", "Reprice threshold", "Suggest a new price when cost moves more than this."],
  ["default_target_margin", "Default target margin", "Used for thin-margin alerts on manually priced products."],
  ["alert_credit_risk_pct", "Credit risk alert", "Alert when overdue credit exceeds this % of the last 30 days' sales."],
] as const;

const DAY_FIELDS = [
  ["trading_days_per_month", "Trading days per month", "Used for daily break-even."],
  ["alert_low_cash_days", "Low cash alert (days)", "Alert when cash covers fewer days of fixed costs. 0 turns it off."],
  ["alert_slow_moving_days", "Slow-moving after (days)", "Alert when a product has not sold for this long."],
  ["alert_max_days_of_stock", "Max days of stock", "Alert when stock would last longer than this at the current rate."],
] as const;

type PercentKey = (typeof PERCENT_FIELDS)[number][0];
type DayKey = (typeof DAY_FIELDS)[number][0];

function fractionToPercent(fraction: string): string {
  return String(Number((Number(fraction) * 100).toFixed(2)));
}

/** "12.5" -> "0.1250"; null if not a percentage with at most 2 decimal places. */
function percentToFraction(input: string): string | null {
  const clean = input.trim().replace(/%$/, "");
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
  return (Math.round(Number(clean) * 100) / 10000).toFixed(4);
}

export default function SettingsPage() {
  return (
    <OwnerOnly>
      <PageHeader title="Settings" description="Business rules, alert thresholds and users." />
      <div className="space-y-6">
        <BusinessSettings />
        <Users />
      </div>
    </OwnerOnly>
  );
}

type FormState = {
  name: string;
  rounding: string;
  allocation: Settings["default_allocation_method"];
} & Record<PercentKey | DayKey, string>;

function toForm(s: Settings): FormState {
  return {
    name: s.name,
    rounding: centsToInput(s.price_rounding_cents),
    allocation: s.default_allocation_method,
    price_floor_pct: fractionToPercent(s.price_floor_pct),
    reprice_threshold_pct: fractionToPercent(s.reprice_threshold_pct),
    default_target_margin: fractionToPercent(s.default_target_margin),
    alert_credit_risk_pct: fractionToPercent(s.alert_credit_risk_pct),
    trading_days_per_month: String(s.trading_days_per_month),
    alert_low_cash_days: String(s.alert_low_cash_days),
    alert_slow_moving_days: String(s.alert_slow_moving_days),
    alert_max_days_of_stock: String(s.alert_max_days_of_stock),
  };
}

function BusinessSettings() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const save = useMutation({
    mutationFn: (body: Schemas["SettingsUpdate"]) => call(api.PATCH("/settings", { body })),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  if (settings.isPending) return <Loading />;
  if (settings.error) return <ErrorText error={settings.error} />;
  // Keyed by the saved values: after a save the form starts again from what the server stored.
  return (
    <SettingsForm
      key={JSON.stringify(settings.data)}
      current={settings.data}
      save={save}
    />
  );
}

function SettingsForm({
  current,
  save,
}: {
  current: Settings;
  save: UseMutationResult<Settings, Error, Schemas["SettingsUpdate"]>;
}) {
  const [form, setForm] = useState<FormState>(() => toForm(current));
  const [formError, setFormError] = useState<string | null>(null);

  const set = (patch: Partial<FormState>) => {
    setForm({ ...form, ...patch });
    save.reset();
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    const body: Schemas["SettingsUpdate"] = {};
    if (form.name.trim() !== current.name) body.name = form.name.trim();
    const rounding = toCents(form.rounding);
    if (rounding === null || rounding < 1) return setFormError("Rounding must be at least KSh 0.01.");
    if (rounding !== current.price_rounding_cents) body.price_rounding_cents = rounding;
    if (form.allocation !== current.default_allocation_method) {
      body.default_allocation_method = form.allocation;
    }
    for (const [key, label] of PERCENT_FIELDS) {
      const fraction = percentToFraction(form[key]);
      if (fraction === null) return setFormError(`${label}: enter a percentage like 10 or 12.5.`);
      if (Number(fraction) !== Number(current[key])) body[key] = fraction;
    }
    for (const [key, label] of DAY_FIELDS) {
      if (!/^\d+$/.test(form[key].trim())) return setFormError(`${label}: enter a whole number.`);
      const value = Number(form[key]);
      if (value !== current[key]) body[key] = value;
    }
    if (Object.keys(body).length === 0) return setFormError("Nothing has changed.");
    save.mutate(body);
  };

  return (
    <Card title="Business">
      <form onSubmit={submit} className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Shop name">
            <Input value={form.name} onChange={(e) => set({ name: e.target.value })} required />
          </Field>
          <Field label="Round prices to (KSh)" hint="e.g. 5 rounds engine prices up to the next KSh 5, so they never fall below the target margin.">
            <Input inputMode="decimal" value={form.rounding} onChange={(e) => set({ rounding: e.target.value })} />
          </Field>
          <Field label="Share delivery costs" hint="How transport, duty and packaging are spread over a delivery.">
            <Select
              value={form.allocation}
              onChange={(e) => set({ allocation: e.target.value as FormState["allocation"] })}
            >
              <option value="by_value">By line value</option>
              <option value="by_quantity">By quantity</option>
            </Select>
          </Field>
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold text-gray-900">Pricing and alert percentages</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            {PERCENT_FIELDS.map(([key, label, hint]) => (
              <Field key={key} label={`${label} (%)`} hint={hint}>
                <div className="relative">
                  <Input
                    inputMode="decimal"
                    value={form[key]}
                    onChange={(e) => set({ [key]: e.target.value })}
                    className="pr-8"
                  />
                  <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-gray-500">
                    %
                  </span>
                </div>
              </Field>
            ))}
          </div>
        </div>

        <div>
          <h3 className="mb-3 text-sm font-semibold text-gray-900">Days</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            {DAY_FIELDS.map(([key, label, hint]) => (
              <Field key={key} label={label} hint={hint}>
                <Input inputMode="numeric" value={form[key]} onChange={(e) => set({ [key]: e.target.value })} />
              </Field>
            ))}
          </div>
        </div>

        <ErrorText error={formError ?? save.error} />
        {save.isSuccess && <Notice tone="green">Settings saved.</Notice>}
        <div className="flex gap-2">
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save settings"}
          </Button>
          <Button variant="ghost" onClick={() => setForm(toForm(current))}>
            Reset
          </Button>
        </div>
      </form>
    </Card>
  );
}

function Users() {
  const session = useSession();
  const router = useRouter();
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => call(api.GET("/users")) });
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [role, setRole] = useState<"cashier" | "owner">("cashier");

  const add = useMutation({
    mutationFn: () => call(api.POST("/users", { body: { name, phone: phone || null, role } })),
    onSuccess: () => {
      setName("");
      setPhone("");
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
  const switchUser = useMutation({
    mutationFn: (userId: string) => signIn(session!.businessId, userId),
    onSuccess: (next) => {
      queryClient.clear();
      router.replace(homeFor(next.role));
    },
  });

  return (
    <Card title="Users">
      {users.isPending ? (
        <Loading />
      ) : users.error ? (
        <ErrorText error={users.error} />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Role</Th>
              <Th />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.data.map((u) => (
              <tr key={u.id}>
                <Td>
                  <span className="font-medium">{u.name}</span>
                  {u.phone && <span className="ml-2 text-xs text-gray-500">{u.phone}</span>}
                </Td>
                <Td>
                  <Badge tone={u.role === "owner" ? "green" : "blue"}>{u.role}</Badge>
                </Td>
                <Td right>
                  {u.id === session?.userId ? (
                    <span className="text-xs text-gray-500">You</span>
                  ) : (
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={switchUser.isPending}
                      onClick={() => switchUser.mutate(u.id)}
                    >
                      Sign in as
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <ErrorText error={switchUser.error} />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate();
        }}
        className="mt-5 border-t border-gray-100 pt-4"
      >
        <h3 className="mb-3 text-sm font-semibold text-gray-900">Add a user</h3>
        <div className="grid gap-3 sm:grid-cols-[1fr_1fr_10rem_auto] sm:items-end">
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <Field label="Phone (optional)">
            <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" />
          </Field>
          <Field label="Role">
            <Select value={role} onChange={(e) => setRole(e.target.value as "cashier" | "owner")}>
              <option value="cashier">Cashier</option>
              <option value="owner">Owner</option>
            </Select>
          </Field>
          <Button type="submit" disabled={add.isPending}>
            Add user
          </Button>
        </div>
        <div className="mt-3">
          <ErrorText error={add.error} />
        </div>
      </form>
      <p className="mt-4 text-xs text-gray-500">
        Development sign-in uses these IDs. Cashiers can sell, view stock and take credit
        repayments; everything else is owner-only.
      </p>
    </Card>
  );
}
