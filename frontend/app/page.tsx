"use client";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import MapView, { MapLayers } from "@/components/MapView";
import PriorityBreakdown, { PriorityT } from "@/components/Priority";
import { ErrorBox, Provenance } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { GridJSON } from "@/lib/raster";
import { useApp } from "@/lib/store";

type Zone = {
  headline: string; center: { lat: number; lon: number }; polygon: number[][]; radius_m: number; area_km2: number;
  distance_km: number; accessibility: { value: number; label: string; method: string };
  habitat: { elevation_m: number | null; habitat: string; source: string; land_cover?: { class: string; fraction: number }[] };
  road_access?: any;
  sampling: { sampling_gap_score: number; sampling_intensity: string; class: string; records: number; observers: number;
    known_taxa: number; note: string };
  priority: PriorityT; biodiversity_label: string; provenance: string; effort_note?: string;
};
type ExploreRes = { status: string; message?: string; errors?: { service: string; detail: string }[]; zone?: Zone;
  signals?: { lat: number; lon: number; score: number }[]; gap_layer?: GridJSON; provenance?: string;
  stats?: { observations_nearby: number; taxa_recorded: number; undersampled_cells: number; effort_complete: boolean } };

export default function Home() {
  const { mode, location, locate, user } = useApp();
  const router = useRouter();
  const [origin, setOrigin] = useState<{ lat: number; lon: number } | null>(null);
  const [scanning, setScanning] = useState(false);
  const [res, setRes] = useState<ExploreRes | null>(null);
  const [preview, setPreview] = useState<{ stats?: ExploreRes["stats"]; gap?: GridJSON; prov?: string } | null>(null);
  const [missions, setMissions] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showGap, setShowGap] = useState(false);
  const [radiusKm, setRadiusKm] = useState(20);

  useEffect(() => {
    setRes(null);
    setPreview(null);
    if (mode === "demo") setOrigin(location);
    else locate().then((l) => setOrigin(l ?? { lat: -12.046, lon: -77.043 }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  useEffect(() => {
    if (user) api<unknown[]>("/api/missions").then((m) => setMissions((m as { status: string }[]).filter((x) => x.status === "active").length)).catch(() => {});
  }, [user]);

  // ambient indicators around the origin (sampling effort sample)
  useEffect(() => {
    if (!origin) return;
    const d = 0.18;
    api(`/api/gap?minlon=${origin.lon - d}&minlat=${origin.lat - d}&maxlon=${origin.lon + d}&maxlat=${origin.lat + d}&mode=${mode}&res=0.026`)
      .then((g) => {
        setPreview({
          gap: g.layer, prov: g.provenance,
          stats: { observations_nearby: g.stats.observations, taxa_recorded: g.stats.taxa,
            undersampled_cells: g.stats.undersampled_cells, effort_complete: g.stats.complete },
        });
      })
      .catch(() => {});
  }, [origin, mode]);

  const explore = async () => {
    if (!origin) return;
    setErr(null);
    setScanning(true);
    setRes(null);
    const t0 = Date.now();
    try {
      const r = await api<ExploreRes>("/api/explore", { method: "POST", json: { mode, lat: origin.lat, lon: origin.lon, radius_km: radiusKm } });
      await new Promise((ok) => setTimeout(ok, Math.max(0, 2200 - (Date.now() - t0))));
      setRes(r);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setScanning(false);
    }
  };

  const start = async () => {
    if (!res?.zone) return;
    if (!user) return router.push("/login?next=/");
    try {
      await api("/api/missions", { method: "POST", json: { zone: res.zone } });
      router.push("/mission");
    } catch (e) {
      setErr((e as ApiError).message);
    }
  };

  const layers: MapLayers = useMemo(() => ({
    zone: res?.zone ? { polygon: res.zone.polygon, center: res.zone.center } : null,
    signals: res?.signals ?? (preview?.gap ? topCells(preview.gap) : []),
    raster: showGap && (res?.gap_layer || preview?.gap) ? { grid: (res?.gap_layer || preview?.gap)!, ramp: "gap", domain: [0, 100], opacity: 0.75 } : null,
    you: origin ? { ...origin, demo: mode === "demo" } : null,
  }), [res, preview, showGap, origin, mode]);

  const stats = res?.stats ?? preview?.stats;
  const z = res?.zone;

  return (
    <div className="relative h-[100dvh] w-full overflow-hidden">
      {origin && (
        <MapView center={z ? z.center : origin} zoom={z ? 11.2 : 10.3} layers={layers} />
      )}
      {/* vignette */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_35%,rgba(4,7,6,0.85)_100%)]" />

      {/* indicators */}
      <div className="pointer-events-none absolute inset-x-0 top-14 z-10 flex justify-center px-4">
        <div className="pointer-events-auto grid grid-cols-4 gap-4 rounded-2xl border border-line bg-void/50 px-4 py-2.5 backdrop-blur md:gap-8">
          <Ind label="obs. nearby" value={stats ? stats.observations_nearby : "—"} />
          <Ind label="taxa recorded" value={stats ? stats.taxa_recorded : "—"} />
          <Ind label="under-sampled" value={stats ? stats.undersampled_cells : "—"} hot />
          <Ind label="active missions" value={missions ?? "—"} />
        </div>
      </div>
      <div className="absolute left-4 top-[7.4rem] z-10 flex flex-col gap-2 md:left-24">
        <Provenance kind={res?.provenance ?? preview?.prov ?? (mode === "demo" ? "DEMO DATA" : "LIVE DATA")} />
        {mode === "demo" && <span className="font-mono text-[9px] text-amber/80">Fictitious field base · not your location</span>}
        <button onClick={() => setShowGap(!showGap)} className={`w-fit rounded-full border px-2 py-0.5 font-mono text-[9px] tracking-[0.18em] ${showGap ? "border-violet text-violet" : "border-line text-mist"}`}>
          SAMPLING GAP LAYER
        </button>
      </div>

      {/* EXPLORE */}
      {!z && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center">
          <button onClick={explore} disabled={scanning || !origin} aria-label="Explore"
            className="group relative flex h-40 w-40 items-center justify-center rounded-full md:h-48 md:w-48">
            <span className="absolute inset-0 animate-pulseRing rounded-full border border-signal/50" />
            <span className="absolute inset-0 animate-pulseRing rounded-full border border-signal/30 [animation-delay:1.4s]" />
            <span className="absolute inset-3 rounded-full border border-signal/40 bg-void/70 shadow-[0_0_80px_-10px_rgba(61,255,197,0.55)] backdrop-blur transition group-hover:shadow-[0_0_110px_-5px_rgba(61,255,197,0.75)]" />
            {scanning && (
              <span className="absolute inset-3 animate-sweep rounded-full bg-[conic-gradient(from_0deg,rgba(61,255,197,0.45),transparent_28%)]" />
            )}
            <span className="relative font-mono text-sm tracking-[0.45em] text-signal glow-text">{scanning ? "SCANNING" : "EXPLORE"}</span>
          </button>
          <div className="mt-6 flex items-center gap-1.5 font-mono text-[10px]">
            <span className="label mr-1">radius</span>
            {[5, 10, 20, 50].map((r) => (
              <button key={r} onClick={() => setRadiusKm(r)} className={`rounded-full border px-2 py-0.5 ${radiusKm === r ? "border-signal text-signal" : "border-line text-mist"}`}>{r} km</button>
            ))}
          </div>
          <p className="mt-6 text-sm font-light tracking-wide text-bone/90">Discover what hasn&apos;t been mapped yet.</p>
          <p className="mt-1 text-xs text-mist">Descubre lo que todavía no está en el mapa.</p>
          {err && <div className="mt-6 max-w-sm"><ErrorBox message={err} /></div>}
          {res?.status === "error" && <div className="mt-6 max-w-sm"><ErrorBox message={res.message} errors={res.errors} /></div>}
        </div>
      )}
      {scanning && <div className="pointer-events-none absolute inset-0 z-0 animate-flicker bg-[linear-gradient(transparent_0,rgba(61,255,197,0.05)_50%,transparent_100%)]" />}

      {/* OPPORTUNITY */}
      {z && (
        <div className="absolute inset-x-0 bottom-16 z-20 p-3 md:bottom-auto md:left-auto md:right-4 md:top-24 md:w-[380px] md:p-0">
          <div className="panel max-h-[62dvh] animate-rise overflow-y-auto p-5 scrollbar-thin md:max-h-[80dvh]">
            <div className="flex items-center justify-between">
              <span className="label text-signal">Opportunity detected</span>
              <Provenance kind={z.provenance} />
            </div>
            <h2 className="mt-3 text-xl font-light text-bone">{z.headline}.</h2>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <div>
                <div className="font-mono text-3xl font-light text-bone">{z.distance_km}<span className="text-sm text-mist"> km</span></div>
                <div className="label mt-1">straight-line</div>
              </div>
              <div className="space-y-1 text-xs text-bone">
                <p>{z.biodiversity_label}</p>
                <p>{z.sampling.sampling_intensity === "LOW" ? "Low" : z.sampling.sampling_intensity === "MEDIUM" ? "Medium" : "High"} observation density</p>
                <p className="text-mist">Access: {z.accessibility.label.toLowerCase()} (proxy)</p>
                {z.road_access?.status === "ok" && (
                  <p className="text-mist">Road/trail: {[z.road_access.road, z.road_access.trail].filter(Boolean).map((w: any) => w.distance_km).sort((a: number, b: number) => a - b)[0] ?? "none"} km{z.road_access.provenance === "DEMO DATA" ? " (DEMO)" : " (OSM)"}</p>
                )}
              </div>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-3 border-y border-line py-3 font-mono text-[11px]">
              <div><div className="label">area</div>{z.area_km2} km²</div>
              <div><div className="label">altitude</div>{z.habitat.elevation_m ?? "—"} m</div>
              <div><div className="label">records</div>{z.sampling.records} · {z.sampling.observers} obs.</div>
            </div>
            <p className="mt-3 text-xs text-mist">Habitat: <span className="text-bone">{z.habitat.habitat}</span></p>
            {z.habitat.land_cover && <p className="text-[10px] text-mist">{z.habitat.land_cover.map((c) => `${c.class} ${Math.round(c.fraction * 100)}%`).join(" · ")} · ESA WorldCover</p>}
            <p className="mt-1 text-[10px] text-mist/70">{z.sampling.note} {z.effort_note}</p>
            <div className="mt-4"><PriorityBreakdown p={z.priority} /></div>
            <div className="mt-5 flex gap-2">
              <button onClick={start} className="btn-signal flex-1">Start expedition</button>
              <button onClick={() => setRes(null)} className="btn-ghost">↺</button>
            </div>
            {err && <div className="mt-3"><ErrorBox message={err} /></div>}
          </div>
        </div>
      )}
    </div>
  );
}

function Ind({ label, value, hot }: { label: string; value: number | string; hot?: boolean }) {
  return (
    <div className="text-center">
      <div className={`font-mono text-base ${hot ? "text-signal" : "text-bone"}`}>{typeof value === "number" && Number.isNaN(value) ? "—" : value}</div>
      <div className="font-mono text-[8px] uppercase tracking-[0.15em] text-mist">{label}</div>
    </div>
  );
}

function topCells(g: GridJSON) {
  const out: { lat: number; lon: number; score: number }[] = [];
  g.values.forEach((v, i) => {
    if (v !== null && v >= 75) {
      const r = Math.floor(i / g.width), c = i % g.width;
      out.push({ lat: g.bbox[3] - (r + 0.5) * g.res, lon: g.bbox[0] + (c + 0.5) * g.res, score: v });
    }
  });
  return out.sort((a, b) => b.score - a.score).slice(0, 14);
}
