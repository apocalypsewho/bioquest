"use client";
import { useState } from "react";
import { Bar } from "./ui";

export type PriorityT = {
  score: number;
  label: string;
  formula: string;
  components: { key: string; value: number | null; weight: number; effective_weight: number; used: boolean;
    description: string; parts?: Record<string, number | null> }[];
};

const NAMES: Record<string, string> = {
  suitability: "Env. suitability",
  model_agreement: "Model agreement",
  sampling_gap: "Sampling gap",
  biodiversity_potential: "Biodiversity potential",
  accessibility: "Accessibility",
  taxonomic_uncertainty: "Taxonomic uncertainty",
};

export default function PriorityBreakdown({ p, open = false }: { p: PriorityT; open?: boolean }) {
  const [show, setShow] = useState(open);
  return (
    <div>
      <button onClick={() => setShow(!show)} className="flex w-full items-end justify-between text-left">
        <div>
          <div className="label">Exploration priority score</div>
          <div className="mt-1 font-mono text-4xl font-light text-signal glow-text">
            {p.score}
            <span className="text-base text-mist">/100</span>
          </div>
        </div>
        <span className="label text-signal/80">{p.label} · {show ? "hide" : "how?"}</span>
      </button>
      {show && (
        <div className="mt-4 space-y-3 animate-rise">
          {p.components.map((c) => (
            <div key={c.key} title={c.description} className={c.used ? "" : "opacity-40"}>
              <div className="flex justify-between font-mono text-[11px]">
                <span className="text-bone">{NAMES[c.key] ?? c.key}</span>
                <span className="text-mist">
                  {c.used ? `${c.value} × ${(c.effective_weight * 100).toFixed(0)}%` : "n/a"}
                </span>
              </div>
              <div className="mt-1">
                <Bar value={c.value} />
              </div>
              <p className="mt-1 text-[10px] leading-snug text-mist/80">{c.description}</p>
              {c.parts && (
                <p className="mt-0.5 font-mono text-[10px] text-mist/70">
                  {Object.entries(c.parts).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v ?? "n/a"}`).join(" · ")}
                </p>
              )}
            </div>
          ))}
          <p className="font-mono text-[10px] text-mist">{p.formula}</p>
        </div>
      )}
    </div>
  );
}
