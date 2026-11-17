"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CircleUserRound, LogOut, Settings } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { accountClient } from "@/lib/auriscore/account-client";
import { useAccount } from "./account-panel";

export function AccountMenu({ disabled = false }: { disabled?: boolean }) {
  const { user } = useAccount();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return <div className="relative">
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label="Menu akun" title={disabled ? "Menu akun tersedia setelah rekaman selesai" : "Menu akun"}
          disabled={disabled || busy}
          className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-border bg-white text-emerald-900 transition-colors hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 focus-visible:ring-offset-2 disabled:opacity-50">
          <CircleUserRound className="h-6 w-6" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-44 rounded-xl p-1.5">
        <DropdownMenuItem asChild className="min-h-11 rounded-lg cursor-pointer">
          <Link href="/settings"><Settings aria-hidden="true" />Settings</Link>
        </DropdownMenuItem>
        <DropdownMenuItem disabled={!user || busy} className="min-h-11 rounded-lg cursor-pointer" onSelect={async () => {
          setBusy(true); setError(null);
          try {
            const { error } = await accountClient().auth.signOut({ scope: "local" });
            if (error) throw error;
            router.replace("/");
            router.refresh();
          } catch { setError("Keluar belum berhasil. Coba lagi."); setBusy(false); }
        }}><LogOut aria-hidden="true" />{busy ? "Memproses…" : "Keluar"}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
    {error && <p role="alert" className="absolute right-0 top-full z-50 mt-2 w-60 rounded-lg border bg-white p-3 text-sm shadow-sm">{error}</p>}
  </div>;
}
