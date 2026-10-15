"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import MapView from "@/components/MapView";
import { ErrorBox, Provenance, Row, Spinner } from "@/components/ui";
import { api, ApiError, photoUrl } from "@/lib/api";

const FLAGS = [
  { cat: "new_local_record", label: "🟢 New local record" },
  { cat: "range_extension", label: "🔵 Potential range extension" },
  { cat: "rare_observation", label: "🟣 Unusual / rare observation" },
  { cat: "taxonomically_unresolved", label: "🟠 Requires taxonomic review" },
  { cat: "potentially_undescribed", label: "🔴 Potential taxonomically interesting record" },
];

function Detail({ id }: { id: string }) {
  const sp = useSearchParams();
  const [o, setO] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [inat, setInat] = useState<any>(null);
  const [consent, setConsent] = useState(false);
  const [morph, setMorph] = useState<[string, string][]>([["", ""]]);
  const [disc, setDisc] = useState({ category: "", evidence_level: 0, rationale: "" });
  const [meta, setMeta] = useState<any>(null);
  const [note, setNote] = useState<string | null>(null);
  const [screen, setScreen] = useState<any>(null);
  const [screening, setScreening] = useState(false);
  const [projects, setProjects] = useState<any[]>([]);

  useEffect(() => {
    api(`/api/observations/${id}`).then((x) => {
      setO(x);
      const e = Object.entries(x.morphology || {}) as [string, string][];
      if (e.length) setMorph(e);
    }).catch((e: ApiError) => setErr(e.message));
    api("/api/inat/status").then(setInat).catch(() => {});
    api("/api/discoveries/meta").then(setMeta);
    api("/api/projects").then(setProjects).catch(() => {});
  }, [id]);

  const runScreen = async () => {
    setScreening(true);
    setErr(null);
    try {
      const r = await api(`/api/observations/${id}/assess`, { method: "POST" });
      setScreen(r);
      if (r.suggested_discovery_category) setDisc((d) => ({ ...d, category: r.suggested_discovery_category, rationale: d.rationale || r.reasons.join(" ") }));
    } catch (e) {
      const d = (e as ApiError).detail as any;
      setErr(typeof d === "string" ? d : d?.message ?? (e as ApiError).message);
    } finally {
      setScreening(false);
    }
  };
  const refreshInat = async () => {
    try {
      const r = await api(`/api/observations/${id}/inat-refresh`, { method: "POST" });
      setO(r.observation);
      setNote(`iNaturalist: ${r.quality_grade?.replace("_", " ")}${r.community_taxon ? ` · community taxon ${r.community_taxon}` : ""}${r.xp_awarded ? ` · +${r.xp_awarded} XP (validation)` : ""}`);
    } catch (e) { setErr((e as ApiError).message); }
  };
  const share = async (pid: number) => {
    try {
      const p = await api(`/api/projects/${pid}/observations`, { method: "POST", json: { observation_id: Number(id) } });
      setNote(`Shared with project “${p.name}”.`);
    } catch (e) { setErr((e as ApiError).message); }
  };

  const saveMorph = async () => {
    const morphology = Object.fromEntries(morph.filter(([k]) => k.trim()));
    setO(await api(`/api/observations/${id}`, { method: "PATCH", json: { morphology } }));
    setNote("Morphology saved.");
  };
  const submit = async () => {
    try {
      setO(await api(`/api/observations/${id}/inat-submit`, { method: "POST", json: { consent } }));
      setNote("Published to your iNaturalist account.");
    } catch (e) { setErr((e as ApiError).message); }
  };
  const flag = async () => {
    try {
      const d = await api("/api/discoveries", { method: "POST", json: { observation_id: Number(id), ...disc } });
      setNote(`Recorded as “${d.category_label}” · evidence level ${d.evidence_level} (${d.evidence_label}).${d.note ? " " + d.note : ""}`);
    } catch (e) { setErr((e as ApiError).message); }
  };

  if (!o) return <div className="px-4 pt-20">{err ? <ErrorBox message={err} /> : <Spinner />}</div>;
  return (
    <div className="mx-auto max-w-3xl px-4 pb-28 pt-20 md:pb-12">
      <div className="flex items-start justify-between">
        <div>
          <div className="label">Observation #{o.id}</div>
          <h1 className="mt-1 text-2xl font-light italic text-bone">{o.taxon_name || "Unidentified organism"}</h1>
          <p className="font-mono text-[11px] text-amber">{o.id_status.replace(/_/g, " ")}</p>
        </div>
        <Provenance kind={o.provenance} />
      </div>
      {o.photos.length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-2">
          {o.photos.map((p: any) => p.kind === "photo" ? <img key={p.id} src={photoUrl(p.url)} alt="" className="rounded-xl border border-line" />
            : <audio key={p.id} controls src={photoUrl(p.url)} className="w-full" />)}
        </div>
      )}
      {o.lat != null && <div className="mt-4 h-56 overflow-hidden rounded-2xl border border-line"><MapView center={{ lat: o.lat, lon: o.lon }} zoom={12} layers={{ points: [{ lat: o.lat, lon: o.lon }] }} /></div>}
      <div className="mt-4 panel p-4">
        <Row k="coordinates" v={o.lat != null ? `${o.lat.toFixed(5)}, ${o.lon.toFixed(5)}` : "—"} />
        <Row k="privacy" v={`${o.coordinate_privacy} · ${o.coordinate_display}`} />
        <Row k="observed" v={o.observed_at?.slice(0, 16).replace("T", " ")} />
        <Row k="habitat / micro" v={`${o.habitat || "—"} / ${o.microhabitat || "—"}`} />
        <Row k="method" v={o.method} />
        <Row k="individuals · sex" v={`${o.individual_count ?? "—"} · ${o.sex ?? "—"}`} />
        <Row k="measurements" v={Object.entries(o.measurements).map(([k, v]) => `${k}: ${v}`).join(", ") || "—"} />
        <Row k="observer" v={o.observer} />
        {o.inat_url && <Row k="iNaturalist" v={<a href={o.inat_url} target="_blank" rel="noreferrer" className="text-signal">{o.inat_observation_id} ↗</a>} />}
      </div>
      {o.notes && <p className="mt-3 text-sm text-mist">{o.notes}</p>}
      {note && <p className="mt-4 rounded-xl border border-signal/40 bg-signal/10 p-3 text-sm text-signal">{note}</p>}
      {err && <div className="mt-4"><ErrorBox message={err} /></div>}

      <section className={`mt-6 panel p-4 ${sp.get("morph") ? "border-signal/40" : ""}`}>
        <div className="label mb-3">Morphology (diagnostic characters, colouration, structures)</div>
        {morph.map(([k, v], i) => (
          <div key={i} className="mb-2 grid grid-cols-[1fr_1.4fr] gap-2">
            <input className="input" placeholder="character" value={k} onChange={(e) => setMorph(morph.map((m, j) => j === i ? [e.target.value, m[1]] : m))} />
            <input className="input" placeholder="state / value" value={v} onChange={(e) => setMorph(morph.map((m, j) => j === i ? [m[0], e.target.value] : m))} />
          </div>
        ))}
        <div className="flex gap-2">
          <button onClick={() => setMorph([...morph, ["", ""]])} className="btn-ghost">+ character</button>
          <button onClick={saveMorph} className="btn-signal">Save morphology</button>
        </div>
      </section>

      <section className="mt-6 panel p-4">
        <div className="flex items-center justify-between"><span className="label">Is this record unusual?</span>{screen && <Provenance kind={screen.provenance} />}</div>
        <p className="mt-1 text-[11px] text-mist">Compares the record with valid public occurrences ({o.is_demo ? "DEMO" : "iNaturalist + GBIF"}) and, if one exists, the latest distribution model.</p>
        {!screen && <button onClick={runScreen} disabled={screening} className="btn-ghost mt-3">{screening ? "Comparing…" : "Screen against known records"}</button>}
        {screen && (
          <div className="mt-3 text-sm">
            <div className="flex flex-wrap gap-1.5">
              {screen.flags.length ? screen.flags.map((f: string) => <span key={f} className="rounded-full border border-amber/60 px-2 py-0.5 font-mono text-[9px] tracking-widest text-amber">{f}</span>)
                : <span className="font-mono text-[10px] text-signal">No unusual signal</span>}
            </div>
            <ul className="mt-2 list-disc space-y-1 pl-4 text-[12px] text-mist">{screen.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
            <div className="mt-2">
              <Row k="valid known records" v={screen.facts.known_valid_records} />
              {screen.facts.distance_to_nearest_known_record_km != null && <Row k="nearest known record" v={`${screen.facts.distance_to_nearest_known_record_km} km`} />}
              {screen.facts.environmental_suitability != null && <Row k="environmental suitability" v={`${screen.facts.environmental_suitability} (p10 thr ${screen.facts.model_threshold_p10?.toFixed?.(2) ?? "—"})`} />}
            </div>
            <p className="mt-2 text-[10px] text-amber/80">{screen.disclaimer}</p>
          </div>
        )}
      </section>

      <section className="mt-6 panel p-4">
        <div className="label mb-2">Flag as potentially interesting</div>
        <p className="mb-3 text-[11px] text-mist">{meta?.disclaimer}</p>
        <div className="grid gap-2">
          {FLAGS.map((x) => (
            <label key={x.cat} className="flex items-center gap-2 text-sm"><input type="radio" name="cat" checked={disc.category === x.cat} onChange={() => setDisc({ ...disc, category: x.cat })} /> {x.label}</label>
          ))}
        </div>
        <select className="input mt-3" value={disc.evidence_level} onChange={(e) => setDisc({ ...disc, evidence_level: Number(e.target.value) })}>
          {meta && Object.entries(meta.evidence_levels).map(([k, v]) => <option key={k} value={k}>{k} — {v as string}</option>)}
        </select>
        <textarea className="input mt-2" placeholder="Rationale: why is it unusual? which characters / comparisons?" value={disc.rationale} onChange={(e) => setDisc({ ...disc, rationale: e.target.value })} />
        <button disabled={!disc.category} onClick={flag} className="btn-ghost mt-3">Record discovery</button>
        <p className="mt-2 text-[10px] text-mist">Working classification, not a scientific certification. Levels 4–5 require specialist review.</p>
      </section>

      <section className={`mt-6 panel p-4 ${sp.get("submit") ? "border-signal/40" : ""}`}>
        <div className="label mb-2">Submit to iNaturalist</div>
        {o.is_demo ? <p className="text-sm text-amber">DEMO observations can never be submitted to iNaturalist.</p>
          : o.inat_observation_id ? (
            <div className="text-sm">
              <p className="text-signal">Already on iNaturalist.</p>
              <button onClick={refreshInat} className="btn-ghost mt-2">Check community identification</button>
              <p className="mt-1 text-[10px] text-mist">Research Grade on iNaturalist earns the validation XP once.</p>
            </div>
          )
            : !inat?.configured ? <p className="text-sm text-mist">iNaturalist OAuth is not configured on this server (see README → API keys).</p>
              : !inat?.connected ? <p className="text-sm text-mist">Connect your iNaturalist account in <a href="/settings" className="text-signal">Settings</a> first.</p>
                : (
                  <>
                    <p className="text-sm text-mist">Connected as <b className="text-bone">@{inat.login}</b>. This will publish the observation and photos to your account with geoprivacy “{({ public: "open", approximate: "obscured", private: "private" } as any)[o.coordinate_privacy]}”.</p>
                    <label className="mt-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> I explicitly consent to publish this observation.</label>
                    <button disabled={!consent} onClick={submit} className="btn-signal mt-3">Publish to iNaturalist</button>
                  </>
                )}
      </section>

      {projects.length > 0 && (
        <section className="mt-6 panel p-4">
          <div className="label mb-2">Share with a project</div>
          <div className="flex flex-wrap gap-2">
            {projects.map((p) => <button key={p.id} onClick={() => share(p.id)} className="btn-ghost">{p.name}</button>)}
          </div>
          <p className="mt-2 text-[10px] text-mist">Members see the coordinates with your privacy setting applied ({o.coordinate_privacy}).</p>
        </section>
      )}
    </div>
  );
}

export default function Page({ params }: { params: { id: string } }) {
  return <Suspense><Detail id={params.id} /></Suspense>;
}
