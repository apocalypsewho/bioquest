"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ErrorBox, NeedLogin, Provenance } from "@/components/ui";
import { api, API_URL, ApiError } from "@/lib/api";
import { enqueue, uploadMedia, uuid } from "@/lib/offline";
import { useApp } from "@/lib/store";

function NewFind() {
  const { user, ready, mode, location, locate } = useApp();
  const sp = useSearchParams();
  const router = useRouter();
  const [photo, setPhoto] = useState<File | null>(null);
  const [audio, setAudio] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [ai, setAi] = useState<any>(null);
  const [pos, setPos] = useState<{ lat: number; lon: number; acc?: number; alt?: number | null } | null>(null);
  const [f, setF] = useState({ taxon_name: "", notes: "", habitat: "", microhabitat: "", temperature_c: "", method: "visual observation",
    individual_count: "1", sex: "", length_mm: "", coordinate_privacy: "", observer: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (mode === "demo" && location) setPos({ lat: location.lat + 0.01, lon: location.lon - 0.012, acc: 8, alt: null });
    else if (navigator.geolocation)
      navigator.geolocation.getCurrentPosition((p) => setPos({ lat: p.coords.latitude, lon: p.coords.longitude, acc: p.coords.accuracy, alt: p.coords.altitude }),
        () => setPos(null), { enableHighAccuracy: true, timeout: 10000 });
  }, [mode, location, locate]);

  const onPhoto = async (file: File | undefined) => {
    if (!file) return;
    setPhoto(file);
    setPreview(URL.createObjectURL(file));
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mode", mode);
    try {
      const r = await fetch(`${API_URL}/api/ai/suggest`, { method: "POST", body: fd });
      const s = await r.json();
      setAi(s);
      if (s.suggestions?.[0] && !f.taxon_name) setF((x) => ({ ...x, taxon_name: `${s.suggestions[0].name} sp.` }));
    } catch {
      setAi({ available: false, message: "AI suggestion unavailable offline." });
    }
  };

  const body = () => ({
    expedition_id: sp.get("expedition") ? Number(sp.get("expedition")) : null,
    mission_id: sp.get("mission") ? Number(sp.get("mission")) : null,
    taxon_name: f.taxon_name || null, lat: pos?.lat ?? null, lon: pos?.lon ?? null, accuracy_m: pos?.acc ?? null,
    altitude_m: pos?.alt ?? null, notes: f.notes, habitat: f.habitat, microhabitat: f.microhabitat,
    temperature_c: f.temperature_c ? Number(f.temperature_c) : null, method: f.method,
    individual_count: f.individual_count ? Number(f.individual_count) : null, sex: f.sex || null,
    measurements: f.length_mm ? { body_length_mm: Number(f.length_mm) } : {},
    coordinate_privacy: f.coordinate_privacy || null, observer: f.observer, observed_at: new Date().toISOString(),
    ai_suggestion: ai?.available ? ai : null, is_demo: mode === "demo",
  });

  const save = async (then?: (id: number) => void) => {
    setSaving(true);
    setErr(null);
    const client_uuid = uuid();
    const media = [photo, audio].filter(Boolean).map((m) => ({ name: m!.name, type: m!.type, blob: m! as Blob }));
    try {
      if (!navigator.onLine) throw new ApiError(0, "offline");
      const o = await api("/api/observations", { method: "POST", json: { ...body(), client_uuid } });
      await uploadMedia(o.id, media);
      setMsg(`Saved · +${o.xp_awarded.reduce((a: number, x: any) => a + x.points, 0)} XP`);
      then ? then(o.id) : setTimeout(() => router.push(`/observations/${o.id}`), 700);
    } catch (e) {
      if ((e as ApiError).status === 0) {
        await enqueue({ client_uuid, observation: body(), media });
        setMsg("No connection: saved on this device. It will sync automatically when you are back online.");
      } else setErr((e as ApiError).message);
    } finally {
      setSaving(false);
    }
  };

  if (ready && !user) return <div className="px-4 pt-20"><NeedLogin /></div>;
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });

  return (
    <div className="mx-auto max-w-2xl pb-28 md:pb-12">
      <label className="relative block aspect-[4/3] w-full cursor-pointer overflow-hidden bg-moss md:mt-16 md:rounded-b-3xl">
        {preview ? <img src={preview} alt="" className="h-full w-full object-cover" /> : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-mist">
            <span className="text-4xl">◉</span><span className="label">Tap to take / choose a photo</span>
          </div>
        )}
        <input type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => onPhoto(e.target.files?.[0])} />
        <div className="absolute left-4 top-16 font-mono text-xs tracking-[0.35em] text-bone md:top-4">NEW FIND</div>
      </label>

      <div className="space-y-4 px-4 pt-5">
        <div className="panel p-4">
          <div className="flex items-center justify-between">
            <span className="label">Suggested taxon</span>
            {ai && <span className="font-mono text-[9px] tracking-widest text-violet">{ai.label ?? "AI suggestion"}</span>}
          </div>
          <input className="input mt-2 text-lg italic" placeholder="e.g. Mummucina sp." value={f.taxon_name} onChange={set("taxon_name")} />
          {ai?.available && ai.suggestions?.[0] && (
            <div className="mt-2 font-mono text-[11px] text-mist">
              Confidence: <span className="text-bone">{Math.round(ai.suggestions[0].confidence * 100)}%</span> · Status: <span className="text-amber">Needs identification</span>
              {ai.characters_to_check && <p className="mt-1">Check: {ai.characters_to_check.join(", ")}</p>}
              <Provenance kind={ai.provenance} className="mt-2" />
            </div>
          )}
          {ai && !ai.available && <p className="mt-2 text-[11px] text-mist">{ai.message}</p>}
          <p className="mt-2 text-[10px] text-mist/70">AI output is a suggestion, never a confirmed identification.</p>
        </div>

        <div className="panel grid grid-cols-2 gap-3 p-4 font-mono text-[11px]">
          <div><div className="label">GPS</div>{pos ? `${pos.lat.toFixed(5)}, ${pos.lon.toFixed(5)}` : "acquiring…"}{mode === "demo" && <div className="text-amber">DEMO position</div>}</div>
          <div><div className="label">accuracy / alt.</div>{pos?.acc ? `±${Math.round(pos.acc)} m` : "—"} · {pos?.alt ? `${Math.round(pos.alt)} m` : "—"}</div>
          <div><div className="label">time</div>{new Date().toLocaleString()}</div>
          <div>
            <div className="label">coordinates</div>
            <select className="input mt-1 py-1.5 text-xs" value={f.coordinate_privacy} onChange={set("coordinate_privacy")}>
              <option value="">default ({user?.default_coordinate_privacy})</option>
              <option value="public">public (exact)</option>
              <option value="approximate">approximate (0.1°)</option>
              <option value="private">private</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <input className="input" placeholder="Habitat" value={f.habitat} onChange={set("habitat")} />
          <input className="input" placeholder="Microhabitat" value={f.microhabitat} onChange={set("microhabitat")} />
          <input className="input" placeholder="Temperature °C" inputMode="decimal" value={f.temperature_c} onChange={set("temperature_c")} />
          <select className="input" value={f.method} onChange={set("method")}>
            <option>visual observation</option><option>photograph</option><option>UV light</option><option>pitfall (permitted)</option>
            <option>beating sheet</option><option>sound recording</option><option>other</option>
          </select>
          <input className="input" placeholder="Individuals" inputMode="numeric" value={f.individual_count} onChange={set("individual_count")} />
          <select className="input" value={f.sex} onChange={set("sex")}>
            <option value="">Sex (if applicable)</option><option>male</option><option>female</option><option>juvenile</option><option>unknown</option>
          </select>
          <input className="input" placeholder="Body length (mm)" inputMode="decimal" value={f.length_mm} onChange={set("length_mm")} />
          <input className="input" placeholder={`Observer (${user?.display_name ?? ""})`} value={f.observer} onChange={set("observer")} />
        </div>
        <textarea className="input min-h-24" placeholder="Notes" value={f.notes} onChange={set("notes")} />
        <label className="block text-xs text-mist">Audio (optional) <input type="file" accept="audio/*" className="mt-1 block text-xs" onChange={(e) => setAudio(e.target.files?.[0] ?? null)} /></label>

        {msg && <p className="rounded-xl border border-signal/40 bg-signal/10 p-3 text-sm text-signal">{msg}</p>}
        {err && <ErrorBox message={err} />}
        <div className="grid grid-cols-2 gap-2">
          <button disabled={saving} onClick={() => save()} className="btn-signal py-3.5">Save</button>
          <button disabled={saving} onClick={() => save((id) => router.push(`/observations/${id}?submit=1`))} className="btn-ghost py-3.5">Submit to iNaturalist</button>
          <button disabled={saving} onClick={() => save((id) => router.push(`/compare?keys=&obs=${id}`))} className="btn-ghost">Compare</button>
          <button disabled={saving} onClick={() => save((id) => router.push(`/observations/${id}?morph=1`))} className="btn-ghost">Add morphology</button>
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return <Suspense><NewFind /></Suspense>;
}
