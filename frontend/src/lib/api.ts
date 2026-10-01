import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./api-schema";
import { authHeaders, readSession, writeSession } from "./session";

// Types generated from the backend's OpenAPI schema: run `npm run gen:api` after API changes.
export type Schemas = components["schemas"];

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** FastAPI errors are `{detail: string}` or, for validation, `{detail: [{loc, msg}]}`. */
function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const field = d.loc?.filter((p) => p !== "body").join(".");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return `Request failed (${status})`;
}

const auth: Middleware = {
  onRequest({ request }) {
    for (const [k, v] of Object.entries(authHeaders(readSession()))) request.headers.set(k, v);
    return request;
  },
  onResponse({ response }) {
    // The stored sign-in no longer matches a user (e.g. the database was reset).
    if (response.status === 401 && readSession()) writeSession(null);
    return response;
  },
};

export const api = createClient<paths>({ baseUrl: "/api" });
api.use(auth);

/** Unwrap an openapi-fetch result: return data or throw an ApiError with the backend message. */
export async function call<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await promise;
  if (!response.ok) throw new ApiError(response.status, errorMessage(error, response.status));
  return data as T;
}

/** Download a CSV/XLSX export (needs the auth headers, so it can't be a plain link). */
export async function download(path: string, params: Record<string, string | undefined>) {
  const query = new URLSearchParams(
    Object.entries(params).filter((e): e is [string, string] => !!e[1]),
  );
  const response = await fetch(`/api${path}?${query}`, { headers: authHeaders(readSession()) });
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(await response.json().catch(() => null), response.status));
  }
  const name =
    /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "")?.[1] ?? "export";
  const url = URL.createObjectURL(await response.blob());
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  link.click();
  URL.revokeObjectURL(url);
}

export function newId() {
  return crypto.randomUUID();
}
