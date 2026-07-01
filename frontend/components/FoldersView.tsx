"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  addEmployee,
  createFolder,
  deleteEmployee,
  deleteFolder,
  downloadFile,
  fileUrl,
  getEmployees,
  getFolders,
} from "@/lib/api";
import type { Employee, Folder } from "@/lib/types";

// Folders is a REFERENCE PHOTO LIBRARY (a "knowledge bank") for Create & Chat. You don't generate here —
// you add employees (photo + name + role), then mention them with @ in Create/Chat to feature them.
export function FoldersView() {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [addName, setAddName] = useState("");
  const [addRole, setAddRole] = useState("");
  const [addBusy, setAddBusy] = useState(false);
  const [preview, setPreview] = useState<Employee | null>(null); // photo lightbox target
  const fileRef = useRef<HTMLInputElement>(null);

  const loadFolders = useCallback(async () => {
    try { setFolders(await getFolders()); } catch { /* keep current */ }
  }, []);
  useEffect(() => { loadFolders(); }, [loadFolders]);

  const loadEmployees = useCallback(async (fid: number) => {
    try { setEmployees(await getEmployees(fid)); } catch { setEmployees([]); }
  }, []);
  useEffect(() => {
    if (selected == null) { setEmployees([]); return; }
    loadEmployees(selected);
  }, [selected, loadEmployees]);

  const folder = folders.find((f) => f.id === selected) || null;

  async function onNewFolder() {
    const name = window.prompt("Folder name (e.g. “Leadership”, “Sales team”):");
    if (name == null) return;
    try {
      const f = await createFolder(name.trim() || "Untitled folder");
      await loadFolders();
      setSelected(f.id);
    } catch { alert("Couldn't create the folder."); }
  }

  async function onDeleteFolder(id: number) {
    if (!confirm("Delete this folder and its employees? This can't be undone.")) return;
    try { await deleteFolder(id); } catch { /* still refresh */ }
    if (selected === id) setSelected(null);
    await loadFolders();
  }

  async function onAddEmployee(file: File) {
    if (selected == null) return;
    if (!addName.trim()) { alert("Enter the employee's name first."); return; }
    setAddBusy(true);
    try {
      await addEmployee(selected, addName.trim(), addRole.trim(), file);
      setAddName(""); setAddRole("");
      await loadEmployees(selected);
      await loadFolders();
    } catch { alert("Couldn't add that photo — use a JPG/PNG under 25 MB."); }
    finally { setAddBusy(false); }
  }

  async function onDeleteEmployee(id: number) {
    if (!confirm("Remove this employee from the folder?")) return;
    try { await deleteEmployee(id); } catch { /* still refresh */ }
    if (selected != null) { await loadEmployees(selected); await loadFolders(); }
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Rail: folders */}
      <div className="rail flex w-60 shrink-0 flex-col border-r border-[var(--border)]">
        <div className="p-3">
          <button onClick={onNewFolder} className="btn-primary w-full">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
            New folder
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {folders.length === 0 ? (
            <p className="px-2 py-3 text-xs text-muted">No folders yet. Create one and add employee photos.</p>
          ) : (
            folders.map((f) => (
              <div key={f.id} className="group relative">
                <button
                  onClick={() => setSelected(f.id)}
                  className={`mb-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 pr-9 text-left text-sm transition ${
                    selected === f.id ? "bg-[var(--brand-navy)] text-cream" : "text-muted hover:bg-[var(--surface-2)] hover:text-foreground"
                  }`}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>
                  <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  <span className="shrink-0 text-[10px] opacity-70">{f.employee_count}</span>
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); onDeleteFolder(f.id); }}
                  title="Delete folder"
                  aria-label={`Delete ${f.name}`}
                  className="absolute right-1.5 top-1.5 rounded-md p-1 text-muted opacity-0 transition hover:text-[var(--brand-red)] focus-visible:opacity-100 group-hover:opacity-100"
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m2 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" /></svg>
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Main */}
      <div className="min-w-0 flex-1 overflow-y-auto p-6">
        {!folder ? (
          <div className="flex h-full items-center justify-center text-center text-sm text-muted">
            <div>
              <p className="mb-1 font-medium text-foreground">Employee photo library</p>
              <p>Create a folder and add employees (photo + name + role). This is a reference library —<br />in <span className="font-medium text-foreground">Create</span> or <span className="font-medium text-foreground">Chat</span>, type <span className="font-mono">@</span> to feature anyone here in a post with their real photo.</p>
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-4xl">
            <h2 className="font-heading text-xl font-semibold">{folder.name}</h2>
            <p className="mt-1 text-sm text-muted">
              A reference photo library. To make a post featuring someone here, go to <span className="font-medium text-foreground">Create</span> or <span className="font-medium text-foreground">Chat</span> and type <span className="font-mono">@</span> their name — their real photo is used (never an AI face).
            </p>

            {/* Add employee */}
            <div className="mt-5 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
              <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted">Add an employee — name, role, then upload their photo from your device</div>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={addName}
                  onChange={(e) => setAddName(e.target.value)}
                  placeholder="Name (e.g. Nishant Trivedi)"
                  className="min-w-[12rem] flex-1 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none"
                />
                <input
                  value={addRole}
                  onChange={(e) => setAddRole(e.target.value)}
                  placeholder="Role (e.g. COO)"
                  className="min-w-[9rem] flex-1 rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5 text-sm outline-none"
                />
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) onAddEmployee(f); }}
                />
                <button
                  onClick={() => fileRef.current?.click()}
                  disabled={addBusy || !addName.trim()}
                  className="btn-primary shrink-0 disabled:opacity-50"
                  title={addName.trim() ? "Choose a photo from your device" : "Enter a name first"}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" /></svg>
                  {addBusy ? "Uploading…" : "Upload photo"}
                </button>
              </div>
            </div>

            {/* Employees */}
            {employees.length === 0 ? (
              <p className="mt-5 text-sm text-muted">No employees yet — add one above.</p>
            ) : (
              <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {employees.map((emp) => (
                  <div key={emp.id} className="group relative flex items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3">
                    {emp.file_url ? (
                      <button
                        type="button"
                        onClick={() => setPreview(emp)}
                        title={`View ${emp.name}'s photo`}
                        aria-label={`View ${emp.name}'s photo`}
                        className="shrink-0 rounded-lg"
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={fileUrl(emp.file_url)} alt={emp.name} className="h-12 w-12 cursor-zoom-in rounded-lg object-cover transition hover:opacity-90" />
                      </button>
                    ) : (
                      <div className="h-12 w-12 shrink-0 rounded-lg bg-[var(--surface-2)]" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{emp.name}</div>
                      {emp.role ? <div className="truncate text-xs text-muted">{emp.role}</div> : null}
                    </div>
                    <button
                      onClick={() => onDeleteEmployee(emp.id)}
                      title="Remove"
                      aria-label={`Remove ${emp.name}`}
                      className="absolute right-1.5 top-1.5 rounded-md p-1 text-muted opacity-0 transition hover:text-[var(--brand-red)] focus-visible:opacity-100 group-hover:opacity-100"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {preview && preview.file_url && (
        <EmployeePhotoModal emp={preview} onClose={() => setPreview(null)} />
      )}
    </div>
  );
}

// In-app lightbox for an employee's uploaded photo — mirrors AssetCard's MediaPreviewModal so the app
// has one consistent preview look. Click the backdrop or press Escape to close.
function EmployeePhotoModal({ emp, onClose }: { emp: Employee; onClose: () => void }) {
  const url = fileUrl(emp.file_url);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div
        className="relative flex max-h-[92vh] w-auto max-w-3xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border)] px-4 py-2.5">
          <span className="min-w-0 truncate font-heading text-sm font-semibold">
            {emp.name}{emp.role ? ` — ${emp.role}` : ""}
          </span>
          <div className="flex shrink-0 items-center gap-1">
            <button
              onClick={() => downloadFile(url, `${emp.name || "employee"}.jpg`).catch(() => {})}
              type="button"
              title="Download"
              aria-label="Download"
              className="rounded-lg p-1.5 text-muted transition hover:text-foreground"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" /></svg>
            </button>
            <button onClick={onClose} type="button" aria-label="Close preview" className="rounded-lg p-1.5 text-muted transition hover:text-foreground">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
            </button>
          </div>
        </div>
        <div className="flex items-center justify-center overflow-auto bg-[var(--surface-2)] p-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={url} alt={emp.name} className="max-h-[78vh] w-auto rounded-lg" />
        </div>
      </div>
    </div>
  );
}
