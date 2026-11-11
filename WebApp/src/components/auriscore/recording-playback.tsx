"use client";

import { useEffect, useRef, useState } from "react";
import { Download, FileAudio, Play, Pause } from "lucide-react";

export function RecordingPlayback({ file }: { file: File }) {
  const audio = useRef<HTMLAudioElement>(null);
  const download = useRef<HTMLAnchorElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    const url = URL.createObjectURL(file);
    if (download.current) download.current.href = url;
    const element = audio.current;
    if (element) {
      element.src = url;
      const onPlay = () => setIsPlaying(true);
      const onPause = () => setIsPlaying(false);
      const onEnded = () => setIsPlaying(false);
      element.addEventListener("play", onPlay);
      element.addEventListener("pause", onPause);
      element.addEventListener("ended", onEnded);
      return () => {
        element.removeEventListener("play", onPlay);
        element.removeEventListener("pause", onPause);
        element.removeEventListener("ended", onEnded);
        element.pause();
        element.removeAttribute("src");
        URL.revokeObjectURL(url);
      };
    }
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [file]);

  const fileSizeKb = Math.round(file.size / 1024);

  return (
    <div className="my-3 p-3 bg-muted/40 rounded-xl border border-border/70 space-y-2.5">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 truncate">
          <FileAudio className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span className="font-semibold text-emerald-950 truncate">{file.name || "Rekaman audio PCG"}</span>
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
        />
      </div>
    </div>
  );
}
