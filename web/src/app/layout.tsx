import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";

// Cinzel auto-hospedada (variable 400–700): la API de Google Fonts no está
// disponible en este entorno, así que servimos el woff2 desde /src/app/fonts.
const cinzel = localFont({
  src: [{ path: "./fonts/cinzel-var.woff2", weight: "400 700", style: "normal" }],
  variable: "--font-cinzel",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Cambiador de Voz DM — La forja de voces",
  description:
    "Consola de voz para el Dungeon Master: voces DSP en tiempo real, editor de parámetros, lectura de textos y un elenco latino de personajes (FakeYou) para dar voz a tus PNJs. Versión web, espejo de voz_dnd.",
  keywords: ["D&D", "cambiador de voz", "DM", "DSP", "tiempo real", "TTS", "FakeYou", "PNJ"],
};

export const viewport: Viewport = {
  themeColor: "#1e150f",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body
        className={`${GeistSans.variable} ${GeistMono.variable} ${cinzel.variable} antialiased bg-background text-foreground`}
      >
        {children}
        <Toaster position="top-center" richColors theme="dark" />
      </body>
    </html>
  );
}
