"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useApp } from "@/lib/store";

const MAIN = [
  { href: "/", label: "Explore", icon: "◎" },
  { href: "/species", label: "Species", icon: "⌕" },
  { href: "/mission", label: "Mission", icon: "◇" },
  { href: "/observations", label: "Finds", icon: "✦" },
  { href: "/profile", label: "Profile", icon: "◐" },
];
const MORE = [
  { href: "/expeditions", label: "Expeditions" },
  { href: "/discoveries", label: "Discoveries" },
  { href: "/compare", label: "Compare species" },
  { href: "/projects", label: "Projects" },
  { href: "/settings", label: "Settings" },
  { href: "/admin", label: "Admin" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { mode, user, online, pending } = useApp();
  const [more, setMore] = useState(false);
  const isActive = (h: string) => (h === "/" ? path === "/" : path.startsWith(h));
  return (
    <div className="min-h-[100dvh] bg-void">
      {/* top strip */}
      <div className="pointer-events-none fixed inset-x-0 top-0 z-40 flex items-center justify-between bg-gradient-to-b from-void via-void/85 to-transparent px-4 pb-5 pt-[max(env(safe-area-inset-top),12px)] md:pl-24">
        <Link href="/" className="pointer-events-auto font-mono text-sm tracking-[0.5em] text-bone">
          BIOQUEST
        </Link>
        <div className="pointer-events-auto flex items-center gap-2">
          {!online && <span className="rounded-full border border-amber/50 px-2 py-0.5 font-mono text-[9px] tracking-widest text-amber">OFFLINE</span>}
          {pending > 0 && <span className="rounded-full border border-cyan/50 px-2 py-0.5 font-mono text-[9px] tracking-widest text-cyan">{pending} TO SYNC</span>}
          <Link href="/settings" className={`rounded-full border px-2 py-0.5 font-mono text-[9px] tracking-[0.2em] ${mode === "demo" ? "border-amber/60 text-amber" : "border-signal/50 text-signal"}`}>
            {mode === "demo" ? "DEMO MODE" : "LIVE"}
          </Link>
          {!user && (
            <Link href="/login" className="font-mono text-[10px] tracking-[0.2em] text-mist hover:text-signal">
              SIGN IN
            </Link>
          )}
        </div>
      </div>

      {/* desktop rail */}
      <nav className="fixed inset-y-0 left-0 z-40 hidden w-20 flex-col items-center gap-2 border-r border-line bg-abyss/80 pt-20 backdrop-blur md:flex">
        {MAIN.map((m) => (
          <Link key={m.href} href={m.href} className={`flex w-16 flex-col items-center rounded-xl py-2 text-lg transition ${isActive(m.href) ? "bg-signal/10 text-signal" : "text-mist hover:text-bone"}`}>
            <span>{m.icon}</span>
            <span className="mt-1 font-mono text-[8px] uppercase tracking-[0.15em]">{m.label}</span>
          </Link>
        ))}
        <button onClick={() => setMore(!more)} className="mt-2 font-mono text-[9px] tracking-[0.2em] text-mist hover:text-bone">MORE</button>
      </nav>

      {more && (
        <div className="fixed bottom-20 left-4 right-4 z-50 animate-rise panel p-2 md:bottom-auto md:left-24 md:right-auto md:top-1/2 md:w-56" onClick={() => setMore(false)}>
          {MORE.map((m) => (
            <Link key={m.href} href={m.href} className="block rounded-lg px-3 py-2.5 font-mono text-xs tracking-[0.15em] text-bone hover:bg-signal/10 hover:text-signal">
              {m.label.toUpperCase()}
            </Link>
          ))}
        </div>
      )}

      <main className="md:pl-20">{children}</main>

      {/* mobile bottom nav */}
      <nav className="fixed inset-x-0 bottom-0 z-40 flex items-stretch justify-around border-t border-line bg-abyss/90 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
        {MAIN.map((m) => (
          <Link key={m.href} href={m.href} className={`flex flex-1 flex-col items-center py-2.5 ${isActive(m.href) ? "text-signal" : "text-mist"}`}>
            <span className="text-base leading-none">{m.icon}</span>
            <span className="mt-1 font-mono text-[8px] uppercase tracking-[0.15em]">{m.label}</span>
          </Link>
        ))}
        <button onClick={() => setMore(!more)} className="flex flex-1 flex-col items-center py-2.5 text-mist">
          <span className="text-base leading-none">⋯</span>
          <span className="mt-1 font-mono text-[8px] uppercase tracking-[0.15em]">More</span>
        </button>
      </nav>
    </div>
  );
}

export function Page({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <div className={`mx-auto px-4 pb-28 pt-20 md:pb-12 ${wide ? "max-w-6xl" : "max-w-3xl"}`}>{children}</div>
  );
}
