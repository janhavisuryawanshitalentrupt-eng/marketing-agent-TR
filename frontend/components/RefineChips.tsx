"use client";

import { useState } from "react";

// Quick one-tap refinements shown under an image reply. Each sends a plain follow-up prompt, which the
// agent already understands (it regenerates / adjusts the last image). "More options" reveals extra chips
// inline (no dropdown positioning to go wrong).
const PRIMARY = [
  { label: "Make it square", prompt: "Make a square (1:1) version of this image.", icon: SquareIcon },
  { label: "Add company logo", prompt: "Add our company logo to this image.", icon: BuildingIcon },
  { label: "Use different colors", prompt: "Try a different colour palette for this image.", icon: PaletteIcon },
];
const MORE = [
  { label: "Make it vertical", prompt: "Make a vertical (portrait, 4:5) version of this image." },
  { label: "Punchier headline", prompt: "Rewrite the headline on this image to be punchier." },
  { label: "Cleaner & minimal", prompt: "Make this image cleaner and more minimal." },
  { label: "Add a tagline", prompt: "Add a short tagline to this image." },
];

export function RefineChips({ onPick, disabled }: { onPick: (prompt: string) => void; disabled?: boolean }) {
  const [more, setMore] = useState(false);
  const chip =
    "inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-muted shadow-sm transition hover:border-[var(--brand-red)] hover:text-foreground disabled:cursor-default disabled:opacity-50";
  return (
    <div className="flex flex-wrap gap-2 pt-0.5">
      {PRIMARY.map((c) => {
        const Icon = c.icon;
        return (
          <button key={c.label} type="button" disabled={disabled} onClick={() => onPick(c.prompt)} className={chip}>
            <Icon />
            <span>{c.label}</span>
          </button>
        );
      })}
      {more &&
        MORE.map((c) => (
          <button key={c.label} type="button" disabled={disabled} onClick={() => onPick(c.prompt)} className={chip}>
            <span>{c.label}</span>
          </button>
        ))}
      <button type="button" disabled={disabled} onClick={() => setMore((m) => !m)} className={chip}>
        <GridIcon />
        <span>{more ? "Fewer options" : "More options"}</span>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" className={`transition ${more ? "rotate-180" : ""}`}><path d="M6 9l6 6 6-6" /></svg>
      </button>
    </div>
  );
}

function SquareIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" /></svg>;
}
function BuildingIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 21h18M6 21V5a2 2 0 012-2h4a2 2 0 012 2v16M18 21V11a1 1 0 00-1-1h-3M9 7h2M9 11h2M9 15h2" /></svg>;
}
function PaletteIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3a9 9 0 100 18 2 2 0 002-2 2 2 0 011.5-3.4H18a3 3 0 003-3A6 6 0 0012 3z" /><circle cx="7.5" cy="10.5" r="1" fill="currentColor" /><circle cx="12" cy="7.5" r="1" fill="currentColor" /><circle cx="16.5" cy="10.5" r="1" fill="currentColor" /></svg>;
}
function GridIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></svg>;
}
