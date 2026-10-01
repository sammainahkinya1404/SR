"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { type Role, writeSession } from "@/lib/session";
import { useSession } from "@/lib/use-session";
import { Loading, cx } from "./ui";

type NavItem = { href: string; label: string; roles: Role[] };

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", roles: ["owner"] },
  { href: "/pos", label: "Sell (POS)", roles: ["owner", "cashier"] },
  { href: "/sales", label: "Sales", roles: ["owner", "cashier"] },
  { href: "/stock", label: "Stock", roles: ["owner", "cashier"] },
  { href: "/sets", label: "Sets", roles: ["owner"] },
  { href: "/customers", label: "Customers", roles: ["owner", "cashier"] },
  { href: "/expenses", label: "Expenses", roles: ["owner"] },
  { href: "/cash", label: "Cash & accounts", roles: ["owner"] },
  { href: "/reports", label: "Reports", roles: ["owner"] },
  { href: "/alerts", label: "Alerts", roles: ["owner"] },
  { href: "/settings", label: "Settings", roles: ["owner"] },
];

export function homeFor(role: Role) {
  return role === "owner" ? "/dashboard" : "/pos";
}

export function AppShell({ children }: { children: ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (session === null) router.replace("/login");
  }, [session, router]);

  if (!session) return <Loading />;

  const items = NAV.filter((item) => item.roles.includes(session.role));
  const signOut = () => {
    writeSession(null);
    queryClient.clear();
  };

  const nav = (
    <nav className="flex flex-col gap-0.5">
      {items.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setMenuOpen(false)}
            className={cx(
              "rounded-md px-3 py-2 text-sm font-medium",
              active ? "bg-emerald-50 text-emerald-800" : "text-gray-700 hover:bg-gray-100",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen lg:flex">
      <aside className="hidden w-60 shrink-0 border-r border-gray-200 bg-white p-4 lg:flex lg:flex-col">
        <p className="mb-1 px-3 text-base font-semibold text-emerald-800">Duka Manager</p>
        <p className="mb-5 truncate px-3 text-xs text-gray-500">{session.businessName}</p>
        {nav}
        <div className="mt-auto border-t border-gray-100 px-3 pt-4 text-xs text-gray-600">
          <p className="font-medium text-gray-900">{session.userName}</p>
          <p className="capitalize">{session.role}</p>
          <button onClick={signOut} className="mt-2 text-emerald-700 hover:underline">
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3 lg:hidden">
          <div>
            <p className="text-sm font-semibold text-emerald-800">Duka Manager</p>
            <p className="text-xs text-gray-500">{session.businessName}</p>
          </div>
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="rounded-md px-3 py-1.5 text-sm ring-1 ring-gray-300"
            aria-expanded={menuOpen}
          >
            Menu
          </button>
        </header>
        {menuOpen && (
          <div className="border-b border-gray-200 bg-white p-3 lg:hidden">
            {nav}
            <button onClick={signOut} className="mt-2 px-3 text-sm text-emerald-700">
              Sign out ({session.userName})
            </button>
          </div>
        )}
        <main className="mx-auto w-full max-w-6xl flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}

/** Wrap owner-only pages: cashiers are sent to their home page. */
export function OwnerOnly({ children }: { children: ReactNode }) {
  const session = useSession();
  const router = useRouter();
  const allowed = session?.role === "owner";
  useEffect(() => {
    if (session && !allowed) router.replace(homeFor(session.role));
  }, [session, allowed, router]);
  return allowed ? children : <Loading />;
}
