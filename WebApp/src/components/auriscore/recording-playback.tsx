"use client";

import { useEffect, useRef, useState } from "react";
import { Download, FileAudio } from "lucide-react";
import type { OrganAnalysisResult } from "@/lib/auriscore/analysis-result";
import { recordingWaveform } from "@/lib/auriscore/recording-waveform";
import { RecordingInspector } from "./recording-inspector";

export function RecordingPlayback({ file, result }: { file: Blob; result?: OrganAnalysisResult | null }) {
  const audio = useRef<HTMLAudioElement>(null);
  const download = useRef<HTMLAnchorElement>(null);
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [decoded, setDecoded] = useState<{
    file: Blob; wave: ReturnType<typeof recordingWaveform> | null;
  }>();

  useEffect(() => {
    let current = true;
    const url = URL.createObjectURL(file);
    if (download.current) download.current.href = url;
    const element = audio.current;
    if (element) element.src = url;
    void file.arrayBuffer().then(buffer => {
      if (current) setDecoded({ file, wave: recordingWaveform(buffer) });
    }).catch(() => {
      if (current) setDecoded({ file, wave: null });
    });
    return () => {
      current = false;
      element?.pause();
      element?.removeAttribute("src");
      URL.revokeObjectURL(url);
    };
  }, [file]);

  const fileSizeKb = Math.round(file.size / 1024);

  return (
    <div className="my-3 min-w-0 p-3 bg-muted/40 rounded-xl border border-border/70 space-y-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2 truncate">
          <FileAudio className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span className="font-semibold text-emerald-950 truncate">{file instanceof File ? file.name : "Rekaman audio PCG"}</span>
          <span className="text-[11px] text-muted-foreground flex-shrink-0">({fileSizeKb} KB)</span>
        </div>

        <a
          ref={download}
          download="auriscore-recording.wav"
          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-[11.5px] font-semibold text-emerald-700 hover:text-emerald-800 bg-white hover:bg-emerald-50 rounded-lg border border-border/80 shadow-2xs transition-all flex-shrink-0"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Unduh WAV rekaman</span>
        </a>
      </div>

      <div className="w-full">
        <audio
          ref={audio}
          controls
          preload="metadata"
          aria-label="Putar ulang rekaman"
          className="w-full h-9 rounded-lg"
          onLoadedMetadata={event => { setPosition(event.currentTarget.currentTime); setPlaying(!event.currentTarget.paused); }}
          onTimeUpdate={event => setPosition(event.currentTarget.currentTime)}
          onSeeked={event => setPosition(event.currentTarget.currentTime)}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
        />
      </div>
      {decoded?.file === file && (decoded.wave
        ? <RecordingInspector wave={decoded.wave} result={result} playing={playing} position={position}
            onSeek={time => {
              if (!audio.current || !Number.isFinite(audio.current.duration)) return;
              audio.current.currentTime = Math.min(time, audio.current.duration);
              setPosition(audio.current.currentTime);
            }} />
        : <p className="text-xs text-muted-foreground">Grafik tersedia untuk rekaman WAV PCM16 mono.</p>)}
    </div>
  );
}
