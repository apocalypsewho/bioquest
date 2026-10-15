"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Page } from "@/components/Shell";
import { NeedLogin, PageHeader, Provenance, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useApp } from "@/lib/store";

export default function Discoveries() {
  const { user, ready } = useApp();
  const [list, setList] = useState<any[] | null>(null);
  const [meta, setMeta] = useState<any>(null);
  useEffect(() => {
    api("/api/discoveries/meta").then(setMeta);
    if (user) api("/api/discoveries").then(setList);
  }, [user]);
  if (ready && !user) return <Page><NeedLogin /></Page>;
  return (
    <Page>
      <PageHeader kicker="Working classification" title="YOUR DISCOVERIES">{meta?.note}</PageHeader>
      {!list && <Spinner />}
      {list?.length === 0 && <p className="text-sm text-mist">No flagged records yet. Flag an observation from its detail page.</p>}
      <div className="space-y-2">
        {list?.map((d) => (
          <Link key={d.id} href={`/observations/${d.observation_id}`} className="panel flex items-center justify-between p-4 hover:border-signal/40">
            <div>
              <div className="text-bone">{d.category_label}</div>
              <div className="font-mono text-[10px] text-mist">Evidence level {d.evidence_level} — {d.evidence_label} · {d.review_status.replace("_", " ")}</div>
              {d.rationale && <div className="mt-1 text-xs text-mist">{d.rationale}</div>}
            </div>
            {d.is_demo && <Provenance kind="DEMO DATA" />}
          </Link>
        ))}
      </div>
      {meta && (
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <div className="panel p-4 text-sm">
            <div className="label mb-2">Categories</div>
            {Object.values(meta.categories).map((c: any) => <p key={c}>{c}</p>)}
          </div>
          <div className="panel p-4 text-sm">
            <div className="label mb-2">Evidence level</div>
            {Object.entries(meta.evidence_levels).map(([k, v]) => <p key={k} className="font-mono text-xs">{k} — {v as string}</p>)}
          </div>
          <p className="text-xs text-mist md:col-span-2">{meta.disclaimer}</p>
        </div>
      )}
    </Page>
  );
}
