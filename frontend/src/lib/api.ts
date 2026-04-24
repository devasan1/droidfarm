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
  listTrashedPhones: () => req<Phone[]>("/api/phones/trash"),
  restorePhone: (id: number) => req<Phone>(`/api/phones/${id}/restore`, { method: "POST" }),
  purgePhone: (id: number) => req<void>(`/api/phones/${id}/purge`, { method: "POST" }),
  startPhone: (id: number) => req<Phone>(`/api/phones/${id}/start`, { method: "POST" }),
  stopPhone: (id: number) => req<Phone>(`/api/phones/${id}/stop`, { method: "POST" }),
  wipePhone: (id: number) => req<Phone>(`/api/phones/${id}/wipe`, { method: "POST" }),
  regenerateFingerprint: (id: number, device_profile?: string) =>
    req<Phone>(
      `/api/phones/${id}/regenerate-fingerprint${
        device_profile ? `?device_profile=${encodeURIComponent(device_profile)}` : ""
      }`,
      { method: "POST" },
    ),
  deviceProfiles: () =>
    req<{ manufacturer: string; model: string; android_release: string }[]>(
      "/api/phones/device-profiles",
    ),
  screenshotUrl: (id: number, cacheBust?: number) =>
    `/api/phones/${id}/screenshot${cacheBust ? `?t=${cacheBust}` : ""}`,
  tapPhone: (id: number, x: number, y: number) =>
    req<void>(`/api/phones/${id}/tap`, {
      method: "POST",
      body: JSON.stringify({ x: Math.round(x), y: Math.round(y) }),
    }),
  swipePhone: (id: number, x1: number, y1: number, x2: number, y2: number, duration_ms = 120) =>
    req<void>(`/api/phones/${id}/swipe`, {
      method: "POST",
      body: JSON.stringify({
        x1: Math.round(x1),
        y1: Math.round(y1),
        x2: Math.round(x2),
        y2: Math.round(y2),
        duration_ms,
      }),
    }),
  textPhone: (id: number, text: string) =>
    req<void>(`/api/phones/${id}/text`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  keyeventPhone: (id: number, keycode: string | number) =>
    req<void>(`/api/phones/${id}/keyevent`, {
      method: "POST",
      body: JSON.stringify({ keycode }),
    }),
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
