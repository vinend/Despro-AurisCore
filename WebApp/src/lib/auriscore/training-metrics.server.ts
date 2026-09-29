import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";

import type { TrainingMetrics } from "./training-metrics";

interface RawMetrics {
  status: string;
  sample_rate: number;
  signal_band_max_hz: number;
  development_split_counts: {
    train: { subjects: number; recordings: number };
    validation: { subjects: number; recordings: number };
  };
  threshold_selection: {
    threshold: number;
    target_sensitivity: number;
    minimum_specificity: number;
    constraints_met: boolean;
  };
  validation: {
    subject: {
      accuracy: number;
      precision: number;
      recall_sensitivity: number;
      specificity: number;
      negative_predictive_value: number;
      macro_f1: number;
      confusion_matrix: [[number, number], [number, number]];
    };
  };
  training_epochs: number;
  best_validation_loss: number;
  warning: string;
}

const metricsPath = path.resolve(
  process.cwd(),
  "../AI-Pipeline/artifacts/metrics/cnn_metrics.json"
);

/** Load the latest local real-data CNN validation result for the demo UI. */
export async function loadTrainingMetrics(): Promise<TrainingMetrics | null> {
  try {
    const raw = JSON.parse(
      await readFile(metricsPath, "utf8")
    ) as RawMetrics;
    const subject = raw.validation.subject;

    return {
      status: raw.status,
      sampleRate: raw.sample_rate,
      signalBandMaxHz: raw.signal_band_max_hz,
      trainSubjects: raw.development_split_counts.train.subjects,
      trainRecordings: raw.development_split_counts.train.recordings,
      validationSubjects: raw.development_split_counts.validation.subjects,
      validationRecordings: raw.development_split_counts.validation.recordings,
      threshold: raw.threshold_selection.threshold,
      targetSensitivity: raw.threshold_selection.target_sensitivity,
      minimumSpecificity: raw.threshold_selection.minimum_specificity,
      constraintsMet: raw.threshold_selection.constraints_met,
      accuracy: subject.accuracy,
      precision: subject.precision,
      sensitivity: subject.recall_sensitivity,
      specificity: subject.specificity,
      negativePredictiveValue: subject.negative_predictive_value,
      macroF1: subject.macro_f1,
      confusionMatrix: subject.confusion_matrix,
      trainingEpochs: raw.training_epochs,
      bestValidationLoss: raw.best_validation_loss,
      warning: raw.warning,
    };
  } catch (error) {
    console.warn("[training-metrics] CNN metrics unavailable:", error);
    return null;
  }
}
