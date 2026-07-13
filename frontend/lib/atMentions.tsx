"use client";

// Shared mention/command palette for every chat box (Chat, Campaign). Typing "@" surfaces teammates
// from the Folders library (mention one to feature their REAL photo); typing "/" surfaces create actions
// (image / deck / PDF …). Two separate triggers so each list stays focused. Keeping it in one module
// guarantees the inputs behave identically — wire it up with `useAtMentions` + `<AtMenu/>`.

import { useEffect, useState } from "react";
import { fileUrl, getAllEmployees } from "@/lib/api";
import type { Employee } from "@/lib/types";

// One entry in the palette — an employee (people) or a quick-action command.
export type AtItem = { key: string; label: string; hint: string; insert: string; kind: "person" | "command"; thumb: string | null };
export type AtCommand = { key: string; label: string; hint: string; insert: string };

// Baseline quick-actions (Create). Chat/Campaign pass a superset.
export const DEFAULT_AT_COMMANDS: AtCommand[] = [
  { key: "image", label: "Create image", hint: "generate an image", insert: "Create an image of " },
  { key: "deck", label: "Create deck", hint: "slide deck", insert: "Create a slide deck about " },
  { key: "pdf", label: "Create PDF", hint: "document", insert: "Write a PDF document about " },
];

// Campaign studio: images / decks / PDFs / captions all land in the campaign folder.
export const CAMPAIGN_AT_COMMANDS: AtCommand[] = [
  ...DEFAULT_AT_COMMANDS,
  { key: "post", label: "Write a post", hint: "social caption", insert: "Write a social post about " },
];

/**
 * The "@" mention behavior for a chat textarea. Returns the current menu + helpers:
 *  - call `handleAtKey(e)` FIRST in your onKeyDown; if it returns true the key was consumed.
 *  - call `onInputChange()` in the textarea onChange (so re-typing "@" reopens a dismissed menu).
 *  - render `<AtMenu {...} />` inside a `relative` row when `showAtMenu` is true.
 */
export function useAtMentions(
  input: string,
  setInput: React.Dispatch<React.SetStateAction<string>>,
  busy: boolean,
  taRef: React.RefObject<HTMLTextAreaElement | null>,
  commands: AtCommand[] = DEFAULT_AT_COMMANDS,
) {
  const [menuSel, setMenuSel] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const [people, setPeople] = useState<Employee[]>([]);
  // Employees from the Folders library populate the "@" picker (mention one to feature their real photo).
  useEffect(() => { getAllEmployees().then(setPeople).catch(() => {}); }, []);

  // Two SEPARATE triggers (Slack/Notion style): "@name" -> teammates from Folders; "/cmd" -> create
  // actions (image / deck / PDF …). Each surfaces ONLY its own set — "@" never lists create actions and
  // "/" never lists people.
  const atMatch = dismissed ? null : input.match(/(^|\s)@(\w*)$/);
  const slashMatch = dismissed ? null : input.match(/(^|\s)\/([\w-]*)$/);
  const trigger: "@" | "/" | null = atMatch ? "@" : slashMatch ? "/" : null;
  const query = (atMatch ? atMatch[2] : slashMatch ? slashMatch[2] : "").toLowerCase();
  const atMenu: AtItem[] =
    trigger === "@"
      ? people
          .filter((e) => e.name.toLowerCase().includes(query) || (e.role || "").toLowerCase().includes(query))
          .slice(0, 8)
          .map((e) => ({ key: `emp-${e.id}`, label: e.name, hint: e.role || "team member",
                         insert: `@${e.name} `, kind: "person" as const, thumb: e.file_url ?? null }))
      : trigger === "/"
      ? commands
          .filter((c) => c.key.includes(query) || c.label.toLowerCase().includes(query))
          .map((c) => ({ ...c, kind: "command" as const, thumb: null }))
      : [];
  const showAtMenu = atMenu.length > 0 && !busy;

  function pickCommand(c: { insert: string }) {
    // Derive the trigger from the CURRENT text (not a captured value) so it always replaces the right
    // token — a trailing "/cmd" or "@name" — regardless of render timing.
    setInput((prev) => {
      const re = /(^|\s)\/[\w-]*$/.test(prev) ? /(^|\s)\/([\w-]*)$/ : /(^|\s)@(\w*)$/;
      return prev.replace(re, (_m, lead) => lead + c.insert);
    });
    setMenuSel(0);
    setDismissed(false);
    requestAnimationFrame(() => taRef.current?.focus());
  }

  // Call FIRST in the textarea onKeyDown. Returns true when the "@" / "/" menu consumed the key.
  function handleAtKey(e: React.KeyboardEvent<HTMLTextAreaElement>): boolean {
    if (!showAtMenu) return false;
    if (e.key === "ArrowDown") { e.preventDefault(); setMenuSel((i) => (i + 1) % atMenu.length); return true; }
    if (e.key === "ArrowUp") { e.preventDefault(); setMenuSel((i) => (i - 1 + atMenu.length) % atMenu.length); return true; }
    if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); pickCommand(atMenu[Math.min(menuSel, atMenu.length - 1)]); return true; }
    if (e.key === "Escape") { e.preventDefault(); setDismissed(true); return true; }
    return false;
  }

  // Call in the textarea onChange (after setInput) so re-typing "@" / "/" re-opens a dismissed menu.
  function onInputChange() { setDismissed(false); }

  return { atMenu, showAtMenu, menuSel, setMenuSel, pickCommand, handleAtKey, onInputChange };
}

/** The dropdown UI for the "@" palette. Render inside a `relative` flex row, before the textarea. */
export function AtMenu({
  atMenu, menuSel, setMenuSel, pickCommand,
}: {
  atMenu: AtItem[];
  menuSel: number;
  setMenuSel: (i: number) => void;
  pickCommand: (c: AtItem) => void;
}) {
  return (
    <div className="absolute bottom-full left-0 z-30 mb-2 max-h-80 w-72 overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-lg">
      {atMenu.map((c, i) => {
        const prev = atMenu[i - 1];
        const header = !prev || prev.kind !== c.kind ? (c.kind === "person" ? "People" : "Create") : null;
        const active = i === Math.min(menuSel, atMenu.length - 1);
        return (
          <div key={c.key}>
            {header && (
              <div className="border-b border-[var(--border)] px-3 py-1.5 text-[10px] uppercase tracking-wide text-muted">{header}</div>
            )}
            <button
              type="button"
              onMouseDown={(e) => { e.preventDefault(); pickCommand(c); }}
              onMouseEnter={() => setMenuSel(i)}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition ${
                active ? "bg-[var(--surface-2)] text-foreground" : "text-muted hover:bg-[var(--surface-2)]"
              }`}
            >
              {c.kind === "person" ? (
                c.thumb ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={fileUrl(c.thumb)} alt="" className="h-6 w-6 shrink-0 rounded-full object-cover" />
                ) : (
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--brand-navy)] text-[10px] font-semibold text-cream">{c.label.charAt(0)}</span>
                )
              ) : (
                <span className="font-medium text-[var(--brand-red)]">/</span>
              )}
              <span className="flex-1 truncate">{c.label}</span>
              <span className="shrink-0 text-[11px] text-muted">{c.hint}</span>
            </button>
          </div>
        );
      })}
    </div>
  );
}
