/**
 * Helper tampilan: label bahasa Indonesia dan format waktu zona Asia/Jakarta.
 */

import type { OrganMode, QualityFlag } from "./protocol";

export const ORGAN_MODE_LABELS: Record<OrganMode, string> = {
  mitral: "Mitral",
  aortic: "Aortik",
  pulmonic: "Pulmonik",
  tricuspid: "Trikuspidal",
};

export const QUALITY_LABELS: Record<QualityFlag, string> = {
  good: "Baik",
  fair: "Cukup",
  poor: "Buruk",
};

/** Contoh: "7,3 dtk" / "10,0 dtk". */
export function formatDurationMs(ms: number): string {
  return `${(ms / 1000).toFixed(1).replace(".", ",")} dtk`;
}

/** Timer rekaman, contoh: "0:07,3". */
export function formatElapsedMs(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const tenths = Math.floor((ms % 1000) / 100);
  return `${minutes}:${String(seconds).padStart(2, "0")},${tenths}`;
}

const timestampFormatter = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Jakarta",
});

/** Contoh: "8 Sep 2026, 14.05" (zona waktu Jakarta). */
export function formatTimestamp(ts: number): string {
  return timestampFormatter.format(new Date(ts));
}
