import { useEffect, useState } from "react";
import { Play, Plus, RotateCcw, Square, Trash2 } from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import type { Phone } from "../lib/types";
import AddPhoneModal from "../components/AddPhoneModal";

export default function Phones() {
  const [phones, setPhones] = useState<Phone[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setPhones(await api.listPhones());
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink-50">Phones</h1>
          <p className="text-sm text-ink-400">
            {phones.length} phone{phones.length === 1 ? "" : "s"} · {phones.filter((p) => p.status === "running").length} running
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowAdd(true)}>
          <Plus size={16} /> Add phone
        </button>
      </header>

      {error && (
        <div className="mb-4 rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {phones.length === 0 ? (
        <EmptyState onAdd={() => setShowAdd(true)} />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {phones.map((p) => (
            <PhoneTile key={p.id} phone={p} onChange={refresh} />
          ))}
        </div>
      )}

      {showAdd && (
        <AddPhoneModal
          onClose={() => setShowAdd(false)}
          onCreated={() => {
            setShowAdd(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="card flex flex-col items-center justify-center gap-3 p-16 text-center">
      <div className="text-lg font-medium text-ink-100">No phones yet</div>
      <div className="max-w-sm text-sm text-ink-400">
        Each phone you add becomes its own LDPlayer instance with its own proxy, locale, timezone, and GPS. Import a proxy list first (Proxies → Import), then click Add phone.
      </div>
      <button className="btn-primary mt-2" onClick={onAdd}>
        <Plus size={16} /> Add your first phone
      </button>
    </div>
  );
}

function statusColor(s: Phone["status"]): string {
  switch (s) {
    case "running":
      return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
    case "starting":
    case "stopping":
      return "bg-amber-500/20 text-amber-300 border-amber-500/30";
    case "crashed":
      return "bg-red-500/20 text-red-300 border-red-500/30";
    default:
      return "bg-ink-800 text-ink-300 border-ink-700";
  }
}

function PhoneTile({ phone, onChange }: { phone: Phone; onChange: () => void }) {
  const [busy, setBusy] = useState<"start" | "stop" | "wipe" | "delete" | null>(null);

  async function act(kind: "start" | "stop" | "wipe" | "delete") {
    if (kind === "wipe" && !window.confirm(
      `Wipe ${phone.name}? Data + cache will be erased and the phone will be re-cloned from the ${phone.show_setup_wizard ? "factory" : "configured"} template (~20s).`,
    )) return;
    if (kind === "delete" && !window.confirm(`Delete ${phone.name} and free its proxy?`)) return;
    setBusy(kind);
    try {
      if (kind === "start") await api.startPhone(phone.id);
      if (kind === "stop") await api.stopPhone(phone.id);
      if (kind === "wipe") await api.wipePhone(phone.id);
      if (kind === "delete") await api.deletePhone(phone.id);
      onChange();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card flex flex-col gap-3 p-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="font-medium text-ink-50">{phone.name}</div>
          <div className="text-xs text-ink-400">
            {phone.device_profile} · Android {phone.android_version} · {phone.resolution}
          </div>
        </div>
        <span className={clsx("chip border", statusColor(phone.status))}>
          {phone.status}
        </span>
      </div>

      <div className="flex aspect-[9/16] items-center justify-center rounded-md border border-ink-800 bg-ink-950 text-xs text-ink-600">
        {phone.status === "running" ? (
          <span>live preview lands next</span>
        ) : (
          <span>{phone.status === "crashed" ? phone.last_error ?? "crashed" : "idle"}</span>
        )}
      </div>

      <div className="space-y-1 text-xs text-ink-400">
        <div className="flex items-center gap-1">
          <span className="text-ink-500">boot:</span>
          <span className="text-ink-200">
            {phone.show_setup_wizard ? "factory (setup wizard)" : "configured (skips wizard)"}
          </span>
        </div>
        {phone.proxy ? (
          <div className="flex items-center gap-1">
            <span className="text-ink-500">proxy:</span>
            <span className="font-mono text-ink-200">
              {phone.proxy.host}:{phone.proxy.port}
            </span>
            {phone.proxy.country && (
              <span className="chip">{phone.proxy.country}{phone.proxy.city ? ` · ${phone.proxy.city}` : ""}</span>
            )}
          </div>
        ) : (
          <div className="text-ink-500">no proxy</div>
        )}
        {(() => {
          const g = phone.geo_overrides as {
            country?: string; city?: string; locale?: string;
            timezone?: string; latitude?: number; longitude?: number;
          };
          if (!g || (!g.country && !g.locale)) return null;
          return (
            <>
              <div className="flex items-center gap-1">
                <span className="text-ink-500">spoofed:</span>
                <span className="text-ink-200">
                  {g.city ? `${g.city}, ` : ""}{g.country ?? "?"}
                </span>
                {g.locale && <span className="chip">{g.locale}</span>}
              </div>
              {g.timezone && (
                <div className="flex items-center gap-1">
                  <span className="text-ink-500">tz:</span>
                  <span className="text-ink-200">{g.timezone}</span>
                </div>
              )}
              {g.latitude !== undefined && g.longitude !== undefined && (
                <div className="flex items-center gap-1">
                  <span className="text-ink-500">gps:</span>
                  <span className="font-mono text-ink-200">
                    {Number(g.latitude).toFixed(3)}, {Number(g.longitude).toFixed(3)}
                  </span>
                </div>
              )}
            </>
          );
        })()}
        <div className="flex items-center gap-1">
          <span className="text-ink-500">cpu/ram:</span>
          <span className="text-ink-200">{phone.cpu} vCPU · {phone.ram_mb} MB</span>
        </div>
      </div>

      <div className="flex items-center gap-2 pt-1">
        {phone.status === "running" || phone.status === "starting" ? (
          <button className="btn-secondary" disabled={busy !== null} onClick={() => act("stop")}>
            <Square size={14} /> Stop
          </button>
        ) : (
          <button className="btn-secondary" disabled={busy !== null} onClick={() => act("start")}>
            <Play size={14} /> Start
          </button>
        )}
        <button
          className="btn-ghost"
          title="Wipe + re-clone from template"
          disabled={busy !== null}
          onClick={() => act("wipe")}
        >
          <RotateCcw size={14} />
        </button>
        <button
          className="btn-ghost ml-auto text-red-300 hover:bg-red-500/10 hover:text-red-200"
          disabled={busy !== null}
          onClick={() => act("delete")}
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}
