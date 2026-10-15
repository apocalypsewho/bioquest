"use client";
import { useEffect } from "react";

/** Registers /sw.js in production builds so the app shell opens offline. */
export default function SWRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }, []);
  return null;
}
