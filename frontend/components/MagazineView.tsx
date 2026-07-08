"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  deleteAsset,
  downloadFile,
  fileUrl,
  generateMagazine,
  generateMagazineFromData,
  getAllEmployees,
  getMagazines,
  pdfCoverUrl,
} from "@/lib/api";
import type { Asset, Employee, MagSpotlight, MagStat, MagazineDataResult, MagazineSpec } from "@/lib/types";
import { useToast } from "./Toast";
import { ConfirmDialog } from "./Dialog";

const MAX_COVER_STATS = 6;
const MAX_SPOTLIGHT_STATS = 4;

function emptyCover(): MagazineSpec["cover"] {
  return { employee_id: null, headline: "", tagline: "", stats: [] };
}

function emptySpotlight(): MagSpotlight {
  return { employee_id: null, office: "", blurb: "", stats: [] };
}

// Small {label, value} row editor shared by the cover champion and each spotlight.
function StatsEditor({
  stats,
  onChange,
  max,
}: {
  stats: MagStat[];
  onChange: (next: MagStat[]) => void;
  max: number;
}) {
  function update(i: number, patch: Partial<MagStat>) {
    onChange(stats.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));
  }
  function remove(i: number) {
    onChange(stats.filter((_, idx) => idx !== i));
  }
  function add() {
    if (stats.length >= max) return;
    onChange([...stats, { label: "", value: "" }]);
  }
  return (
    <div className="space-y-1.5">
      {stats.map((s, i) => (
        <div key={i} className="flex items-center gap-1.5">
          <input
            value={s.label}
            onChange={(e) => update(i, { label: e.target.value })}
            placeholder="Label (e.g. New Jobs)"
            className="min-w-0 flex-1 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-xs outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
          />
          <input
            value={s.value}
            onChange={(e) => update(i, { value: e.target.value })}
            placeholder="Value (e.g. 19)"
            className="w-24 shrink-0 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-xs outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
          />
          <button
            onClick={() => remove(i)}
            type="button"
            title="Remove stat"
            aria-label="Remove stat"
            className="shrink-0 rounded-md p-1 text-muted transition hover:text-[var(--brand-red)]"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </div>
      ))}
      <button
        onClick={add}
        type="button"
        disabled={stats.length >= max}
        className="rounded-lg border border-[var(--border)] px-2.5 py-1 text-[11px] text-muted transition hover:border-[var(--brand-red)] hover:text-foreground disabled:opacity-40"
      >
        + Add stat
      </button>
    </div>
  );
}

function EmployeeSelect({
  employees,
  value,
  onChange,
}: {
  employees: Employee[];
  value: number | null;
  onChange: (id: number | null) => void;
}) {
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none focus:border-[var(--brand-red)]"
    >
      <option value="">Select an employee…</option>
      {employees.map((e) => (
        <option key={e.id} value={e.id}>
          {e.name}{e.role ? ` — ${e.role}` : ""}
        </option>
      ))}
    </select>
  );
}

function SpotlightCard({
  spotlight,
  employees,
  onChange,
  onRemove,
}: {
  spotlight: MagSpotlight;
  employees: Employee[];
  onChange: (next: MagSpotlight) => void;
  onRemove: () => void;
}) {
  return (
    <div className="relative rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3.5">
      <button
        onClick={onRemove}
        type="button"
        title="Remove spotlight"
        aria-label="Remove spotlight"
        className="absolute right-2.5 top-2.5 rounded-md p-1 text-muted transition hover:text-[var(--brand-red)]"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
      </button>
      <div className="grid gap-2.5 pr-6 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Employee</label>
          <EmployeeSelect
            employees={employees}
            value={spotlight.employee_id}
            onChange={(id) => onChange({ ...spotlight, employee_id: id })}
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Office</label>
          <input
            value={spotlight.office}
            onChange={(e) => onChange({ ...spotlight, office: e.target.value })}
            placeholder="e.g. Pune"
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
          />
        </div>
      </div>
      <div className="mt-2.5 pr-6">
        <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Blurb</label>
        <textarea
          value={spotlight.blurb}
          onChange={(e) => onChange({ ...spotlight, blurb: e.target.value })}
          rows={2}
          placeholder="A few lines about their story or achievement…"
          className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
        />
      </div>
      <div className="mt-2.5 pr-6">
        <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Stats</label>
        <StatsEditor
          stats={spotlight.stats}
          onChange={(stats) => onChange({ ...spotlight, stats })}
          max={MAX_SPOTLIGHT_STATS}
        />
      </div>
    </div>
  );
}

function IssueCard({
  asset,
  onDelete,
}: {
  asset: Asset;
  onDelete: (a: Asset) => void;
}) {
  const meta = asset.meta || {};
  const edition = typeof meta.edition === "string" ? meta.edition : undefined;
  const pages = typeof meta.pages === "number" ? meta.pages : undefined;
  const profileName = typeof meta.profile_name === "string" ? meta.profile_name : undefined;
  const url = fileUrl(asset.file_url);
  const cover = pdfCoverUrl(asset.file_url);
  const [imgOk, setImgOk] = useState(true);
  const { toast } = useToast();

  return (
    <div className="group overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] transition hover:border-[var(--brand-red)] hover:shadow-[var(--shadow-card)]">
      {/* Cover thumbnail (the PDF's real first page) — click to open the full PDF. */}
      <button
        onClick={() => url && window.open(url, "_blank", "noopener,noreferrer")}
        className="relative block aspect-[7/10] w-full cursor-zoom-in overflow-hidden bg-[var(--surface-2)]"
        aria-label={`Open ${asset.title || "magazine"}`}
      >
        {cover && imgOk ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={cover} alt="" onError={() => setImgOk(false)} className="h-full w-full object-cover object-top" />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-2.5 p-4 text-center" style={{ background: "var(--grad-navy)" }}>
            <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" className="text-white/90">
              <path d="M4 19.5A2.5 2.5 0 016.5 17H20M4 19.5A2.5 2.5 0 006.5 22H20V2H6.5A2.5 2.5 0 004 4.5v15z" />
            </svg>
            <span className="line-clamp-2 text-xs font-medium text-cream">{asset.title || "Magazine"}</span>
            {edition && <span className="line-clamp-1 text-[10px] text-cream/70">{edition}</span>}
          </div>
        )}
        {profileName && (
          <span className="absolute left-2 top-2 rounded-full bg-black/45 px-2 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm">
            {profileName}
          </span>
        )}
        <span className="pointer-events-none absolute inset-0 flex items-end justify-center bg-gradient-to-t from-black/45 to-transparent p-2 opacity-0 transition group-hover:opacity-100">
          <span className="rounded-full bg-white/90 px-3 py-1 text-[11px] font-medium text-[var(--brand-navy)]">Open PDF</span>
        </span>
      </button>
      <div className="flex items-center gap-2 p-3">
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{asset.title || "Untitled issue"}</div>
          <div className="mt-0.5 truncate text-[11px] text-muted">
            {[edition, pages ? `${pages} pages` : null].filter(Boolean).join(" · ") || "PDF"}
          </div>
        </div>
        <button
          onClick={() =>
            url &&
            downloadFile(url, `${asset.title || "magazine"}.pdf`)
              .then(() => toast("Downloaded", { kind: "success" }))
              .catch(() => toast("Download failed — please try again", { kind: "error" }))
          }
          disabled={!url}
          title="Download PDF"
          aria-label="Download"
          className="shrink-0 rounded-lg bg-[var(--brand-navy)] p-2 text-cream transition hover:opacity-90 disabled:opacity-50"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" /></svg>
        </button>
        <button
          onClick={() => onDelete(asset)}
          title="Delete issue"
          aria-label="Delete"
          className="shrink-0 rounded-lg border border-[var(--border)] p-2 text-muted transition hover:border-[var(--brand-red)] hover:text-[var(--brand-red)]"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" /></svg>
        </button>
      </div>
    </div>
  );
}

const THEME_CHIPS = ["Diwali", "Christmas", "New Year", "Cricket", "Monsoon", "Summer"];
const FEATURE_OPTIONS: [string, string][] = [["All", ""], ["3", "3"], ["5", "5"], ["10", "10"]];

// Drag-and-drop roster upload with a file chip (replaces the native file input).
function RosterDropzone({
  file,
  onFile,
  inputRef,
}: {
  file: File | null;
  onFile: (f: File | null) => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}) {
  const [drag, setDrag] = useState(false);
  const accept = (f: File | null) => {
    if (f && /\.(csv|xlsx)$/i.test(f.name)) onFile(f);
  };
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); accept(e.dataTransfer.files?.[0] || null); }}
      className={`rounded-xl border-2 border-dashed p-5 transition ${
        drag ? "border-[var(--brand-red)] bg-[var(--brand-red)]/5" : "border-[var(--border)] bg-[var(--surface-2)]"
      }`}
    >
      <input ref={inputRef} type="file" accept=".csv,.xlsx" className="hidden" onChange={(e) => onFile(e.target.files?.[0] || null)} />
      {file ? (
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-cream" style={{ background: "var(--grad-navy)" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M6 2h9l5 5v15H6zM14 2v6h6" /></svg>
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{file.name}</div>
            <div className="text-[11px] text-muted">{(file.size / 1024).toFixed(0)} KB · ready</div>
          </div>
          <button type="button" onClick={() => inputRef.current?.click()} className="shrink-0 rounded-lg border border-[var(--border)] px-2.5 py-1 text-xs text-muted transition hover:border-[var(--brand-red)] hover:text-foreground">Replace</button>
          <button type="button" onClick={() => { onFile(null); if (inputRef.current) inputRef.current.value = ""; }} aria-label="Remove file" className="shrink-0 rounded-lg p-1.5 text-muted transition hover:text-[var(--brand-red)]">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </div>
      ) : (
        <button type="button" onClick={() => inputRef.current?.click()} className="flex w-full flex-col items-center gap-2 py-3 text-center">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-[var(--surface-3)] text-[var(--brand-red)]">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" /></svg>
          </span>
          <div className="text-sm font-medium">Drag a CSV or Excel roster here</div>
          <div className="text-[11px] text-muted">or click to browse · .csv, .xlsx</div>
        </button>
      )}
    </div>
  );
}

// A numbered step header with a trailing divider rule (matches the builder's 1/2/3 sections).
function StepHead({ n, label }: { n: number; label: string }) {
  return (
    <div className="mb-3.5 mt-6 flex items-center gap-2.5 first:mt-0">
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--brand-navy)] text-[10px] font-semibold text-cream">{n}</span>
      <span className="text-sm font-semibold text-foreground">{label}</span>
      <span className="h-px flex-1 bg-[var(--border)]" />
    </div>
  );
}

// Live, templated preview of the cover — driven by the form fields (NOT a real render). Gives a sense of the
// masthead, theme edition line, title and how many people get featured before you generate.
function CoverPreview({ title, edition, theme, featureLabel }: { title: string; edition: string; theme: string; featureLabel: string }) {
  const t = title.trim() || "Talentrupt Times";
  const ed = edition.trim() || "Vol 1 · September 2025";
  const th = theme.trim();
  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-card)]">
      {/* Navy masthead */}
      <div className="px-4 pb-4 pt-3.5" style={{ background: "var(--grad-navy)" }}>
        <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-[var(--brand-coral)]">
          <span className="truncate">{th ? `${th} Edition` : "Special Edition"}</span>
          <span className="shrink-0 pl-2">Talentrupt</span>
        </div>
        <div className="mt-2 truncate font-serif text-2xl font-bold leading-tight text-white">{t}</div>
        <div className="mt-1 text-[11px] text-cream/70">{ed}</div>
      </div>
      {/* Hero photo placeholder (real team photo drops in on generate) */}
      <div className="relative h-40" style={{ backgroundImage: "repeating-linear-gradient(45deg, var(--surface-2) 0, var(--surface-2) 10px, var(--surface-3) 10px, var(--surface-3) 20px)" }}>
        <span className="absolute bottom-2.5 left-2.5 rounded-md bg-[var(--surface)]/90 px-2 py-0.5 font-mono text-[10px] text-muted">team hero photo</span>
        <span className="absolute bottom-2.5 right-2.5 rounded-full bg-[var(--brand-red)] px-2.5 py-0.5 text-[10px] font-medium text-cream">{featureLabel}</span>
      </div>
      {/* Article skeleton lines */}
      <div className="space-y-2 p-4">
        <div className="h-2.5 w-3/4 rounded bg-[var(--surface-2)]" />
        <div className="h-2.5 w-full rounded bg-[var(--surface-2)]" />
        <div className="h-2.5 w-2/3 rounded bg-[var(--surface-2)]" />
      </div>
    </div>
  );
}

// Date helpers for grouping past issues by month (like a shelf).
function assetTime(a: Asset): number {
  if (a.created_at) {
    const t = Date.parse(a.created_at);
    if (!Number.isNaN(t)) return t;
  }
  return 0;
}
function monthLabel(a: Asset): string {
  if (!a.created_at) return "Earlier";
  const d = new Date(a.created_at);
  return Number.isNaN(d.getTime()) ? "Earlier" : d.toLocaleString(undefined, { month: "long", year: "numeric" });
}

export function MagazineView() {
  const { toast } = useToast();
  const [view, setView] = useState<"create" | "issues">("create");
  const [mode, setMode] = useState<"data" | "manual">("data");
  const [issueSort, setIssueSort] = useState<"newest" | "oldest">("newest");
  const [deleteIssue, setDeleteIssue] = useState<Asset | null>(null);

  const [employees, setEmployees] = useState<Employee[]>([]);
  const [employeesError, setEmployeesError] = useState(false);
  const [issues, setIssues] = useState<Asset[]>([]);
  const [issuesLoading, setIssuesLoading] = useState(true);

  const [title, setTitle] = useState("Talentrupt Times");
  const [edition, setEdition] = useState("");
  const [theme, setTheme] = useState("");
  const [editorial, setEditorial] = useState("");
  const [cover, setCover] = useState<MagazineSpec["cover"]>(emptyCover());
  const [spotlights, setSpotlights] = useState<MagSpotlight[]>([]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // --- Data-file mode ---
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dataFile, setDataFile] = useState<File | null>(null);
  const [dataTitle, setDataTitle] = useState("Talentrupt Times");
  const [dataEdition, setDataEdition] = useState("");
  const [dataTheme, setDataTheme] = useState("");
  const [dataEditorial, setDataEditorial] = useState("");
  const [dataFeatureCount, setDataFeatureCount] = useState("");
  const [dataRankBy, setDataRankBy] = useState("");
  const [dataBusy, setDataBusy] = useState(false);
  const [dataError, setDataError] = useState("");
  const [dataResult, setDataResult] = useState<MagazineDataResult | null>(null);

  useEffect(() => {
    getAllEmployees()
      .then(setEmployees)
      .catch(() => setEmployeesError(true));
    getMagazines()
      .then(setIssues)
      .catch(() => setIssues([]))
      .finally(() => setIssuesLoading(false));
  }, []);

  function addSpotlight() {
    setSpotlights((prev) => [...prev, emptySpotlight()]);
  }
  function updateSpotlight(i: number, next: MagSpotlight) {
    setSpotlights((prev) => prev.map((s, idx) => (idx === i ? next : s)));
  }
  function removeSpotlight(i: number) {
    setSpotlights((prev) => prev.filter((_, idx) => idx !== i));
  }

  function cleanStats(stats: MagStat[]): MagStat[] {
    return stats.filter((s) => s.label.trim().length > 0).map((s) => ({ label: s.label.trim(), value: s.value.trim() }));
  }

  async function onGenerate() {
    if (busy || cover.employee_id == null) return;
    setBusy(true);
    setError("");
    const spec: MagazineSpec = {
      title: title.trim() || "Talentrupt Times",
      edition: edition.trim(),
      theme: theme.trim(),
      editorial: editorial.trim(),
      cover: {
        employee_id: cover.employee_id,
        headline: cover.headline.trim(),
        tagline: cover.tagline.trim(),
        stats: cleanStats(cover.stats),
      },
      spotlights: spotlights.map((s) => ({
        employee_id: s.employee_id,
        office: s.office.trim(),
        blurb: s.blurb.trim(),
        stats: cleanStats(s.stats),
      })),
    };
    try {
      const asset = await generateMagazine(spec);
      setIssues((prev) => [asset, ...prev]);
      toast("Magazine generated", { kind: "success", action: { label: "View", onClick: () => setView("issues") } });
    } catch {
      setError("Couldn't generate the magazine — please try again.");
      toast("Couldn't generate the magazine", { kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  async function onGenerateFromData() {
    if (dataBusy || !dataFile || !dataTheme.trim()) return;
    setDataBusy(true);
    setDataError("");
    try {
      const result = await generateMagazineFromData(dataFile, {
        theme: dataTheme.trim(),
        title: dataTitle.trim() || "Talentrupt Times",
        edition: dataEdition.trim(),
        feature_count: dataFeatureCount.trim(),
        editorial: dataEditorial.trim(),
        rank_by: dataRankBy.trim(),
      });
      setIssues((prev) => [result.asset, ...prev]);
      setDataResult(result);
      setDataFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      toast(`Magazine built · ${result.featured?.length ?? 0} featured`, { kind: "success", action: { label: "View", onClick: () => setView("issues") } });
    } catch (e) {
      const msg = (e as Error)?.message || "Couldn't generate the magazine — please try again.";
      setDataError(msg);
      toast("Couldn't build the magazine", { kind: "error" });
    } finally {
      setDataBusy(false);
    }
  }

  // Past issues sorted + grouped by month (a shelf).
  const issueGroups = useMemo(() => {
    const sorted = [...issues].sort((a, b) => {
      const d = assetTime(b) - assetTime(a) || b.id - a.id;
      return issueSort === "newest" ? d : -d;
    });
    const out: { key: string; items: Asset[] }[] = [];
    const idx = new Map<string, number>();
    for (const a of sorted) {
      const key = monthLabel(a);
      if (!idx.has(key)) { idx.set(key, out.length); out.push({ key, items: [] }); }
      out[idx.get(key)!].items.push(a);
    }
    return out;
  }, [issues, issueSort]);

  async function confirmDeleteIssue() {
    const a = deleteIssue;
    if (!a) return;
    setDeleteIssue(null);
    setIssues((prev) => prev.filter((x) => x.id !== a.id)); // optimistic
    try {
      await deleteAsset(a.id);
      toast("Issue deleted", { kind: "success" });
    } catch {
      toast("Couldn't delete — please try again", { kind: "error" });
      getMagazines().then(setIssues).catch(() => {});
    }
  }

  const noEmployees = !employeesError && employees.length === 0;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6">
      <div className="mx-auto w-full max-w-6xl">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-heading text-xl font-semibold">Magazine</h2>
            <p className="mt-1 text-sm text-muted">
              Generate a branded multi-page magazine from your team&apos;s real photos and stats.
            </p>
          </div>
          {/* Primary view switch — mirrors Chat's "Chat / Your generations" tabs. */}
          <div className="flex shrink-0 rounded-lg border border-[var(--border)] p-0.5 text-xs font-medium">
            <button
              onClick={() => setView("create")}
              type="button"
              className={`rounded-md px-3 py-1.5 transition ${view === "create" ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:text-foreground"}`}
            >
              Create
            </button>
            <button
              onClick={() => setView("issues")}
              type="button"
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${view === "issues" ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:text-foreground"}`}
            >
              Past issues
              {issues.length > 0 && (
                <span className={`rounded-full px-1.5 text-[10px] leading-4 ${view === "issues" ? "bg-cream/25 text-cream" : "bg-[var(--surface-3)] text-muted"}`}>
                  {issues.length}
                </span>
              )}
            </button>
          </div>
        </div>

        {view === "create" && (
        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          {/* LEFT — the builder form */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-5">
            {/* Mode toggle */}
            <div className="mb-5 flex rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-1 text-sm font-medium">
              <button
                onClick={() => setMode("data")}
                type="button"
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 transition ${mode === "data" ? "bg-[var(--surface)] text-foreground shadow-[var(--shadow-card)]" : "text-muted hover:text-foreground"}`}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M6 2h9l5 5v15H6zM14 2v6h6" /></svg>
                From data file
              </button>
              <button
                onClick={() => setMode("manual")}
                type="button"
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 transition ${mode === "manual" ? "bg-[var(--surface)] text-foreground shadow-[var(--shadow-card)]" : "text-muted hover:text-foreground"}`}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4z" /></svg>
                Manual entry
              </button>
            </div>

            {noEmployees && (
              <div className="mb-4 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3 text-sm text-muted">
                You don&apos;t have any employees yet. Add real photos in{" "}
                <a href="/folders" className="font-medium text-[var(--brand-red)] hover:underline">Folders</a>{" "}
                first — the magazine cover and spotlights feature real team photos.
              </div>
            )}

            {mode === "data" && (
              <div>
                <StepHead n={1} label="Roster source" />
                <RosterDropzone file={dataFile} onFile={setDataFile} inputRef={fileInputRef} />
                <p className="mt-2 text-[11px] text-muted">
                  CSV or Excel with a <span className="font-medium text-foreground">Name</span> column + metric columns — or a full award report workbook. Photos pull from Folders by name.
                </p>

                <StepHead n={2} label="Cover & edition" />
                <div className="grid gap-2.5 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Title</label>
                    <input
                      value={dataTitle}
                      onChange={(e) => setDataTitle(e.target.value)}
                      placeholder="Talentrupt Times"
                      className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Edition</label>
                    <input
                      value={dataEdition}
                      onChange={(e) => setDataEdition(e.target.value)}
                      placeholder="Vol 1 · September 2025"
                      className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                    />
                  </div>
                </div>
                <div className="mt-2.5">
                  <label className="mb-1.5 block text-[11px] uppercase tracking-wide text-muted">Theme</label>
                  <div className="flex flex-wrap gap-1.5">
                    {THEME_CHIPS.map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setDataTheme(t)}
                        className={`rounded-full border px-3 py-1 text-xs transition ${
                          dataTheme.trim().toLowerCase() === t.toLowerCase()
                            ? "border-transparent bg-[var(--brand-navy)] text-cream"
                            : "border-[var(--border)] text-foreground hover:border-[var(--brand-red)]"
                        }`}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                  <input
                    value={dataTheme}
                    onChange={(e) => setDataTheme(e.target.value)}
                    placeholder="…or type a custom theme"
                    className="mt-2 w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-xs outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                  />
                </div>

                <StepHead n={3} label="Content" />
                <div className="grid gap-2.5 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Feature count</label>
                    <div className="flex items-center gap-0.5 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] p-0.5">
                      {FEATURE_OPTIONS.map(([label, val]) => {
                        const active = dataFeatureCount.trim() === val;
                        return (
                          <button
                            key={label}
                            type="button"
                            onClick={() => setDataFeatureCount(val)}
                            className={`flex-1 rounded-md px-2 py-1 text-xs font-medium transition ${
                              active ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:text-foreground"
                            }`}
                          >
                            {label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <div>
                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Rank by <span className="normal-case text-muted/70">(column, optional)</span></label>
                    <input
                      value={dataRankBy}
                      onChange={(e) => setDataRankBy(e.target.value)}
                      placeholder="e.g. Offers"
                      className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                    />
                  </div>
                </div>
                <div className="mt-2.5">
                  <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Editorial message</label>
                  <textarea
                    value={dataEditorial}
                    onChange={(e) => setDataEditorial(e.target.value)}
                    rows={3}
                    placeholder="A short note from leadership…"
                    className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                  />
                  <p className="mt-1 text-[11px] text-muted">Leave blank and Myra writes it.</p>
                </div>
              </div>
            )}

            {mode === "manual" && (
              <div>
                <StepHead n={1} label="Issue basics" />
                <div className="grid gap-2.5 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Title</label>
                    <input
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="Talentrupt Times"
                      className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Edition</label>
                    <input
                      value={edition}
                      onChange={(e) => setEdition(e.target.value)}
                      placeholder="Vol 1 · September 2025"
                      className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Theme</label>
                    <input
                      value={theme}
                      onChange={(e) => setTheme(e.target.value)}
                      placeholder="Diwali / Christmas / Monsoon / Cricket…"
                      className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                    />
                  </div>
                </div>
                <div className="mt-2.5">
                  <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Editorial message</label>
                  <textarea
                    value={editorial}
                    onChange={(e) => setEditorial(e.target.value)}
                    rows={3}
                    placeholder="A short note from leadership…"
                    className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                  />
                  <p className="mt-1 text-[11px] text-muted">Leave blank and Myra writes it.</p>
                </div>

                <StepHead n={2} label="Cover champion" />
                <div className="grid gap-2.5 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Employee</label>
                    <EmployeeSelect
                      employees={employees}
                      value={cover.employee_id}
                      onChange={(id) => setCover({ ...cover, employee_id: id })}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Headline</label>
                    <input
                      value={cover.headline}
                      onChange={(e) => setCover({ ...cover, headline: e.target.value })}
                      placeholder="Spark of Brilliance"
                      className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                    />
                  </div>
                </div>
                <div className="mt-2.5">
                  <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Tagline</label>
                  <textarea
                    value={cover.tagline}
                    onChange={(e) => setCover({ ...cover, tagline: e.target.value })}
                    rows={2}
                    placeholder="Jerry's energy and results speak volumes…"
                    className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                  />
                </div>
                <div className="mt-2.5">
                  <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Stats</label>
                  <StatsEditor
                    stats={cover.stats}
                    onChange={(stats) => setCover({ ...cover, stats })}
                    max={MAX_COVER_STATS}
                  />
                </div>

                <StepHead n={3} label="Spotlights" />
                <div className="mb-2.5 flex justify-end">
                  <button
                    onClick={addSpotlight}
                    type="button"
                    className="rounded-lg border border-[var(--border)] px-2.5 py-1 text-[11px] text-muted transition hover:border-[var(--brand-red)] hover:text-foreground"
                  >
                    + Add spotlight
                  </button>
                </div>
                {spotlights.length === 0 ? (
                  <p className="text-sm text-muted">No spotlights yet — optional. Add one to feature more of the team.</p>
                ) : (
                  <div className="space-y-3">
                    {spotlights.map((s, i) => (
                      <SpotlightCard
                        key={i}
                        spotlight={s}
                        employees={employees}
                        onChange={(next) => updateSpotlight(i, next)}
                        onRemove={() => removeSpotlight(i)}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* RIGHT — live preview + generate */}
          <div className="self-start lg:sticky lg:top-6">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted">Live preview</div>
            <CoverPreview
              title={mode === "data" ? dataTitle : title}
              edition={mode === "data" ? dataEdition : edition}
              theme={mode === "data" ? dataTheme : theme}
              featureLabel={
                mode === "data"
                  ? dataFeatureCount.trim()
                    ? `Top ${dataFeatureCount.trim()}`
                    : "All features"
                  : `${1 + spotlights.length} featured`
              }
            />

            {mode === "data" ? (
              <button
                onClick={onGenerateFromData}
                disabled={dataBusy || !dataFile || !dataTheme.trim()}
                className="btn-primary mt-4 w-full"
                title={!dataFile ? "Choose a roster file first" : !dataTheme.trim() ? "Enter a theme first" : undefined}
              >
                {dataBusy ? "Generating…" : "Generate magazine →"}
              </button>
            ) : (
              <button
                onClick={onGenerate}
                disabled={busy || cover.employee_id == null}
                className="btn-primary mt-4 w-full"
                title={cover.employee_id == null ? "Select a cover champion first" : undefined}
              >
                {busy ? "Generating…" : "Generate magazine →"}
              </button>
            )}

            {(mode === "data" ? dataBusy : busy) ? (
              <div className="mt-2 flex items-center justify-center gap-2 text-xs text-muted">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />
                Building your magazine… this can take up to a minute.
              </div>
            ) : (
              <div className="mt-2 text-center text-[11px] text-muted">~40s · multi-page · PDF + web</div>
            )}
            {mode === "data"
              ? dataError && <p className="mt-2 text-center text-xs text-[var(--brand-red)]">{dataError}</p>
              : error && <p className="mt-2 text-center text-xs text-[var(--brand-red)]">{error}</p>}

            {mode === "data" && dataResult && (
              <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3.5 text-sm">
                {dataResult.format === "award" && (
                  <span className="mb-2 inline-flex items-center rounded-full bg-[var(--brand-navy)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-cream">
                    Award report detected
                  </span>
                )}
                <p className="text-foreground">
                  Featured {dataResult.featured.length} {dataResult.featured.length === 1 ? "person" : "people"}
                  {dataResult.featured.length > 0 ? `: ${dataResult.featured.join(", ")}` : ""}.
                </p>
                {dataResult.awards && dataResult.awards.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {dataResult.awards.map((a) => (
                      <p key={a.title} className="text-[12px] text-foreground">
                        <span className="font-medium">{a.title}:</span>{" "}
                        <span className="text-muted">{a.winners.join(" · ")}</span>
                      </p>
                    ))}
                  </div>
                )}
                {dataResult.unmatched.length > 0 && (
                  <p className="mt-1.5 text-amber-600">
                    No Folders photo for: {dataResult.unmatched.join(", ")} — add their photo in{" "}
                    <a href="/folders" className="font-medium underline">Folders</a> so they appear with a picture.
                  </p>
                )}
                {dataResult.format !== "award" && (
                  <p className="mt-1.5 text-[11px] text-muted">
                    Detected columns — Name: {dataResult.columns.name ?? "—"}
                    {dataResult.columns.office ? ` · Office: ${dataResult.columns.office}` : ""}
                    {dataResult.columns.metrics.length ? ` · Metrics: ${dataResult.columns.metrics.join(", ")}` : ""}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
        )}

        {view === "issues" && (
        <div className="mt-6">
          {/* A shelf of real cover thumbnails, grouped by month. */}
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="font-heading text-lg font-semibold">Past issues</h3>
              <p className="mt-0.5 text-xs text-muted">Every magazine you&apos;ve generated, newest first.</p>
            </div>
            {issues.length > 1 && (
              <div className="flex items-center rounded-lg border border-[var(--border)] p-0.5">
                {(["newest", "oldest"] as const).map((s) => (
                  <button
                    key={s}
                    onClick={() => setIssueSort(s)}
                    className={`rounded-md px-2.5 py-1 text-xs capitalize transition ${
                      issueSort === s ? "bg-[var(--surface-3)] text-foreground" : "text-muted hover:text-foreground"
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
          {issuesLoading ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)]">
                  <div className="skeleton aspect-[7/10] w-full rounded-none" />
                  <div className="flex items-center gap-2 p-3">
                    <div className="skeleton h-3 flex-1" />
                    <div className="skeleton h-7 w-7 rounded-lg" />
                  </div>
                </div>
              ))}
            </div>
          ) : issues.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface)] px-4 py-12 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--surface-2)] text-muted">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 016.5 17H20M4 19.5A2.5 2.5 0 006.5 22H20V2H6.5A2.5 2.5 0 004 4.5v15z" /></svg>
              </div>
              <p className="text-sm text-muted">No magazines yet.</p>
              <button
                type="button"
                onClick={() => setView("create")}
                className="btn-primary"
              >
                Create your first issue
              </button>
            </div>
          ) : (
            issueGroups.map((g) => (
              <section key={g.key} className="mb-6">
                <div className="mb-3 flex items-center gap-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{g.key}</h3>
                  <span className="text-[11px] text-muted/70">· {g.items.length}</span>
                </div>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
                  {g.items.map((asset) => (
                    <IssueCard key={asset.id} asset={asset} onDelete={setDeleteIssue} />
                  ))}
                </div>
              </section>
            ))
          )}
        </div>
        )}
      </div>

      {deleteIssue && (
        <ConfirmDialog
          title="Delete this issue?"
          message={`"${deleteIssue.title || "Untitled issue"}" will be removed from your past issues. This can't be undone.`}
          confirmLabel="Delete"
          onConfirm={confirmDeleteIssue}
          onCancel={() => setDeleteIssue(null)}
        />
      )}
    </div>
  );
}
