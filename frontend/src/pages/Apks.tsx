import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Download, ExternalLink, Package, Trash2, Upload } from "lucide-react";
import { api } from "../lib/api";
import type { Apk, Phone } from "../lib/types";

interface CatalogEntry {
  slug: string;
  display_name: string;
  package: string;
  category: string;
  description: string;
  source_url: string;
  homepage_url: string;
  installed: boolean;
}

export default function Apks() {
  const [apks, setApks] = useState<Apk[]>([]);
  const [phones, setPhones] = useState<Phone[]>([]);
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [showCatalog, setShowCatalog] = useState(false);
  const [fetchingSlug, setFetchingSlug] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  async function refresh() {
    try {
      const [a, p, c] = await Promise.all([
        api.listApks(),
        api.listPhones(),
        api.listCatalog(),
      ]);
      setApks(a);
      setPhones(p);
      setCatalog(c);
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

  async function fetchFromCatalog(entry: CatalogEntry) {
    const url = window.prompt(
      `Paste a direct-download .apk URL for ${entry.display_name}.\n\n` +
        `Tip: open the "Source page" link and grab the current version's direct APK download URL ` +
        `from APKMirror / APKPure / your own mirror.\n\n` +
        `DroidFarm will download it to the library and tag it with package ${entry.package}.`,
      "",
    );
    if (!url) return;
    setFetchingSlug(entry.slug);
    setFlash(null);
    try {
      await api.fetchCatalogApk(entry.slug, url.trim());
      setFlash(`added ${entry.display_name} to library`);
      refresh();
    } catch (ex) {
      setError(String(ex));
    } finally {
      setFetchingSlug(null);
      setTimeout(() => setFlash(null), 4000);
    }
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
        <div className="flex items-center gap-2">
          <button
            className="btn-secondary"
            onClick={() => setShowCatalog((v) => !v)}
          >
            <Package size={16} /> {showCatalog ? "Hide catalog" : "Add from catalog"}
          </button>
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
        </div>
      </header>

      {showCatalog && (
        <div className="card mb-4 p-5">
          <div className="mb-3 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-ink-50">Common apps catalog</h2>
              <p className="text-sm text-ink-400">
                Pre-load TikTok / Instagram / YouTube / Facebook / etc. Click
                <span className="mx-1 inline-flex items-center gap-0.5 rounded bg-ink-800 px-1.5 py-0.5 text-xs text-ink-200">
                  <ExternalLink size={10} /> Source page
                </span>
                to grab the direct-download URL (APKMirror is the usual one),
                then paste it into{" "}
                <span className="mx-1 inline-flex items-center gap-0.5 rounded bg-ink-800 px-1.5 py-0.5 text-xs text-ink-200">
                  <Download size={10} /> Fetch
                </span>
                — DroidFarm grabs the APK into the library.
              </p>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {catalog.map((entry) => (
              <div
                key={entry.slug}
                className="flex items-start justify-between gap-3 rounded-lg border border-ink-800 bg-ink-900/50 p-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-ink-100">
                      {entry.display_name}
                    </span>
                    {entry.installed && (
                      <span
                        className="chip flex items-center gap-1 text-emerald-300"
                        title="already in library"
                      >
                        <CheckCircle2 size={10} /> in library
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 text-xs text-ink-500">
                    {entry.category} · {entry.package}
                  </div>
                  <div className="mt-1 line-clamp-2 text-xs text-ink-400">
                    {entry.description}
                  </div>
                </div>
                <div className="flex flex-col gap-1">
                  <a
                    className="btn-ghost text-xs"
                    href={entry.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="open APKMirror page"
                  >
                    <ExternalLink size={12} /> Source
                  </a>
                  <button
                    className="btn-secondary text-xs"
                    disabled={fetchingSlug === entry.slug}
                    onClick={() => fetchFromCatalog(entry)}
                  >
                    <Download size={12} />
                    {fetchingSlug === entry.slug ? "…" : "Fetch"}
                  </button>
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-ink-500">
            Why no one-click downloads? Google Play APKs aren't ours to redistribute.
            Opening the source page in your browser and pasting the direct URL keeps
            this clean + always serves you the latest version.
          </p>
        </div>
      )}

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
