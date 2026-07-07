"use client";

import { useEffect, useRef, useState } from "react";
import {
  downloadFile,
  fileUrl,
  generateMagazine,
  generateMagazineFromData,
  getAllEmployees,
  getMagazines,
} from "@/lib/api";
import type { Asset, Employee, MagSpotlight, MagStat, MagazineDataResult, MagazineSpec } from "@/lib/types";

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

function IssueCard({ asset }: { asset: Asset }) {
  const meta = asset.meta || {};
  const edition = typeof meta.edition === "string" ? meta.edition : undefined;
  const pages = typeof meta.pages === "number" ? meta.pages : undefined;
  const url = fileUrl(asset.file_url);

  return (
    <div className="flex flex-col rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex items-start gap-3">
        <div
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-cream"
          style={{ background: "var(--grad-navy)" }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--brand-red)]">
            <path d="M4 19.5A2.5 2.5 0 016.5 17H20M4 19.5A2.5 2.5 0 006.5 22H20V2H6.5A2.5 2.5 0 004 4.5v15z" />
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{asset.title || "Untitled issue"}</div>
          <div className="mt-0.5 truncate text-[11px] text-muted">
            {[edition, pages ? `${pages} pages` : null].filter(Boolean).join(" · ") || "PDF"}
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={() => url && window.open(url, "_blank", "noopener,noreferrer")}
          disabled={!url}
          className="btn-ghost flex-1 !px-3 !py-1.5 !text-xs disabled:opacity-50"
        >
          Open
        </button>
        <button
          onClick={() => url && downloadFile(url, `${asset.title || "magazine"}.pdf`).catch(() => {})}
          disabled={!url}
          className="btn-primary flex-1 !px-3 !py-1.5 !text-xs disabled:opacity-50"
        >
          Download
        </button>
      </div>
    </div>
  );
}

export function MagazineView() {
  const [mode, setMode] = useState<"data" | "manual">("data");

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
    } catch {
      setError("Couldn't generate the magazine — please try again.");
    } finally {
      setBusy(false);
    }
  }

  function onDataFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setDataFile(e.target.files && e.target.files[0] ? e.target.files[0] : null);
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
    } catch (e) {
      setDataError((e as Error)?.message || "Couldn't generate the magazine — please try again.");
    } finally {
      setDataBusy(false);
    }
  }

  const noEmployees = !employeesError && employees.length === 0;

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-3xl">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-heading text-xl font-semibold">Magazine</h2>
            <p className="mt-1 text-sm text-muted">
              Generate a branded multi-page magazine from your team&apos;s real photos and stats.
            </p>
          </div>
          <div className="flex shrink-0 rounded-lg border border-[var(--border)] p-0.5 text-xs font-medium">
            <button
              onClick={() => setMode("data")}
              type="button"
              className={`rounded-md px-3 py-1.5 transition ${mode === "data" ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:text-foreground"}`}
            >
              From data file
            </button>
            <button
              onClick={() => setMode("manual")}
              type="button"
              className={`rounded-md px-3 py-1.5 transition ${mode === "manual" ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:text-foreground"}`}
            >
              Manual
            </button>
          </div>
        </div>

        {noEmployees && (
          <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3 text-sm text-muted">
            You don&apos;t have any employees yet. Add real photos in{" "}
            <a href="/folders" className="font-medium text-[var(--brand-red)] hover:underline">Folders</a>{" "}
            first — the magazine cover and spotlights feature real team photos.
          </div>
        )}

        {mode === "data" && (
          <div className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
            <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted">Roster file</div>
            <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--surface-2)] p-4">
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx"
                onChange={onDataFileChange}
                className="block w-full text-sm text-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-[var(--brand-navy)] file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-cream hover:file:opacity-90"
              />
              {dataFile && (
                <p className="mt-2 truncate text-xs text-foreground">Selected: {dataFile.name}</p>
              )}
              <p className="mt-2 text-[11px] text-muted">
                Upload a CSV or Excel roster (a Name column + metric columns like Submissions, Interviews,
                Offers, Starts…). We rank the team, feature the top performers, and pull each person&apos;s
                photo from Folders by name.
              </p>
            </div>

            <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Theme</label>
                <input
                  value={dataTheme}
                  onChange={(e) => setDataTheme(e.target.value)}
                  placeholder="Diwali / Christmas / Cricket…"
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                />
              </div>
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
              <div>
                <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Feature count</label>
                <input
                  type="number"
                  min={0}
                  value={dataFeatureCount}
                  onChange={(e) => setDataFeatureCount(e.target.value)}
                  placeholder="All"
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1.5 text-sm outline-none placeholder:text-muted focus:border-[var(--brand-red)]"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1 block text-[11px] uppercase tracking-wide text-muted">Rank by (column, optional)</label>
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

            <div className="mt-4">
              <button
                onClick={onGenerateFromData}
                disabled={dataBusy || !dataFile || !dataTheme.trim()}
                className="btn-primary w-full"
                title={!dataFile ? "Choose a roster file first" : !dataTheme.trim() ? "Enter a theme first" : undefined}
              >
                {dataBusy ? "Generating…" : "Generate magazine"}
              </button>
              {dataBusy && (
                <div className="mt-2 flex items-center justify-center gap-2 text-xs text-muted">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />
                  Analyzing your roster and generating the magazine… this can take up to a minute.
                </div>
              )}
              {dataError && <p className="mt-2 text-center text-xs text-[var(--brand-red)]">{dataError}</p>}
            </div>

            {dataResult && (
              <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3.5 text-sm">
                <p className="text-foreground">
                  Featured {dataResult.featured.length} {dataResult.featured.length === 1 ? "person" : "people"}
                  {dataResult.featured.length > 0 ? `: ${dataResult.featured.join(", ")}` : ""}.
                </p>
                {dataResult.unmatched.length > 0 && (
                  <p className="mt-1.5 text-amber-600">
                    No Folders photo for: {dataResult.unmatched.join(", ")} — add their photo in{" "}
                    <a href="/folders" className="font-medium underline">Folders</a> so they appear with a picture.
                  </p>
                )}
                <p className="mt-1.5 text-[11px] text-muted">
                  Detected columns — Name: {dataResult.columns.name}
                  {dataResult.columns.office ? ` · Office: ${dataResult.columns.office}` : ""}
                  {dataResult.columns.metrics.length ? ` · Metrics: ${dataResult.columns.metrics.join(", ")}` : ""}
                </p>
              </div>
            )}
          </div>
        )}

        {mode === "manual" && (
        <>
        {/* Issue basics */}
        <div className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
          <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted">Issue basics</div>
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
        </div>

        {/* Cover champion */}
        <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
          <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted">Cover champion</div>
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
        </div>

        {/* Spotlights */}
        <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-4">
          <div className="mb-2.5 flex items-center justify-between">
            <div className="text-[11px] uppercase tracking-wider text-muted">Spotlights</div>
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

        {/* Generate */}
        <div className="mt-5">
          <button
            onClick={onGenerate}
            disabled={busy || cover.employee_id == null}
            className="btn-primary w-full"
            title={cover.employee_id == null ? "Select a cover champion first" : undefined}
          >
            {busy ? "Generating…" : "Generate magazine"}
          </button>
          {busy && (
            <div className="mt-2 flex items-center justify-center gap-2 text-xs text-muted">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />
              Generating your magazine… this can take up to a minute.
            </div>
          )}
          {error && <p className="mt-2 text-center text-xs text-[var(--brand-red)]">{error}</p>}
        </div>
        </>
        )}

        {/* Past issues */}
        <div className="mt-8">
          <div className="mb-2.5 text-[11px] uppercase tracking-wider text-muted">Past issues</div>
          {issuesLoading ? (
            <div className="flex items-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-6 text-sm text-muted">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--brand-red)]" />
              Loading past issues…
            </div>
          ) : issues.length === 0 ? (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-6 text-sm text-muted">
              No magazines yet — generate your first issue above.
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {issues.map((asset) => (
                <IssueCard key={asset.id} asset={asset} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
