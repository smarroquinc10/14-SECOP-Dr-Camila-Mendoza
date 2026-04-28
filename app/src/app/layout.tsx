import type { Metadata } from "next";
import { Inter, Source_Serif_4, JetBrains_Mono } from "next/font/google";
import "./globals.css";
// AccessGate envuelve la app entera con un passphrase prompt para que
// solo la Dra Camila pueda entrar. Detalle de la barrera y cómo cambiar
// el passphrase: ver docstring en components/access-gate.tsx.
import { AccessGate } from "@/components/access-gate";
// UpdatePrompt es un opt-in del bundle Tauri. En la versión web (GitHub
// Pages) no se monta — `isInTauri()` adentro del componente devuelve false
// y se queda silencioso. La importamos igualmente para no quitarla del
// codepath cuando alguien decida volver al MSI.
import { UpdatePrompt } from "@/components/update-prompt";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});
const serif = Source_Serif_4({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-serif",
  weight: ["400", "600", "700"],
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-mono",
  weight: ["400", "500", "600"],
});

// Next no prefija el path de `icons` con `basePath` automáticamente, así
// que en GitHub Pages (basePath = "/14-SECOP-Dr-Camila-Mendoza") el
// favicon resolvía a /feab-logo-square.png y daba 404. Lo construimos a
// mano leyendo la misma env var que usa next.config.ts.
const _basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  title: "Sistema de Seguimiento Contratos FEAB · Dra Cami",
  description:
    "Sistema de Seguimiento de Contratos SECOP II · FEAB Fondo Especial para la Administración de Bienes · Fiscalía General de la Nación",
  // El feab-logo-square.png es el cubo FEAB (4 cuadrados azul marino con
  // F/E/A/B). Lo recortamos del feab-banner.png y lo padeamos en blanco
  // para que sirva como icon de la pestaña/favicon de WebView2.
  icons: { icon: `${_basePath}/feab-logo-square.png` },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es" className={`${inter.variable} ${serif.variable} ${mono.variable}`}>
      <head>
        {/*
          Content-Security-Policy via meta tag (GitHub Pages no permite
          headers HTTP custom, pero meta http-equiv funciona para CSP).
          Limita qué orígenes pueden cargar scripts/imágenes/conexiones,
          mitigando inyecciones de HTML de terceros.
          Permitidos:
            - 'self'       → todo lo que viene del propio Pages
            - data:        → para imágenes inline (PNG base64 ocasionales)
            - datos.gov.co → para los fetches LIVE a Socrata (jbjy + rpmr)
            - fonts.googleapis.com / fonts.gstatic.com → next/font
          'unsafe-inline' en script-src lo necesita Next 16 para hidratar
          (tiene scripts inline en el HTML); el riesgo lo bajamos prohibiendo
          inserción cruda de HTML del SECOP en el código (React escapa por default).
        */}
        <meta
          httpEquiv="Content-Security-Policy"
          content="default-src 'self'; img-src 'self' data: https:; font-src 'self' data: https://fonts.gstatic.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; script-src 'self' 'unsafe-inline' 'unsafe-eval'; connect-src 'self' https://www.datos.gov.co https://*.github.io https://api.github.com; base-uri 'self'; form-action 'self';"
        />
      </head>
      <body className="font-sans">
        <AccessGate>
          {children}
          {/* Auto-updater popup — invisible cuando no hay update o cuando
              corremos fuera de Tauri (npm run dev en browser normal). */}
          <UpdatePrompt />
        </AccessGate>
      </body>
    </html>
  );
}
