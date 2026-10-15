"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Page } from "@/components/Shell";
import { ErrorBox, PageHeader, Row } from "@/components/ui";
import { api, API_URL, ApiError } from "@/lib/api";
import { useApp } from "@/lib/store";

function Settings() {
  const { mode, setMode, user, setAuth, refreshUser } = useApp();
  const sp = useSearchParams();
  const router = useRouter();
  const [inat, setInat] = useState<any>(null);
  const [ping, setPing] = useState<any>(null);
  const [src, setSrc] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (user) api("/api/inat/status").then(setInat).catch(() => {});
    api("/api/sources").then(setSrc).catch((e: ApiError) => setErr(e.message));
  }, [user]);

  const connect = async () => {
    try { window.location.href = (await api("/api/inat/oauth/start")).url; } catch (e) { setErr((e as ApiError).message); }
  };
  const disconnect = async () => { await api("/api/inat", { method: "DELETE" }); setInat({ ...inat, connected: false }); };
  const privacy = async (v: string) => { await api("/api/auth/me", { method: "PATCH", json: { default_coordinate_privacy: v } }); refreshUser(); };

  return (
    <Page>
      <PageHeader kicker="Configuration" title="SETTINGS" />
      {sp.get("inat") === "connected" && <p className="mb-4 rounded-xl border border-signal/40 bg-signal/10 p-3 text-sm text-signal">iNaturalist connected.</p>}
      {err && <ErrorBox message={err} />}

      <section className="panel p-5">
        <div className="label mb-3">Data mode</div>
        <div className="grid grid-cols-2 gap-2">
          <button onClick={() => setMode("live")} className={mode === "live" ? "btn-signal" : "btn-ghost"}>Live data</button>
          <button onClick={() => setMode("demo")} className={mode === "demo" ? "btn bg-amber text-void" : "btn-ghost"}>Demo mode</button>
        </div>
        <p className="mt-3 text-xs text-mist">LIVE queries iNaturalist and GBIF from the BIOQUEST server. DEMO uses fictitious taxa, points and a synthetic environment, always labelled DEMO and never mixed with real data.</p>
        <button onClick={async () => setPing(await api("/api/sources/ping"))} className="btn-ghost mt-3">Test live sources</button>
        {ping && Object.entries(ping).map(([k, v]: any) => (
          <p key={k} className={`mt-2 font-mono text-xs ${v.reachable ? "text-signal" : "text-danger"}`}>{k}: {v.reachable ? "reachable" : `unreachable — ${v.detail}`}</p>
        ))}
      </section>

      {user && (
        <section className="mt-4 panel p-5">
          <div className="label mb-3">iNaturalist</div>
          {!inat ? null : !inat.configured ? (
            <p className="text-sm text-mist">OAuth is not configured on this server. Set BIOQUEST_INAT_CLIENT_ID / SECRET (see README).</p>
          ) : inat.connected ? (
            <div className="flex items-center justify-between"><span className="text-sm">Connected as <b>@{inat.login}</b></span><button onClick={disconnect} className="btn-ghost">Disconnect</button></div>
          ) : (
            <button onClick={connect} className="btn-signal">Connect iNaturalist</button>
          )}
          <p className="mt-3 text-[11px] text-mist">BIOQUEST never publishes anything without your explicit consent for each observation.</p>
        </section>
      )}

      {user && (
        <section className="mt-4 panel p-5">
          <div className="label mb-3">Default coordinate privacy</div>
          <div className="grid grid-cols-3 gap-2">
            {["public", "approximate", "private"].map((v) => (
              <button key={v} onClick={() => privacy(v)} className={user.default_coordinate_privacy === v ? "btn-signal" : "btn-ghost"}>{v}</button>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-mist">Approximate = generalised to a 0.1° cell for others. Sensitive taxa are always generalised to 0.2°. Your exact position is never shown to other users.</p>
        </section>
      )}

      {src && (
        <section className="mt-4 panel p-5">
          <div className="label mb-2">Sources</div>
          <Row k="API" v={API_URL} />
          <Row k="iNaturalist OAuth" v={src.inaturalist.oauth_configured ? "configured" : "not configured"} />
          {Object.values(src.environment).map((e: any) => (
            <Row key={e.code} k={e.label} v={<span className={e.available ? "text-signal" : "text-mist"}>{e.available ? "available" : e.status}</span>} />
          ))}
          {src.land_cover && <Row k={src.land_cover.label} v={<span className={src.land_cover.available ? "text-signal" : "text-mist"}>{src.land_cover.available ? "available" : src.land_cover.status}</span>} />}
          {src.roads && <Row k="Roads & trails" v={src.roads.attribution} />}
        </section>
      )}

      {user && (
        <section className="mt-4 panel flex items-center justify-between p-5">
          <span className="text-sm">Signed in as <b>{user.username}</b> ({user.role})</span>
          <button onClick={() => { setAuth(null, null); router.push("/"); }} className="btn-ghost">Sign out</button>
        </section>
      )}
    </Page>
  );
}

export default function P() { return <Suspense><Settings /></Suspense>; }
