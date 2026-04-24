import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";
import { api } from "../lib/api";
import type { HostGeo, Phone, Proxy, ProxyMode } from "../lib/types";

interface Props {
  onClose: () => void;
  onCreated: (p: Phone) => void;
}

type ProxyChoice = "auto" | "pick" | "bypass";

export default function AddPhoneModal({ onClose, onCreated }: Props) {
  const [proxies, setProxies] = useState<Proxy[]>([]);
  const [existingPhones, setExistingPhones] = useState<Phone[]>([]);
  const [hostGeo, setHostGeo] = useState<HostGeo | null>(null);
  const [name, setName] = useState("");
  const [resolution, setResolution] = useState("1080x1920");
  const [dpi, setDpi] = useState(420);
  const [cpu, setCpu] = useState(2);
  const [ramMb, setRamMb] = useState(4096);
  const [proxyMode, setProxyMode] = useState<ProxyMode>("tun2socks");
  const [proxyChoice, setProxyChoice] = useState<ProxyChoice>("auto");
  const [proxyId, setProxyId] = useState<number | null>(null);
  const [autostart, setAutostart] = useState(true);
  const [showSetupWizard, setShowSetupWizard] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Bypass-IP geo override.
  const [overrideCountry, setOverrideCountry] = useState<string>("");
  const [overrideCity, setOverrideCity] = useState<string>("");
  const [countries, setCountries] = useState<string[]>([]);
  const [cities, setCities] = useState<
    { name: string; latitude: number; longitude: number; timezone: string }[]
  >([]);

  useEffect(() => {
    api.listProxies().then(setProxies).catch(() => {});
    api.listPhones().then(setExistingPhones).catch(() => {});
  }, []);

  // Lazy-load host geo + curated country list the first time the user picks "bypass".
  useEffect(() => {
    if (proxyChoice === "bypass" && hostGeo === null) {
      api.hostGeo().then(setHostGeo).catch(() => setHostGeo({ ok: false, error: "unreachable", ip: null, country: null, region: null, city: null, latitude: null, longitude: null, timezone: null, provider: null }));
    }
    if (proxyChoice === "bypass" && countries.length === 0) {
      api.geoCountries().then(setCountries).catch(() => {});
    }
  }, [proxyChoice, hostGeo, countries.length]);

  // When the override country changes, refresh the city list for it.
  useEffect(() => {
    setOverrideCity("");
    if (!overrideCountry) {
      setCities([]);
      return;
    }
    api.geoCities(overrideCountry).then(setCities).catch(() => setCities([]));
  }, [overrideCountry]);

  // Default name: phone-NN with NN = first free slot
  useEffect(() => {
    if (name) return;
    const used = new Set(existingPhones.map((p) => p.name));
    for (let i = 1; i < 100; i++) {
      const candidate = `phone-${String(i).padStart(2, "0")}`;
      if (!used.has(candidate)) {
        setName(candidate);
        break;
      }
    }
  }, [existingPhones, name]);

  const availableProxies = useMemo(
    () => proxies.filter((p) => p.assigned_to_phone_id === null),
    [proxies],
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const phone = await api.createPhone({
        name,
        resolution,
        dpi,
        cpu,
        ram_mb: ramMb,
        proxy_mode: proxyChoice === "bypass" ? "none" : proxyMode,
        autostart,
        proxy_id: proxyChoice === "pick" ? proxyId : null,
        auto_assign_proxy: proxyChoice === "auto",
        bypass_ip: proxyChoice === "bypass",
        show_setup_wizard: showSetupWizard,
        geo_override_country:
          proxyChoice === "bypass" && overrideCountry ? overrideCountry : null,
        geo_override_city:
          proxyChoice === "bypass" && overrideCountry && overrideCity
            ? overrideCity
            : null,
      });
      onCreated(phone);
    } catch (e) {
      setError(String(e));
      setSubmitting(false);
    }
  }

  const proxyChoiceInvalid =
    (proxyChoice === "auto" && availableProxies.length === 0) ||
    (proxyChoice === "pick" && proxyId === null);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <form
        className="card w-full max-w-xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <header className="flex items-center justify-between border-b border-ink-800 px-5 py-3">
          <h2 className="text-lg font-medium text-ink-50">Add phone</h2>
          <button type="button" className="btn-ghost" onClick={onClose}>
            <X size={16} />
          </button>
        </header>

        <div className="space-y-4 px-5 py-4">
          <div>
            <label className="label">Name</label>
            <input
              className="input mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Resolution</label>
              <select className="input mt-1" value={resolution} onChange={(e) => setResolution(e.target.value)}>
                <option value="720x1280">720×1280 (HD)</option>
                <option value="1080x1920">1080×1920 (FHD)</option>
                <option value="1440x2560">1440×2560 (QHD)</option>
              </select>
            </div>
            <div>
              <label className="label">DPI</label>
              <input
                className="input mt-1"
                type="number"
                value={dpi}
                min={160}
                max={640}
                step={20}
                onChange={(e) => setDpi(parseInt(e.target.value, 10))}
              />
            </div>
            <div>
              <label className="label">vCPU</label>
              <input className="input mt-1" type="number" value={cpu} min={1} max={8} onChange={(e) => setCpu(parseInt(e.target.value, 10))} />
            </div>
            <div>
              <label className="label">RAM (MB)</label>
              <input
                className="input mt-1"
                type="number"
                value={ramMb}
                min={1024}
                max={16384}
                step={512}
                onChange={(e) => setRamMb(parseInt(e.target.value, 10))}
              />
            </div>
          </div>

          <hr className="border-ink-800" />

          <div>
            <label className="label">Proxy</label>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {(["auto", "pick", "bypass"] as ProxyChoice[]).map((v) => (
                <button
                  type="button"
                  key={v}
                  className={[
                    "rounded-md border px-3 py-2 text-sm",
                    proxyChoice === v
                      ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                      : "border-ink-700 text-ink-300 hover:border-ink-600",
                  ].join(" ")}
                  onClick={() => setProxyChoice(v)}
                >
                  {v === "auto" && "Auto-assign unique"}
                  {v === "pick" && "Pick from list"}
                  {v === "bypass" && "Bypass (VM's IP)"}
                </button>
              ))}
            </div>
            {proxyChoice === "auto" && (
              <p className="mt-2 text-xs text-ink-400">
                {availableProxies.length > 0
                  ? `Will pick 1 of ${availableProxies.length} free proxies and lock it to this phone.`
                  : "No unassigned proxies — import more in the Proxies tab first."}
              </p>
            )}
            {proxyChoice === "pick" && (
              <select
                className="input mt-2"
                value={proxyId ?? ""}
                onChange={(e) => setProxyId(e.target.value ? parseInt(e.target.value, 10) : null)}
                required
              >
                <option value="">— select a free proxy —</option>
                {availableProxies.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label || `${p.host}:${p.port}`}
                    {p.country ? ` · ${p.country}` : ""}
                    {p.city ? ` / ${p.city}` : ""}
                  </option>
                ))}
              </select>
            )}
            {proxyChoice === "bypass" && (
              <div className="mt-2 rounded-md border border-ink-700 bg-ink-950 p-3 text-xs text-ink-300">
                <div className="mb-1 font-medium text-ink-100">
                  Phone will use the VM&apos;s own IP
                </div>
                {hostGeo === null ? (
                  <div className="text-ink-400">looking up host geo…</div>
                ) : !hostGeo.ok ? (
                  <div className="text-amber-300">
                    Host geoIP lookup failed ({hostGeo.error ?? "unknown"}). Phone will still work, but locale/timezone/GPS won&apos;t be spoofed.
                  </div>
                ) : (
                  <div className="space-y-0.5">
                    <div><span className="text-ink-500">egress IP:</span> <span className="font-mono text-ink-100">{hostGeo.ip}</span></div>
                    <div>
                      <span className="text-ink-500">appears as:</span>{" "}
                      <span className="text-ink-100">
                        {hostGeo.city ? `${hostGeo.city}, ` : ""}
                        {hostGeo.region ? `${hostGeo.region}, ` : ""}
                        {hostGeo.country ?? "?"}
                      </span>
                    </div>
                    <div><span className="text-ink-500">timezone:</span> {hostGeo.timezone ?? "?"}</div>
                    <div><span className="text-ink-500">provider:</span> {hostGeo.provider ?? "?"}</div>
                  </div>
                )}

                <div className="mt-3 border-t border-ink-800 pt-3">
                  <div className="mb-1 font-medium text-ink-100">
                    Override phone location (optional)
                  </div>
                  <p className="mb-2 text-ink-400">
                    Phone egresses through the VM&apos;s real IP either way.
                    Set this to pin locale / timezone / GPS to a different
                    country + city so the phone <i>feels like</i> it&apos;s
                    there.
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <select
                      className="input"
                      value={overrideCountry}
                      onChange={(e) => setOverrideCountry(e.target.value)}
                    >
                      <option value="">— use VM&apos;s own location —</option>
                      {countries.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                    <select
                      className="input"
                      value={overrideCity}
                      onChange={(e) => setOverrideCity(e.target.value)}
                      disabled={!overrideCountry}
                    >
                      <option value="">
                        {overrideCountry
                          ? cities.length === 0
                            ? "— no cities curated —"
                            : "— country default (capital) —"
                          : "— pick country first —"}
                      </option>
                      {cities.map((c) => (
                        <option key={c.name} value={c.name}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  {overrideCountry && (
                    <div className="mt-1 text-ink-400">
                      Phone will appear as{" "}
                      <span className="text-ink-200">
                        {overrideCity ? `${overrideCity}, ` : ""}
                        {overrideCountry}
                      </span>
                      . Network traffic still exits through the VM&apos;s
                      real IP.
                    </div>
                  )}
                </div>
              </div>
            )}
            {proxyChoice !== "bypass" && (
              <div className="mt-3">
                <label className="label">Routing mode</label>
                <select
                  className="input mt-1"
                  value={proxyMode}
                  onChange={(e) => setProxyMode(e.target.value as ProxyMode)}
                >
                  <option value="tun2socks">tun2socks (recommended — all app traffic)</option>
                  <option value="system-http">system HTTP proxy (fast, but apps can bypass)</option>
                </select>
              </div>
            )}
          </div>

          <hr className="border-ink-800" />

          <div>
            <label className="label">First-boot experience</label>
            <p className="mt-1 text-xs text-ink-500">
              Every phone is cloned from a clean template — no apps, no cache, no saved data.
              Pick whether it should boot straight to the launcher or run through Android&apos;s
              first-boot setup wizard.
            </p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {([
                { v: false, title: "Skip setup wizard", sub: "Boots to launcher, already past Welcome/language/Wi-Fi/Google account." },
                { v: true, title: "Show setup wizard", sub: "Clean phone that walks you through the usual first-boot flow." },
              ] as const).map((opt) => (
                <button
                  type="button"
                  key={String(opt.v)}
                  onClick={() => setShowSetupWizard(opt.v)}
                  className={[
                    "rounded-md border px-3 py-2 text-left",
                    showSetupWizard === opt.v
                      ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                      : "border-ink-700 text-ink-300 hover:border-ink-600",
                  ].join(" ")}
                >
                  <div className="text-sm font-medium">{opt.title}</div>
                  <div className="mt-0.5 text-[11px] text-ink-400">{opt.sub}</div>
                </button>
              ))}
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm text-ink-200">
            <input
              type="checkbox"
              checked={autostart}
              onChange={(e) => setAutostart(e.target.checked)}
            />
            Start phone immediately and keep running until stopped
          </label>

          {error && (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-300">
              {error}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-ink-800 px-5 py-3">
          <button type="button" className="btn-secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={submitting || !name || proxyChoiceInvalid}
          >
            {submitting ? "Creating…" : "Add phone"}
          </button>
        </footer>
      </form>
    </div>
  );
}
