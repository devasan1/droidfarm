import { NavLink, Outlet } from "react-router-dom";
import { Smartphone, Globe2, Package, Trash2 } from "lucide-react";

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
        </nav>
        <div className="mt-auto px-2 text-[11px] text-ink-500">
          v0.1.0 · {new Date().getFullYear()}
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
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
