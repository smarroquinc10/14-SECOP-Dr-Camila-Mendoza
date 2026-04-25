import type { Metadata } from "next";
import { Inter, Source_Serif_4, JetBrains_Mono } from "next/font/google";
import "./globals.css";
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

export const metadata: Metadata = {
  title: "Sistema de Seguimiento Contratos FEAB · Dra Cami",
  description:
    "Sistema de Seguimiento de Contratos SECOP II · FEAB Fondo Especial para la Administración de Bienes · Fiscalía General de la Nación",
  // El feab-logo-square.png es el cubo FEAB (4 cuadrados azul marino con
  // F/E/A/B). Lo recortamos del feab-banner.png y lo padeamos en blanco
  // para que sirva como icon de la pestaña/favicon de WebView2.
  icons: { icon: "/feab-logo-square.png" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es" className={`${inter.variable} ${serif.variable} ${mono.variable}`}>
      <body className="font-sans">
        {children}
        {/* Auto-updater popup — invisible cuando no hay update o cuando
            corremos fuera de Tauri (npm run dev en browser normal). */}
        <UpdatePrompt />
      </body>
    </html>
  );
}
