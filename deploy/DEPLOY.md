# Deploying the Talentrupt Marketing Agent

Deploys onto the shared **htuniverse.com DigitalOcean droplet** (see `INFRA_BRIEF.md`) using the same
stack as the other apps — **PM2 → shared Nginx → Let's Encrypt** — but this app is **two processes**:

| Process | What | Internal port (example) | PM2 name |
|---|---|---|---|
| `talentrupt-web` | Next.js UI (`next start`) | `4600` | from `ecosystem.config.js` |
| `talentrupt-api` | FastAPI/uvicorn — REST + SSE + generated files (`/api/...`) | `8100` | from `ecosystem.config.js` |

- **Public host:** `marketing.htuniverse.com` (pick your own; **not** `trstudio.*`, which is a different app).
- **One Nginx host** routes `/api/ → :8100` and `/ → :4600` (see `deploy/nginx-marketing.conf`).
- **Ports stay localhost-only** (not added to UFW) — Nginx is the only public entry point.

> Pick ports that are free on the droplet. In use per the brief: `4200, 4500, 4001, 8001, 4400, 8080`.
> If you change ports/host, update them in `ecosystem.config.js`, `deploy/nginx-marketing.conf`,
> `deploy/deploy.sh` (`WEB_ORIGIN`), and `backend/.env` (`CORS_ORIGINS`).

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
DOMAIN=marketing.htuniverse.com LE_EMAIL=surajit@talentrupt.com ./deploy/bootstrap.sh
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
# Only needed if you keep the team-photo cutout deps (rembg/onnxruntime use OpenCV):
apt install -y libgl1 libglib2.0-0
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
            #   CORS_ORIGINS=https://marketing.htuniverse.com
            #   STORAGE_DIR=/root/talentrupt-agent/storage
```
The DB tables and storage folders are created automatically on first start.

### 5. Frontend (the API base is baked in at BUILD time)
```bash
cd /root/talentrupt-agent/frontend
NEXT_PUBLIC_API_BASE=https://marketing.htuniverse.com npm ci
NEXT_PUBLIC_API_BASE=https://marketing.htuniverse.com npm run build
```
> ⚠️ `next build` is memory-heavy and the droplet is small (1.9 GB RAM, 6 apps). If the build OOMs,
> either add swap temporarily, stop a process during the build, or **build locally and rsync** the
> `frontend/.next` + `frontend/node_modules` to the server.

### 6. Start both processes
```bash
cd /root/talentrupt-agent
pm2 start ecosystem.config.js
pm2 save          # so they come back after a reboot
pm2 status
```

### 7. Nginx
```bash
cp deploy/nginx-marketing.conf /etc/nginx/sites-available/marketing
ln -s /etc/nginx/sites-available/marketing /etc/nginx/sites-enabled/marketing
nginx -t && systemctl reload nginx
```

### 8. TLS (its own cert, like avasupport, so it can never affect the shared cert)
```bash
certbot certonly --nginx -d marketing.htuniverse.com
systemctl reload nginx
```
Auto-renews via the existing `certbot.timer`.

### 9. Firewall
Do **nothing** — leave `8100`/`4600` out of UFW so they stay localhost-only (standard posture).

### 10. Verify
```bash
curl -s https://marketing.htuniverse.com/api/health      # {"status":"ok", "llm_ready":true, ...}
```
Open `https://marketing.htuniverse.com`, sign in, generate one image (confirms the OpenAI key + SSE).

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
- **`CORS_ORIGINS=https://marketing.htuniverse.com`**.
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
- **Rebuilt every deploy:** `frontend/.next`, `frontend/node_modules`, `backend/.venv` deps.

## Gotchas
- **RAM** — uvicorn + onnxruntime/rembg + a Node server on a 2 GB box with 6 other apps is tight. If you
  don't need team-photo cutouts, you can drop `rembg`/`onnxruntime` from `requirements.txt` to save
  memory (the code falls back gracefully).
- **First-run downloads** — `rembg` fetches a ~176 MB model and `imageio-ffmpeg` a ~30 MB binary on
  first use (needs outbound network + disk).
- **OpenAI cost** — every image/text generation is billable; the key stays server-side only.
