"use client";
import Link from "next/link";
import { ReactNode } from "react";

export function Provenance({ kind, className = "" }: { kind?: string | null; className?: string }) {
  const k = (kind || "").toUpperCase();
  const style = k.startsWith("MODEL")
    ? "border-violet/50 text-violet bg-violet/10"
    : k.includes("DEMO")
      ? "border-amber/60 text-amber bg-[repeating-linear-gradient(135deg,rgba(255,181,71,0.14)_0_6px,transparent_6px_12px)]"
      : k.includes("LIVE")
        ? "border-signal/50 text-signal bg-signal/10"
        : "border-line text-mist";
  return (
    <span className={`inline-flex w-fit items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.18em] ${style} ${className}`}>
      <span className="h-1 w-1 rounded-full bg-current" />
      {kind || "UNKNOWN SOURCE"}
    </span>
  );
}

export function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="label truncate">{label}</div>
      <div className="mt-1 font-mono text-lg text-bone">{value}</div>
      {sub && <div className="text-[11px] text-mist">{sub}</div>}
    </div>
  );
}

export function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line/60 py-2 last:border-0">
      <span className="label">{k}</span>
      <span className="text-right font-mono text-sm text-bone">{v}</span>
    </div>
  );
}

export function ErrorBox({ errors, message }: { errors?: { service: string; detail: string }[]; message?: string }) {
  if (!message && !errors?.length) return null;
  return (
    <div className="rounded-xl border border-danger/40 bg-danger/10 p-3 text-xs text-danger">
      {message && <p>{message}</p>}
      {errors?.map((e, i) => (
        <p key={i} className="font-mono">
          {e.service}: {e.detail}
        </p>
      ))}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-mist">
      <span className="relative h-5 w-5">
        <span className="absolute inset-0 rounded-full border border-signal/30" />
        <span className="absolute inset-0 animate-sweep rounded-full border-t border-signal" />
      </span>
      {label && <span className="label">{label}</span>}
    </div>
  );
}

export function PageHeader({ kicker, title, children }: { kicker?: string; title: string; children?: ReactNode }) {
  return (
    <header className="mb-6 animate-rise">
      {kicker && <div className="label mb-2 text-signal/80">{kicker}</div>}
      <h1 className="text-2xl font-light tracking-[0.12em] text-bone md:text-3xl">{title}</h1>
      {children && <div className="mt-2 text-sm text-mist">{children}</div>}
    </header>
  );
}

export function NeedLogin() {
  return (
    <div className="panel p-6 text-sm text-mist">
      Sign in to keep missions, observations and your collection.{" "}
      <Link href="/login" className="text-signal">
        Sign in →
      </Link>
    </div>
  );
}

export function Bar({ value, color = "bg-signal" }: { value: number | null; color?: string }) {
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-line">
      <div className={`h-full ${color} transition-all duration-700`} style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%` }} />
    </div>
  );
}

export function RoadAccess({ zone }: { zone: any }) {
  const ra = zone.road_access;
  const near = (w: any) => (w ? `${w.distance_km} km (${w.highway}${w.name ? ` · ${w.name}` : ""})` : "none mapped nearby");
  return (
    <>
      <Row k="accessibility" v={`${zone.accessibility.label.toLowerCase()} (proxy)`} />
      {ra?.status === "ok" && (
        <>
          <Row k="nearest road" v={near(ra.road)} />
          <Row k="nearest trail" v={near(ra.trail)} />
          <p className="pt-1 text-right text-[9px] text-mist">{ra.source}{ra.note ? ` · ${ra.note}` : ""}</p>
        </>
      )}
      {ra?.status === "error" && <p className="pt-1 text-right text-[10px] text-amber">{ra.message} ({ra.error?.detail})</p>}
    </>
  );
}

export function LandCover({ habitat }: { habitat: any }) {
  if (!habitat?.land_cover?.length) return null;
  return (
    <div className="pt-1 text-right font-mono text-[10px] text-mist">
      {habitat.land_cover.map((c: any) => `${c.class} ${Math.round(c.fraction * 100)}%`).join(" · ")}
    </div>
  );
}
