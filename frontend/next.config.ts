import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Export a fully static site so ONE FastAPI/uvicorn process serves both the UI and /api — no Node
  // server at runtime. `next build` writes the static site to `frontend/out/`.
  output: "export",
  // Emit `route/index.html` so deep links + refresh resolve when served as plain files.
  trailingSlash: true,
  // Static export can't use the on-the-fly image optimizer (we use plain <img>, so this is a no-op).
  images: { unoptimized: true },
};

export default nextConfig;
