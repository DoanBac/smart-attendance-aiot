/**
 * Returns the API base URL (http/https).
 *
 * When running in the browser, uses window.location.origin so the app works
 * from any domain (localhost, Cloudflare Tunnel, custom domain) without
 * needing a rebuild.
 *
 * Server-side (SSR/build), falls back to NEXT_PUBLIC_API_URL env var.
 */
export function getApiBase(): string {
  if (typeof window !== "undefined") {
    return window.location.origin;
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

/**
 * Returns the WebSocket base URL (ws/wss).
 * Automatically upgrades to wss:// when page is on https.
 */
export function getWsBase(): string {
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}`;
  }
  const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  return api.replace(/^http/, "ws");
}

/**
 * fetch wrapper tự động đính kèm Authorization header.
 * Nếu server trả 401 (token hết hạn / không hợp lệ) → xóa token + redirect /login.
 */
export async function apiFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const base = getApiBase();
  const token = typeof window !== "undefined"
    ? localStorage.getItem("access_token")
    : null;

  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${base}${path}`, { ...options, headers });

  if (res.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("access_token");
    window.location.replace("/login");
  }

  return res;
}
