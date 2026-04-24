import { useEffect, useRef, useState } from "react";
import { Trash2, Upload } from "lucide-react";
import { api } from "../lib/api";
import type { Apk } from "../lib/types";

export default function Apks() {
  const [apks, setApks] = useState<Apk[]>([]);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function refresh() {
    try {
      setApks(await api.listApks());
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, []);

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
                    <button
                      className="btn-ghost text-red-300 hover:bg-red-500/10"
                      onClick={() => remove(a)}
                    >
                      <Trash2 size={14} />
                    </button>
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
