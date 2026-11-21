"use client";

import { useEffect, useId, useMemo, useRef } from "react";
import { ChevronDown } from "lucide-react";
import type { OrganAnalysisResult } from "@/lib/auriscore/analysis-result";
import { recordingLabels, recordingMarks, type recordingWaveform } from "@/lib/auriscore/recording-waveform";

type Waveform = ReturnType<typeof recordingWaveform>;
const colors = ["#5eead4", "#fde68a", "#fda4af", "#c4b5fd", "#93c5fd", "#bef264", "#fdba74"];
const seconds = (value: number) => `${value.toFixed(2)} dtk`;
const markerTime = (start: number, end: number) =>
  end > start ? `${start.toFixed(2)}–${seconds(end)}` : seconds(start);

export function RecordingInspector({ wave, result, position, playing, onSeek }: {
  wave: Waveform;
  result?: OrganAnalysisResult | null;
  position: number;
  playing: boolean;
  onSeek: (position: number) => void;
}) {
  const heading = useId();
  const viewport = useRef<HTMLDivElement>(null);
  const playhead = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const { duration, spectrum } = wave;
  const time = Math.min(position, duration);
  const percent = (value: number) => `${100 * value / duration}%`;
  const marks = useMemo(() => recordingMarks(result, duration), [result, duration]);
  const lanes = useMemo(() => {
    const groups = new Map<(typeof marks)[number]["label"], typeof marks>();
    for (const mark of marks) {
      const lane = groups.get(mark.label);
      if (lane) lane.push(mark);
      else groups.set(mark.label, [mark]);
    }
    return [...groups];
  }, [marks]);
  const active = marks.filter(mark => mark.start_s === mark.end_s
    ? Math.abs(time - mark.start_s) <= 0.04
    : time >= mark.start_s && time < mark.end_s);
  const activeLabels = [...new Set(active.map(mark => mark.score === undefined
    ? recordingLabels[mark.label]
    : `${recordingLabels[mark.label]} (skor ${mark.score.toFixed(3)})`))];

  useEffect(() => {
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    const image = context.createImageData(spectrum.width, spectrum.height);
    image.data.set(spectrum.pixels);
    context.putImageData(image, 0, 0);
  }, [spectrum]);

  function reveal(value: number) {
    const container = viewport.current;
    if (!container) return;
    const x = value / duration * container.scrollWidth;
    if (x < container.scrollLeft || x > container.scrollLeft + container.clientWidth - 2) {
      container.scrollLeft = x - container.clientWidth / 3;
    }
  }
  function seek(value: number) {
    reveal(value);
    onSeek(value);
  }

  useEffect(() => {
    if (!playing) return;
    const container = viewport.current;
    const line = playhead.current;
    if (!container || !line) return;
    const x = line.offsetLeft;
    if (x < container.scrollLeft || x > container.scrollLeft + container.clientWidth - 2)
      container.scrollLeft = x - container.clientWidth / 3;
  }, [playing, time]);

  return <section aria-labelledby={heading} className="space-y-3">
    <h3 id={heading} className="text-sm font-semibold text-emerald-950">Waveform dan spektrogram rekaman</h3>
    <div ref={viewport} className="overflow-x-auto rounded-lg border border-emerald-950/30 bg-[#102520] text-white"
      tabIndex={0} aria-label="Grafik rekaman, geser mendatar untuk melihat bagian lain">
      <div className="relative" style={{ minWidth: Math.max(280, Math.round(duration * 68)) }}>
        <button type="button" tabIndex={-1} aria-label="Klik grafik untuk pindah posisi audio"
          className="relative block w-full cursor-crosshair text-left"
          onClick={event => {
            const box = event.currentTarget.getBoundingClientRect();
            if (box.width > 0) seek(Math.max(0, Math.min(duration, (event.clientX - box.left) / box.width * duration)));
          }}>
          <svg viewBox={`0 0 ${wave.columns} 100`} preserveAspectRatio="none"
            className="block h-24 w-full" aria-hidden="true">
            <path d={`M0 50H${wave.columns}`} stroke="#527365" vectorEffect="non-scaling-stroke" />
            <path d={wave.path} stroke="#9de8b9" fill="none" vectorEffect="non-scaling-stroke" />
          </svg>
          <span className="relative block border-t border-white/15">
            <canvas ref={canvas} width={spectrum.width} height={spectrum.height} className="block h-28 w-full"
              aria-label={`Spektrogram 0 hingga ${wave.nyquist} Hz`} role="img" />
            <span className="absolute top-0.5 left-1 rounded bg-black/60 px-1 text-[10px]">{wave.nyquist / 1000} kHz</span>
            <span className="absolute bottom-0.5 left-1 rounded bg-black/60 px-1 text-[10px]">0 Hz</span>
          </span>
          {lanes.map(([label, entries], lane) => entries.map((mark, index) =>
            <span key={`${label}-${index}`} aria-hidden="true" className="pointer-events-none absolute inset-y-0 min-w-px opacity-15"
              style={{ left: percent(mark.start_s), width: percent(mark.end_s - mark.start_s), backgroundColor: colors[lane % colors.length] }} />))}
        </button>
        {lanes.map(([label, entries], lane) => <div key={label} className="relative h-8 border-t border-white/15">
          <span className="pointer-events-none sticky left-1 z-10 rounded bg-[#102520] px-1 text-[10px] font-medium"
            style={{ color: colors[lane % colors.length] }}>{recordingLabels[label]}</span>
          {entries.map((mark, index) => {
            const name = `${recordingLabels[label]} · ${markerTime(mark.start_s, mark.end_s)}`;
            return <button key={index} type="button" onClick={() => seek(mark.start_s)} title={name} aria-label={name}
              className="absolute bottom-0 h-5 min-w-[4px] rounded-sm border border-[#102520] focus-visible:z-20 focus-visible:outline-2 focus-visible:outline-white"
              style={{ left: percent(mark.start_s), width: percent(mark.end_s - mark.start_s),
                backgroundColor: colors[lane % colors.length], opacity: active.includes(mark) ? 1 : 0.72 }} />;
          })}
        </div>)}
        <div ref={playhead} aria-hidden="true" className="pointer-events-none absolute inset-y-0 z-10 border-l-2 border-white"
          style={{ left: percent(time) }} />
      </div>
    </div>
    <label className="block text-xs font-medium text-emerald-950">
      Posisi audio · {seconds(time)} / {seconds(duration)}
      <input type="range" min={0} max={duration} step="any" value={time}
        aria-valuetext={seconds(time)} onChange={event => seek(event.currentTarget.valueAsNumber)}
        className="block w-full accent-emerald-700" />
    </label>
    <p className="min-h-4 text-xs text-muted-foreground">
      {activeLabels.length ? activeLabels.join(", ")
        : marks.length ? "Tidak ada penanda pada posisi ini." : result ? "Belum ada penanda untuk rekaman ini." : "Penanda muncul setelah hasil analisis tersedia."}
    </p>
    {marks.length > 0 && <details className="group rounded-lg border border-border bg-background">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 text-sm font-semibold [&::-webkit-details-marker]:hidden">
        <span>Waktu deteksi <span className="font-normal text-muted-foreground">({marks.length})</span></span>
        <ChevronDown aria-hidden="true" className="size-4 group-open:rotate-180" />
      </summary>
      <ul className="max-h-64 divide-y divide-border overflow-y-auto border-t border-border">
        {marks.map((mark, index) => <li key={index}>
          <button type="button" onClick={() => seek(mark.start_s)}
            className="flex w-full flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-3 py-2 text-left text-sm hover:bg-muted focus-visible:outline-2 focus-visible:-outline-offset-2">
            <span>{recordingLabels[mark.label]}</span>
            <span className="text-xs tabular-nums text-muted-foreground">{markerTime(mark.start_s, mark.end_s)}</span>
          </button>
        </li>)}
      </ul>
    </details>}
    {lanes.some(([label]) => label === "murmur") &&
      <p className="text-xs text-muted-foreground">Penanda Murmur menunjukkan jendela yang melewati ambang referensi rekaman. Batas awal dan akhir belum divalidasi.</p>}
  </section>;
}
