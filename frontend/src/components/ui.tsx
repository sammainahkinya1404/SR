"use client";

import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "danger" | "ghost";

const variants: Record<Variant, string> = {
  primary: "bg-emerald-700 text-white hover:bg-emerald-800 disabled:bg-emerald-700/50",
  secondary: "bg-white text-gray-800 ring-1 ring-gray-300 hover:bg-gray-50 disabled:text-gray-400",
  danger: "bg-red-600 text-white hover:bg-red-700 disabled:bg-red-600/50",
  ghost: "text-gray-700 hover:bg-gray-100 disabled:text-gray-400",
};

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "lg" }) {
  return (
    <button
      type="button"
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600",
        "disabled:cursor-not-allowed",
        size === "sm" && "px-2.5 py-1 text-sm",
        size === "md" && "px-3.5 py-2 text-sm",
        size === "lg" && "px-5 py-3 text-base",
        variants[variant],
        className,
      )}
    />
  );
}

const fieldClass =
  "block rounded-md border-0 bg-white px-3 py-2 text-sm ring-1 ring-gray-300 " +
  "placeholder:text-gray-400 focus:ring-2 focus:ring-emerald-600 focus:outline-none " +
  "disabled:bg-gray-50 disabled:text-gray-500";

/** Fields fill their container unless the caller gives a width (e.g. "w-20"). */
function fieldClasses(className?: string, extra?: string) {
  return cx(fieldClass, !/(^|\s)w-/.test(className ?? "") && "w-full", extra, className);
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={fieldClasses(className)} />;
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={fieldClasses(className, "pr-8")} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={fieldClasses(className)} />;
}

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cx("block", className)}>
      <span className="mb-1 block text-sm font-medium text-gray-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-gray-500">{hint}</span>}
    </label>
  );
}

export function Card({
  title,
  actions,
  children,
  className,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cx("rounded-lg bg-white shadow-sm ring-1 ring-gray-200", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-gray-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">{title}</h1>
        {description && <p className="mt-1 text-sm text-gray-600">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

const badgeTones = {
  gray: "bg-gray-100 text-gray-700",
  green: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  amber: "bg-amber-50 text-amber-800 ring-amber-600/20",
  red: "bg-red-50 text-red-700 ring-red-600/20",
  blue: "bg-sky-50 text-sky-800 ring-sky-600/20",
};

export function Badge({
  tone = "gray",
  children,
}: {
  tone?: keyof typeof badgeTones;
  children: ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ring-gray-500/10",
        badgeTones[tone],
      )}
    >
      {children}
    </span>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  const raw = error instanceof Error ? error.message : String(error);
  // Backend messages start lower-case ("only the owner can…"); show them as sentences.
  const message = raw.charAt(0).toUpperCase() + raw.slice(1);
  return (
    <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
      {message}
    </p>
  );
}

export function Notice({ tone = "amber", children }: { tone?: "amber" | "green"; children: ReactNode }) {
  return (
    <p
      className={cx(
        "rounded-md px-3 py-2 text-sm",
        tone === "amber" ? "bg-amber-50 text-amber-900" : "bg-emerald-50 text-emerald-900",
      )}
    >
      {children}
    </p>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <p className="py-6 text-center text-sm text-gray-500">{label}</p>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-8 text-center text-sm text-gray-500">{children}</p>;
}

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="-mx-4 overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 text-sm">{children}</table>
    </div>
  );
}

export function Th({ children, right }: { children?: ReactNode; right?: boolean }) {
  return (
    <th
      scope="col"
      className={cx(
        "px-4 py-2 text-xs font-semibold tracking-wide text-gray-500 uppercase",
        right ? "text-right" : "text-left",
      )}
    >
      {children}
    </th>
  );
}

export function Td({
  children,
  right,
  className,
}: {
  children?: ReactNode;
  right?: boolean;
  className?: string;
}) {
  return (
    <td className={cx("px-4 py-2 whitespace-nowrap", right && "num text-right", className)}>
      {children}
    </td>
  );
}

export function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-gray-200">
      <p className="text-xs font-medium text-gray-500">{label}</p>
      <p className="num mt-1 text-xl font-semibold text-gray-900">{value}</p>
      {sub && <div className="mt-1 text-xs text-gray-500">{sub}</div>}
    </div>
  );
}

/** A simple overlay modal; clicking the backdrop closes it. */
export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/30 p-4 sm:items-center"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div role="dialog" aria-modal="true" aria-label={title} className="w-full max-w-lg rounded-lg bg-white shadow-xl">
        <header className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
          <h2 className="text-base font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded p-1 text-gray-500 hover:bg-gray-100" aria-label="Close">
            ✕
          </button>
        </header>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}
