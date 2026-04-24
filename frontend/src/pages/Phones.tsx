import { useEffect, useState } from "react";
import { Play, Plus, RotateCcw, Square, Trash2, Timer, Maximize2 } from "lucide-react";
import clsx from "clsx";
import { api } from "../lib/api";
import type { Phone } from "../lib/types";
import AddPhoneModal from "../components/AddPhoneModal";
import ConfirmModal from "../components/ConfirmModal";
import PhoneViewer from "../components/PhoneViewer";

export default function Phones() {
  const [phones, setPhones] = useState<Phone[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

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

  // Drop selected ids that no longer refer to live phones.
  useEffect(() => {
    setSelected((prev) => {
      const live = new Set(phones.map((p) => p.id));
      let changed = false;
      const next = new Set<number>();
      for (const id of prev) {
        if (live.has(id)) next.add(id);
        else changed = true;
      }
      return changed ? next : prev;
    });
  }, [phones]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function selectAll() {
    setSelected(new Set(phones.map((p) => p.id)));
  }
  function clearSel() {
    setSelected(new Set());
  }

  async function bulk(
    fn: (id: number) => Promise<unknown>,
    label: string,
  ) {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    setBulkBusy(true);
    setError(null);
    const errors: string[] = [];
    for (const id of ids) {
      try {
        await fn(id);
      } catch (e) {
        errors.push(`${id}: ${String(e)}`);
      }
    }
    setBulkBusy(false);
    if (errors.length) setError(`${label} partial failure: ${errors.join("; ")}`);
    refresh();
  }

  return (
    <div className="p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink-50">Phones</h1>
          <p className="text-sm text-ink-400">
            {phones.length} phone{phones.length === 1 ? "" : "s"} · {phones.filter((p) => p.status === "running").length} running
            {selected.size > 0 && (
              <span className="ml-2 text-indigo-300">· {selected.size} selected</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {phones.length > 0 && (
            <>
              <button className="btn-ghost" onClick={selectAll} title="Select all">
                Select all
              </button>
              {selected.size > 0 && (
                <button className="btn-ghost" onClick={clearSel}>Clear</button>
              )}
            </>
          )}
          <button className="btn-primary" onClick={() => setShowAdd(true)}>
            <Plus size={16} /> Add phone
          </button>
        </div>
      </header>

      {selected.size > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-md border border-indigo-500/30 bg-indigo-500/10 p-3 text-sm text-ink-100">
          <span className="text-ink-200">
            {selected.size} phone{selected.size === 1 ? "" : "s"} selected —
          </span>
          <button
            className="btn-secondary"
            disabled={bulkBusy}
            onClick={() => bulk(api.startPhone, "start")}
          >
            <Play size={14} /> Start
          </button>
          <button
            className="btn-secondary"
            disabled={bulkBusy}
            onClick={() => bulk(api.stopPhone, "stop")}
          >
            <Square size={14} /> Stop
          </button>
          <button
            className="btn-secondary"
            disabled={bulkBusy}
            onClick={() => {
              if (
                window.confirm(
                  `Wipe ${selected.size} phone${
                    selected.size === 1 ? "" : "s"
                  }? Each will be re-cloned from its template (installed apps + data erased). Proxies + geo + fingerprint preserved.`,
                )
              )
                bulk(api.wipePhone, "wipe");
            }}
          >
            <RotateCcw size={14} /> Wipe
          </button>
          <button
            className="btn-secondary"
            disabled={bulkBusy}
            onClick={() => {
              if (
                window.confirm(
                  `Move ${selected.size} phone${
                    selected.size === 1 ? "" : "s"
                  } to Trash? Data preserved; can be restored from the Trash page.`,
                )
              )
                bulk(api.deletePhone, "delete");
            }}
          >
            <Trash2 size={14} /> Trash
          </button>
          {bulkBusy && <span className="text-xs text-ink-400">working…</span>}
        </div>
      )}

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
            <PhoneTile
              key={p.id}
              phone={p}
              onChange={refresh}
              selected={selected.has(p.id)}
              onToggleSelect={() => toggle(p.id)}
            />
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

function PhoneTile({
  phone,
  onChange,
  selected,
  onToggleSelect,
}: {
  phone: Phone;
  onChange: () => void;
  selected?: boolean;
  onToggleSelect?: () => void;
}) {
  const [busy, setBusy] = useState<"start" | "stop" | "wipe" | "delete" | "install" | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [installMsg, setInstallMsg] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<"wipe" | "delete" | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [tick, setTick] = useState(0);
  const uptime = useUptime(phone.status === "running" ? phone.last_started_at : null);

  // Poll a new thumbnail every ~2s while the phone is running.
  useEffect(() => {
    if (phone.status !== "running") return;
    const t = setInterval(() => setTick((x) => x + 1), 2000);
    return () => clearInterval(t);
  }, [phone.status]);

  async function uploadAndInstall(files: FileList | File[]) {
    const list = Array.from(files).filter((f) => f.name.toLowerCase().endsWith(".apk"));
    if (list.length === 0) return;
    if (phone.status !== "running") {
      setInstallMsg("phone not running — start it first");
      return;
    }
    setBusy("install");
    try {
      for (const f of list) {
        setInstallMsg(`uploading ${f.name}…`);
        const apk = await api.uploadApk(f);
        setInstallMsg(`installing ${f.name}…`);
        const r = await api.installApkOnPhone(phone.id, apk.id);
        if (!r.ok) {
          setInstallMsg(`failed: ${r.error ?? "unknown"}`);
          break;
        }
        setInstallMsg(`installed ${f.name}`);
      }
    } catch (e) {
      setInstallMsg(String(e));
    } finally {
      setBusy(null);
      setTimeout(() => setInstallMsg(null), 4000);
    }
  }

  async function act(kind: "start" | "stop" | "wipe" | "delete") {
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
    <div
      className={clsx(
        "card relative flex flex-col gap-3 p-4 transition-colors",
        dragOver && "border-emerald-500 ring-2 ring-emerald-500/40",
        selected && "border-indigo-500 ring-2 ring-indigo-500/40",
      )}
      onDragOver={(e) => {
        if (Array.from(e.dataTransfer.items).some((i) => i.kind === "file")) {
          e.preventDefault();
          setDragOver(true);
        }
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        uploadAndInstall(e.dataTransfer.files);
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-start gap-2">
          {onToggleSelect && (
            <input
              type="checkbox"
              checked={!!selected}
              onChange={onToggleSelect}
              className="mt-1 h-4 w-4 cursor-pointer accent-indigo-500"
              title="Select phone for bulk actions"
              aria-label={`Select ${phone.name}`}
            />
          )}
          <div>
            <div className="font-medium text-ink-50">{phone.name}</div>
            <div className="text-xs text-ink-400">
              {phone.device_profile} · Android {phone.android_version} · {phone.resolution}
            </div>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={clsx("chip border", statusColor(phone.status))}>
            {phone.status}
          </span>
          {uptime && (
            <span className="flex items-center gap-1 text-[11px] text-ink-400">
              <Timer size={11} />
              up {uptime}
            </span>
          )}
        </div>
      </div>
      {installMsg && (
        <div className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-200">
          {installMsg}
        </div>
      )}

      <div
        className={clsx(
          "group relative flex aspect-[9/16] items-center justify-center overflow-hidden rounded-md border border-ink-800 bg-ink-950 text-xs text-ink-600",
          phone.status === "running" && "cursor-zoom-in",
        )}
        onClick={() => phone.status === "running" && setExpanded(true)}
      >
        {phone.status === "running" ? (
          <>
            <img
              src={api.screenshotUrl(phone.id, tick)}
              alt={`${phone.name} preview`}
              className="h-full w-full object-fill"
              draggable={false}
              onError={() => {
                /* keep prior frame on transient failures */
              }}
            />
            <button
              type="button"
              className="absolute right-2 top-2 rounded-md bg-ink-900/80 p-1.5 text-ink-200 opacity-0 backdrop-blur hover:bg-ink-800 group-hover:opacity-100"
              title="Expand (interactive view)"
              onClick={(e) => {
                e.stopPropagation();
                setExpanded(true);
              }}
            >
              <Maximize2 size={14} />
            </button>
          </>
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
        {(() => {
          const fp = phone.fingerprint as {
            manufacturer?: string; model?: string; imei?: string;
            android_id?: string;
          };
          if (!fp || !fp.model) return null;
          const imeiShort = fp.imei ? `${fp.imei.slice(0, 4)}…${fp.imei.slice(-3)}` : "—";
          return (
            <div
              className="flex items-center gap-1"
              title={`IMEI ${fp.imei ?? "?"} · Android ID ${fp.android_id ?? "?"}`}
            >
              <span className="text-ink-500">device:</span>
              <span className="text-ink-200">
                {fp.manufacturer} {fp.model}
              </span>
              <span className="chip">IMEI {imeiShort}</span>
            </div>
          );
        })()}
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
          onClick={() => setConfirm("wipe")}
        >
          <RotateCcw size={14} />
        </button>
        <button
          className="btn-ghost ml-auto text-red-300 hover:bg-red-500/10 hover:text-red-200"
          disabled={busy !== null}
          onClick={() => setConfirm("delete")}
          title="Move to Trash (reversible)"
        >
          <Trash2 size={14} />
        </button>
      </div>

      {expanded && (
        <PhoneViewer phone={phone} onClose={() => setExpanded(false)} />
      )}

      <ConfirmModal
        open={confirm === "wipe"}
        title={`Wipe ${phone.name}?`}
        confirmLabel="Wipe + re-clone"
        onClose={() => setConfirm(null)}
        onConfirm={async () => {
          setConfirm(null);
          await act("wipe");
        }}
        message={
          <>
            <p>
              All data, cache, cookies, and installed apps on this phone
              will be erased.
            </p>
            <p className="text-ink-400">
              The phone will then be re-cloned from the{" "}
              <b>
                {phone.show_setup_wizard ? "factory" : "configured"}
              </b>{" "}
              template (~20s). Proxy and geo overrides are kept.
            </p>
          </>
        }
      />

      <ConfirmModal
        open={confirm === "delete"}
        title={`Move ${phone.name} to Trash?`}
        confirmLabel="Move to Trash"
        onClose={() => setConfirm(null)}
        onConfirm={async () => {
          setConfirm(null);
          await act("delete");
        }}
        message={
          <>
            <p>
              You are trying to delete <b>{phone.name}</b>. The phone will
              stop and be hidden from the grid, but its data, installed
              apps, and LDPlayer instance are preserved.
            </p>
            <p className="text-ink-400">
              You can <b>Restore</b> it anytime from the Trash page.
              Permanent deletion (purge) is a separate action there.
            </p>
          </>
        }
      />
    </div>
  );
}

function useUptime(startedAt: string | null): string | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!startedAt) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [startedAt]);
  if (!startedAt) return null;
  const ms = now - new Date(startedAt).getTime();
  if (ms < 0 || !Number.isFinite(ms)) return null;
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}
