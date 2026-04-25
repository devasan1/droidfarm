import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Smartphone, Globe2, Package, Trash2, Settings as SettingsIcon, Clock } from "lucide-react";
import { api } from "./lib/api";

export default function App() {
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 flex-col border-r border-ink-800 bg-ink-900 px-3 py-6">
        <div className="mb-8 px-2">
          <div className="text-lg font-semibold text-emerald-400">DroidFarm</div>
          <div className="text-xs text-ink-400">local android farm</div>
        </div>
        <nav className="flex flex-col gap-1">
          <Nav to="/phones" icon={<Smartphone size={16} />}>Phones</Nav>
          <Nav to="/proxies" icon={<Globe2 size={16} />}>Proxies</Nav>
          <Nav to="/apks" icon={<Package size={16} />}>APK library</Nav>
          <Nav to="/trash" icon={<Trash2 size={16} />}>Trash</Nav>
          <Nav to="/schedules" icon={<Clock size={16} />}>Schedules</Nav>
          <Nav to="/settings" icon={<SettingsIcon size={16} />}>Settings</Nav>
        </nav>
        <DriverBadge />
        <div className="mt-2 px-2 text-[11px] text-ink-500">
          v0.1.0 · {new Date().getFullYear()}
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}

type DriverInfo = {
  mock: boolean;
  driver: "ldplayer" | "android_emulator" | "mock";
  ldconsole: string | null;
  androidSdk: string | null;
};

function DriverBadge() {
  const [info, setInfo] = useState<DriverInfo | null>(null);
  useEffect(() => {
    let alive = true;
    api
      .health()
      .then((h) => {
        if (alive)
          setInfo({
            mock: h.mock_driver,
            driver: h.driver,
            ldconsole: h.ldconsole,
            androidSdk: h.android_sdk,
          });
      })
      .catch(() => {
        /* health failed; show nothing */
      });
    return () => {
      alive = false;
    };
  }, []);
  if (!info) {
    return <div className="mt-auto" />;
  }
  if (info.driver === "mock") {
    return (
      <NavLink
        to="/settings"
        title="Phones will be virtual stubs until LDPlayer or the Android SDK is detected. Click to open Settings."
        className="mt-auto mx-2 mb-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-[11px] leading-tight text-amber-300 hover:bg-amber-500/15"
      >
        <div className="font-medium">Driver: Mock</div>
        <div className="text-amber-300/70">No emulator backend · click to setup</div>
      </NavLink>
    );
  }
  if (info.driver === "android_emulator") {
    return (
      <div
        title={info.androidSdk ?? ""}
        className="mt-auto mx-2 mb-1 rounded-md border border-emerald-500/20 bg-emerald-500/5 px-2 py-1.5 text-[11px] leading-tight text-emerald-300"
      >
        <div className="font-medium">Driver: AndroidEmulator</div>
        <div className="truncate text-emerald-300/60" title={info.androidSdk ?? ""}>
          {info.androidSdk ?? ""}
        </div>
      </div>
    );
  }
  return (
    <div
      title={info.ldconsole ?? ""}
      className="mt-auto mx-2 mb-1 rounded-md border border-emerald-500/20 bg-emerald-500/5 px-2 py-1.5 text-[11px] leading-tight text-emerald-300"
    >
      <div className="font-medium">Driver: LDPlayer</div>
      <div className="truncate text-emerald-300/60" title={info.ldconsole ?? ""}>
        {info.ldconsole ?? ""}
      </div>
    </div>
  );
}

function Nav({
  to,
  icon,
  children,
}: {
  to: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        [
          "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm",
          isActive
            ? "bg-emerald-500/10 text-emerald-400"
            : "text-ink-300 hover:bg-ink-800 hover:text-ink-100",
        ].join(" ")
      }
    >
      {icon}
      {children}
    </NavLink>
  );
}
