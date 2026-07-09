#!/usr/bin/env bash
# Nightly LOCAL backup of the SQLite DB + storage/ dir, with rotation. Installed as a cron job by
# .github/workflows/deploy.yml (runs on the droplet). Keeps the newest $RETENTION archives under
# $BACKUP_DIR. This protects against accidental deletion / DB corruption (roll back to a recent day);
# it does NOT survive total loss of the droplet — for that, add an off-site copy later.
#
# Overridable via env (used by the local test): APP_ROOT, BACKUP_DIR, PYTHON, RETENTION.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/root/talentrupt-agent}"
BACKUP_DIR="${BACKUP_DIR:-/root/talentrupt-backups}"
PYTHON="${PYTHON:-$APP_ROOT/backend/.venv/bin/python}"
RETENTION="${RETENTION:-7}"
ENVF="$APP_ROOT/backend/.env"

# Resolve the real DB path from .env DATABASE_URL (sqlite:///path) if set, else the default location.
DB="$APP_ROOT/backend/talentrupt.db"
if [ -f "$ENVF" ]; then
  URL="$(grep -E '^DATABASE_URL=' "$ENVF" 2>/dev/null | head -1 | tr -d '\r' | sed 's/^DATABASE_URL=//' || true)"
  case "$URL" in
    sqlite:////*) DB="/${URL#sqlite:////}" ;;   # sqlite:////abs/path -> /abs/path
    sqlite:///*)  DB="${URL#sqlite:///}" ;;      # sqlite:///rel_or_abs
  esac
fi

# Resolve the real storage dir from .env STORAGE_DIR if set, else the default.
STORAGE="$APP_ROOT/storage"
if [ -f "$ENVF" ]; then
  SD="$(grep -E '^STORAGE_DIR=' "$ENVF" 2>/dev/null | head -1 | tr -d '\r' | sed 's/^STORAGE_DIR=//' || true)"
  if [ -n "$SD" ]; then STORAGE="$SD"; fi
fi

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Consistent SQLite snapshot via the online backup API (safe while the app is running; captures WAL).
if [ -f "$DB" ]; then
  "$PYTHON" - "$DB" "$WORK/talentrupt.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close(); src.close()
PY
else
  echo "WARN: DB not found at $DB — backing up storage only"
fi

# Bundle the DB snapshot + the storage dir into one archive.
ARCHIVE="$BACKUP_DIR/backup-$TS.tar.gz"
TAR_ARGS=()
if [ -f "$WORK/talentrupt.db" ]; then TAR_ARGS+=("-C" "$WORK" "talentrupt.db"); fi
if [ -d "$STORAGE" ]; then TAR_ARGS+=("-C" "$(dirname "$STORAGE")" "$(basename "$STORAGE")"); fi
if [ ${#TAR_ARGS[@]} -eq 0 ]; then
  echo "ERROR: nothing to back up (no DB and no storage dir)"; exit 1
fi
tar --force-local -czf "$ARCHIVE" "${TAR_ARGS[@]}"
echo "$(date -u +%FT%TZ) backup OK: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"

# Rotate: keep only the newest $RETENTION archives, delete the rest.
ls -1t "$BACKUP_DIR"/backup-*.tar.gz 2>/dev/null | tail -n +$((RETENTION + 1)) | xargs -r rm -f
