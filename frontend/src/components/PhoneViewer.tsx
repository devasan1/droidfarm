import { useCallback, useEffect, useRef, useState } from "react";
import {
  X,
  ArrowLeft,
  Circle,
  Square as SquareStack,
  Power,
  Volume2,
  VolumeX,
} from "lucide-react";
import { api } from "../lib/api";
import type { Phone } from "../lib/types";

interface Props {
  phone: Phone;
  onClose: () => void;
}

/**
 * Full-size interactive phone view. Mirrors the screen at ~5fps via
 * /api/phones/{id}/screenshot and forwards taps / swipes / keystrokes
 * back through the adb input endpoints. The image element itself is
 * kept at its native pixel dimensions (resolution from the Phone model)
 * so tap coordinates map 1:1 with the emulator's framebuffer — we just
 * scale it visually with CSS.
 */
export default function PhoneViewer({ phone, onClose }: Props) {
  const [tick, setTick] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const dragStart = useRef<{ x: number; y: number; t: number } | null>(null);
  const [nw, nh] = phone.resolution.split("x").map((n) => parseInt(n, 10) || 1);
  const nativeW = Math.max(1, nw);
  const nativeH = Math.max(1, nh);

  // Poll screenshots ~5fps. Only start another fetch once the prior image
  // has loaded to avoid queueing up stale frames.
  useEffect(() => {
    let alive = true;
    let timer: number | null = null;
    const schedule = () => {
      if (!alive) return;
      timer = window.setTimeout(() => setTick((t) => t + 1), 200);
    };
    const img = imgRef.current;
    if (!img) return;
    const onLoad = () => schedule();
    const onError = () => schedule();
    img.addEventListener("load", onLoad);
    img.addEventListener("error", onError);
    schedule();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
      img.removeEventListener("load", onLoad);
      img.removeEventListener("error", onError);
    };
  }, []);

  const coordsFrom = useCallback(
    (e: React.MouseEvent<HTMLImageElement>) => {
      const el = e.currentTarget;
      const rect = el.getBoundingClientRect();
      const sx = nativeW / rect.width;
      const sy = nativeH / rect.height;
      return {
        x: (e.clientX - rect.left) * sx,
        y: (e.clientY - rect.top) * sy,
      };
    },
    [nativeW, nativeH],
  );

  async function onMouseDown(e: React.MouseEvent<HTMLImageElement>) {
    const p = coordsFrom(e);
    dragStart.current = { x: p.x, y: p.y, t: performance.now() };
  }

  async function onMouseUp(e: React.MouseEvent<HTMLImageElement>) {
    const start = dragStart.current;
    dragStart.current = null;
    if (!start) return;
    const end = coordsFrom(e);
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const dt = performance.now() - start.t;
    const dist2 = dx * dx + dy * dy;
    try {
      // < 8px total movement or < 150ms → tap; else swipe.
      if (dist2 < 64 && dt < 400) {
        await api.tapPhone(phone.id, start.x, start.y);
      } else {
        await api.swipePhone(
          phone.id,
          start.x,
          start.y,
          end.x,
          end.y,
          Math.max(80, Math.min(800, Math.round(dt))),
        );
      }
    } catch (ex) {
      setErr(String(ex));
    }
  }

  async function sendText(text: string) {
    try {
      await api.textPhone(phone.id, text);
    } catch (ex) {
      setErr(String(ex));
    }
  }

  async function sendKey(keycode: string | number) {
    try {
      await api.keyeventPhone(phone.id, keycode);
    } catch (ex) {
      setErr(String(ex));
    }
  }

  // Global keyboard handler: route printable chars to adb input text,
  // Enter/Backspace/Tab/arrows to keyevent, Escape to close.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      // Ctrl+V / Cmd+V paste clipboard text into the focused field.
      if ((e.ctrlKey || e.metaKey) && (e.key === "v" || e.key === "V")) {
        e.preventDefault();
        navigator.clipboard
          .readText()
          .then((txt) => {
            if (txt) sendText(txt);
          })
          .catch((ex) => setErr(`clipboard: ${ex}`));
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "Enter") {
        e.preventDefault();
        sendKey(66); // KEYCODE_ENTER
        return;
      }
      if (e.key === "Backspace") {
        e.preventDefault();
        sendKey(67); // KEYCODE_DEL
        return;
      }
      if (e.key === "Tab") {
        e.preventDefault();
        sendKey(61); // KEYCODE_TAB
        return;
      }
      if (e.key === "ArrowLeft") return sendKey(21);
      if (e.key === "ArrowRight") return sendKey(22);
      if (e.key === "ArrowUp") return sendKey(19);
      if (e.key === "ArrowDown") return sendKey(20);
      if (e.key.length === 1) {
        e.preventDefault();
        sendText(e.key);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const src = api.screenshotUrl(phone.id, tick);

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
    >
      <div
        className="relative flex max-h-full max-w-full gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-col items-center">
          <div
            className="relative overflow-hidden rounded-2xl border border-ink-700 bg-black shadow-2xl"
            style={{
              aspectRatio: `${nativeW} / ${nativeH}`,
              height: "min(85vh, calc(100vw * 9/16))",
              maxWidth: "calc(85vh * 9/16)",
            }}
          >
            <img
              ref={imgRef}
              src={src}
              alt={`${phone.name} live`}
              draggable={false}
              onMouseDown={onMouseDown}
              onMouseUp={onMouseUp}
              className="h-full w-full cursor-crosshair select-none object-fill"
            />
            {err && (
              <div className="absolute inset-x-3 bottom-3 rounded bg-red-950/80 px-3 py-2 text-xs text-red-200">
                {err}
              </div>
            )}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              className="btn-secondary"
              title="Back (KEYCODE_BACK)"
              onClick={() => sendKey(4)}
            >
              <ArrowLeft size={14} />
            </button>
            <button
              type="button"
              className="btn-secondary"
              title="Home (KEYCODE_HOME)"
              onClick={() => sendKey(3)}
            >
              <Circle size={14} />
            </button>
            <button
              type="button"
              className="btn-secondary"
              title="Recents (KEYCODE_APP_SWITCH)"
              onClick={() => sendKey(187)}
            >
              <SquareStack size={14} />
            </button>
            <button
              type="button"
              className="btn-secondary"
              title="Power"
              onClick={() => sendKey(26)}
            >
              <Power size={14} />
            </button>
            <button
              type="button"
              className="btn-secondary"
              title={muted ? "Unmute" : "Mute"}
              onClick={() => {
                sendKey(muted ? 24 : 164);
                setMuted((m) => !m);
              }}
            >
              {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
            </button>
          </div>
        </div>

        <aside className="hidden w-64 flex-col gap-2 text-xs text-ink-300 md:flex">
          <div className="card px-3 py-2">
            <div className="font-medium text-ink-100">{phone.name}</div>
            <div className="text-ink-400">
              {phone.device_profile} · Android {phone.android_version} ·{" "}
              {phone.resolution}
            </div>
          </div>
          <div className="card space-y-1 px-3 py-2 leading-relaxed">
            <div className="font-medium text-ink-100">Controls</div>
            <div>
              <span className="text-ink-500">Click</span> the screen to tap.
            </div>
            <div>
              <span className="text-ink-500">Drag</span> to swipe (for
              scrolling).
            </div>
            <div>
              <span className="text-ink-500">Type</span> directly to send text
              — Enter / Backspace / Arrows / Tab all route through.
            </div>
            <div>
              <span className="text-ink-500">Ctrl+V</span> to paste clipboard
              text (handy for long passwords / tokens).
            </div>
            <div>
              <span className="text-ink-500">Esc</span> to close.
            </div>
          </div>
        </aside>

        <button
          type="button"
          className="absolute -right-2 -top-2 rounded-full bg-ink-800 p-1.5 text-ink-200 shadow hover:bg-ink-700"
          onClick={onClose}
          title="Close (Esc)"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
