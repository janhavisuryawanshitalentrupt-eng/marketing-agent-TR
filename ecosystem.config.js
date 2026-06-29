// PM2 process definitions for the Talentrupt Marketing Agent.
// Run from the repo root ON THE DROPLET:
//   pm2 start ecosystem.config.js && pm2 save
//
// Prerequisites (done once — see deploy/DEPLOY.md):
//   - backend/.venv exists:  python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
//   - backend/.env is filled in (LLM_PROVIDER=openai, IMAGE_PROVIDER=openai, OPENAI_API_KEY, ...)
//   - frontend is built:     cd frontend && NEXT_PUBLIC_API_BASE=https://marketing.htuniverse.com npm ci && npm run build
const path = require("path");
const ROOT = __dirname;

module.exports = {
  apps: [
    {
      // FastAPI / uvicorn — REST + SSE + serves generated files under /api/files/...
      name: "talentrupt-api",
      cwd: path.join(ROOT, "backend"),
      script: ".venv/bin/python",
      args: "-m uvicorn app.main:app --host 127.0.0.1 --port 8100",
      interpreter: "none", // .venv/bin/python IS the interpreter
      autorestart: true,
      max_restarts: 10,
      env: { PYTHONUNBUFFERED: "1" },
    },
    {
      // Next.js web app — `next start` reads PORT from the environment.
      name: "talentrupt-web",
      cwd: path.join(ROOT, "frontend"),
      script: "npm",
      args: "start",
      autorestart: true,
      max_restarts: 10,
      env: { NODE_ENV: "production", PORT: "4600" },
    },
  ],
};
