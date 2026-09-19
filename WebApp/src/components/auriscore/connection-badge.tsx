import { Badge } from "@/components/ui/badge";
import type { PcgConnectionState } from "@/lib/auriscore/pcg-connection";

interface ConnectionBadgeProps {
  state: PcgConnectionState;
  /** true bila hello.device mengandung "Mock" → wajib tampil badge simulasi. */
  isMock: boolean;
}

/**
 * Badge status koneksi (seksi 7):
 * - "Terputus" (merah) saat disconnected.
 * - "Terhubung, simulasi" (kuning) bila hello.device mengandung "Mock".
 * - "Perangkat" (hijau) untuk perangkat asli.
 * - Tambahan "Menyampung…" untuk fase connecting (dicatat di DECISIONS.md).
 */
export function ConnectionBadge({ state, isMock }: ConnectionBadgeProps) {
  if (state === "connected") {
    if (isMock) {
      return (
        <Badge className="gap-1.5 border-amber-300 bg-amber-100 text-amber-800 hover:bg-amber-100">
          <span className="size-1.5 shrink-0 rounded-full bg-amber-500" />
          Terhubung, simulasi
        </Badge>
      );
    }
    return (
      <Badge className="gap-1.5 border-emerald-300 bg-emerald-100 text-emerald-800 hover:bg-emerald-100">
        <span className="size-1.5 shrink-0 rounded-full bg-emerald-500" />
        Perangkat
      </Badge>
    );
  }

  if (state === "connecting") {
    return (
      <Badge variant="outline" className="gap-1.5 text-muted-foreground">
        <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-muted-foreground/50" />
        Menyambung…
      </Badge>
    );
  }

  return (
    <Badge className="gap-1.5 border-red-300 bg-red-100 text-red-700 hover:bg-red-100">
      <span className="size-1.5 shrink-0 rounded-full bg-red-500" />
      Terputus
    </Badge>
  );
}
