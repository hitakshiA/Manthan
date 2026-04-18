/** Base HTTP client. In dev, Vite proxies /api → localhost:8000 */

export const BASE_URL =
  import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "/api" : "");

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export function get<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
}

export function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export async function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}${path}`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export async function uploadMulti<T>(
  path: string,
  files: File[],
  opts: { primary?: string } = {},
): Promise<T> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const qs = opts.primary ? `?primary=${encodeURIComponent(opts.primary)}` : "";
  const res = await fetch(`${BASE_URL}${path}${qs}`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json() as Promise<T>;
}
