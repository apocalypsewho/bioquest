"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Page } from "@/components/Shell";
import { Bar, ErrorBox, NeedLogin, PageHeader, Provenance, Spinner, Stat } from "@/components/ui";
import { api, ApiError, photoUrl } from "@/lib/api";
import { useApp } from "@/lib/store";

const XP_LABEL: Record<string, string> = { explore: "Explore", observation: "Observation", new_locality: "New locality",
  rare_species: "Rare species", validation: "Validation", scientific_finding: "Relevant scientific finding", well_documented: "Well documented record" };

export default function Profile() {
  const { user, ready } = useApp();
  const [p, setP] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (user) api("/api/profile").then(setP).catch((e: ApiError) => setErr(e.message)); }, [user]);
  if (ready && !user) return <Page><NeedLogin /></Page>;
  if (!p) return <Page>{err ? <ErrorBox message={err} /> : <Spinner />}</Page>;
  const prevLvl = 50 * (p.user.level - 1) ** 2;
  return (
    <Page wide>
      <PageHeader kicker={`@${p.user.username}`} title="MY BIODIVERSITY" />
      <div className="panel p-5">
        <div className="flex items-end justify-between">
          <div><div className="label">Level {p.user.level}</div><div className="mt-1 font-mono text-3xl text-signal glow-text">{p.user.xp} XP</div></div>
          <span className="font-mono text-[10px] text-mist">next level at {p.user.next_level_xp} XP</span>
        </div>
        <div className="mt-3"><Bar value={((p.user.xp - prevLvl) / (p.user.next_level_xp - prevLvl)) * 100} /></div>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-4 panel p-5 md:grid-cols-7">
        <Stat label="observations" value={p.stats.observations} />
        <Stat label="species" value={p.stats.species} />
        <Stat label="localities" value={p.stats.localities} />
        <Stat label="expeditions" value={p.stats.expeditions} />
        <Stat label="photos" value={p.stats.photos} />
        <Stat label="finds" value={p.stats.discoveries} />
        <Stat label="missions done" value={p.stats.missions_completed} />
      </div>
      {p.stats.demo_records > 0 && <p className="mt-2 font-mono text-[10px] text-amber">{p.stats.demo_records} of your records are DEMO records.</p>}

      <h2 className="label mt-8 mb-3">Recent observations</h2>
      {p.recent_observations.length === 0 && <p className="text-sm text-mist">None yet — <Link href="/observations/new" className="text-signal">record your first find</Link>.</p>}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {p.recent_observations.map((o: any) => (
          <Link key={o.id} href={`/observations/${o.id}`} className="panel overflow-hidden hover:border-signal/40">
            <div className="aspect-[4/3] bg-moss">{o.photos[0]?.kind === "photo" ? <img src={photoUrl(o.photos[0].url)} alt="" className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center text-mist">✦</div>}</div>
            <div className="p-2.5"><div className="truncate text-sm italic">{o.taxon_name || "Unidentified"}</div><Provenance kind={o.provenance} className="mt-1" /></div>
          </Link>
        ))}
      </div>

      <div className="mt-8 grid gap-4 md:grid-cols-2">
        <div className="panel p-4">
          <div className="label mb-2">XP log</div>
          {p.xp_events.map((e: any, i: number) => (
            <div key={i} className="flex justify-between border-b border-line/50 py-1.5 font-mono text-[11px] last:border-0">
              <span>{XP_LABEL[e.kind] ?? e.kind}</span><span className="text-signal">+{e.points}</span>
            </div>
          ))}
        </div>
        <div className="panel p-4 text-[11px] text-mist">
          <div className="label mb-2">How XP works</div>
          {Object.entries(p.xp_rules).map(([k, v]) => <p key={k} className="flex justify-between font-mono"><span>{XP_LABEL[k] ?? k}</span><span>+{v as number}</span></p>)}
          <p className="mt-3">XP rewards data quality, new localities, documentation and verified identifications — not the number of organisms. BIOQUEST never rewards collecting animals.</p>
        </div>
      </div>
    </Page>
  );
}
