import type {
  Apk,
  HostGeo,
  Phone,
  PhoneIn,
  Proxy,
  ProxyIn,
  Schedule,
  ScheduleActionSpec,
} from "./types";

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
    let detail: string = r.statusText;
    try {
      const body = await r.json();
      const d = body.detail ?? body.error ?? body.message;
      if (typeof d === "string") {
        detail = d;
      } else if (Array.isArray(d)) {
        detail = d
          .map((x: { msg?: string; message?: string } | string) =>
            typeof x === "string" ? x : x.msg ?? x.message ?? JSON.stringify(x),
          )
          .join("; ");
      } else if (d != null) {
        detail = JSON.stringify(d);
      }
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
  setProxyAutoRotate: (id: number, auto_rotate: boolean) =>
    req<Proxy>(`/api/proxies/${id}/auto-rotate`, {
      method: "POST",
      body: JSON.stringify({ auto_rotate }),
    }),
  rotateProxy: (id: number) =>
    req<{
      ok: boolean;
      phone: string;
      old_proxy: string;
      new_proxy: string;
      new_country: string | null;
    }>(`/api/proxies/${id}/rotate`, { method: "POST" }),
  proxyStats: () =>
    req<{
      total: number;
      healthy: number;
      unhealthy: number;
      in_use: number;
      free: number;
      auto_rotate_enabled: number;
      avg_latency_ms: number | null;
      last_checked_at: string | null;
    }>("/api/proxies/stats"),

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
  // Catalog of common apps users want to pre-load.
  listCatalog: () =>
    req<
      {
        slug: string;
        display_name: string;
        package: string;
        category: string;
        description: string;
        source_url: string;
        homepage_url: string;
        installed: boolean;
      }[]
    >("/api/apks/catalog"),
  fetchCatalogApk: (slug: string, url: string, filename?: string) =>
    req<Apk>(`/api/apks/catalog/${slug}/fetch`, {
      method: "POST",
      body: JSON.stringify({ url, filename }),
    }),
  // Per-phone automation: shell, launch, logcat, packages.
  phoneShell: (id: number, cmd: string, timeout_s?: number) =>
    req<{ ok: boolean; stdout: string; stderr?: string }>(
      `/api/phones/${id}/shell`,
      { method: "POST", body: JSON.stringify({ cmd, timeout_s }) },
    ),
  phoneLaunch: (id: number, pkg: string) =>
    req<void>(`/api/phones/${id}/launch`, {
      method: "POST",
      body: JSON.stringify({ package: pkg }),
    }),
  phoneForceStop: (id: number, pkg: string) =>
    req<void>(`/api/phones/${id}/force-stop`, {
      method: "POST",
      body: JSON.stringify({ package: pkg }),
    }),
  phoneUninstall: (id: number, pkg: string) =>
    req<void>(`/api/phones/${id}/uninstall`, {
      method: "POST",
      body: JSON.stringify({ package: pkg }),
    }),
  phonePackages: (id: number) =>
    req<string[]>(`/api/phones/${id}/packages`),
  phoneLogcat: async (id: number, lines = 300) => {
    const r = await fetch(`/api/phones/${id}/logcat?lines=${lines}`);
    if (!r.ok) throw new Error(await r.text());
    return await r.text();
  },

  listSchedules: () => req<Schedule[]>("/api/schedules"),
  scheduleActions: () =>
    req<{ actions: ScheduleActionSpec[] }>("/api/schedules/actions"),
  createSchedule: (body: {
    name: string;
    cron: string;
    action: string;
    target_phone_ids?: number[];
    params?: Record<string, unknown>;
    enabled?: boolean;
  }) =>
    req<Schedule>("/api/schedules", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  patchSchedule: (
    id: number,
    body: Partial<{
      name: string;
      cron: string;
      action: string;
      target_phone_ids: number[];
      params: Record<string, unknown>;
      enabled: boolean;
    }>,
  ) =>
    req<Schedule>(`/api/schedules/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  runScheduleNow: (id: number) =>
    req<Schedule>(`/api/schedules/${id}/run`, { method: "POST" }),
  deleteSchedule: (id: number) =>
    req<void>(`/api/schedules/${id}`, { method: "DELETE" }),
};
