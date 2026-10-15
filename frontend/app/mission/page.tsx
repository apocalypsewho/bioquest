"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import MapView from "@/components/MapView";
import PriorityBreakdown from "@/components/Priority";
import { ErrorBox, NeedLogin, Provenance, RoadAccess, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/lib/store";

export default function MissionPage() {
  const { user, ready, mode } = useApp();
  const [missions, setMissions] = useState<any[] | null>(null);
  const [exp, setExp] = useState<any>(null);
  const [done, setDone] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [route, setRoute] = useState<number[][]>([]);
  const watch = useRef<number | null>(null);
  const buffer = useRef<(number | string)[][]>([]);

  const load = () => api("/api/missions").then(setMissions).catch((e: ApiError) => setErr(e.message));
  useEffect(() => {
    if (user) {
      load();
      api("/api/expeditions").then((l: any[]) => {
        const active = l.find((e) => e.status === "active");
        if (active) {
          setExp(active);
          setRoute(active.route);
        }
      });
    }
  }, [user]);

  const m = missions?.find((x) => x.status === "active") ?? null;

  // GPS track while an expedition is active (in DEMO MODE the track is simulated around the zone)
  useEffect(() => {
    if (!exp || !m) return;
    const flush = async () => {
      if (!buffer.current.length) return;
      const pts = buffer.current;
      buffer.current = [];
      try { await api(`/api/expeditions/${exp.id}/track`, { method: "POST", json: { points: pts } }); } catch { buffer.current.unshift(...pts); }
    };
    const push = (lon: number, lat: number) => {
      const p = [lon, lat, new Date().toISOString()];
      buffer.current.push(p);
      setRoute((r) => [...r, p as number[]]);
    };
    let sim: ReturnType<typeof setInterval> | null = null;
    if (exp.is_demo) {
      let i = route.length;
      sim = setInterval(() => {
        i++;
        const a = i / 6;
        push(m.center.lon + 0.004 * i * Math.cos(a) * 0.15, m.center.lat + 0.004 * i * Math.sin(a) * 0.15);
      }, 2500);
    } else if (navigator.geolocation) {
      watch.current = navigator.geolocation.watchPosition((p) => push(p.coords.longitude, p.coords.latitude), undefined,
        { enableHighAccuracy: true, maximumAge: 5000 });
    }
    const t = setInterval(flush, 10000);
    return () => {
      flush();
      clearInterval(t);
      if (sim) clearInterval(sim);
      if (watch.current != null) navigator.geolocation.clearWatch(watch.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exp?.id, m?.id]);

  const startExp = async () => {
    try {
      const e = await api("/api/expeditions", { method: "POST", json: { mission_id: m.id, name: `Mission #${m.code}`, is_demo: mode === "demo" || m.provenance.includes("DEMO") } });
      setExp(e);
      setRoute([]);
    } catch (e) { setErr((e as ApiError).message); }
  };
  const finish = async () => {
    try {
      if (buffer.current.length) await api(`/api/expeditions/${exp.id}/track`, { method: "POST", json: { points: buffer.current } });
      buffer.current = [];
      setDone(await api(`/api/expeditions/${exp.id}/finish`, { method: "POST" }));
      setExp(null);
      load();
    } catch (e) { setErr((e as ApiError).message); }
  };

  if (ready && !user) return <div className="px-4 pt-20"><NeedLogin /></div>;
  if (done) return <Complete d={done} />;

  return (
    <div className="md:grid md:h-[100dvh] md:grid-cols-[minmax(360px,440px)_1fr]">
      <div className="h-[44dvh] md:order-2 md:h-full">
        {m ? <MapView center={m.center} zoom={12.5} layers={{ zone: { polygon: m.zone.polygon, center: m.center }, route }} />
          : <div className="flex h-full items-center justify-center text-mist">{missions ? "" : <Spinner />}</div>}
      </div>
      <div className="px-4 pb-28 pt-4 md:order-1 md:h-full md:overflow-y-auto md:pb-10 md:pt-20 scrollbar-thin">
        {err && <ErrorBox message={err} />}
        {missions && !m && (
          <div className="panel p-6 text-sm text-mist">
            No active mission. <Link href="/" className="text-signal">Explore</Link> or <Link href="/species" className="text-signal">model a species</Link> to generate one.
          </div>
        )}
        {m && (
          <div className="animate-rise">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs tracking-[0.3em] text-signal">MISSION #{m.code}</span>
              <Provenance kind={m.provenance} />
            </div>
            <div className="mt-6 space-y-5">
              <Block k="Target" v={m.target_name ? <i>{m.target_name}</i> : "All taxa (open survey)"} />
              <Block k="Objective" v={m.objective} />
              <div className="grid grid-cols-3 gap-4">
                <Block k="Area" v={`${m.area_km2} km²`} />
                <Block k="Distance" v={m.distance_km != null ? `${m.distance_km} km` : "—"} />
                <Block k="Priority" v={`${m.priority?.score ?? "—"}/100`} />
              </div>
              <div className="grid grid-cols-3 gap-4">
                <Block k="Model agreement" v={m.zone.model_agreement ?? "n/a"} />
                <Block k="Sampling gap" v={m.zone.sampling?.sampling_intensity === "LOW" ? "HIGH" : m.zone.sampling?.sampling_intensity === "MEDIUM" ? "MEDIUM" : "LOW"} />
                <Block k="Habitat" v={<span className="text-xs">{m.zone.habitat?.habitat}</span>} />
              </div>
            </div>
            {m.zone.road_access && <div className="mt-6 panel p-4"><RoadAccess zone={m.zone} /></div>}
            {m.priority && <div className="mt-6 panel p-4"><PriorityBreakdown p={m.priority} /></div>}
            {m.guidance && (
              <div className="mt-6 panel p-4 text-xs text-mist">
                <div className="flex items-center justify-between"><span className="label text-signal">Sampling guidance · {m.guidance.group}</span></div>
                <ul className="mt-2 list-disc space-y-1 pl-4 text-bone/90">
                  {m.guidance.taxon_methods.map((t: string, i: number) => <li key={i}>{t}</li>)}
                  {m.guidance.habitat_tip && <li>{m.guidance.habitat_tip}</li>}
                </ul>
                <ul className="mt-2 list-disc space-y-1 pl-4">
                  {m.guidance.always.map((t: string, i: number) => <li key={i}>{t}</li>)}
                </ul>
                <p className="mt-2 text-[10px] text-amber/80">{m.guidance.label}</p>
              </div>
            )}
            <p className="mt-4 text-[11px] text-mist">Observe and photograph; do not collect unless you hold the required permits. Respect private land and protected areas.</p>
            {!exp ? (
              <button onClick={startExp} className="btn-signal mt-6 w-full py-4">Start expedition</button>
            ) : (
              <div className="mt-6 panel p-4">
                <div className="flex items-center justify-between">
                  <span className="label text-signal">Expedition active</span>
                  <span className="font-mono text-[10px] text-mist">{route.length} GPS pts{exp.is_demo ? " · simulated (DEMO)" : ""}</span>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <Link href={`/observations/new?expedition=${exp.id}&mission=${m.id}`} className="btn-signal py-3">New find</Link>
                  <button onClick={finish} className="btn-ghost py-3">Finish</button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Block({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <div className="label">{k}</div>
      <div className="mt-1 text-bone">{v}</div>
    </div>
  );
}

function Complete({ d }: { d: any }) {
  return (
    <div className="flex min-h-[100dvh] flex-col items-center justify-center px-6 text-center">
      <div className="label text-signal">Expedition complete</div>
      <div className="mt-6 font-mono text-5xl font-light text-bone glow-text">{d.distance_km} km</div>
      <div className="mt-8 grid grid-cols-2 gap-x-10 gap-y-4 font-mono text-sm text-bone md:grid-cols-4">
        <div><b className="text-xl">{d.habitats}</b><div className="label">habitats</div></div>
        <div><b className="text-xl">{d.observations}</b><div className="label">observations</div></div>
        <div><b className="text-xl">{d.taxa}</b><div className="label">taxa</div></div>
        <div><b className="text-xl">{d.unusual_records}</b><div className="label">unusual records</div></div>
      </div>
      <p className="mt-6 text-xs text-mist">{d.duration_min} min{d.is_demo ? " · DEMO expedition" : ""}</p>
      <div className="mt-8 flex gap-3">
        <Link href="/profile" className="btn-signal">My biodiversity</Link>
        <Link href="/expeditions" className="btn-ghost">Expeditions</Link>
      </div>
    </div>
  );
}
