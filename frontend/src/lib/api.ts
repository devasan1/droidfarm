import type { Apk, HostGeo, Phone, PhoneIn, Proxy, ProxyIn } from "./types";

const BASE = "";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await r.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (r.status === 204) return undefined as unknown as T;
  return r.json() as Promise<T>;
}

export const api = {
  health: () => req<{ ok: boolean; mock_driver: boolean; ldconsole: string | null }>("/api/health"),

  listPhones: () => req<Phone[]>("/api/phones"),
  hostGeo: () => req<HostGeo>("/api/phones/host-geo"),
  getPhone: (id: number) => req<Phone>(`/api/phones/${id}`),
  createPhone: (body: PhoneIn) =>
    req<Phone>("/api/phones", { method: "POST", body: JSON.stringify(body) }),
  deletePhone: (id: number) => req<void>(`/api/phones/${id}`, { method: "DELETE" }),
  startPhone: (id: number) => req<Phone>(`/api/phones/${id}/start`, { method: "POST" }),
  stopPhone: (id: number) => req<Phone>(`/api/phones/${id}/stop`, { method: "POST" }),
  wipePhone: (id: number) => req<Phone>(`/api/phones/${id}/wipe`, { method: "POST" }),
  geoCountries: () => req<string[]>("/api/phones/geo-countries"),
  geoCities: (country: string) =>
    req<{ name: string; country: string; latitude: number; longitude: number; timezone: string }[]>(
      `/api/phones/geo-cities?country=${encodeURIComponent(country)}`,
    ),
  installApkOnPhone: (phoneId: number, apkId: number) =>
    req<{ ok: boolean; filename: string; error: string | null }>(
      `/api/phones/${phoneId}/install-apk`,
      { method: "POST", body: JSON.stringify({ apk_id: apkId }) },
    ),

  listProxies: () => req<Proxy[]>("/api/proxies"),
  createProxy: (body: ProxyIn) =>
    req<Proxy>("/api/proxies", { method: "POST", body: JSON.stringify(body) }),
  importProxies: (text: string, defaultScheme = "http") =>
    req<{ imported: number; skipped: number; proxies: Proxy[]; errors: unknown[] }>(
      "/api/proxies/import",
      { method: "POST", body: JSON.stringify({ text, default_scheme: defaultScheme }) },
    ),
  deleteProxy: (id: number) => req<void>(`/api/proxies/${id}`, { method: "DELETE" }),
  checkProxy: (id: number) => req<Proxy>(`/api/proxies/${id}/check`, { method: "POST" }),
  checkAllProxies: () =>
    req<{ queued: number }>(`/api/proxies/check-all`, { method: "POST" }),

  listApks: () => req<Apk[]>("/api/apks"),
  deleteApk: (id: number) => req<void>(`/api/apks/${id}`, { method: "DELETE" }),
  // Upload uses multipart, not JSON.
  uploadApk: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const r = await fetch("/api/apks", { method: "POST", body: form });
    if (!r.ok) throw new Error(await r.text());
    return (await r.json()) as Apk;
  },
};
