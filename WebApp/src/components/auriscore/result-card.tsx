"use client";

import { motion } from "framer-motion";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Loader2,
  Mic,
} from "lucide-react";

import type { RecordingPhase } from "@/hooks/use-recording";
import type { ClassificationResult } from "@/lib/auriscore/fake-classifier";
import {
  formatDurationMs,
  formatTimestamp,
  ORGAN_MODE_LABELS,
} from "@/lib/auriscore/format";
import { cn } from "@/lib/utils";

interface ResultCardProps {
  phase: RecordingPhase;
  result: ClassificationResult | null;
}

/**
 * Kartu hasil (seksi 9): muncul setelah rekaman — label Normal/Abnormal,
 * confidence acak 87–97%, timestamp, dan teks kecil "hasil simulasi".
 */
export function ResultCard({ phase, result }: ResultCardProps) {
  return (
    <Card
      className={cn(
        phase === "done" &&
          result &&
          (result.label === "Normal" ? "border-emerald-300" : "border-red-300")
      )}
    >
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          Hasil klasifikasi
          {phase === "done" && result && (
            <Badge
              variant="outline"
              className="ml-auto text-[11px] font-normal text-muted-foreground"
            >
              hasil simulasi
            </Badge>
          )}
        </CardTitle>
        <CardDescription>Klasifikasi tiruan, bukan model AI.</CardDescription>
      </CardHeader>
      <CardContent>
        {phase === "idle" && <Idle />}
        {phase === "recording" && <Recording />}
        {phase === "processing" && <Processing />}
        {phase === "done" && result && <Done result={result} />}
      </CardContent>
    </Card>
  );
}

function Idle() {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed bg-muted/30 px-4 py-8 text-center">
      <Mic className="size-5 text-muted-foreground/70" />
      <p className="text-sm font-medium">Belum ada rekaman</p>
      <p className="max-w-xs text-xs text-muted-foreground">
        Tekan Rekam untuk memulai sesi 10 detik. Hasil klasifikasi tiruan akan
        tampil di sini.
      </p>
    </div>
  );
}

function Recording() {
  return (
    <div className="flex items-center gap-3 rounded-lg border bg-muted/30 px-4 py-6">
      <span className="relative flex size-2.5 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-75" />
        <span className="relative inline-flex size-2.5 rounded-full bg-rose-500" />
      </span>
      <p className="text-sm font-medium">Sesi rekaman berjalan…</p>
    </div>
  );
}

function Processing() {
  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-muted/30 px-4 py-6">
      <p className="flex items-center gap-2 text-sm font-medium">
        <Loader2 className="size-4 animate-spin text-teal-600" />
        Memproses rekaman…
      </p>
      <div className="space-y-2">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-48" />
      </div>
    </div>
  );
}

function Done({ result }: { result: ClassificationResult }) {
  const normal = result.label === "Normal";
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="flex flex-col gap-4"
    >
      <div className="flex items-center gap-4">
        <span
          className={cn(
            "flex size-11 shrink-0 items-center justify-center rounded-full",
            normal ? "bg-emerald-100 text-emerald-600" : "bg-red-100 text-red-600"
          )}
        >
          {normal ? (
            <CheckCircle2 className="size-6" />
          ) : (
            <AlertTriangle className="size-6" />
          )}
        </span>
        <div className="min-w-0">
          <p
            className={cn(
              "text-2xl font-semibold leading-tight",
              normal ? "text-emerald-700" : "text-red-700"
            )}
          >
            {result.label}
          </p>
          <p className="text-sm text-muted-foreground">
            Keyakinan {result.confidencePercent}%{" "}
            <span className="text-xs">(nilai acak, simulasi)</span>
          </p>
        </div>
      </div>
      <dl className="grid grid-cols-3 gap-2 text-sm">
        <div className="rounded-md bg-muted/50 p-2">
          <dt className="text-xs text-muted-foreground">Mode organ</dt>
          <dd className="truncate font-medium">
            {ORGAN_MODE_LABELS[result.organMode]}
          </dd>
        </div>
        <div className="rounded-md bg-muted/50 p-2">
          <dt className="text-xs text-muted-foreground">Durasi</dt>
          <dd className="font-medium tabular-nums">
            {formatDurationMs(result.durationMs)}
          </dd>
        </div>
        <div className="rounded-md bg-muted/50 p-2">
          <dt className="text-xs text-muted-foreground">Waktu</dt>
          <dd className="font-medium tabular-nums">
            {formatTimestamp(result.ts)}
          </dd>
        </div>
      </dl>
      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
        <Info className="mt-0.5 size-3.5 shrink-0" />
        Hasil klasifikasi tiruan — bukan diagnosis medis.
      </p>
    </motion.div>
  );
}
