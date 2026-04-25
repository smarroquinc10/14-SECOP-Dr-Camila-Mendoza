import type { NextConfig } from "next";

const config: NextConfig = {
  // Local desktop app — no external image optimization needed.
  images: { unoptimized: true },
  // Bridge requests to the FastAPI backend running on :8000.
  async rewrites() {
    return [
      { source: "/api/secop/:path*", destination: "http://localhost:8000/:path*" },
    ];
  },
  // Suppress source-map warnings from heavy dependencies during dev.
  productionBrowserSourceMaps: false,
};

export default config;
