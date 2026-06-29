// PM2 process definition for the Talentrupt Marketing Agent — a SINGLE process.
// The frontend is exported to static files (frontend/out) and served by the FastAPI/uvicorn process,
// so there is no separate Node server: one process serves the UI, the API, SSE, and generated files.
//
// Run from the repo root ON THE DROPLET:
//   pm2 start ecosystem.config.js && pm2 save
//
// Prerequisites (done once — see deploy/DEPLOY.md):
//   - backend/.venv exists:  python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
//   - backend/.env is filled in (LLM_PROVIDER=openai, IMAGE_PROVIDER=openai, OPENAI_API_KEY, ...)
//   - frontend is built:     cd frontend && NEXT_PUBLIC_API_BASE= npm ci && NEXT_PUBLIC_API_BASE= npm run build
const path = require("path");
const ROOT = __dirname;

module.exports = {
  apps: [
    {
      // FastAPI / uvicorn — serves the static UI (frontend/out) AND the API + SSE + /api/files/...
      name: "talentrupt-api",
      cwd: path.join(ROOT, "backend"),
      script: ".venv/bin/python",
      args: "-m uvicorn app.main:app --host 127.0.0.1 --port 8100",
      interpreter: "none", // .venv/bin/python IS the interpreter
      autorestart: true,
      max_restarts: 10,
      env: { PYTHONUNBUFFERED: "1" },
    },
  ],
};
