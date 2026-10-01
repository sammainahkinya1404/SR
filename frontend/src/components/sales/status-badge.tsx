"use client";

import { Badge } from "@/components/ui";

export function SaleStatusBadge({ status }: { status: string }) {
  if (status === "returned") return <Badge tone="red">Returned</Badge>;
  if (status === "partially_returned") return <Badge tone="amber">Part returned</Badge>;
  return <Badge tone="green">Completed</Badge>;
}
