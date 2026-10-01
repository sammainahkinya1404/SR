"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { homeFor } from "@/components/app-shell";
import { Loading } from "@/components/ui";
import { useSession } from "@/lib/use-session";

export default function Home() {
  const session = useSession();
  const router = useRouter();
  useEffect(() => {
    if (session === null) router.replace("/login");
    else if (session) router.replace(homeFor(session.role));
  }, [session, router]);
  return <Loading />;
}
