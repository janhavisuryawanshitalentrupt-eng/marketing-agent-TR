#!/usr/bin/env bash
# Redeploy the Talentrupt Marketing Agent ON THE DROPLET.
#   cd /root/talentrupt-agent && ./deploy/deploy.sh
#
# First-time setup is in deploy/DEPLOY.md — this script only handles routine redeploys
# (pull -> backend deps -> rebuild frontend -> restart PM2). It does NOT touch .env, the DB,
# or the storage folder (those persist on the server and are gitignored).
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "==> [1/4] git pull"
git pull --ff-only

echo "==> [2/4] backend deps"
./backend/.venv/bin/pip install -q -r backend/requirements.txt

echo "==> [3/4] frontend static export (relative API base -> same-origin /api)"
cd "$APP_DIR/frontend"
npm ci
NEXT_PUBLIC_API_BASE="" npm run build
cd "$APP_DIR"

echo "==> [4/4] restart PM2 (single process)"
pm2 restart talentrupt-api --update-env
pm2 save

echo "==> Done. Check: pm2 status && curl -s https://myra.htuniverse.com/api/health"
