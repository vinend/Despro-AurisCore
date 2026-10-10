"use client";
import { useEffect, useRef } from "react";
export function RecordingPlayback({ file }: { file: File }) {
  const audio = useRef<HTMLAudioElement>(null);
  useEffect(() => {
    const url = URL.createObjectURL(file);
    const element = audio.current;
    if (element) element.src = url;
    return () => { element?.pause(); element?.removeAttribute("src"); URL.revokeObjectURL(url); };
  }, [file]);
  return <audio ref={audio} controls preload="metadata" aria-label="Putar ulang rekaman" />;
}
