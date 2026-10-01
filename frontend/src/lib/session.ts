// Dev-stub sign-in: the backend trusts X-Business-Id / X-User-Id headers (see backend
// app/api/deps.py). When real auth (owner OTP, cashier PIN + JWT) lands, only this file and the
// login page should need to change.

export type Role = "owner" | "cashier";

export type Session = {
  businessId: string;
  businessName: string;
  userId: string;
  userName: string;
  role: Role;
};

const KEY = "retail.session";
const listeners = new Set<() => void>();

export function readSession(): Session | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function writeSession(session: Session | null) {
  try {
    if (session) localStorage.setItem(KEY, JSON.stringify(session));
    else localStorage.removeItem(KEY);
  } catch {
    // Storage blocked (private mode): the session lasts for this page only.
  }
  listeners.forEach((fn) => fn());
}

export function subscribeSession(fn: () => void) {
  listeners.add(fn);
  const onStorage = (e: StorageEvent) => e.key === KEY && fn();
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(fn);
    window.removeEventListener("storage", onStorage);
  };
}

export function authHeaders(
  session: Pick<Session, "businessId" | "userId"> | null,
): Record<string, string> {
  return session ? { "X-Business-Id": session.businessId, "X-User-Id": session.userId } : {};
}
