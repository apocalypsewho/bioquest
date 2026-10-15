"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ErrorBox } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/lib/store";

function Login() {
  const { setAuth } = useApp();
  const router = useRouter();
  const sp = useSearchParams();
  const [reg, setReg] = useState(false);
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      const r = await api(`/api/auth/${reg ? "register" : "login"}`, { method: "POST", json: { username: u, password: p } });
      setAuth(r.token, r.user);
      router.push(sp.get("next") || "/");
    } catch (e) { setErr((e as ApiError).message); }
  };
  return (
    <div className="flex min-h-[100dvh] items-center justify-center px-6">
      <form onSubmit={submit} className="w-full max-w-sm animate-rise">
        <div className="text-center font-mono text-sm tracking-[0.5em] text-signal glow-text">BIOQUEST</div>
        <p className="mt-2 text-center text-xs text-mist">Discover what hasn&apos;t been mapped yet.</p>
        <div className="mt-10 space-y-3">
          <input className="input" placeholder="username" autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} />
          <input className="input" type="password" placeholder="password (min 6)" autoComplete={reg ? "new-password" : "current-password"} value={p} onChange={(e) => setP(e.target.value)} />
        </div>
        {err && <div className="mt-3"><ErrorBox message={err} /></div>}
        <button className="btn-signal mt-6 w-full py-3.5">{reg ? "Create account" : "Sign in"}</button>
        <button type="button" onClick={() => setReg(!reg)} className="mt-4 w-full font-mono text-[10px] tracking-[0.2em] text-mist hover:text-signal">
          {reg ? "I HAVE AN ACCOUNT" : "CREATE AN ACCOUNT"}
        </button>
        <p className="mt-6 text-center text-[10px] text-mist/70">The first account created becomes the administrator.</p>
      </form>
    </div>
  );
}
export default function P() { return <Suspense><Login /></Suspense>; }
