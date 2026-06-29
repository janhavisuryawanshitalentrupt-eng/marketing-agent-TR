#!/usr/bin/env bash
# Redeploy the Talentrupt Marketing Agent ON THE DROPLET.
#   cd /root/talentrupt-agent && ./deploy/deploy.sh
#
# First-time setup is in deploy/DEPLOY.md — this script only handles routine redeploys
# (pull -> backend deps -> rebuild frontend -> restart PM2). It does NOT touch .env, the DB,
# or the storage folder (those persist on the server and are gitignored).
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# The frontend bakes this in at build time; must match the public origin Nginx serves.
WEB_ORIGIN="${WEB_ORIGIN:-https://marketing.htuniverse.com}"
cd "$APP_DIR"

echo "==> [1/4] git pull"
git pull --ff-only

echo "==> [2/4] backend deps"
./backend/.venv/bin/pip install -q -r backend/requirements.txt

echo "==> [3/4] frontend build (NEXT_PUBLIC_API_BASE=$WEB_ORIGIN)"
cd "$APP_DIR/frontend"
npm ci
NEXT_PUBLIC_API_BASE="$WEB_ORIGIN" npm run build
cd "$APP_DIR"

echo "==> [4/4] restart PM2"
pm2 restart talentrupt-api talentrupt-web --update-env
pm2 save

echo "==> Done. Check: pm2 status && curl -s https://marketing.htuniverse.com/api/health"
