# deploy/ship.ps1 — ONE command: build -> push -> auto-deploy to production.
#
# This is the whole release process. It:
#   1. builds the frontend locally as a pre-flight gate (fails fast if the build is broken,
#      so a broken build never reaches production),
#   2. commits every change,
#   3. pushes — which triggers .github/workflows/deploy.yml to ship it to
#      https://myra.htuniverse.com and restart the `myra` process.
#
# You never touch the droplet. After the one-time secret setup (see APPLICATION.md / DEPLOY.md),
# this is fully hands-off.
#
# Usage:
#   ./deploy/ship.ps1 "short description of what changed"

param(
  [Parameter(Mandatory = $true)]
  [string]$Message
)

$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
Set-Location $repo

Write-Host "==> [1/3] Building frontend (pre-flight gate)..." -ForegroundColor Cyan
Push-Location frontend
try {
  $env:NEXT_PUBLIC_API_BASE = ""
  if (-not (Test-Path node_modules)) { npm ci }
  npm run build
}
finally { Pop-Location }

Write-Host "==> [2/3] Committing..." -ForegroundColor Cyan
git add -A
# Nothing staged? Then there is nothing to ship — bail cleanly.
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
  Write-Host "No changes to commit. Nothing to deploy." -ForegroundColor Yellow
  exit 0
}
git commit -m $Message

Write-Host "==> [3/3] Pushing (this triggers the production deploy)..." -ForegroundColor Cyan
git push

Write-Host ""
Write-Host "Done. CI is now building + deploying to https://myra.htuniverse.com" -ForegroundColor Green
Write-Host "Track it: repo -> Actions -> 'Deploy' (the newest run)." -ForegroundColor Green
