/** Exact application-side shape of the Python heart-analysis-v1 JSON contract. */
import { z } from "zod";

const finite = z.number().finite();
const nullableFinite = finite.nullable();
const interval = z.object({
  start_s: finite,
  end_s: finite,
  duration_ms: finite,
});

const rhythm = z.object({
  algorithm_version: z.string().min(1),
  heart_rate_bpm: nullableFinite,
  label: z.enum(["normal", "tachycardia", "bradycardia", "unknown"]),
  irregular: z.boolean().nullable(),
  interval_std_ms: nullableFinite,
  beat_intervals_ms: z.array(finite),
  usable_intervals: z.number().int().nonnegative(),
});

const cardiacEvents = z.object({
  algorithm_version: z.string().min(1),
  status: z.enum(["paired_candidates", "insufficient_evidence"]),
  candidate_times_s: z.array(finite),
  s1_times_s: z.array(finite),
  s2_times_s: z.array(finite),
  s3_candidates_s: z.array(finite),
  s4_candidates_s: z.array(finite),
  systolic_intervals: z.array(interval),
  diastolic_intervals: z.array(interval),
  systolic_interval_ms: nullableFinite,
  diastolic_interval_ms: nullableFinite,
});

const unavailableMurmur = z.object({
  status: z.literal("unavailable"),
  model_version: z.null(),
  preprocessing_version: z.null(),
  threshold_version: z.null(),
  probability: z.null(),
  threshold: z.null(),
  label: z.null(),
});

const availableMurmur = z.object({
  status: z.literal("available"),
  model_version: z.string().min(1),
  preprocessing_version: z.string(),
  threshold_version: z.string(),
  probability: finite.min(0).max(1),
  threshold: finite.min(0).max(1),
  label: z.enum(["present", "absent"]),
});

export const heartAnalysisSchema = z.object({
  schema_version: z.literal("heart-analysis-v1"),
  mode: z.literal("heart"),
  quality: z.object({
    valid: z.boolean(),
    score: nullableFinite,
    reason: z.string().nullable(),
  }),
  rhythm: rhythm.nullable(),
  cardiac_events: cardiacEvents.nullable(),
  murmur: z.discriminatedUnion("status", [unavailableMurmur, availableMurmur]).nullable(),
  visualization: z.object({
    waveform_available: z.boolean(),
    spectrogram_available: z.boolean(),
    event_annotations_available: z.boolean(),
  }),
}).superRefine((value, context) => {
  if (!value.quality.valid && (value.rhythm || value.cardiac_events || value.murmur)) {
    context.addIssue({ code: "custom", message: "Invalid audio must not contain analysis branches" });
  }
  if (value.quality.valid && (!value.rhythm || !value.cardiac_events || !value.murmur)) {
    context.addIssue({ code: "custom", message: "Valid audio must identify every branch" });
  }
  if (value.murmur?.status === "available") {
    const expected = value.murmur.probability >= value.murmur.threshold ? "present" : "absent";
    if (value.murmur.label !== expected) {
      context.addIssue({ code: "custom", message: "Murmur label conflicts with score" });
    }
  }
});

export type HeartAnalysisResult = z.infer<typeof heartAnalysisSchema>;

export function parseHeartAnalysisResult(input: unknown): HeartAnalysisResult {
  const parsed = heartAnalysisSchema.safeParse(input);
  if (!parsed.success) throw new Error("Respons Heart analysis tidak sesuai heart-analysis-v1.");
  return parsed.data;
}
