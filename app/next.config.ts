import type { NextConfig } from "next";

// El frontend es un static export que se sirve en TRES contextos:
//
//   1. Dev local — `npm run dev` en localhost:3000 — sin basePath.
//   2. GitHub Pages — https://smarroquinc10.github.io/<repo>/ — necesita
//      basePath para que los assets resuelvan al subpath correcto.
//   3. Tauri MSI (legacy) — http://tauri.localhost — sin basePath.
//
// Como `basePath` se hornea en el HTML al build time, lo controlamos vía
// env var: el workflow `.github/workflows/deploy-pages.yml` exporta
// `NEXT_PUBLIC_BASE_PATH=/14-SECOP-Dr-Camila-Mendoza` antes del build.
// Localmente y en Tauri no se setea, así que basePath queda vacío.
//
// La misma env var la usa `lib/state-store.ts:withBasePath()` para
// resolver fetches a `/data/*.json` con el prefix correcto.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const config: NextConfig = {
  output: "export",
  // Trailing slash mejora compatibilidad con GitHub Pages que sirve
  // subpaths como /index.html — sin trailing slash, Pages a veces 404ea.
  trailingSlash: true,
  basePath: basePath || undefined,
  assetPrefix: basePath ? `${basePath}/` : undefined,
  // Static export no puede usar Image Optimization API.
  images: { unoptimized: true },
  productionBrowserSourceMaps: false,
};

export default config;
