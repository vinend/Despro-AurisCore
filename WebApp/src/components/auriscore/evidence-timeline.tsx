import React from "react";

export interface TimedEvidence {
  start_s: number;
  end_s: number;
  label: string;
  score?: number;
}

/** Absolute recording times. Overlapping intervals stay separate and readable. */
export function EvidenceTimeline({ title, duration, intervals, explanation, emptyMessage, timeOffset = 0 }: {
  timeOffset?: number; title: string; duration: number; intervals: TimedEvidence[]; explanation: string; emptyMessage: string;
}) {
  if (!Number.isFinite(duration) || duration <= 0) return null;
  return <section className="mt-5 space-y-3" aria-label={title}>
    <h4 className="font-semibold">{title}</h4>
    <p className="text-sm text-muted-foreground">{explanation}</p>
    <div className="flex justify-between text-xs text-muted-foreground"><span>{timeOffset.toFixed(2)} detik</span><span>{(duration + timeOffset).toFixed(2)} detik</span></div>
    {intervals.length === 0 ? <p role="status">{emptyMessage}</p> :
      <div className="max-h-80 overflow-y-auto space-y-3 pr-2">
        {intervals.map((event, i) => <div key={`${event.start_s}-${event.label}-${i}`}>
          <div className="flex flex-wrap justify-between gap-x-3 text-sm">
            <span>{event.label}</span>
            <span>{(event.start_s + timeOffset).toFixed(2)}–{(event.end_s + timeOffset).toFixed(2)} detik{event.score !== undefined ? ` · skor ${event.score.toFixed(3)}` : ""}</span>
          </div>
          <div className="relative h-3 mt-1 rounded bg-muted" aria-hidden="true">
            <span className="absolute h-3 rounded bg-amber-600" style={{left: `${event.start_s / duration * 100}%`,
              width: `${(event.end_s - event.start_s) / duration * 100}%`, minWidth: "2px"}} />
          </div>
        </div>)}
      </div>}
  </section>;
}
