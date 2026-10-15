"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, Mode } from "./api";
import { flushQueue, queueSize } from "./offline";

export type User = { id: number; username: string; display_name: string; role: string; xp: number;
  default_coordinate_privacy: string };
export type LatLon = { lat: number; lon: number; source: "gps" | "demo" | "map" };

type Ctx = {
  mode: Mode;
  setMode: (m: Mode) => void;
  user: User | null;
  setAuth: (token: string | null, user: User | null) => void;
  refreshUser: () => Promise<void>;
  location: LatLon | null;
  locate: () => Promise<LatLon | null>;
  online: boolean;
  pending: number;
  syncNow: () => Promise<void>;
  ready: boolean;
};

const AppCtx = createContext<Ctx | null>(null);

const DEMO_ORIGIN: LatLon = { lat: -11.95, lon: -75.25, source: "demo" };

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<Mode>("demo");
  const [user, setUser] = useState<User | null>(null);
  const [gps, setGps] = useState<LatLon | null>(null);
  const [online, setOnline] = useState(true);
  const [pending, setPending] = useState(0);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const m = localStorage.getItem("bq_mode") as Mode | null;
      if (m) setModeState(m);
    } catch {}
    setOnline(navigator.onLine);
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    api("/api/auth/me").then(setUser).catch(() => setUser(null)).finally(() => setReady(true));
    queueSize().then(setPending);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);

  const syncNow = useCallback(async () => {
    await flushQueue();
    setPending(await queueSize());
  }, []);

  useEffect(() => {
    if (online && user) syncNow();
  }, [online, user, syncNow]);

  useEffect(() => {
    const t = setInterval(() => queueSize().then(setPending), 4000);
    return () => clearInterval(t);
  }, []);

  const setMode = (m: Mode) => {
    setModeState(m);
    try {
      localStorage.setItem("bq_mode", m);
    } catch {}
  };

  const setAuth = (token: string | null, u: User | null) => {
    try {
      if (token) localStorage.setItem("bq_token", token);
      else localStorage.removeItem("bq_token");
    } catch {}
    setUser(u);
  };

  const refreshUser = async () => {
    try {
      setUser(await api("/api/auth/me"));
    } catch {}
  };

  const locate = useCallback(
    () =>
      new Promise<LatLon | null>((resolve) => {
        if (!navigator.geolocation) return resolve(null);
        navigator.geolocation.getCurrentPosition(
          (p) => {
            const l = { lat: p.coords.latitude, lon: p.coords.longitude, source: "gps" as const };
            setGps(l);
            resolve(l);
          },
          () => resolve(null),
          { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
        );
      }),
    [],
  );

  // In DEMO MODE everything happens around a fictitious field base, never your real position.
  const location = mode === "demo" ? DEMO_ORIGIN : gps;

  return (
    <AppCtx.Provider value={{ mode, setMode, user, setAuth, refreshUser, location, locate, online, pending, syncNow, ready }}>
      {children}
    </AppCtx.Provider>
  );
}

export function useApp() {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside provider");
  return c;
}
