# Deploying the Talentrupt Marketing Agent

Deploys onto the shared **htuniverse.com DigitalOcean droplet** (see `INFRA_BRIEF.md`) using the same
stack as the other apps — **PM2 → shared Nginx → Let's Encrypt** — as a **single process**:

| Process | What | Internal port | PM2 name |
|---|---|---|---|
| `talentrupt-api` | FastAPI/uvicorn — serves the **static UI** (`frontend/out`) **and** the API + SSE + generated files | `8100` | from `ecosystem.config.js` |

The Next.js frontend is **statically exported** (`output: 'export'` → `frontend/out`) and served by the
same uvicorn process — there is **no separate Node server**.

- **Public host:** `myra.htuniverse.com` (pick your own; **not** `trstudio.*`, which is a different app).
- **One Nginx host** proxies everything to `:8100` (`/api/` with SSE buffering off, `/` for the UI).
- **Port stays localhost-only** (not added to UFW) — Nginx is the only public entry point.
- **Build with a relative API base** (`NEXT_PUBLIC_API_BASE=` empty) so the UI calls same-origin `/api`.

> Pick a port that's free on the droplet. In use per the brief: `4200, 4500, 4001, 8001, 4400, 8080`.

---

## Fast path (one command)

After DNS is live and the repo is cloned, `deploy/bootstrap.sh` does the entire server-side setup
(packages → venv+deps → frontend build → PM2 → own Nginx file → own cert → verify). It's isolated —
it only writes its own `sites-available/talentrupt-agent` and its own cert, and leaves UFW alone, so it
can't affect the other 6 apps.

```bash
# on the droplet, as root
git clone <repo-url> /root/talentrupt-agent
cd /root/talentrupt-agent
DOMAIN=myra.htuniverse.com LE_EMAIL=surajit@talentrupt.com ./deploy/bootstrap.sh
# first run stops after creating backend/.env — fill it in, then re-run the same command
```

The manual, step-by-step version below explains exactly what that script does.

---

## First-time setup (manual / reference)

### 1. DNS (GoDaddy)
Add an A record: `marketing → 206.189.132.167` (per `dns/godaddy-htuniverse.md` in the infra repo).

### 2. Get the code on the droplet
```bash
ssh root@206.189.132.167
git clone <repo-url> /root/talentrupt-agent
cd /root/talentrupt-agent
git checkout main          # or the release branch
```

### 3. System packages (once)
```bash
apt update
apt install -y python3-venv
# Only needed if you ALSO install requirements-optional.txt (rembg/onnxruntime use OpenCV):
# apt install -y libgl1 libglib2.0-0
```

### 4. Backend
```bash
cd /root/talentrupt-agent/backend
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env   # fill it in — see "Environment" below. AT MINIMUM:
            #   LLM_PROVIDER=openai  IMAGE_PROVIDER=openai  OPENAI_API_KEY=sk-...
            #   ADMIN_PASSWORD / MEMBER_PASSWORD / ADMIN_TOKEN / MEMBER_TOKEN
            #   CORS_ORIGINS=https://myra.htuniverse.com
            #   STORAGE_DIR=/root/talentrupt-agent/storage
```
The DB tables and storage folders are created automatically on first start.

### 5. Frontend — static export (served by the backend; build with an EMPTY API base)
```bash
cd /root/talentrupt-agent/frontend
NEXT_PUBLIC_API_BASE= npm ci
NEXT_PUBLIC_API_BASE= npm run build   # writes frontend/out (served by uvicorn)
```
Empty `NEXT_PUBLIC_API_BASE` makes the UI call same-origin `/api`, so it works behind any host.
> ⚠️ `next build` is memory-heavy and the droplet is small (1.9 GB RAM, 6 apps). If the build OOMs,
> either add swap temporarily, stop a process during the build, or **build locally and rsync** the
> `frontend/out` to the server.

### 6. Start the process
```bash
cd /root/talentrupt-agent
pm2 delete talentrupt-web 2>/dev/null || true   # only needed if migrating from an old 2-process deploy
pm2 start ecosystem.config.js
pm2 save          # so it comes back after a reboot
pm2 status
```

### 7. Nginx
```bash
cp deploy/nginx-myra.conf /etc/nginx/sites-available/talentrupt-agent
ln -s /etc/nginx/sites-available/talentrupt-agent /etc/nginx/sites-enabled/talentrupt-agent
nginx -t && systemctl reload nginx
```

### 8. TLS (its own cert, like avasupport, so it can never affect the shared cert)
```bash
certbot certonly --nginx -d myra.htuniverse.com
systemctl reload nginx
```
Auto-renews via the existing `certbot.timer`.

### 9. Firewall
Do **nothing** — leave `8100`/`4600` out of UFW so they stay localhost-only (standard posture).

### 10. Verify
```bash
curl -s https://myra.htuniverse.com/api/health      # {"status":"ok", "llm_ready":true, ...}
```
Open `https://myra.htuniverse.com`, sign in, generate one image (confirms the OpenAI key + SSE).

---

## Routine redeploys
```bash
ssh root@206.189.132.167
cd /root/talentrupt-agent && ./deploy/deploy.sh        # pull -> deps -> rebuild -> pm2 restart
```
(Override the host with `WEB_ORIGIN=https://your.host ./deploy/deploy.sh`.)

---

## Environment (`backend/.env`)
Full template + comments live in `backend/.env.example`. The ones that matter most:

- **`LLM_PROVIDER=openai` + `IMAGE_PROVIDER=openai` + `OPENAI_API_KEY`** — without all three you get the
  deterministic fallback (no real AI). This is the #1 thing people miss.
- **`ADMIN_PASSWORD` / `MEMBER_PASSWORD`** and **`ADMIN_TOKEN` / `MEMBER_TOKEN`** — replace the dev
  defaults; make the tokens long random strings (`openssl rand -hex 24`).
- **`CORS_ORIGINS=https://myra.htuniverse.com`**.
- **`STORAGE_DIR`** — a persistent path (default `…/storage`); holds generated assets + uploads.
- **`KNOWLEDGE_ZIP_PATH` / `KNOWLEDGE_EXTRA_PDFS` / `BRAND_LOGO_PATH`** — these ground generation in
  Talentrupt's real brand. They default to **Windows** paths that don't exist on Linux. Copy the files
  to the droplet (e.g. `/root/talentrupt-agent/assets/`) and set absolute paths, or leave blank
  (generation still works, just less brand-grounded). First boot with `KNOWLEDGE_*` set runs vision
  ingestion (OpenAI cost, a few minutes).

---

## What persists vs. what's rebuilt
- **Persists on the server (never in git):** `backend/.env`, `backend/talentrupt.db*`, `storage/`. A
  `git pull` / redeploy does not touch them.
- **Rebuilt every deploy:** `frontend/out` (static export), `frontend/node_modules`, `backend/.venv` deps.

## Gotchas
- **RAM** — `next build` + uvicorn on a 2 GB box with 6 other apps is tight. The team-photo cut-out deps
  (`rembg`/`onnxruntime`) are now in `requirements-optional.txt` and NOT installed by default, which
  keeps memory + the dep tree light. Only `pip install -r requirements-optional.txt` if you want HEIC +
  background removal (and then `apt install libgl1 libglib2.0-0`).
- **First-run downloads** — `imageio-ffmpeg` fetches a ~30 MB binary on first use (and `rembg`, if you
  installed the optional extras, a ~176 MB model).
- **OpenAI cost** — every image/text generation is billable; the key stays server-side only.
