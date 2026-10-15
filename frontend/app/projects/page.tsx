"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Page } from "@/components/Shell";
import { ErrorBox, NeedLogin, PageHeader, Provenance } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/lib/store";

export default function Projects() {
  const { user, ready } = useApp();
  const [list, setList] = useState<any[] | null>(null);
  const [open, setOpen] = useState<any>(null);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [member, setMember] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const load = () => api("/api/projects").then(setList).catch((e: ApiError) => setErr(e.message));
  useEffect(() => { if (user) load(); }, [user]);

  const create = async () => {
    setErr(null);
    try {
      const p = await api("/api/projects", { method: "POST", json: { name, description: desc } });
      setName(""); setDesc("");
      await load();
      show(p.id);
    } catch (e) { setErr((e as ApiError).message); }
  };
  const show = async (id: number) => setOpen(await api(`/api/projects/${id}`));
  const add = async () => {
    setErr(null);
    try {
      await api(`/api/projects/${open.id}/members`, { method: "POST", json: { username: member.trim() } });
      setMember("");
      show(open.id);
      load();
    } catch (e) { setErr((e as ApiError).message); }
  };

  if (ready && !user) return <Page><NeedLogin /></Page>;
  return (
    <Page>
      <PageHeader kicker="Collaboration" title="PROJECTS">Group observations with other BIOQUEST users. Shared records keep each owner&apos;s coordinate privacy.</PageHeader>
      {err && <div className="mb-4"><ErrorBox message={err} /></div>}
      <div className="panel p-4">
        <div className="label mb-2">New project</div>
        <input className="input" placeholder="Name (e.g. Valle del Mantaro survey)" value={name} onChange={(e) => setName(e.target.value)} />
        <textarea className="input mt-2" placeholder="Description" value={desc} onChange={(e) => setDesc(e.target.value)} />
        <button disabled={name.trim().length < 2} onClick={create} className="btn-signal mt-3">Create project</button>
      </div>
      <div className="mt-6 space-y-2">
        {list?.length === 0 && <p className="text-sm text-mist">No projects yet.</p>}
        {list?.map((p) => (
          <button key={p.id} onClick={() => show(p.id)} className={`panel block w-full p-4 text-left ${open?.id === p.id ? "border-signal/50" : ""}`}>
            <div className="flex items-center justify-between"><span className="text-bone">{p.name}</span><span className="font-mono text-[10px] text-mist">{p.is_owner ? "owner" : "member"}</span></div>
            <div className="mt-1 font-mono text-[10px] text-mist">{p.members.length} members · {p.n_observations} observations</div>
          </button>
        ))}
      </div>
      {open && (
        <div className="mt-6 panel animate-rise p-4">
          <div className="label text-signal">{open.name}</div>
          {open.description && <p className="mt-1 text-sm text-mist">{open.description}</p>}
          <div className="mt-3 font-mono text-[11px] text-mist">Members: {open.members.map((m: any) => `${m.username}${m.role === "owner" ? " (owner)" : ""}`).join(", ")}</div>
          {open.is_owner && (
            <div className="mt-3 flex gap-2">
              <input className="input" placeholder="BIOQUEST username" value={member} onChange={(e) => setMember(e.target.value)} />
              <button disabled={!member.trim()} onClick={add} className="btn-ghost whitespace-nowrap">Add member</button>
            </div>
          )}
          <div className="mt-4 space-y-2">
            {open.observations.length === 0 && <p className="text-xs text-mist">No shared observations yet. Share one from its observation page.</p>}
            {open.observations.map((o: any) => (
              <div key={o.id} className="flex items-center justify-between border-t border-line/60 pt-2 text-sm">
                <div>
                  <i className="text-bone">{o.taxon_name || "Unidentified"}</i>
                  <div className="font-mono text-[10px] text-mist">by {o.shared_by} · {o.lat != null ? `${o.lat.toFixed(2)}, ${o.lon.toFixed(2)}` : "hidden"} · {o.coordinate_display}</div>
                </div>
                <div className="flex items-center gap-2">
                  <Provenance kind={o.provenance} />
                  {o.shared_by === user?.username && <Link href={`/observations/${o.id}`} className="font-mono text-[10px] text-signal">open</Link>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Page>
  );
}
