"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Page } from "@/components/Shell";
import { ErrorBox, PageHeader, Provenance, Spinner } from "@/components/ui";
import { api, ApiError, keyToSlug } from "@/lib/api";
import { useApp } from "@/lib/store";

type Taxon = { key: string; source: string; scientific_name: string; rank: string; common_name: string | null;
  observations_count: number | null; photo_url: string | null; classification: Record<string, string>; provenance: string };

const SRC: Record<string, string> = { inaturalist: "iNaturalist", gbif: "GBIF", demo: "DEMO" };

export default function SpeciesSearch() {
  const { mode } = useApp();
  const [q, setQ] = useState("");
  const [res, setRes] = useState<{ results: Taxon[]; errors: { service: string; detail: string }[]; provenance: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) return setRes(null);
    const t = setTimeout(async () => {
      setLoading(true);
      setErr(null);
      try {
        setRes(await api(`/api/taxa/search?q=${encodeURIComponent(q)}&mode=${mode}`));
      } catch (e) {
        setErr((e as ApiError).message);
      } finally {
        setLoading(false);
      }
    }, 350);
    return () => clearTimeout(t);
  }, [q, mode]);

  return (
    <Page>
      <PageHeader kicker="Species search" title="WHERE COULD IT LIVE?">
        Search any taxon. BIOQUEST queries iNaturalist and GBIF{mode === "demo" ? " — in DEMO MODE only fictitious taxa exist" : ""}.
      </PageHeader>
      <input autoFocus className="input py-4 text-lg font-light" placeholder={mode === "demo" ? "Try “Demoquestia”" : "Mummucina, Mummucina exlineae…"}
        value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="mt-6 space-y-2">
        {loading && <Spinner label="querying sources" />}
        {err && <ErrorBox message={err} />}
        {res && <ErrorBox errors={res.errors} />}
        {res && !loading && res.results.length === 0 && !res.errors.length && <p className="text-sm text-mist">No taxa found.</p>}
        {res?.results.map((t) => (
          <Link key={t.key} href={`/species/${keyToSlug(t.key)}`} className="panel flex items-center gap-4 p-3 transition hover:border-signal/40">
            <div className="h-14 w-14 shrink-0 overflow-hidden rounded-xl bg-moss">
              {t.photo_url ? <img src={t.photo_url} alt="" className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center text-mist">✦</div>}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate italic text-bone">{t.scientific_name}</div>
              <div className="truncate text-xs text-mist">{t.common_name || Object.values(t.classification).slice(-3, -1).join(" › ") || "—"}</div>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <span className="label">{t.rank}</span>
                <span className="font-mono text-[10px] text-mist">via {SRC[t.source] ?? t.source}</span>
                {t.observations_count != null && <span className="font-mono text-[10px] text-mist">{t.observations_count} obs</span>}
              </div>
            </div>
            <Provenance kind={t.provenance} />
          </Link>
        ))}
      </div>
    </Page>
  );
}
