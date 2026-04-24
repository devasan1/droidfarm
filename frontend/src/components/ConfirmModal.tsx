import { useEffect, useState } from "react";
import { AlertTriangle, X } from "lucide-react";

interface Props {
  open: boolean;
  title: string;
  message: React.ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  danger?: boolean;
  /**
   * If provided, the confirm button is disabled until the user types this
   * exact string into an input. Use for irreversible actions (purge).
   */
  typeToConfirm?: string;
  onConfirm: () => void | Promise<void>;
  onClose: () => void;
}

export default function ConfirmModal({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel = "Cancel",
  danger = false,
  typeToConfirm,
  onConfirm,
  onClose,
}: Props) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setTyped("");
      setBusy(false);
    }
  }, [open]);

  if (!open) return null;
  const typedOk = !typeToConfirm || typed === typeToConfirm;

  async function go() {
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-md overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <header
          className={[
            "flex items-center justify-between border-b px-5 py-3",
            danger
              ? "border-red-900/40 bg-red-950/20"
              : "border-ink-800",
          ].join(" ")}
        >
          <div className="flex items-center gap-2">
            <AlertTriangle
              size={16}
              className={danger ? "text-red-400" : "text-amber-400"}
            />
            <h2 className="text-base font-medium text-ink-50">{title}</h2>
          </div>
          <button
            type="button"
            className="rounded-md p-1 text-ink-400 hover:bg-ink-800 hover:text-ink-100"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </header>
        <div className="space-y-3 px-5 py-4 text-sm text-ink-200">
          {message}
          {typeToConfirm && (
            <div>
              <div className="mb-1 text-xs text-ink-400">
                Type{" "}
                <span className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-ink-100">
                  {typeToConfirm}
                </span>{" "}
                to confirm:
              </div>
              <input
                autoFocus
                className="input"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder={typeToConfirm}
              />
            </div>
          )}
        </div>
        <footer className="flex items-center justify-end gap-2 border-t border-ink-800 bg-ink-900 px-5 py-3">
          <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={danger ? "btn-danger" : "btn-primary"}
            onClick={go}
            disabled={busy || !typedOk}
          >
            {busy ? "…" : confirmLabel}
          </button>
        </footer>
      </div>
    </div>
  );
}
