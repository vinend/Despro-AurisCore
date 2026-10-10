import { z } from "zod";
import { heartAnalysisSchema } from "./heart-result.ts";

export type AnalysisMode = "heart" | "abdomen";
const finite = z.number().finite();
const unit = finite.min(0).max(1);
const quality = z.object({ valid: z.boolean(), reason: z.string().nullable() });
const activity = z.object({
  target: z.literal("bowel_sound_activity"), inference_unit: z.literal("window"), aggregation: z.literal("none"),
  model_version: z.string().min(1), preprocessing_version: z.string().min(1), threshold_version: z.string().min(1),
  threshold: unit, score_kind: z.literal("uncalibrated_sigmoid"), probability_is_calibrated: z.literal(false),
  window_seconds: finite.positive(), overlap: finite.min(0).lt(1),
  windows: z.array(z.object({ start_s: finite.nonnegative(), end_s: finite.positive(), score: unit,
    label: z.enum(["present", "absent"]) })).min(1).max(512),
  window_count: z.number().int().positive(), active_window_count: z.number().int().nonnegative(),
  active_window_fraction: unit, analyzed_duration_s: finite.positive(), discarded_tail_s: finite.nonnegative(),
}).superRefine((value, ctx) => {
  const active = value.windows.filter(w => w.label === "present").length;
  if (value.window_count !== value.windows.length || value.active_window_count !== active
      || Math.abs(value.active_window_fraction - active / value.window_count) > 1e-6)
    ctx.addIssue({ code: "custom", message: "Inconsistent activity summary" });
  value.windows.forEach((w, i) => {
    if (w.end_s <= w.start_s || w.end_s > value.analyzed_duration_s + 1e-6
        || (i > 0 && w.start_s <= value.windows[i - 1].start_s)
        || Math.abs(w.end_s - w.start_s - value.window_seconds) > .001
        || w.label !== (w.score >= value.threshold ? "present" : "absent"))
      ctx.addIssue({ code: "custom", message: "Invalid activity window" });
  });
});
export const abdomenAnalysisSchema = z.object({
  schema_version: z.literal("abdomen-analysis-v1"), mode: z.literal("abdomen"), quality,
  activity: activity.nullable(), bowel_events: z.null(), bowel_rate_per_minute: z.null(),
  bowel_rate_variability: z.null(), pattern_categories: z.null(), limitations: z.array(z.string()).optional(),
});
const fields = {
  schema_version: z.literal("organ-analysis-v1"), request_id: z.string().nullable(),
  source: z.enum(["wav", "pcm", "unknown"]), status: z.enum(["completed", "partial", "unavailable", "error"]), quality,
  backend_version: z.string().nullable(), model_version: z.string().nullable(),
  errors: z.array(z.object({ code: z.string(), message: z.string(), component: z.string(), retryable: z.boolean() })),
};
export const organAnalysisSchema = z.discriminatedUnion("mode", [
  z.object({ ...fields, mode: z.literal("heart"), analysis: heartAnalysisSchema.nullable() }),
  z.object({ ...fields, mode: z.literal("abdomen"), analysis: abdomenAnalysisSchema.nullable() }),
]).superRefine((value, ctx) => {
  if ((!value.quality.valid && value.analysis !== null)
      || ((value.status === "error" || value.status === "unavailable") && value.analysis !== null)
      || (value.status === "completed" && (!value.analysis || value.errors.length > 0))
      || (value.status === "partial" && (!value.analysis || value.errors.length === 0))
      || (value.status !== "completed" && value.errors.length === 0)
      || (value.analysis !== null && value.analysis.quality.valid !== value.quality.valid)
      || (value.mode === "abdomen" && value.analysis?.activity && value.analysis.activity.model_version !== value.model_version)
      || (value.mode === "heart" && value.analysis?.murmur?.status === "available" && value.analysis.murmur.model_version !== value.model_version)
      || (value.mode === "abdomen" && value.status === "completed" && !value.analysis?.activity))
    ctx.addIssue({ code: "custom", message: "Inconsistent analysis availability" });
});
export type OrganAnalysisResult = z.infer<typeof organAnalysisSchema>;
export type AbdomenAnalysisResult = z.infer<typeof abdomenAnalysisSchema>;
export function parseOrganAnalysisResult(input: unknown, mode?: AnalysisMode): OrganAnalysisResult {
  const parsed = organAnalysisSchema.safeParse(input);
  if (!parsed.success || (mode && parsed.data.mode !== mode)) throw new Error("Respons analisis organ tidak valid.");
  return parsed.data;
}
export function analysisNotice(result: OrganAnalysisResult): string | null {
  const code = result.errors[0]?.code;
  if (!code) return null;
  if (["MODEL_UNAVAILABLE", "MODEL_NOT_AUTHORIZED"].includes(code)) return result.mode === "heart"
    ? "Analisis Murmur belum tersedia; hasil DSP Heart tetap ditampilkan."
    : "Model aktivitas abdomen belum tersedia untuk digunakan.";
  if (["LOW_SIGNAL_QUALITY", "INVALID_AUDIO", "MURMUR_INSUFFICIENT_AUDIO", "ABDOMEN_INSUFFICIENT_AUDIO"].includes(code))
    return "Audio belum cukup untuk dianalisis. Gunakan WAV mono dengan sinyal jelas dan rekam ulang lebih lama.";
  if (code === "AUDIO_TOO_LARGE") return "Rekaman melewati batas ukuran atau durasi analisis.";
  return "Sebagian analisis belum tersedia. Coba ulang; jika tetap gagal, periksa layanan analisis.";
}
