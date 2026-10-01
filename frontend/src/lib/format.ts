// Money crosses the API as integer cents; fractions and quantities as decimal strings.

const kes = new Intl.NumberFormat("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function ksh(cents: number | null | undefined, withSymbol = true): string {
  if (cents === null || cents === undefined) return "—";
  const text = kes.format(cents / 100);
  return withSymbol ? `KSh ${text}` : text;
}

/** Parse what a user typed in KSh ("1,250.5") into cents; null if it isn't a valid amount. */
export function toCents(input: string): number | null {
  const clean = input.replace(/[,\s]/g, "").replace(/^KSh/i, "");
  if (!/^-?\d+(\.\d{0,2})?$/.test(clean)) return null;
  const [whole, frac = ""] = clean.replace("-", "").split(".");
  const cents = Number(whole) * 100 + Number(frac.padEnd(2, "0"));
  return clean.startsWith("-") ? -cents : cents;
}

export function centsToInput(cents: number): string {
  return (cents / 100).toFixed(2);
}

export function pct(fraction: string | number | null | undefined, digits = 1): string {
  if (fraction === null || fraction === undefined) return "—";
  return `${(Number(fraction) * 100).toFixed(digits)}%`;
}

export function qty(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return String(Number(value));
}

export function ratio(value: string | number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return Number(value).toFixed(digits);
}

// Business dates and times are Kenyan (EAT, UTC+3, no daylight saving).
const dateFmt = new Intl.DateTimeFormat("en-KE", {
  timeZone: "Africa/Nairobi",
  day: "2-digit",
  month: "short",
  year: "numeric",
});
const timeFmt = new Intl.DateTimeFormat("en-KE", {
  timeZone: "Africa/Nairobi",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

/** Backend timestamps are UTC; SQLite drops the offset, so add Z when it is missing. */
function parseTs(ts: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(ts) ? ts : `${ts}Z`);
}

export function dateTime(ts: string | null | undefined): string {
  return ts ? timeFmt.format(parseTs(ts)) : "—";
}

export function date(d: string | null | undefined): string {
  return d ? dateFmt.format(new Date(`${d}T12:00:00+03:00`)) : "—";
}

/** Today's business date in Kenya as YYYY-MM-DD. */
export function todayKenya(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Nairobi" }).format(new Date());
}
