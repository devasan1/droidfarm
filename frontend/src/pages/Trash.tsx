import { useCallback, useEffect, useState } from "react";
import { Trash2, RotateCcw, AlertTriangle } from "lucide-react";
import { api } from "../lib/api";
import type { Phone } from "../lib/types";
import ConfirmModal from "../components/ConfirmModal";

export default function Trash() {
  const [phones, setPhones] = useState<Phone[]>([]);
  const [loading, setLoading] = useState(true);
  const [purging, setPurging] = useState<Phone | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api
      .listTrashedPhones()
      .then(setPhones)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function restore(p: Phone) {
    try {
      await api.restorePhone(p.id);
      refresh();
    } catch (e) {
      setErr(String(e));
    }
  }

  async function purge() {
    if (!purging) return;
    try {
      await api.purgePhone(purging.id);
      setPurging(null);
      refresh();
    } catch (e) {
      setErr(String(e));
    }
  }

  return (
    <div className="p-6">
      <header className="mb-4 flex items-center gap-3">
        <Trash2 size={20} className="text-ink-300" />
        <div>
          <h1 className="text-xl font-semibold text-ink-50">Trash</h1>
          <p className="text-xs text-ink-400">
            Phones here still have all their data and their LDPlayer instance
            on disk. <b>Restore</b> brings them back intact. <b>Purge</b>{" "}
            permanently destroys the instance and cannot be undone.
          </p>
        </div>
      </header>

      {err && (
        <div className="mb-3 rounded-md border border-red-900/40 bg-red-950/30 px-3 py-2 text-sm text-red-200">
          {err}
        </div>
      )}

      {loading ? (
        <div className="text-sm text-ink-400">loading…</div>
      ) : phones.length === 0 ? (
        <div className="card p-8 text-center text-sm text-ink-400">
          Trash is empty. Deleted phones land here so you can restore them by
          name if you change your mind.
        </div>
      ) : (
        <div className="card divide-y divide-ink-800">
          {phones.map((p) => (
            <div key={p.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <div className="font-mono text-ink-100">{p.name}</div>
                <div className="text-xs text-ink-400">
                  {p.resolution} · {p.ram_mb} MB · trashed{" "}
                  {p.deleted_at ? new Date(p.deleted_at).toLocaleString() : "—"}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => restore(p)}
                  title="Bring this phone back with its data intact"
                >
                  <RotateCcw size={14} />
                  Restore
                </button>
                <button
                  type="button"
                  className="btn-danger"
                  onClick={() => setPurging(p)}
                  title="Permanently destroy the LDPlayer instance"
                >
                  <AlertTriangle size={14} />
                  Purge
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmModal
        open={purging !== null}
        title={`Permanently delete ${purging?.name ?? ""}?`}
        danger
        typeToConfirm={purging?.name}
        confirmLabel="Permanently delete"
        onClose={() => setPurging(null)}
        onConfirm={purge}
        message={
          <>
            <p>
              This <b>cannot be undone</b>. The LDPlayer instance, all
              installed apps, cache, cookies, and login sessions on this
              phone will be destroyed.
            </p>
            <p className="text-ink-400">
              If you only want to stop using the phone, use{" "}
              <b>Restore</b> and then Stop instead — the data stays safe.
            </p>
          </>
        }
      />
    </div>
  );
}
