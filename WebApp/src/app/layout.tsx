import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

export const metadata: Metadata = {
  title: "AurisCore — Prototipe Stetoskop Digital",
  description:
    "Prototipe web app AurisCore: stream PCG simulasi dan analisis DSP Heart dari WAV lokal.",
  keywords: ["AurisCore", "stetoskop digital", "PCG", "WebSocket", "prototipe"],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
  themeColor: "#14251e",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="id" suppressHydrationWarning>
      <body className="antialiased bg-background text-foreground min-h-screen selection:bg-emerald-500/20">
        {children}
        <Toaster />
      </body>
    </html>
  );
}
