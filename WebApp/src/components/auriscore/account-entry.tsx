"use client";

import { useState } from "react";
import { Activity, ArrowRight } from "lucide-react";
import { AccountPanel, useAccount } from "./account-panel";
import { MainScreen } from "./main-screen";

/** Account entry precedes capture, while guest access preserves local use. */
export function AccountEntry() {
  const { user, ready, recovery } = useAccount();
  const [guest, setGuest] = useState(false);
  if (!ready) return <main className="min-h-screen grid place-items-center"><p role="status">Memuat akun…</p></main>;
  if ((user || guest) && !recovery) return <MainScreen />;
  return <main className="min-h-screen grid place-items-center px-5 py-10 sm:py-14 bg-[radial-gradient(ellipse_at_top,_#e2eee7_0%,_#f8faf8_60%)]">
    <div className="w-full max-w-[440px]">
      <div className="mb-8 flex flex-col items-center gap-3 text-center">
        <div className="grid h-14 w-14 place-items-center rounded-2xl bg-emerald-900 text-white shadow-lg shadow-emerald-900/10"><Activity className="h-7 w-7" aria-hidden="true" /></div>
        <div><p className="text-2xl font-semibold tracking-tight text-emerald-950">AurisCore</p>
          <p className="mt-1 text-xs font-medium tracking-[0.16em] uppercase text-muted-foreground">Stetoskop Digital</p></div>
      </div>
      <div className="rounded-3xl border border-white bg-white p-6 shadow-[0_16px_64px_-24px_rgba(20,60,40,0.22)] sm:p-8">
        <AccountPanel presentation="entry" />
        {!recovery && <div className="mt-6 border-t border-border pt-5 text-center">
          <button className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl text-sm font-medium text-emerald-900 transition-colors hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2" onClick={() => setGuest(true)}>Lanjut sebagai tamu <ArrowRight className="h-4 w-4" aria-hidden="true" /></button>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">Tanpa akun, riwayat hanya tersedia selama halaman pemeriksaan terbuka.</p>
        </div>}
      </div>
      <p className="mt-6 text-center text-xs leading-relaxed text-muted-foreground">Pendamping auskultasi untuk Heart, Lung, dan Abdomen.<br />Hasil skrining bukan diagnosis medis.</p>
    </div>
  </main>;
}
