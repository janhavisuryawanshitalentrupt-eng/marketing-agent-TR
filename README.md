# Talentrupt AI — Marketing Agent

An internal AI marketing & business‑development workspace for **Talentrupt** (offshore RPO — "RPO Done Right"), built to sell into the US market. Turn a request into finished work: real US prospects, on‑brand content, sector‑coherent campaigns.

## Surfaces
- **Chat** — all‑access agent (tool‑calling): find/analyze prospects, write copy, generate visuals, search the brand library.
- **Create** — generate on‑brand images, decks (.pptx), and PDFs from a prompt; regenerate/refine any asset; upload brand assets.
- **Campaigns** — sector‑coherent, scored target clients per campaign; content calendar; CSV export; archive.
- **Business Dev** — web‑grounded US prospect discovery, fit scoring, pipeline, outreach **tracking** (track‑only), optional verified‑contact enrichment, CSV export, bulk actions.
- **Tasks** — follow‑up reminders (overdue / today / upcoming).
- **Analytics** — pipeline funnel, prospects by sector, outreach, campaigns, and content at a glance.

Anti‑fabrication and US‑default discovery are enforced throughout (no AI‑guessed names/emails; discovery is web‑grounded).

## Stack
- **Frontend:** Next.js 16 (App Router) · React 19 · TypeScript · Tailwind CSS v4
- **Backend:** FastAPI · SQLAlchemy 2 · SQLite · Pydantic v2 · httpx
- **Generation:** python‑pptx (decks) · reportlab (PDFs) · Pillow (images/logo) · pypdf (ingestion)
- **AI:** OpenAI‑compatible API (chat + JSON mode, embeddings, `gpt-image-1`, vision) via httpx

## Layout
```
backend/   FastAPI app (app/), requirements.txt, .env.example
frontend/  Next.js app (app/, components/, lib/)
```

## Setup

### 1. Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate           # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           # Windows  (macOS/Linux: cp .env.example .env)
# then edit .env and set OPENAI_API_KEY (+ LLM_PROVIDER=openai, IMAGE_PROVIDER=openai)
```

### 2. Frontend
```bash
cd frontend
npm install
```

## Run
```bash
# Terminal 1 — backend (http://127.0.0.1:8000)
cd backend
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — frontend (http://localhost:3000)
cd frontend
npm run dev
```
Open **http://localhost:3000** and sign in with the dev credentials (defaults in `.env.example`): `Admin@talentrupt.com` / `Admin123`.

> Without an `OPENAI_API_KEY`, the app still runs in a deterministic local mode (no live AI). Set the key for full discovery, chat, and generation.

## Configuration (`backend/.env`)
Copy from `.env.example`. Key settings:
- `LLM_PROVIDER=openai` + `OPENAI_API_KEY=...` — chat, discovery, JSON generation, embeddings.
- `IMAGE_PROVIDER=openai` — `gpt-image-1` images (falls back to a deterministic brand compositor otherwise).
- `KNOWLEDGE_ZIP_PATH`, `KNOWLEDGE_EXTRA_PDFS` — optional brand source library to ingest (`POST /api/knowledge/import`).
- `ENRICHMENT_PROVIDER` (`apollo`|`hunter`) + `ENRICHMENT_API_KEY` — **optional**; enables real verified decision‑maker contacts. Off by default (contacts stay role‑only).
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_TOKEN` — dev‑grade auth.

## Notes
- The SQLite DB, `node_modules`, `.venv`, `.next`, generated `storage/`, and **`backend/.env`** are gitignored — not committed. A fresh clone needs the three setup steps above.
- Dev‑grade single‑user auth by design; not production hardened.
