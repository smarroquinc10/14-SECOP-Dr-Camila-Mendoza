import type { NextConfig } from "next";

// Tauri MSI ships a static export. The frontend runs from
// http://tauri.localhost (Windows) or tauri://localhost (macOS/Linux) and
// fetches the FastAPI sidecar on http://127.0.0.1:8000 directly — see
// app/src/lib/api.ts. CORS for those origins is configured in
// src/secop_ii/api.py.
const config: NextConfig = {
  output: "export",
  // Static export can't use the Image Optimization API.
  images: { unoptimized: true },
  // Static export can't ship Next.js rewrites either; the frontend now
  // calls FastAPI directly. We keep the rewrite OFF deliberately so dev
  // and prod use the exact same network path (no behavior split).
  productionBrowserSourceMaps: false,
};

export default config;
