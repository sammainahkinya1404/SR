"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { PageHeader, cx } from "@/components/ui";
import { useSession } from "@/lib/use-session";
import AddStock from "./add-stock";
import { AvailableStock } from "./available-stock";

type Tab = "available" | "add";

const TABS: { key: Tab; label: string; ownerOnly: boolean }[] = [
  { key: "available", label: "Available Stock", ownerOnly: false },
  { key: "add", label: "Add Stock", ownerOnly: true },
];

export function StockTabs() {
  const params = useSearchParams();
  const session = useSession();
  const isOwner = session?.role === "owner";
  const [tab, setTab] = useState<Tab>(() =>
    params.get("tab") === "add" && isOwner ? "add" : "available",
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Stock"
        description="Available Stock shows every item with its buying price, selling price and margin — click a price to change it. Add Stock is where new deliveries go in."
      />
      <div className="flex w-fit gap-1 rounded-lg bg-gray-200/60 p-1">
        {TABS.filter((t) => !t.ownerOnly || isOwner).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cx(
              "rounded-md px-5 py-1.5 text-sm font-medium",
              tab === t.key ? "bg-white shadow-sm" : "text-gray-600",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "available" ? <AvailableStock /> : <AddStock />}
    </div>
  );
}
