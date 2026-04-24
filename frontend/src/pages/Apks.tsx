import { useEffect, useRef, useState } from "react";
import { Download, Trash2, Upload } from "lucide-react";
import { api } from "../lib/api";
import type { Apk, Phone } from "../lib/types";

export default function Apks() {
  const [apks, setApks] = useState<Apk[]>([]);
  const [phones, setPhones] = useState<Phone[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function refresh() {
    try {
      const [a, p] = await Promise.all([api.listApks(), api.listPhones()]);
      setApks(a);
      setPhones(p);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  async function installOn(apkId: number, phoneId: number) {
    setFlash(null);
    try {
      const r = await api.installApkOnPhone(phoneId, apkId);
      setFlash(r.ok ? `installed on phone ${phoneId}` : `failed: ${r.error ?? "unknown"}`);
    } catch (e) {
      setFlash(String(e));
    } finally {
      setTimeout(() => setFlash(null), 4000);
    }
  }

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      await api.uploadApk(f);
      refresh();
    } catch (ex) {
      setError(String(ex));
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function onDrop(e: React.DragEvent) {
    e.preventDefault();
    for (const f of Array.from(e.dataTransfer.files)) {
      if (!f.name.toLowerCase().endsWith(".apk")) continue;
      try {
        await api.uploadApk(f);
      } catch (ex) {
        setError(String(ex));
      }
    }
    refresh();
  }

  async function remove(a: Apk) {
    if (!window.confirm(`Delete ${a.filename}?`)) return;
    try {
      await api.deleteApk(a.id);
      refresh();
    } catch (ex) {
      setError(String(ex));
    }
  }

  return (
    <div className="p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink-50">APK library</h1>
          <p className="text-sm text-ink-400">
            Drop APKs here once; install them onto any phone with one click.
          </p>
        </div>
        <label className="btn-primary cursor-pointer">
          <Upload size={16} /> Upload APK
          <input
            ref={fileRef}
            type="file"
            accept=".apk"
            className="hidden"
            onChange={onPick}
          />
        </label>
      </header>

      {error && (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-300">
          {error}
        </div>
      )}
      {flash && (
        <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-sm text-emerald-200">
          {flash}
        </div>
      )}

      <div
        className="card p-6"
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
      >
        {apks.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-12 text-center text-ink-400">
            <Upload size={28} className="text-ink-600" />
            <div>Drop .apk files anywhere on this card</div>
            <div className="text-xs text-ink-500">or click "Upload APK" above</div>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-ink-400">
              <tr>
                <th className="px-2 py-2">Filename</th>
                <th className="px-2 py-2">Size</th>
                <th className="px-2 py-2">Added</th>
                <th className="px-2 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {apks.map((a) => (
                <tr key={a.id}>
                  <td className="px-2 py-2 text-ink-100">{a.filename}</td>
                  <td className="px-2 py-2 text-ink-300">
                    {(a.size_bytes / (1024 * 1024)).toFixed(1)} MB
                  </td>
                  <td className="px-2 py-2 text-ink-300">
                    {new Date(a.added_at).toLocaleString()}
                  </td>
                  <td className="px-2 py-2 text-right">
                    <div className="inline-flex items-center gap-1">
                      <select
                        className="input py-1 text-xs"
                        defaultValue=""
                        onChange={(e) => {
                          const id = Number(e.target.value);
                          if (id) installOn(a.id, id);
                          e.currentTarget.value = "";
                        }}
                      >
                        <option value="" disabled>
                          <Download size={12} /> Install to…
                        </option>
                        {phones
                          .filter((p) => p.status === "running")
                          .map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.name}
                            </option>
                          ))}
                        {phones.filter((p) => p.status === "running").length === 0 && (
                          <option disabled>no running phones</option>
                        )}
                      </select>
                      <button
                        className="btn-ghost text-red-300 hover:bg-red-500/10"
                        onClick={() => remove(a)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
