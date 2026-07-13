"use client";

import { useState } from "react";

// Quick one-tap refinements shown under an image reply. Each sends a plain follow-up prompt, which the
// agent already understands (it regenerates / adjusts the last image). "More options" reveals extra chips
// inline (no dropdown positioning to go wrong). Two sets: generic image tweaks, and — for an EMPLOYEE
// post — look-oriented options that drive the AI portrait engine (new pose/setting/wardrobe) so the user
// can quickly get a DIFFERENT image if they don't like the one they got.
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

// Employee / person posts: options that re-run the AI portrait with a different look (same face).
const PERSON_PRIMARY = [
  { label: "Try a different look", prompt: "Regenerate this featuring the same person, but a completely different look — new pose, setting and style.", icon: SparkIcon },
  { label: "More formal", prompt: "Make it more formal — put them in a sharp suit or blazer and a polished professional setting (same person, same face).", icon: SuitIcon },
  { label: "Different background", prompt: "Keep the same person but use a different background and scene.", icon: SceneIcon },
];
const PERSON_MORE = [
  { label: "Bright office", prompt: "Feature the same person in a bright, modern office with soft daylight." },
  { label: "Clean studio", prompt: "Feature the same person on a clean studio backdrop with soft, flattering light." },
  { label: "Outdoor / rooftop", prompt: "Feature the same person in a bright outdoor rooftop setting with a soft city skyline." },
  { label: "Bolder brand colors", prompt: "Make it bolder — lean into the Talentrupt navy and coral brand colours (same person)." },
  { label: "Warmer & brighter", prompt: "Make it warmer and brighter (same person, same face)." },
];

export function RefineChips({
  onPick,
  disabled,
  kind = "image",
}: {
  onPick: (prompt: string) => void;
  disabled?: boolean;
  kind?: "image" | "person";
}) {
  const [more, setMore] = useState(false);
  const primary = kind === "person" ? PERSON_PRIMARY : PRIMARY;
  const extra = kind === "person" ? PERSON_MORE : MORE;
  const chip =
    "inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm text-muted shadow-sm transition hover:border-[var(--brand-red)] hover:text-foreground disabled:cursor-default disabled:opacity-50";
  return (
    <div className="flex flex-wrap gap-2 pt-0.5">
      {primary.map((c) => {
        const Icon = c.icon;
        return (
          <button key={c.label} type="button" disabled={disabled} onClick={() => onPick(c.prompt)} className={chip}>
            <Icon />
            <span>{c.label}</span>
          </button>
        );
      })}
      {more &&
        extra.map((c) => (
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
function SparkIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l1.8 4.9L18.7 9l-4.9 1.8L12 15.7 10.2 10.8 5.3 9l4.9-1.1L12 3z" /><path d="M18.5 15.5l.6 1.7 1.7.6-1.7.6-.6 1.7-.6-1.7-1.7-.6 1.7-.6.6-1.7z" /></svg>;
}
function SuitIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3l6 4 6-4v18l-4-3-2 3-2-3-4 3V3z" /><path d="M12 7v6" /></svg>;
}
function SceneIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9.5" r="1.5" /><path d="M21 16l-5-5-6 6" /></svg>;
}
