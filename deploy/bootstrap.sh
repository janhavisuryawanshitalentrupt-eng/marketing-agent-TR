#!/usr/bin/env bash
# First-time deployment of the Talentrupt Marketing Agent onto the shared htuniverse.com droplet.
# Mirrors the infra brief's pattern (own folder + own PM2 procs + localhost ports + own Nginx file +
# own Let's Encrypt cert, exactly like the AVA IT Support app).
#
# RUN AS ROOT ON THE DROPLET, from the cloned repo:
#   git clone <repo-url> /root/talentrupt-agent
#   cd /root/talentrupt-agent
#   DOMAIN=marketing.htuniverse.com LE_EMAIL=surajit@talentrupt.com ./deploy/bootstrap.sh
#
# PREREQUISITE: the DNS A record  DOMAIN -> this droplet  must already resolve (certbot needs it).
# It is SAFE for the other 6 apps: it only writes its OWN sites-available file + its OWN cert, and
# leaves UFW alone (ports stay localhost-only). It does NOT touch the shared cert or any other vhost.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${DOMAIN:-marketing.htuniverse.com}"
LE_EMAIL="${LE_EMAIL:-surajit@talentrupt.com}"
API_PORT="${API_PORT:-8100}"
WEB_PORT="${WEB_PORT:-4600}"
WEB_ORIGIN="https://$DOMAIN"
SITE="talentrupt-agent"
cd "$APP_DIR"

echo "==> Target: $WEB_ORIGIN   (api :$API_PORT, web :$WEB_PORT)   dir: $APP_DIR"

echo "==> [1/8] System packages"
apt-get update -y
apt-get install -y python3-venv nginx certbot python3-certbot-nginx
apt-get install -y libgl1 libglib2.0-0 || true   # only needed for the rembg/onnx photo-cutout deps
command -v pm2 >/dev/null || { echo "PM2 not found — install Node/PM2 first (see infra brief)"; exit 1; }

echo "==> [2/8] Backend venv + deps"
[ -d backend/.venv ] || python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip -q
backend/.venv/bin/pip install -q -r backend/requirements.txt

echo "==> [3/8] backend/.env"
if [ ! -f backend/.env ]; then
  cp backend/.env.example backend/.env
  echo "    Created backend/.env from the template."
  echo "    >>> EDIT backend/.env now, then re-run this script. Required for real output:"
  echo "          LLM_PROVIDER=openai   IMAGE_PROVIDER=openai   OPENAI_API_KEY=sk-..."
  echo "          ADMIN_PASSWORD=...  MEMBER_PASSWORD=...  ADMIN_TOKEN=...  MEMBER_TOKEN=..."
  echo "          CORS_ORIGINS=$WEB_ORIGIN   STORAGE_DIR=$APP_DIR/storage"
  echo "    Stopping so the app never boots with placeholder secrets."
  exit 1
fi

echo "==> [4/8] Frontend build (NEXT_PUBLIC_API_BASE=$WEB_ORIGIN)"
( cd frontend && NEXT_PUBLIC_API_BASE="$WEB_ORIGIN" npm ci && NEXT_PUBLIC_API_BASE="$WEB_ORIGIN" npm run build )

echo "==> [5/8] PM2 processes (talentrupt-api + talentrupt-web)"
pm2 startOrReload ecosystem.config.js
pm2 save

echo "==> [6/8] TLS cert (its OWN cert — never touches the shared cert)"
if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
  # Minimal HTTP vhost so certbot can solve the http-01 challenge for a brand-new domain.
  cat > "/etc/nginx/sites-available/$SITE" <<EOF
server { listen 80; listen [::]:80; server_name $DOMAIN; location / { return 200 'bootstrapping'; } }
EOF
  ln -sf "/etc/nginx/sites-available/$SITE" "/etc/nginx/sites-enabled/$SITE"
  nginx -t && systemctl reload nginx
  certbot certonly --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$LE_EMAIL"
fi

echo "==> [7/8] Nginx site (proxy /api -> :$API_PORT with SSE, / -> :$WEB_PORT)"
sed -e "s/marketing\.htuniverse\.com/$DOMAIN/g" \
    -e "s/127\.0\.0\.1:8100/127.0.0.1:$API_PORT/g" \
    -e "s/127\.0\.0\.1:4600/127.0.0.1:$WEB_PORT/g" \
    deploy/nginx-marketing.conf > "/etc/nginx/sites-available/$SITE"
ln -sf "/etc/nginx/sites-available/$SITE" "/etc/nginx/sites-enabled/$SITE"
nginx -t && systemctl reload nginx

echo "==> [8/8] Verify"
sleep 2
echo -n "    health: "; curl -fsS "$WEB_ORIGIN/api/health" || echo "(not ready yet — check: pm2 logs talentrupt-api)"
echo ""
echo "==> Done. Open $WEB_ORIGIN  (firewall: leave $API_PORT/$WEB_PORT out of UFW — localhost-only)."
