"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";
import { homeFor } from "@/components/app-shell";
import { Badge, Button, Card, ErrorText, Field, Input, Loading } from "@/components/ui";
import { api, call } from "@/lib/api";
import { signIn } from "@/lib/sign-in";
import { useSession } from "@/lib/use-session";

export default function LoginPage() {
  const session = useSession();
  const router = useRouter();
  const setup = useQuery({
    queryKey: ["setup"],
    queryFn: () => call(api.GET("/setup")),
    enabled: session === null,
  });

  useEffect(() => {
    if (session) router.replace(homeFor(session.role));
  }, [session, router]);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center p-4">
      <h1 className="text-2xl font-semibold text-emerald-800">
        {setup.data?.business_name ?? "Duka Manager"}
      </h1>
      <p className="mt-1 mb-6 text-sm text-gray-600">
        {setup.data?.configured
          ? "Who is working?"
          : "Stock, sales, credit and profit for your shop."}
      </p>

      {session !== null || setup.isPending ? (
        <Loading />
      ) : setup.error ? (
        <ErrorText error={setup.error} />
      ) : setup.data.configured ? (
        <PickUser businessId={setup.data.business_id!} users={setup.data.users} />
      ) : (
        <SetUpShop />
      )}

      <p className="mt-6 text-xs text-gray-500">
        Development sign-in: owner OTP and cashier PIN login come later.
      </p>
    </main>
  );
}

function PickUser({
  businessId,
  users,
}: {
  businessId: string;
  users: { id: string; name: string; role: "owner" | "cashier" }[];
}) {
  const login = useMutation({ mutationFn: (userId: string) => signIn(businessId, userId) });
  return (
    <div className="space-y-3">
      <Card>
        <ul className="-my-2 divide-y divide-gray-100">
          {users.map((u) => (
            <li key={u.id}>
              <button
                onClick={() => login.mutate(u.id)}
                disabled={login.isPending}
                className="flex w-full items-center justify-between py-3 text-left hover:text-emerald-800"
              >
                <span className="font-medium">{u.name}</span>
                <Badge tone={u.role === "owner" ? "green" : "blue"}>{u.role}</Badge>
              </button>
            </li>
          ))}
        </ul>
      </Card>
      <p className="text-xs text-gray-500">The owner adds cashiers under Settings → Users.</p>
      <ErrorText error={login.error} />
    </div>
  );
}

function SetUpShop() {
  const [name, setName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [phone, setPhone] = useState("");
  const open = useMutation({
    mutationFn: async () => {
      const business = await call(
        api.POST("/businesses", {
          body: { name, owner_name: ownerName, owner_phone: phone || null },
        }),
      );
      return signIn(business.id, business.owner_id);
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    open.mutate();
  };

  return (
    <Card title="Set up your shop">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Shop name">
          <Input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        </Field>
        <Field label="Your name (owner)">
          <Input value={ownerName} onChange={(e) => setOwnerName(e.target.value)} required />
        </Field>
        <Field label="Phone (optional)">
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" />
        </Field>
        <ErrorText error={open.error} />
        <Button type="submit" className="w-full" disabled={open.isPending}>
          {open.isPending ? "Setting up…" : "Start"}
        </Button>
      </form>
    </Card>
  );
}
