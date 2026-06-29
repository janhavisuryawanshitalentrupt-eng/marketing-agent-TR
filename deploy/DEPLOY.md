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

## Accounts & data isolation
Two logins, each with its own private data (conversations, campaigns, assets, opportunities, tasks):

| Login | Role | Sees |
|---|---|---|
| `Admin@talentrupt.com` | admin | everything, incl. **Tasks** & **Analytics** |
| `nishant@talentrupt.com` | member | Chat / Create / Campaigns / Business Dev — **no** Tasks/Analytics |

- Passwords + tokens come from `backend/.env` (`ADMIN_PASSWORD`/`MEMBER_PASSWORD`, `ADMIN_TOKEN`/`MEMBER_TOKEN`).
- Role is derived server-side from the token; Tasks/Analytics are enforced admin-only at the API, not just the UI.
- Every record is scoped by `owner`; one account can't see or touch the other's data. A one-time migration
  (auto-runs on startup) assigns all pre-existing data to **admin**.

---

## Routine redeploys — fully automated (build → push → deploy)

**Every release is one command, run from your PC:**

```powershell
./deploy/ship.ps1 "what changed"
```

That builds the frontend locally (a pre-flight gate), commits, and pushes. The push triggers
**`.github/workflows/deploy.yml`**, which rebuilds the UI on GitHub's runner (so the 2 GB droplet never
runs `next build`), ships the code + built UI, runs `pm2 restart myra`, and health-checks
`/api/health`. **You never touch the droplet.** Extracting the deploy never touches `backend/.env`,
`talentrupt.db*`, or `storage/` (git-ignored, never in the archive).

Watch a deploy: repo → **Actions** → the latest **Deploy** run.

### Auto-deploy enablement (one-time)
CI can't bootstrap its own access to a server — someone with droplet access must authorize it once.
A deploy keypair has already been generated at `~/.ssh/talentrupt_deploy` (private) +
`~/.ssh/talentrupt_deploy.pub` (public). Then:

1. **Authorize the key on the droplet** (run on your PC; enter the root password once):
   ```powershell
   type $env:USERPROFILE\.ssh\talentrupt_deploy.pub | ssh root@206.189.132.167 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
   ```
2. **Add two GitHub repo secrets** (repo → Settings → Secrets and variables → Actions → New secret):
   - `DROPLET_HOST` = `206.189.132.167`
   - `DROPLET_SSH_KEY` = the full contents of `~/.ssh/talentrupt_deploy` (the **private** key file)

After that, `deploy/ship.ps1` (or any push to `feat/create-chip-brief-intake` / `main`) deploys
automatically — no further manual steps, ever.

### Manual fallback (only if CI is unavailable)
```powershell
git archive --format=tar.gz -o "$env:USERPROFILE\Downloads\myra-deploy.tar.gz" feat/create-chip-brief-intake
scp "$env:USERPROFILE\Downloads\myra-deploy.tar.gz" root@206.189.132.167:/root/myra-deploy.tar.gz
```
```bash
# on the droplet
tar -xzf /root/myra-deploy.tar.gz -C /root/talentrupt-agent
cd /root/talentrupt-agent/frontend && NEXT_PUBLIC_API_BASE= npm run build && pm2 restart myra
```

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
- **Persists on the server (never in the tarball):** `backend/.env`, `backend/talentrupt.db*`, `storage/`.
  Extracting a redeploy tarball does not touch them.
- **Rebuilt every deploy:** `frontend/out` (static export), `frontend/node_modules`, `backend/.venv` deps.

## Restore pre-deployment dev data (optional)
The droplet started with an **empty** database, so the campaigns/images/decks generated locally during
development are not live. To load them onto the server:

1. Stop the app: `pm2 stop myra`
2. Copy the dev DB up (from your PC):
   `scp "<repo>\backend\talentrupt.db" root@206.189.132.167:/root/talentrupt-agent/backend/talentrupt.db`
3. Copy the media so the gallery resolves (large — ~300 MB):
   `scp -r "<repo>\storage\*" root@206.189.132.167:/root/talentrupt-agent/storage/`
   (`serve_file` looks files up by name under `STORAGE_DIR`, so the Windows `file_path` mismatch is harmless.)
4. `pm2 start myra` — the startup migration assigns all imported rows to **admin**.

A readable export of that data (campaigns, posts, conversations, opportunities) is in
`talentrupt-predeploy-export.json`; the raw DB copy is `talentrupt-predeploy.db`.

## Gotchas
- **RAM** — `next build` + uvicorn on a 2 GB box with 6 other apps is tight. The team-photo cut-out deps
  (`rembg`/`onnxruntime`) are now in `requirements-optional.txt` and NOT installed by default, which
  keeps memory + the dep tree light. Only `pip install -r requirements-optional.txt` if you want HEIC +
  background removal (and then `apt install libgl1 libglib2.0-0`).
- **First-run downloads** — `imageio-ffmpeg` fetches a ~30 MB binary on first use (and `rembg`, if you
  installed the optional extras, a ~176 MB model).
- **OpenAI cost** — every image/text generation is billable; the key stays server-side only.
