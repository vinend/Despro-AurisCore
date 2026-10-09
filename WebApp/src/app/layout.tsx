import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

export const metadata: Metadata = {
  title: "AurisCore — Prototipe Stetoskop Digital",
  description:
    "Prototipe web app AurisCore: stream PCG simulasi dan analisis DSP Heart dari WAV lokal.",
  keywords: ["AurisCore", "stetoskop digital", "PCG", "WebSocket", "prototipe"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="id" suppressHydrationWarning>
      <body
        className="antialiased bg-background text-foreground"
      >
        {children}
        <Toaster />
      </body>
    </html>
  );
}
