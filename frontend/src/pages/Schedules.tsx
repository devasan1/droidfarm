import { useEffect, useMemo, useState } from "react";
import { Clock, Play, Plus, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import type { Phone, Schedule, ScheduleActionSpec } from "../lib/types";

const CRON_PRESETS: Array<{ label: string; cron: string }> = [
  { label: "Every minute (dev)", cron: "* * * * *" },
  { label: "Every 5 min", cron: "*/5 * * * *" },
  { label: "Every 30 min", cron: "*/30 * * * *" },
  { label: "Hourly (on :00)", cron: "0 * * * *" },
  { label: "Every day 07:00 UTC", cron: "0 7 * * *" },
  { label: "Every day 00:00 UTC", cron: "0 0 * * *" },
  { label: "Mon–Fri 09:00 UTC", cron: "0 9 * * 1-5" },
];

export default function Schedules() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [actions, setActions] = useState<ScheduleActionSpec[]>([]);
  const [phones, setPhones] = useState<Phone[]>([]);
  const [showNew, setShowNew] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function refresh() {
    try {
      const [s, a, p] = await Promise.all([
        api.listSchedules(),
        api.scheduleActions(),
        api.listPhones(),
      ]);
      setSchedules(s);
      setActions(a.actions);
      setPhones(p);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  async function toggleEnabled(s: Schedule) {
    try {
      await api.patchSchedule(s.id, { enabled: !s.enabled });
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function runNow(s: Schedule) {
    try {
      const r = await api.runScheduleNow(s.id);
      setInfo(`${s.name}: ${r.last_status}${r.last_error ? ` — ${r.last_error}` : ""}`);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function remove(s: Schedule) {
    if (!window.confirm(`Delete schedule "${s.name}"?`)) return;
    try {
      await api.deleteSchedule(s.id);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink-50">Schedules</h1>
          <p className="text-sm text-ink-400">
            Cron-style jobs. Times are UTC. {schedules.length} total.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowNew(true)}>
          <Plus size={16} /> New schedule
        </button>
      </header>

      {error && (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-300">
          {error}
        </div>
      )}
      {info && (
        <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-sm text-emerald-300">
          {info}
        </div>
      )}

      {schedules.length === 0 ? (
        <div className="card p-16 text-center">
          <Clock className="mx-auto text-ink-500" size={32} />
          <div className="mt-3 text-lg font-medium text-ink-100">No schedules yet</div>
          <div className="mx-auto mt-1 max-w-md text-sm text-ink-400">
            Create one to, e.g., start all phones every morning, rotate GPS every
            30 minutes, or launch TikTok at noon.
          </div>
          <button className="btn-primary mt-4" onClick={() => setShowNew(true)}>
            <Plus size={16} /> New schedule
          </button>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-ink-800 text-left text-xs uppercase tracking-wide text-ink-400">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Cron</th>
                <th className="px-4 py-2">Action</th>
                <th className="px-4 py-2">Targets</th>
                <th className="px-4 py-2">Next</th>
                <th className="px-4 py-2">Last</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2 text-right" />
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {schedules.map((s) => (
                <tr key={s.id}>
                  <td className="px-4 py-2 text-ink-100">{s.name}</td>
                  <td className="px-4 py-2 font-mono text-xs text-ink-300">{s.cron}</td>
                  <td className="px-4 py-2 text-ink-300">
                    {s.action}
                    {Object.keys(s.params).length > 0 && (
                      <div className="text-[11px] text-ink-500 font-mono">
                        {JSON.stringify(s.params)}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2 text-ink-300">
                    {s.target_phone_ids.length === 0
                      ? "(all live phones)"
                      : phones
                          .filter((p) => s.target_phone_ids.includes(p.id))
                          .map((p) => p.name)
                          .join(", ")}
                  </td>
                  <td className="px-4 py-2 text-[11px] text-ink-400">
                    {s.next_run_at ? new Date(s.next_run_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-2 text-[11px] text-ink-400">
                    {s.last_run_at ? new Date(s.last_run_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-2 text-[11px]">
                    {!s.enabled ? (
                      <span className="text-ink-500">disabled</span>
                    ) : s.last_status === "ok" ? (
                      <span className="text-emerald-400">ok</span>
                    ) : s.last_status === "error" ? (
                      <span className="text-red-400">{s.last_error?.slice(0, 60) || "err"}</span>
                    ) : (
                      <span className="text-ink-400">{s.last_status ?? "—"}</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <label className="mr-2 inline-flex cursor-pointer items-center gap-1 text-xs text-ink-300">
                      <input
                        type="checkbox"
                        checked={s.enabled}
                        onChange={() => toggleEnabled(s)}
                      />
                      on
                    </label>
                    <button
                      className="btn-ghost"
                      title="Run now (doesn't affect next scheduled run)"
                      onClick={() => runNow(s)}
                    >
                      <Play size={14} />
                    </button>
                    <button
                      className="btn-ghost text-red-300 hover:bg-red-500/10"
                      onClick={() => remove(s)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showNew && (
        <NewScheduleModal
          actions={actions}
          phones={phones}
          onClose={() => setShowNew(false)}
          onCreated={() => {
            setShowNew(false);
            refresh();
          }}
          onError={setError}
        />
      )}
    </div>
  );
}

function NewScheduleModal({
  actions,
  phones,
  onClose,
  onCreated,
  onError,
}: {
  actions: ScheduleActionSpec[];
  phones: Phone[];
  onClose: () => void;
  onCreated: () => void;
  onError: (e: string) => void;
}) {
  const [name, setName] = useState("");
  const [cron, setCron] = useState("0 7 * * *");
  const [action, setAction] = useState("start");
  const [targets, setTargets] = useState<Set<number>>(new Set());
  const [params, setParams] = useState<Record<string, string>>({});

  const spec = useMemo(
    () => actions.find((a) => a.name === action),
    [actions, action],
  );

  async function submit() {
    try {
      const p: Record<string, unknown> = {};
      for (const pspec of spec?.params ?? []) {
        const raw = params[pspec.name] ?? "";
        if (raw === "" && !pspec.required) continue;
        p[pspec.name] = pspec.type === "number" ? Number(raw) : raw;
      }
      await api.createSchedule({
        name,
        cron,
        action,
        target_phone_ids: Array.from(targets),
        params: p,
        enabled: true,
      });
      onCreated();
    } catch (e) {
      onError(String(e));
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div className="card w-full max-w-xl" onClick={(e) => e.stopPropagation()}>
        <header className="border-b border-ink-800 px-5 py-3 text-lg font-medium text-ink-50">
          New schedule
        </header>
        <div className="space-y-3 px-5 py-4">
          <div>
            <label className="text-xs text-ink-400">Name</label>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="daily-start"
            />
          </div>
          <div>
            <label className="text-xs text-ink-400">Cron (UTC)</label>
            <input
              className="input font-mono"
              value={cron}
              onChange={(e) => setCron(e.target.value)}
            />
            <div className="mt-1 flex flex-wrap gap-1">
              {CRON_PRESETS.map((p) => (
                <button
                  key={p.cron}
                  type="button"
                  className="rounded bg-ink-800 px-2 py-0.5 text-[11px] text-ink-300 hover:bg-ink-700"
                  onClick={() => setCron(p.cron)}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs text-ink-400">Action</label>
            <select
              className="input"
              value={action}
              onChange={(e) => {
                setAction(e.target.value);
                setParams({});
              }}
            >
              {actions.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          {(spec?.params ?? []).map((p) => (
            <div key={p.name}>
              <label className="text-xs text-ink-400">
                {p.name}
                {p.required ? " *" : ""}
              </label>
              <input
                className="input"
                value={params[p.name] ?? (p.default != null ? String(p.default) : "")}
                onChange={(e) =>
                  setParams({ ...params, [p.name]: e.target.value })
                }
                placeholder={p.type}
              />
            </div>
          ))}
          <div>
            <label className="text-xs text-ink-400">Target phones</label>
            <div className="mt-1 grid grid-cols-2 gap-1 rounded-md border border-ink-800 bg-ink-900 p-2 text-xs">
              <label className="col-span-2 flex items-center gap-2 text-ink-400">
                <input
                  type="checkbox"
                  checked={targets.size === 0}
                  onChange={() => setTargets(new Set())}
                />
                All live phones (runs on whatever exists at fire time)
              </label>
              {phones.map((ph) => (
                <label key={ph.id} className="flex items-center gap-2 text-ink-200">
                  <input
                    type="checkbox"
                    checked={targets.has(ph.id)}
                    onChange={() => {
                      const next = new Set(targets);
                      if (next.has(ph.id)) next.delete(ph.id);
                      else next.add(ph.id);
                      setTargets(next);
                    }}
                  />
                  {ph.name}
                </label>
              ))}
            </div>
          </div>
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-ink-800 px-5 py-3">
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn-primary"
            onClick={submit}
            disabled={!name.trim() || !cron.trim() || !action}
          >
            Create
          </button>
        </footer>
      </div>
    </div>
  );
}
