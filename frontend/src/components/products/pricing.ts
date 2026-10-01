import type { Schemas } from "@/lib/api";

export type PricingMode = Schemas["PricingMode"];

export const PRICING_MODES: { value: PricingMode; label: string; hint: string }[] = [
  { value: "manual", label: "Manual price", hint: "You set the price yourself." },
  { value: "target_margin", label: "Target margin", hint: "price = cost ÷ (1 − margin)" },
  { value: "markup", label: "Markup", hint: "price = cost × (1 + markup)" },
];

export function modeLabel(mode: string): string {
  return PRICING_MODES.find((m) => m.value === mode)?.label ?? mode;
}

/** "25" (percent typed by the user) -> "0.2500" (fraction for the API); null if invalid. */
export function percentToFraction(input: string): string | null {
  const n = Number(input.trim());
  if (input.trim() === "" || !Number.isFinite(n) || n < 0) return null;
  return (n / 100).toFixed(4);
}

/** "0.2500" -> "25" for editing. */
export function fractionToPercent(value: string | null | undefined): string {
  if (value === null || value === undefined) return "";
  return String(Number((Number(value) * 100).toFixed(2)));
}

export function isLowStock(p: Schemas["ProductOut"]): boolean {
  return Number(p.reorder_point) > 0 && Number(p.qty_on_hand) <= Number(p.reorder_point);
}
