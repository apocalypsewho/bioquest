"use client";
import { useState } from "react";
import { ApiError, downloadFile } from "@/lib/api";

type Props = {
  /** API path without query string, e.g. /api/observations/export */
  path: string;
  /** Offer the exact-coordinates option (only for the user's own records). */
  allowExact?: boolean;
  title?: string;
};

const LICENSES = [
  { id: "cc-by-nc", label: "CC BY-NC 4.0" },
  { id: "cc-by", label: "CC BY 4.0" },
  { id: "cc0", label: "CC0 1.0" },
];

/** Darwin Core export panel: CSV for spreadsheets, Darwin Core Archive for GBIF IPT / journals. */
export function DwcExport({ path, allowExact = false, title = "Export (Darwin Core)" }: Props) {
  const [coords, setCoords] = useState<"public" | "exact">("public");
  const [license, setLicense] = useState("cc-by-nc");
  const [demo, setDemo] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const go = async (format: "csv" | "dwca") => {
    setBusy(format); setErr(null); setMsg(null);
    const q = new URLSearchParams({ format, license, include_demo: String(demo) });
    if (allowExact) q.set("coordinates", coords);
    try {
      const n = await downloadFile(`${path}?${q}`, format === "csv" ? "bioquest-dwc.csv" : "bioquest-dwca.zip");
      setMsg(n === null ? "Download ready." : `${n} record${n === 1 ? "" : "s"} exported.`);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <details className="panel p-4">
      <summary className="label cursor-pointer select-none">{title}</summary>
      <div className="mt-3 space-y-3 text-sm">
        {allowExact && (
          <fieldset className="space-y-1">
            <legend className="font-mono text-[10px] uppercase text-mist">Coordinates</legend>
            <label className="flex items-start gap-2">
              <input type="radio" name="dwc-coords" checked={coords === "public"} onChange={() => setCoords("public")} />
              <span><span className="text-bone">Shareable</span> <span className="text-mist">— privacy rules applied (approximate → 0.1°, sensitive taxa → 0.2°, private → withheld). Safe for GBIF or co-workers.</span></span>
            </label>
            <label className="flex items-start gap-2">
              <input type="radio" name="dwc-coords" checked={coords === "exact"} onChange={() => setCoords("exact")} />
              <span><span className="text-bone">Exact</span> <span className="text-mist">— your original GPS points, for your own use (manuscript data, collection catalogue). Do not publish as-is.</span></span>
            </label>
          </fieldset>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2">
            <span className="font-mono text-[10px] uppercase text-mist">License</span>
            <select className="input w-auto py-1" value={license} onChange={(e) => setLicense(e.target.value)}>
              {LICENSES.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 text-mist">
            <input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} /> include DEMO records
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          <button disabled={!!busy} onClick={() => go("dwca")} className="btn-signal">{busy === "dwca" ? "Preparing…" : "Darwin Core Archive (.zip)"}</button>
          <button disabled={!!busy} onClick={() => go("csv")} className="btn-ghost">{busy === "csv" ? "Preparing…" : "CSV"}</button>
        </div>
        <p className="text-xs text-mist">The archive (occurrence.txt + meta.xml + eml.xml) can be uploaded to a GBIF IPT or attached as supplementary data to a manuscript.</p>
        {msg && <p className="text-xs text-cyan">{msg}</p>}
        {err && <p className="text-xs text-danger">{err}</p>}
      </div>
    </details>
  );
}
