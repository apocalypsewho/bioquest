"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import MapView from "@/components/MapView";
import PriorityBreakdown from "@/components/Priority";
import { ErrorBox, Provenance, LandCover, RoadAccess, Row, Spinner } from "@/components/ui";
import { api, ApiError, slugToKey } from "@/lib/api";
import { GridJSON, rampCss, RAMPS } from "@/lib/raster";
import { useApp } from "@/lib/store";

const LAYERS: { id: string; label: string; ramp: keyof typeof RAMPS; domain?: [number, number] }[] = [
  { id: "ensemble", label: "Ensemble", ramp: "suitability" },
  { id: "maxent", label: "MaxEnt", ramp: "suitability" },
  { id: "random_forest", label: "Random Forest", ramp: "suitability" },
  { id: "glm", label: "GLM", ramp: "suitability" },
  { id: "gam", label: "GAM", ramp: "suitability" },
  { id: "agreement", label: "Agreement", ramp: "agreement", domain: [0, 3] },
  { id: "extrapolation", label: "Extrapolation", ramp: "extrapolation" },
  { id: "gap", label: "Sampling gap", ramp: "gap", domain: [0, 100] },
];

function ModelInner({ params }: { params: { id: string } }) {
  const key = slugToKey(params.id);
  const { mode, location, user } = useApp();
  const m = key.startsWith("demo:") ? "demo" : mode;
  const sp = useSearchParams();
  const router = useRouter();
  const [runId, setRunId] = useState<number | null>(sp.get("run") ? Number(sp.get("run")) : null);
  const [run, setRun] = useState<any>(null);
  const [layer, setLayer] = useState("ensemble");
  const [grids, setGrids] = useState<Record<string, GridJSON>>({});
  const [cell, setCell] = useState<any>(null);
  const [zone, setZone] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<any>(null);
  const [incQ, setIncQ] = useState(false);
  const [model3, setModel3] = useState<"glm" | "gam">("glm");
  const [bg, setBg] = useState<"random" | "target_group">("target_group");

  const start = async () => {
    setErr(null);
    setRun(null);
    setGrids({});
    setZone(null);
    try {
      const r = await api("/api/models", { method: "POST", json: { taxon_key: key, mode: m, include_questionable: incQ, model3, background: bg } });
      setRunId(r.id);
      router.replace(`?run=${r.id}`);
    } catch (e) {
      setErr((e as ApiError).detail ?? (e as ApiError).message);
    }
  };

  useEffect(() => {
    if (!runId) return;
    let stop = false;
    const poll = async () => {
      try {
        const r = await api(`/api/models/${runId}`);
        if (stop) return;
        setRun(r);
        if (r.status === "running") setTimeout(poll, 1500);
      } catch (e) {
        setErr((e as ApiError).message);
      }
    };
    poll();
    return () => { stop = true; };
  }, [runId]);

  useEffect(() => {
    if (!run || run.status !== "completed" || grids[layer] || layer === "gap") return;
    api(`/api/models/${run.id}/layers/${layer}`).then((l) => setGrids((g) => ({ ...g, [layer]: l.grid })));
  }, [run, layer, grids]);

  const findZone = async () => {
    setBusy(true);
    setErr(null);
    try {
      const z = await api(`/api/models/${run.id}/zone`, { method: "POST", json: location ? { lat: location.lat, lon: location.lon } : {} });
      if (z.status !== "ok") setErr(z.message);
      else {
        setZone(z);
        setGrids((g) => ({ ...g, gap: z.gap_layer }));
      }
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const createMission = async () => {
    if (!user) return router.push("/login");
    try {
      await api("/api/missions", { method: "POST", json: { zone: zone.zone } });
      router.push("/mission");
    } catch (e) {
      setErr((e as ApiError).message);
    }
  };

  const L = LAYERS.find((l) => l.id === layer)!;
  const grid = grids[layer];
  const fit = useMemo(() => (run?.bbox?.length ? (run.bbox as [number, number, number, number]) : null), [run?.bbox]);
  const pts = (run?.metrics?.used_points ?? []).map((p: number[]) => ({ uid: `${p[0]},${p[1]}`, lat: p[0], lon: p[1], source: m === "demo" ? "demo" : "inaturalist", qc_status: "VALID" }));

  const onClick = async (lat: number, lon: number) => {
    if (!run || run.status !== "completed") return;
    setCell({ loading: true, lat, lon });
    const c = await api(`/api/models/${run.id}/cell?lat=${lat}&lon=${lon}`);
    setCell({ ...c, lat, lon });
  };

  const metric = (a: string) => run?.metrics?.[a];

  return (
    <div className="md:grid md:h-[100dvh] md:grid-cols-[minmax(360px,460px)_1fr]">
      <div className="relative h-[46dvh] md:order-2 md:h-full">
        <MapView center={{ lat: -12, lon: -75 }} zoom={5} fitTo={fit}
          layers={{ raster: grid ? { grid, ramp: L.ramp, domain: L.domain } : null, occurrences: pts,
            zone: zone?.zone ? { polygon: zone.zone.polygon, center: zone.zone.center } : null }}
          onClick={onClick} />
        {run?.status === "completed" && (
          <div className="absolute left-3 top-16 z-10 flex max-w-[calc(100%-1.5rem)] flex-wrap gap-1.5">
            {LAYERS.filter((l) => l.id !== "gap" || grids.gap).map((l) => (
              <button key={l.id} onClick={() => setLayer(l.id)}
                className={`rounded-full border px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.15em] backdrop-blur ${layer === l.id ? "border-signal bg-signal/15 text-signal" : "border-line bg-void/60 text-mist"}`}>
                {l.label}
              </button>
            ))}
          </div>
        )}
        {grid && (
          <div className="absolute bottom-10 left-3 z-10 w-56 rounded-xl border border-line bg-void/70 p-2.5 backdrop-blur">
            <div className="label mb-1">{layer === "gap" ? "Sampling gap score" : layer === "agreement" ? "Models agreeing (0–3)" : layer === "extrapolation" ? "Outside training range" : "Environmental suitability"}</div>
            <div className="h-2 rounded-full" style={{ background: rampCss(L.ramp) }} />
            <div className="mt-1 flex justify-between font-mono text-[9px] text-mist"><span>low</span><span>medium</span><span>high</span></div>
          </div>
        )}
        {cell && !cell.loading && cell.inside && (
          <div className="absolute right-3 top-16 z-10 w-56 animate-rise rounded-xl border border-line bg-void/80 p-3 font-mono text-[11px] backdrop-blur">
            <div className="flex justify-between"><span className="label">cell</span><button onClick={() => setCell(null)} className="text-mist">×</button></div>
            <p className="mt-1">Suitability: <b className="text-signal">{cell.environmental_suitability?.toFixed(2)}</b></p>
            <p>Model agreement: {cell.model_agreement}</p>
            <p className="text-mist">{["maxent", "random_forest", "glm", "gam"].filter((a) => a in (cell.values ?? {})).map((a) => `${NAMES[a]} ${fmt(cell.values[a])}`).join(" · ")}</p>
            {cell.extrapolation && <p className="text-danger">Extrapolation — unreliable</p>}
            <p className="mt-1 text-[9px] text-mist">Environmental suitability ≠ probability of presence.</p>
          </div>
        )}
      </div>

      <div className="px-4 pb-28 pt-4 md:order-1 md:h-full md:overflow-y-auto md:pb-10 md:pt-20 scrollbar-thin">
        <div className="label text-signal/80">Distribution modelling</div>
        <h1 className="mt-1 text-xl font-light text-bone"><span className="italic">{run?.scientific_name || key}</span></h1>

        {!runId && (
          <div className="mt-5 panel p-4 text-sm text-mist animate-rise">
            <p>Runs <b className="text-bone">MaxEnt</b>, <b className="text-bone">Random Forest</b> and <b className="text-bone">{model3.toUpperCase()}</b> on quality-controlled occurrences, validates them with spatial block cross-validation and combines them into an ensemble of <b className="text-bone">environmental suitability</b>.</p>
            <p className="mt-2 text-xs">{m === "demo" ? "DEMO: fictitious occurrences + synthetic environment." : "LIVE: iNaturalist + GBIF occurrences, WorldClim v2.1 predictors (must be downloaded on the server)."}</p>
            <label className="mt-3 flex items-center gap-2 text-xs"><input type="checkbox" checked={incQ} onChange={(e) => setIncQ(e.target.checked)} /> include QUESTIONABLE records</label>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <label className="space-y-1"><span className="label block">third model</span>
                <select value={model3} onChange={(e) => setModel3(e.target.value as "glm" | "gam")} className="w-full rounded-lg border border-line bg-void px-2 py-1.5 text-bone">
                  <option value="glm">GLM (quadratic logistic)</option>
                  <option value="gam">GAM (pygam splines)</option>
                </select>
              </label>
              <label className="space-y-1"><span className="label block">background</span>
                <select value={bg} onChange={(e) => setBg(e.target.value as "random" | "target_group")} className="w-full rounded-lg border border-line bg-void px-2 py-1.5 text-bone">
                  <option value="target_group">target-group (bias-corrected)</option>
                  <option value="random">random</option>
                </select>
              </label>
            </div>
            <p className="mt-2 text-[10px]">Target-group background samples pseudo-absences where related taxa were recorded, so the model shares the presences’ sampling bias instead of learning it (Phillips et al. 2009).</p>
            <button onClick={start} className="btn-signal mt-4 w-full py-3">Generate distribution map</button>
          </div>
        )}
        {err && <div className="mt-4"><ErrorBox message={typeof err === "string" ? err : `${err.message ?? ""} ${err.detail ?? ""} ${err.fix ?? ""}`} /></div>}
        {runId && !run && <div className="mt-6"><Spinner label="starting" /></div>}
        {run?.status === "running" && (
          <div className="mt-6 panel p-5">
            <Spinner label="fetching · cleaning · fitting · validating" />
            <p className="mt-3 text-xs text-mist">Spatial cross-validation of three algorithms can take a while.</p>
          </div>
        )}
        {run && run.status !== "running" && (
          <div className="mt-4 space-y-4 animate-rise">
            <div className="flex flex-wrap items-center gap-2">
              <Provenance kind={run.provenance} />
              <span className={`font-mono text-[10px] uppercase tracking-widest ${run.status === "completed" ? "text-signal" : "text-danger"}`}>{run.status.replace("_", " ")}</span>
            </div>
            {run.status === "insufficient_data" && (
              <div className="rounded-xl border border-amber/40 bg-amber/10 p-4 text-sm text-amber">
                <b>Insufficient occurrence data for reliable model.</b> No map was generated to avoid a misleading prediction.
              </div>
            )}
            <div className="panel p-4">
              <Row k="output" v="environmental suitability (relative)" />
              <Row k="models" v={`${["maxent", "random_forest", "glm", "gam"].filter((a) => metric(a)).map((a) => NAMES[a]).join(" · ")} → ensemble`} />
              <Row k="variables" v={run.variables?.join(", ") || "—"} />
              <Row k="environment" v={run.env_provider_label} />
              <Row k="resolution" v={run.resolution_deg ? `${run.resolution_deg.toFixed(3)}° (~${(run.resolution_deg * 111).toFixed(1)} km)` : "—"} />
              <Row k="occurrences" v={`${run.n_occurrences_used} used / ${run.n_occurrences_raw} retrieved`} />
              <Row k="background pts" v={`${run.n_background} · ${run.metrics?.background?.method === "target_group" ? "target-group" : "random"}`} />
              <Row k="date" v={run.created_at?.slice(0, 16).replace("T", " ")} />
            </div>

            {run.status === "completed" && (
              <div className="panel overflow-x-auto p-4">
                <div className="label mb-2">Validation · spatial block CV ({metric("maxent")?.spatial_cv?.block_size_deg ?? "?"}° blocks)</div>
                <table className="w-full font-mono text-[11px]">
                  <thead className="text-mist"><tr><th className="text-left font-normal">model</th><th className="font-normal">AUC</th><th className="font-normal">TSS</th><th className="font-normal">weight</th></tr></thead>
                  <tbody>
                    {["maxent", "random_forest", "glm", "gam"].filter((a) => metric(a)).map((a) => (
                      <tr key={a} className="border-t border-line/60">
                        <td className="py-1.5 text-bone">{NAMES[a]}</td>
                        <td className="text-center">{ms(metric(a).spatial_cv.auc)}</td>
                        <td className="text-center">{ms(metric(a).spatial_cv.tss)}</td>
                        <td className="text-center">{run.metrics.ensemble?.weights?.[a]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <details className="mt-3 text-[11px] text-mist">
                  <summary className="cursor-pointer font-mono text-[10px] tracking-widest text-signal">CONFUSION MATRICES · RANDOM SPLIT · IMPORTANCE</summary>
                  {["maxent", "random_forest", "glm", "gam"].filter((a) => metric(a)).map((a) => {
                    const cm = metric(a).spatial_cv.confusion_matrix_pooled;
                    return (
                      <div key={a} className="mt-2 font-mono">
                        <b className="text-bone">{a}</b> · pooled CV: TP {cm.tp} · FP {cm.fp} · FN {cm.fn} · TN {cm.tn} · random 70/30 AUC {metric(a).random_split_70_30.auc.toFixed(3)} · thr(maxTSS) {metric(a).threshold_max_tss}
                        {metric(a).variable_importance && <div>importance: {Object.entries(metric(a).variable_importance).map(([k, v]) => `${k} ${v}`).join(" · ")}</div>}
                      </div>
                    );
                  })}
                  <p className="mt-2">Ensemble: {run.metrics.ensemble?.method}. Extrapolated area: {(run.metrics.extrapolation_fraction * 100).toFixed(1)}%.</p>
                </details>
              </div>
            )}

            {run.warnings?.length > 0 && (
              <div className="space-y-1.5 rounded-xl border border-line p-3 text-[11px] text-mist">
                <div className="label mb-1 text-amber">Scientific caveats</div>
                {run.warnings.map((w: string, i: number) => <p key={i}>⚠ {w}</p>)}
              </div>
            )}

            {run.status === "completed" && !zone && (
              <button onClick={findZone} disabled={busy} className="btn-signal w-full py-3.5">{busy ? "Scanning sampling gaps…" : "Where should I search?"}</button>
            )}
            {zone?.zone && (
              <div className="panel animate-rise p-5">
                <div className="flex items-center justify-between"><span className="label text-signal">🔬 Exploration zone</span><Provenance kind={zone.zone.provenance} /></div>
                <h3 className="mt-2 text-lg font-light text-bone">{zone.zone.priority.label === "VERY HIGH" || zone.zone.priority.label === "HIGH" ? "HIGH-PRIORITY ZONE" : "CANDIDATE ZONE"}</h3>
                <div className="mt-3">
                  <Row k="environmental suitability" v={`${Math.round(zone.zone.environmental_suitability * 100)}%`} />
                  <Row k="model agreement" v={zone.zone.model_agreement} />
                  <Row k="sampling intensity" v={zone.zone.sampling.sampling_intensity} />
                  <Row k="sampling gap score" v={zone.zone.sampling.sampling_gap_score} />
                  <Row k="altitude" v={zone.zone.habitat.elevation_m ? `${zone.zone.habitat.elevation_m} m` : "—"} />
                  <Row k="habitat" v={zone.zone.habitat.habitat} />
                  <LandCover habitat={zone.zone.habitat} />
                  <Row k="distance" v={`${zone.zone.distance_km} km (${m === "demo" && zone.zone.distance_origin === "your location" ? "from DEMO field base" : zone.zone.distance_origin})`} />
                  <RoadAccess zone={zone.zone} />
                  <Row k="nearest known record" v={zone.zone.distance_to_nearest_known_record_km == null ? "—" : zone.zone.distance_to_nearest_known_record_km < (run.resolution_deg * 111) ? "within this cell" : `${zone.zone.distance_to_nearest_known_record_km} km`} />
                </div>
                <p className="mt-2 text-[10px] text-mist">“Suitability” is environmental suitability from the models, not the probability that the species is present.</p>
                <div className="mt-4"><PriorityBreakdown p={zone.zone.priority} /></div>
                <button onClick={createMission} className="btn-signal mt-5 w-full py-3.5">Planificar expedición</button>
              </div>
            )}
            <button onClick={start} className="btn-ghost w-full">Re-run model</button>
          </div>
        )}
      </div>
    </div>
  );
}

const NAMES: Record<string, string> = { maxent: "MaxEnt", random_forest: "RF", glm: "GLM", gam: "GAM" };
const fmt = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(2));
const ms = (x: { mean: number; sd: number } | null) => (x ? `${x.mean.toFixed(2)} ± ${x.sd.toFixed(2)}` : "—");

export default function ModelPage(props: { params: { id: string } }) {
  return (
    <Suspense>
      <ModelInner {...props} />
    </Suspense>
  );
}
