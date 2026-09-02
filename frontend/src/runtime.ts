const apiOrigin = (import.meta.env.VITE_API_ORIGIN || "").trim().replace(/\/+$/, "");
const sessionHeader = "X-Scivis-Session";
const sessionStorageKey = "scivis_public_session";

function sessionToken(): string {
  try {
    return window.localStorage.getItem(sessionStorageKey) || "";
  } catch {
    return "";
  }
}

function rememberSession(response: Response): void {
  const token = response.headers.get(sessionHeader);
  if (!token) return;
  try {
    window.localStorage.setItem(sessionStorageKey, token);
  } catch {
    // Browsers with blocked storage can still use the first-party cookie path.
  }
}

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${apiOrigin}${normalized}`;
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = sessionToken();
  if (token) headers.set(sessionHeader, token);
  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
    credentials: "include",
  });
  rememberSession(response);
  return response;
}

export function apiResourceUrl(path: string): string {
  const resolved = apiUrl(path);
  const token = sessionToken();
  if (!apiOrigin || !token) return resolved;
  const url = new URL(resolved);
  url.searchParams.set("_scivis_session", token);
  return url.toString();
}

export function siteUrl(path = ""): string {
  return `${import.meta.env.BASE_URL}${path.replace(/^\/+/, "")}`;
}
