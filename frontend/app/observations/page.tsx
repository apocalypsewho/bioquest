"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Page } from "@/components/Shell";
import { ErrorBox, NeedLogin, PageHeader, Provenance, Spinner } from "@/components/ui";
import { api, ApiError, photoUrl } from "@/lib/api";
import { listQueue } from "@/lib/offline";
import { useApp } from "@/lib/store";

export default function Observations() {
  const { user, ready, pending, syncNow, online } = useApp();
  const [list, setList] = useState<any[] | null>(null);
  const [queued, setQueued] = useState<any[]>([]);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (user) api("/api/observations").then(setList).catch((e: ApiError) => setErr(e.message));
    listQueue().then(setQueued);
  }, [user, pending]);
  if (ready && !user) return <Page><NeedLogin /></Page>;
  return (
    <Page>
      <PageHeader kicker="Field records" title="OBSERVATIONS" />
      <Link href="/observations/new" className="btn-signal mb-6 w-full py-3.5">New find</Link>
      {queued.length > 0 && (
        <div className="mb-4 panel flex items-center justify-between p-3 text-sm">
          <span className="text-cyan">{queued.length} saved on this device, waiting to sync</span>
          <button disabled={!online} onClick={syncNow} className="btn-ghost py-1.5">Sync now</button>
        </div>
      )}
      {err && <ErrorBox message={err} />}
      {!list && !err && <Spinner />}
      {list?.length === 0 && <p className="text-sm text-mist">No observations yet.</p>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        {list?.map((o) => (
          <Link key={o.id} href={`/observations/${o.id}`} className="panel overflow-hidden transition hover:border-signal/40">
            <div className="aspect-square bg-moss">
              {o.photos.find((p: any) => p.kind === "photo") ? <img src={photoUrl(o.photos.find((p: any) => p.kind === "photo").url)} alt="" className="h-full w-full object-cover" />
                : <div className="flex h-full items-center justify-center text-2xl text-mist">✦</div>}
            </div>
            <div className="p-3">
              <div className="truncate text-sm italic text-bone">{o.taxon_name || "Unidentified"}</div>
              <div className="mt-1 flex items-center justify-between gap-1">
                <span className="font-mono text-[9px] text-mist">{o.observed_at?.slice(0, 10)}</span>
                <Provenance kind={o.provenance} />
              </div>
            </div>
          </Link>
        ))}
      </div>
    </Page>
  );
}
