import { z } from "zod";
const number = z.number().finite();
const label = z.enum(["inhalation", "exhalation", "wheeze", "rhonchi", "stridor", "crackle", "cas"]);
const interval = z.object({ label, start_s: number.nonnegative(), end_s: number.positive() });
export const lungAnalysisSchema = z.object({
  schema_version: z.literal("lung-analysis-v1"), mode: z.literal("lung"),
  quality: z.object({ valid: z.literal(true), reason: z.null() }), model_version: z.string().min(1),
  supported_classes: z.array(label).min(1).max(7), analyzed_duration_s: number.positive().max(120),
  sound_events: z.array(interval).max(10000), phase_intervals: z.array(interval).max(10000),
  class_scores: z.array(z.object({ label, maximum_frame_score: number.min(0).max(1), threshold: number.min(0).max(1) })).min(1).max(7),
  respiratory: z.object({ respiratory_rate_per_minute: number.positive().nullable(),
    inhalation_duration_s: number.positive().nullable(), exhalation_duration_s: number.positive().nullable(),
    ie_ratio: number.positive().nullable(), complete_cycle_count: z.number().int().nonnegative(), reason: z.string().nullable() }),
  limitations: z.array(z.string()),
}).superRefine((value, ctx) => {
  const phases = new Set(["inhalation", "exhalation"]);
  if (new Set(value.supported_classes).size !== value.supported_classes.length
      || value.class_scores.length !== value.supported_classes.length
      || value.class_scores.some((s, i) => s.label !== value.supported_classes[i]))
    ctx.addIssue({ code: "custom", message: "Inconsistent Lung class support" });
  for (const [events, phase] of [[value.sound_events, false], [value.phase_intervals, true]] as const) {
    events.forEach((e, i) => {
      if (e.end_s <= e.start_s || e.end_s > value.analyzed_duration_s || !value.supported_classes.includes(e.label)
          || phases.has(e.label) !== phase || (i > 0 && e.start_s < events[i - 1].start_s))
        ctx.addIssue({ code: "custom", message: "Invalid Lung event interval" });
    });
  }
  const r = value.respiratory;
  const values = [r.respiratory_rate_per_minute, r.inhalation_duration_s, r.exhalation_duration_s, r.ie_ratio];
  if ((r.reason !== null && values.some(v => v !== null)) || (r.reason === null && (values.some(v => v === null) || r.complete_cycle_count < 3))
      || (r.ie_ratio !== null && r.inhalation_duration_s !== null && r.exhalation_duration_s !== null
        && Math.abs(r.ie_ratio - r.inhalation_duration_s / r.exhalation_duration_s) > 1e-6))
    ctx.addIssue({ code: "custom", message: "Unsupported respiratory measurements" });
});
export type LungAnalysisResult = z.infer<typeof lungAnalysisSchema>;
