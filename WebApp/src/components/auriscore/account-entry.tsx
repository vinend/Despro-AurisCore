"use client";

import { useState } from "react";
import { AccountPanel, useAccount } from "./account-panel";
import { MainScreen } from "./main-screen";

/** Account entry precedes capture, while guest access preserves local use. */
export function AccountEntry() {
  const { user, ready, recovery } = useAccount();
  const [guest, setGuest] = useState(false);
  if (!ready) return <main className="min-h-screen grid place-items-center"><p role="status">Memuat akun…</p></main>;
  if ((user || guest) && !recovery) return <MainScreen />;
  return <main className="min-h-screen bg-background px-5 py-12 grid place-items-center">
    <div className="w-full max-w-xl space-y-6">
      <div className="space-y-2"><p className="text-sm font-semibold text-emerald-800">AurisCore · Stetoskop Digital</p>
        <h1 className="text-3xl font-semibold tracking-tight">Selamat datang.</h1>
        <p className="text-muted-foreground">Masuk untuk mengakses profil, hasil analisis, dan rekaman di perangkat lain.</p>
      </div>
      <AccountPanel />
      {!recovery && <div className="space-y-2 text-center">
        <button className="min-h-11 rounded-lg border bg-white px-5 py-2 font-medium" onClick={() => setGuest(true)}>Lanjut sebagai tamu</button>
        <p className="text-sm text-muted-foreground">Riwayat tamu tersedia selama halaman pemeriksaan terbuka dan tidak tersinkron ke akun.</p>
      </div>}
    </div>
  </main>;
}
