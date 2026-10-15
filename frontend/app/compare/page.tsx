"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Page } from "@/components/Shell";
import { ErrorBox, NeedLogin, PageHeader, Provenance } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/lib/store";

function Compare() {
  const { mode, user, ready } = useApp();
  const sp = useSearchParams();
  const [keys, setKeys] = useState<string[]>((sp.get("keys") || "").split(",").filter(Boolean));
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<any[]>([]);
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (q.length < 2) return setHits([]);
    const t = setTimeout(() => api(`/api/taxa/search?q=${encodeURIComponent(q)}&mode=${mode}`).then((r) => setHits(r.results)).catch(() => {}), 300);
    return () => clearTimeout(t);
  }, [q, mode]);
  useEffect(() => {
    if (!keys.length || !user) return setData(null);
    const m = keys.every((k) => k.startsWith("demo:")) ? "demo" : mode;
    api(`/api/compare?keys=${encodeURIComponent(keys.join(","))}&mode=${m}`).then(setData).catch((e: ApiError) => setErr(e.message));
  }, [keys, mode, user]);

  if (ready && !user) return <Page><NeedLogin /></Page>;
  const taxa = data?.taxa ?? [];
  const ranks = ["kingdom", "phylum", "class", "order", "family", "genus"];
  return (
    <Page wide>
      <PageHeader kicker="Morphology & evidence" title="COMPARE SPECIES">Side-by-side taxonomy, photos, your own measurements and morphology notes.</PageHeader>
      <div className="relative">
        <input className="input" placeholder="Add a taxon to compare…" value={q} onChange={(e) => setQ(e.target.value)} />
        {hits.length > 0 && (
          <div className="absolute z-10 mt-1 w-full panel p-1">
            {hits.slice(0, 6).map((h) => (
              <button key={h.key} onClick={() => { setKeys(Array.from(new Set(keys.concat(h.key))).slice(0, 4)); setQ(""); }} className="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-signal/10">
                <i>{h.scientific_name}</i> <span className="font-mono text-[10px] text-mist">{h.source}</span>
              </button>
            ))}
          </div>
        )}
      </div>
      {err && <ErrorBox message={err} />}
      {taxa.length > 0 && (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr>
                <th />
                {taxa.map((t: any) => (
                  <th key={t.key} className="p-2 text-left align-top font-normal">
                    {t.taxon?.photo_url && <img src={t.taxon.photo_url} alt="" className="mb-2 h-28 w-full rounded-xl object-cover" />}
                    <i className="text-bone">{t.taxon?.scientific_name ?? t.key}</i>
                    <div className="mt-1"><Provenance kind={t.taxon?.provenance} /></div>
                    <button onClick={() => setKeys(keys.filter((k) => k !== t.key))} className="mt-1 font-mono text-[9px] text-mist">REMOVE</button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="font-mono text-[11px]">
              {ranks.map((r) => (
                <tr key={r} className="border-t border-line/60"><td className="label p-2">{r}</td>{taxa.map((t: any) => <td key={t.key} className="p-2">{t.taxon?.classification?.[r] ?? "—"}</td>)}</tr>
              ))}
              <tr className="border-t border-line/60"><td className="label p-2">your obs.</td>{taxa.map((t: any) => <td key={t.key} className="p-2">{t.your_observations}</td>)}</tr>
              <tr className="border-t border-line/60"><td className="label p-2">measurements</td>{taxa.map((t: any) => <td key={t.key} className="p-2">{Object.entries(t.your_measurements || {}).map(([k, v]: any) => `${k}: ${v.min}–${v.max} (n=${v.n})`).join("; ") || "—"}</td>)}</tr>
              <tr className="border-t border-line/60"><td className="label p-2">morphology</td>{taxa.map((t: any) => <td key={t.key} className="p-2">{(t.your_morphology_notes || []).map((m: any) => Object.entries(m).map(([k, v]) => `${k}: ${v}`).join(", ")).join(" | ") || "—"}</td>)}</tr>
              <tr className="border-t border-line/60"><td className="label p-2 align-top">literature</td>{taxa.map((t: any) => (
                <td key={t.key} className="p-2 align-top text-mist">
                  {t.literature?.provenance && <Provenance kind={t.literature.provenance} />}
                  <ul className="mt-1 space-y-1.5 font-sans text-[11px]">
                    {(t.literature?.items || []).slice(0, 6).map((it: any, i: number) => (
                      <li key={i}>
                        {it.url ? <a href={it.url} target="_blank" rel="noreferrer" className="text-bone hover:text-signal">{it.title || "untitled"}</a> : <span className="text-bone">{it.title}</span>}
                        <span className="block font-mono text-[9px]">{[it.authors, it.year, it.venue].filter(Boolean).join(" · ")} · {it.source}</span>
                      </li>
                    ))}
                  </ul>
                  {t.literature?.errors?.map((e: any, i: number) => <p key={i} className="text-danger">{e.service}: {e.detail}</p>)}
                  <p className="mt-1 text-[9px]">{t.literature?.note}</p>
                </td>
              ))}</tr>
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-6 text-[11px] text-mist">Diagnostic comparison needs type material, original descriptions and specialist review; this table only organises the evidence you have.</p>
    </Page>
  );
}
export default function P() { return <Suspense><Compare /></Suspense>; }
