"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import MapView, { Occ } from "@/components/MapView";
import { ErrorBox, Provenance, Row, Spinner } from "@/components/ui";
import { api, ApiError, keyToSlug, slugToKey } from "@/lib/api";
import { useApp } from "@/lib/store";

type QC = { total: number; VALID: number; QUESTIONABLE: number; EXCLUDED: number; reasons: Record<string, number>;
  by_source: Record<string, Record<string, number>>; notes: string[] };

export default function SpeciesProfile({ params }: { params: { id: string } }) {
  const key = slugToKey(params.id);
  const { mode } = useApp();
  const [prof, setProf] = useState<any>(null);
  const [occ, setOcc] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [heat, setHeat] = useState(false);
  const [showList, setShowList] = useState(false);
  const m = key.startsWith("demo:") ? "demo" : mode;

  useEffect(() => {
    api(`/api/taxa/${encodeURIComponent(key)}?mode=${m}`).then(setProf).catch((e: ApiError) => setErr(e.message));
    api(`/api/taxa/${encodeURIComponent(key)}/occurrences?mode=${m}`).then(setOcc).catch((e: ApiError) => setErr(e.message));
  }, [key, m]);

  const records: Occ[] = occ?.records ?? [];
  const bbox = useMemo(() => {
    const pts = records.filter((r) => r.lat != null && r.qc_status !== "EXCLUDED");
    if (!pts.length) return null;
    const lats = pts.map((p) => p.lat!), lons = pts.map((p) => p.lon!);
    return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)] as [number, number, number, number];
  }, [records]);

  const t = prof?.taxon;
  const qc: QC | undefined = occ?.qc;
  const dates = records.map((r) => r.event_date).filter(Boolean).sort() as string[];

  return (
    <div className="md:grid md:h-[100dvh] md:grid-cols-[minmax(360px,440px)_1fr]">
      <div className="h-[42dvh] md:order-2 md:h-full">
        <MapView center={{ lat: -12, lon: -75 }} zoom={4} fitTo={bbox} layers={{ occurrences: records, heatmap: heat }} />
      </div>
      <div className="px-4 pb-28 pt-4 md:order-1 md:h-full md:overflow-y-auto md:pb-10 md:pt-20 scrollbar-thin">
        {err && <ErrorBox message={err} />}
        {!t && !err && <Spinner label="loading taxon" />}
        {t && (
          <div className="animate-rise">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="label">{t.rank}</div>
                <h1 className="mt-1 text-2xl font-light italic text-bone">{t.scientific_name}</h1>
                {t.common_name && <p className="text-sm text-mist">{t.common_name}</p>}
              </div>
              <Provenance kind={prof.provenance} />
            </div>
            {t.photo_url && (
              <figure className="mt-4 overflow-hidden rounded-2xl border border-line">
                <img src={t.photo_url} alt={t.scientific_name} className="max-h-64 w-full object-cover" />
                {t.photo_attribution && <figcaption className="px-3 py-1.5 text-[10px] text-mist">{t.photo_attribution} · via iNaturalist</figcaption>}
              </figure>
            )}
            <p className="mt-4 font-mono text-[11px] text-mist">
              {Object.entries(t.classification as Record<string, string>).map(([r, n]) => n).join(" › ")}
            </p>

            <div className="mt-5 panel p-4">
              {prof.stats.inaturalist && <Row k="iNaturalist georef. obs." v={prof.stats.inaturalist.georeferenced_observations} />}
              {prof.stats.inaturalist && <Row k="last iNat observation" v={prof.stats.inaturalist.last_observation ?? "—"} />}
              {prof.stats.gbif && <Row k="GBIF occurrences" v={prof.stats.gbif.records} />}
              {prof.stats.gbif?.year_range && <Row k="GBIF years" v={prof.stats.gbif.year_range.join("–")} />}
              {prof.stats.demo && <Row k="DEMO records" v={prof.stats.demo.records} />}
              {prof.stats.demo && <Row k="last record" v={prof.stats.demo.last_observation} />}
              <Row k="countries" v={(prof.stats.gbif?.countries ?? prof.stats.demo?.countries ?? []).map((c: any) => `${c.code} (${c.count})`).join(", ") || "—"} />
              <Row k="sources" v={Object.keys(prof.keys).map((s) => ({ inat: "iNaturalist", gbif: "GBIF", demo: "DEMO" } as any)[s]).join(" + ")} />
              {!dates.length ? null : <Row k="records loaded (span)" v={`${records.length} · ${dates[0]?.slice(0, 4)}–${dates[dates.length - 1]?.slice(0, 4)}`} />}
            </div>
            <ErrorBox errors={prof.errors} />
          </div>
        )}

        {occ && (
          <div className="mt-5 animate-rise">
            <div className="flex items-center justify-between">
              <span className="label">Occurrence quality control</span>
              <button onClick={() => setHeat(!heat)} className="font-mono text-[10px] tracking-widest text-mist hover:text-signal">{heat ? "POINTS" : "HEATMAP"}</button>
            </div>
            {occ.sensitive_note && <p className="mt-2 text-xs text-amber">{occ.sensitive_note}</p>}
            {qc && (
              <div className="mt-3 grid grid-cols-3 gap-2 text-center font-mono">
                <div className="rounded-xl border border-signal/30 p-2"><div className="text-lg text-signal">{qc.VALID}</div><div className="label">valid</div></div>
                <div className="rounded-xl border border-amber/30 p-2"><div className="text-lg text-amber">{qc.QUESTIONABLE}</div><div className="label">questionable</div></div>
                <div className="rounded-xl border border-danger/30 p-2"><div className="text-lg text-danger">{qc.EXCLUDED}</div><div className="label">excluded</div></div>
              </div>
            )}
            <div className="mt-3 space-y-1 text-[11px] text-mist">
              {qc && Object.entries(qc.reasons).map(([r, n]) => <p key={r}>· {r} — {n}</p>)}
              {qc?.notes.map((n) => <p key={n} className="text-mist/70">ⓘ {n}</p>)}
              {Object.entries(occ.source_info || {}).map(([s, i]: any) => (
                <p key={s} className="text-mist/70">ⓘ {s}: fetched {i.fetched}{i.total_georeferenced != null ? ` of ${i.total_georeferenced}` : ""}{i.total_with_coordinates != null ? ` of ${i.total_with_coordinates} with coords; ${i.without_coordinates} without coordinates (not mappable)` : ""}{i.truncated ? " — truncated" : ""}</p>
              ))}
            </div>
            <p className="mt-2 font-mono text-[10px] text-mist">Legend: ● filled = VALID · amber ring = QUESTIONABLE · red hollow = EXCLUDED. Nothing is deleted.</p>
            <button onClick={() => setShowList(!showList)} className="mt-2 font-mono text-[10px] tracking-widest text-signal">{showList ? "HIDE" : "SHOW"} FLAGGED RECORDS</button>
            {showList && (
              <div className="mt-2 max-h-64 space-y-1 overflow-y-auto scrollbar-thin">
                {records.filter((r) => r.qc_status !== "VALID").map((r) => (
                  <div key={r.uid} className="rounded-lg border border-line p-2 font-mono text-[10px]">
                    <span className={r.qc_status === "EXCLUDED" ? "text-danger" : "text-amber"}>{r.qc_status}</span> {r.uid}
                    {r.url && <a href={r.url} target="_blank" rel="noreferrer" className="ml-2 text-signal">↗</a>}
                    <div className="text-mist">{r.qc_reasons?.join(" · ")}</div>
                  </div>
                ))}
              </div>
            )}
            <ErrorBox errors={occ.errors} />
          </div>
        )}

        {t && (
          <div className="mt-6 flex flex-col gap-2">
            <Link href={`/species/${keyToSlug(key)}/model`} className="btn-signal w-full py-3.5">Model its distribution</Link>
            <Link href={`/compare?keys=${encodeURIComponent(key)}`} className="btn-ghost w-full">Compare species</Link>
          </div>
        )}
      </div>
    </div>
  );
}
