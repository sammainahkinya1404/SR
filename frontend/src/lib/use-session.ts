"use client";

import { useSyncExternalStore } from "react";
import { type Session, readSession, subscribeSession } from "./session";

let cachedRaw: string | null = null;
let cached: Session | null = null;

function snapshot(): Session | null {
  // useSyncExternalStore needs a stable object while storage is unchanged.
  const raw = JSON.stringify(readSession());
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cached = readSession();
  }
  return cached;
}

/** The signed-in session; `undefined` until the browser has been read (server and hydration). */
export function useSession(): Session | null | undefined {
  return useSyncExternalStore(subscribeSession, snapshot, () => undefined);
}
