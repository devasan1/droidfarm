import { useEffect, useRef, useState } from "react";
import { Download, Upload } from "lucide-react";
import { api } from "../lib/api";

/**
 * Export / import the whole farm as a zip. This is the easiest way
 * to move from a GCP VM to a local machine (or to snapshot the farm
 * before a risky change).
 */
export default function Settings() {
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [includeVm, setIncludeVm] = useState(false);
  const [merge, setMerge] = useState(true);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [health, setHealth] = useState<{
    mock_driver: boolean;
    ldconsole: string | null;
    adb: string;
    platform: string;
  } | null>(null);
  useEffect(() => {
    api
      .health()
      .then((h) =>
        setHealth({
          mock_driver: h.mock_driver,
          ldconsole: h.ldconsole,
          adb: (h as unknown as { adb?: string }).adb ?? "",
          platform: (h as unknown as { platform?: string }).platform ?? "",
        }),
      )
      .catch(() => {
        /* ignore */
      });
  }, []);

  async function onExport() {
    setMsg(null);
    setErr(null);
    const url = `/api/farm/export${includeVm ? "?include_vm=1" : ""}`;
    // Let the browser handle the download directly.
    window.location.href = url;
  }

  async function onImport(file: File) {
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch(`/api/farm/import?merge=${merge ? "true" : "false"}`, {
        method: "POST",
        body: form,
      });
      if (!r.ok) {
        throw new Error(await r.text());
      }
      const body = await r.json();
      setMsg(
        `imported: +${body.created.phones} phones · +${body.created.proxies} proxies · +${body.created.apks} apks (${body.apk_files_restored} apk files)`,
      );
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="p-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-ink-50">Settings</h1>
        <p className="text-sm text-ink-400">
          Back up and restore the whole farm, or move it to another machine.
        </p>
      </header>

      {msg && (
        <div className="mb-4 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">
          {msg}
        </div>
      )}
      {err && (
        <div className="mb-4 rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {err}
        </div>
      )}

      {health && (
        <div className="card mb-4 p-5">
          <h2 className="mb-2 text-lg font-semibold text-ink-50">Driver</h2>
          {health.mock_driver ? (
            <>
              <p className="mb-2 text-sm text-amber-300">
                Currently using the <strong>mock driver</strong> — phones are
                virtual stubs and don't surface adb, screenshots, or input.
              </p>
              <p className="mb-3 text-sm text-ink-400">
                To drive real Android emulators, install LDPlayer 9 from{" "}
                <a
                  href="https://www.ldplayer.net/"
                  target="_blank"
                  rel="noreferrer"
                  className="text-emerald-400 underline"
                >
                  ldplayer.net
                </a>{" "}
                and relaunch DroidFarm. We auto-detect <code>ldconsole.exe</code>{" "}
                under <code>C:\</code>, <code>D:\</code>, <code>E:\</code> on
                start. If you've installed it somewhere else, set the env var{" "}
                <code>DROIDFARM_LDCONSOLE</code> to the full path before
                launching.
              </p>
            </>
          ) : (
            <p className="mb-2 text-sm text-emerald-300">
              LDPlayer driver active.
            </p>
          )}
          <div className="grid grid-cols-[120px_1fr] gap-y-1 text-xs text-ink-400">
            <div>ldconsole</div>
            <div className="font-mono text-ink-200">
              {health.ldconsole ?? "(not found)"}
            </div>
            <div>adb</div>
            <div className="font-mono text-ink-200">{health.adb}</div>
            <div>platform</div>
            <div className="font-mono text-ink-200">{health.platform}</div>
          </div>
        </div>
      )}

      <div className="card mb-4 p-5">
        <h2 className="mb-2 text-lg font-semibold text-ink-50">Export farm</h2>
        <p className="mb-3 text-sm text-ink-400">
          Download a zip containing phone / proxy / APK definitions + the APK
          library bytes. Importing on another DroidFarm install recreates
          everything. Phones will boot clean (no inside-phone state) unless you
          include VM disks below.
        </p>
        <label className="mb-3 flex items-center gap-2 text-sm text-ink-300">
          <input
            type="checkbox"
            checked={includeVm}
            onChange={(e) => setIncludeVm(e.target.checked)}
          />
          also include LDPlayer VM snapshots (Windows only — bigger zip, but
          preserves installed apps / cookies / logins per phone)
        </label>
        <button className="btn-primary" onClick={onExport}>
          <Download size={16} /> Export farm zip
        </button>
      </div>

      <div className="card p-5">
        <h2 className="mb-2 text-lg font-semibold text-ink-50">Import farm</h2>
        <p className="mb-3 text-sm text-ink-400">
          Restore from a DroidFarm zip. By default, only missing rows are
          added — your existing phones / proxies / APKs are never
          overwritten.
        </p>
        <label className="mb-3 flex items-center gap-2 text-sm text-ink-300">
          <input
            type="checkbox"
            checked={merge}
            onChange={(e) => setMerge(e.target.checked)}
          />
          merge into existing farm (unchecking wipes existing phones / proxies
          / apks first — irreversible)
        </label>
        <label className="btn-primary cursor-pointer">
          <Upload size={16} /> {busy ? "importing…" : "Pick zip file…"}
          <input
            ref={fileRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onImport(f);
            }}
            disabled={busy}
          />
        </label>
      </div>
    </div>
  );
}
