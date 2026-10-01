import { ApiError } from "./api";
import { type Session, authHeaders, writeSession } from "./session";

/** Confirm the user against the backend (GET /me), then store the session. */
export async function signIn(businessId: string, userId: string): Promise<Session> {
  const response = await fetch("/api/me", { headers: authHeaders({ businessId, userId }) });
  if (!response.ok) {
    throw new ApiError(
      response.status,
      response.status === 401 ? "That user no longer exists." : `Sign-in failed (${response.status})`,
    );
  }
  const me = (await response.json()) as {
    user: { id: string; name: string; role: Session["role"] };
    business_id: string;
    business_name: string;
  };
  const session: Session = {
    businessId: me.business_id,
    businessName: me.business_name,
    userId: me.user.id,
    userName: me.user.name,
    role: me.user.role,
  };
  writeSession(session);
  return session;
}
