"use client";
import { useEffect, useState } from "react";
import MapView from "@/components/MapView";
import { Page } from "@/components/Shell";
import { NeedLogin, PageHeader, Provenance, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useApp } from "@/lib/store";

export default function Expeditions() {
  const { user, ready } = useApp();
  const [list, setList] = useState<any[] | null>(null);
  const [open, setOpen] = useState<any>(null);
  useEffect(() => { if (user) api("/api/expeditions").then(setList); }, [user]);
  const show = async (id: number) => setOpen(await api(`/api/expeditions/${id}`));
  if (ready && !user) return <Page><NeedLogin /></Page>;
  return (
    <Page wide>
      <PageHeader kicker="Field log" title="MY EXPEDITIONS" />
      {!list && <Spinner />}
      {list?.length === 0 && <p className="text-sm text-mist">No expeditions yet. Start one from a mission.</p>}
      <div className="grid gap-4 md:grid-cols-[1fr_1.2fr]">
        <div className="space-y-2">
          {list?.map((e) => (
            <button key={e.id} onClick={() => show(e.id)} className={`panel w-full p-4 text-left hover:border-signal/40 ${open?.id === e.id ? "border-signal/50" : ""}`}>
              <div className="flex items-center justify-between"><span className="text-bone">{e.name}</span>{e.is_demo && <Provenance kind="DEMO DATA" />}</div>
              <div className="mt-1 font-mono text-[11px] text-mist">
                {e.started_at.slice(0, 10)} · {e.distance_km} km · {e.duration_min} min · {e.observations} obs · {e.taxa} taxa · {e.status}
              </div>
            </button>
          ))}
        </div>
        {open && (
          <div className="panel overflow-hidden">
            <div className="h-72">
              <MapView center={open.route[0] ? { lat: open.route[0][1], lon: open.route[0][0] } : { lat: -12, lon: -75 }} zoom={13}
                layers={{ route: open.route, points: open.observation_list.filter((o: any) => o.lat != null).map((o: any) => ({ lat: o.lat, lon: o.lon })) }} />
            </div>
            <div className="grid grid-cols-4 gap-2 p-4 text-center font-mono text-xs">
              <div><b className="text-lg">{open.distance_km}</b><div className="label">km</div></div>
              <div><b className="text-lg">{open.habitats}</b><div className="label">habitats</div></div>
              <div><b className="text-lg">{open.observations}</b><div className="label">obs</div></div>
              <div><b className="text-lg">{open.unusual_records}</b><div className="label">unusual</div></div>
            </div>
          </div>
        )}
      </div>
    </Page>
  );
}
