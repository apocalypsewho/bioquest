"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Page } from "@/components/Shell";
import { ErrorBox, NeedLogin, PageHeader, Provenance, Row, Stat } from "@/components/ui";
import { api, ApiError, keyToSlug } from "@/lib/api";
import { useApp } from "@/lib/store";

export default function Admin() {
  const { user, ready } = useApp();
  const [o, setO] = useState<any>(null);
  const [src, setSrc] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (user) api("/api/admin/overview").then(setO).catch((e: ApiError) => setErr(e.message));
    api("/api/sources").then(setSrc);
  }, [user]);
  if (ready && !user) return <Page><NeedLogin /></Page>;
  return (
    <Page wide>
      <PageHeader kicker="Model & data administration" title="ADMIN" />
      {err && <ErrorBox message={err} />}
      {o && (
        <>
          <div className="panel grid grid-cols-2 gap-4 p-5 md:grid-cols-4">
            <Stat label="users" value={o.users} />
            <Stat label="observations" value={o.observations} />
            <Stat label="cached occurrences" value={o.occurrences_cached} />
            <Stat label="QC" value={<span className="text-sm">{Object.entries(o.occurrences_by_qc).map(([k, v]) => `${k} ${v}`).join(" · ")}</span>} />
          </div>
          <h2 className="label mb-2 mt-6">Model runs</h2>
          <div className="space-y-2">
            {o.model_runs.map((r: any) => (
              <Link key={r.id} href={`/species/${keyToSlug(r.taxon_key ?? "")}/model?run=${r.id}`} className="panel flex items-center justify-between p-3 font-mono text-xs hover:border-signal/40">
                <span>#{r.id} <i className="text-bone">{r.taxon}</i> · {r.status} · n={r.n_used} · env {r.env} · {r.created_at.slice(0, 16)}</span>
                <Provenance kind={r.provenance} />
              </Link>
            ))}
          </div>
        </>
      )}
      {src && (
        <div className="mt-6 panel p-5">
          <div className="label mb-2">Environmental data providers</div>
          {Object.values(src.environment).map((e: any) => (
            <div key={e.code} className="border-b border-line/50 py-2 last:border-0">
              <Row k={e.label} v={e.available ? "available" : e.status} />
              {e.citation && <p className="text-[10px] text-mist">{e.citation}</p>}
              {e.variables.length > 0 && <p className="font-mono text-[10px] text-mist">{e.variables.map((v: any) => v.code).join(", ")} · native {e.native_resolution_deg.toFixed(3)}°</p>}
            </div>
          ))}
        </div>
      )}
    </Page>
  );
}
