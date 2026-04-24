import { useEffect, useState } from "react";
import { Plus, Trash2, Upload } from "lucide-react";
import { api } from "../lib/api";
import type { Proxy } from "../lib/types";

export default function Proxies() {
  const [proxies, setProxies] = useState<Proxy[]>([]);
  const [importing, setImporting] = useState(false);
  const [importText, setImportText] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setProxies(await api.listProxies());
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  async function doImport() {
    setError(null);
    setFeedback(null);
    try {
      const r = await api.importProxies(importText);
      setFeedback(`Imported ${r.imported} · skipped ${r.skipped}`);
      setImportText("");
      setImporting(false);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function remove(p: Proxy) {
    if (p.assigned_to_phone_id) {
      alert(`Proxy is in use by ${p.assigned_to_phone_name}; stop the phone first.`);
      return;
    }
    if (!window.confirm(`Delete ${p.label || `${p.host}:${p.port}`}?`)) return;
    try {
      await api.deleteProxy(p.id);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  const available = proxies.filter((p) => p.assigned_to_phone_id === null).length;

  return (
    <div className="p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink-50">Proxies</h1>
          <p className="text-sm text-ink-400">
            {proxies.length} total · {available} available · {proxies.length - available} in use
          </p>
        </div>
        <button className="btn-primary" onClick={() => setImporting(true)}>
          <Upload size={16} /> Import list
        </button>
      </header>

      {feedback && (
        <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-sm text-emerald-300">
          {feedback}
        </div>
      )}
      {error && (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {proxies.length === 0 ? (
        <div className="card p-16 text-center">
          <div className="text-lg font-medium text-ink-100">No proxies yet</div>
          <div className="mx-auto mt-1 max-w-md text-sm text-ink-400">
            Paste your proxy list — one per line — and click Import. Each phone you add needs its own proxy so their traffic looks like it comes from different devices.
          </div>
          <button className="btn-primary mt-4" onClick={() => setImporting(true)}>
            <Plus size={16} /> Import proxies
          </button>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-ink-800 text-left text-xs uppercase tracking-wide text-ink-400">
              <tr>
                <th className="px-4 py-2">Label</th>
                <th className="px-4 py-2">Scheme</th>
                <th className="px-4 py-2">Host:Port</th>
                <th className="px-4 py-2">Country / City</th>
                <th className="px-4 py-2">Assigned to</th>
                <th className="px-4 py-2 text-right" />
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {proxies.map((p) => (
                <tr key={p.id}>
                  <td className="px-4 py-2 text-ink-100">{p.label || "—"}</td>
                  <td className="px-4 py-2 text-ink-300">{p.scheme}</td>
                  <td className="px-4 py-2 font-mono text-xs text-ink-300">
                    {p.host}:{p.port}
                  </td>
                  <td className="px-4 py-2 text-ink-300">
                    {p.country ?? "—"}
                    {p.city ? ` · ${p.city}` : ""}
                  </td>
                  <td className="px-4 py-2 text-ink-300">
                    {p.assigned_to_phone_name ?? (
                      <span className="text-ink-500">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      className="btn-ghost text-red-300 hover:bg-red-500/10"
                      onClick={() => remove(p)}
                      disabled={p.assigned_to_phone_id !== null}
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

      {importing && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => setImporting(false)}
        >
          <div className="card w-full max-w-xl" onClick={(e) => e.stopPropagation()}>
            <header className="border-b border-ink-800 px-5 py-3 text-lg font-medium text-ink-50">
              Import proxies
            </header>
            <div className="space-y-3 px-5 py-4">
              <p className="text-sm text-ink-400">
                Paste one proxy per line. Supported formats:
                <code className="mx-1 text-ink-200">user:pass@host:port</code>,
                <code className="mx-1 text-ink-200">host:port:user:pass</code>,
                <code className="mx-1 text-ink-200">host:port</code>,
                <code className="mx-1 text-ink-200">socks5://user:pass@host:port</code>.
                Blank lines and <code>#</code> comments are skipped.
              </p>
              <textarea
                className="input min-h-[220px] font-mono text-xs"
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
                placeholder={`user:pass@proxy1.example.com:8080\nsocks5://user:pass@proxy2.example.com:1080`}
              />
            </div>
            <footer className="flex items-center justify-end gap-2 border-t border-ink-800 px-5 py-3">
              <button className="btn-secondary" onClick={() => setImporting(false)}>
                Cancel
              </button>
              <button className="btn-primary" onClick={doImport} disabled={!importText.trim()}>
                Import
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}
