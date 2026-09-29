import { Activity, BrainCircuit, Database, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { TrainingMetrics } from "@/lib/auriscore/training-metrics";

interface TrainingMetricsCardProps {
  metrics: TrainingMetrics | null;
}

function percentage(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function TrainingMetricsCard({ metrics }: TrainingMetricsCardProps) {
  if (!metrics) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <BrainCircuit className="size-4 text-teal-600" />
            Metrik pelatihan CNN
          </CardTitle>
          <CardDescription>
            Berkas hasil pelatihan lokal belum tersedia.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const [[trueNegative, falsePositive], [falseNegative, truePositive]] =
    metrics.confusionMatrix;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b bg-muted/25">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <BrainCircuit className="size-4 text-teal-600" />
              Metrik pelatihan CNN
            </CardTitle>
            <CardDescription className="mt-1">
              Validasi pengembangan pada dataset CirCor nyata · bukan hasil
              mock-device dan bukan holdout klinis.
            </CardDescription>
          </div>
          <Badge variant="outline" className="border-teal-300 bg-teal-50 text-teal-700">
            data pelatihan nyata
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
          <Metric label="Sensitivitas" value={percentage(metrics.sensitivity)} />
          <Metric label="Spesifisitas" value={percentage(metrics.specificity)} />
          <Metric label="NPV" value={percentage(metrics.negativePredictiveValue)} />
          <Metric label="Macro F1" value={percentage(metrics.macroF1)} />
        </div>

        <div className="grid gap-3 text-sm md:grid-cols-2">
          <div className="rounded-lg border bg-muted/25 p-3">
            <p className="mb-2 flex items-center gap-1.5 font-medium">
              <Database className="size-3.5 text-teal-600" />
              Cakupan data
            </p>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <dt className="text-muted-foreground">Latih</dt>
              <dd className="text-right font-medium tabular-nums">
                {metrics.trainSubjects} subjek · {metrics.trainRecordings} rekaman
              </dd>
              <dt className="text-muted-foreground">Validasi</dt>
              <dd className="text-right font-medium tabular-nums">
                {metrics.validationSubjects} subjek · {metrics.validationRecordings} rekaman
              </dd>
              <dt className="text-muted-foreground">Pipeline</dt>
              <dd className="text-right font-medium tabular-nums">
                {metrics.sampleRate} Hz · band ≤ {metrics.signalBandMaxHz} Hz
              </dd>
              <dt className="text-muted-foreground">Pelatihan</dt>
              <dd className="text-right font-medium tabular-nums">
                {metrics.trainingEpochs} epoch · loss {metrics.bestValidationLoss.toFixed(4)}
              </dd>
            </dl>
          </div>

          <div className="rounded-lg border bg-muted/25 p-3">
            <p className="mb-2 flex items-center gap-1.5 font-medium">
              <Activity className="size-3.5 text-teal-600" />
              Ambang dan confusion matrix
            </p>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <dt className="text-muted-foreground">Ambang model</dt>
              <dd className="text-right font-medium tabular-nums">
                {metrics.threshold.toFixed(4)}
              </dd>
              <dt className="text-muted-foreground">Akurasi / presisi</dt>
              <dd className="text-right font-medium tabular-nums">
                {percentage(metrics.accuracy)} / {percentage(metrics.precision)}
              </dd>
              <dt className="text-muted-foreground">TN / FP</dt>
              <dd className="text-right font-medium tabular-nums">
                {trueNegative} / {falsePositive}
              </dd>
              <dt className="text-muted-foreground">FN / TP</dt>
              <dd className="text-right font-medium tabular-nums">
                {falseNegative} / {truePositive}
              </dd>
            </dl>
          </div>
        </div>

        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" />
          <p>
            Target sensitivitas {percentage(metrics.targetSensitivity)} tercapai,
            tetapi spesifisitas {percentage(metrics.specificity)} masih di bawah
            batas {percentage(metrics.minimumSpecificity)}. Model tetap untuk
            riset dan demonstrasi, bukan diagnosis medis.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-background p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}
