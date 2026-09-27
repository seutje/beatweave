import { useEffect, useRef } from "react";

import type { AudioState } from "../api/types";
import { formatTime } from "../lib/audioPlayback";
import { AudioTransport } from "./AudioTransport";

function Waveform({ audio }: { audio: AudioState }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const ratio = window.devicePixelRatio || 1;
    const width = element.clientWidth;
    const height = element.clientHeight;
    element.width = width * ratio;
    element.height = height * ratio;
    const context = element.getContext("2d");
    if (!context) return;
    context.scale(ratio, ratio);
    context.clearRect(0, 0, width, height);
    const gradient = context.createLinearGradient(0, 0, width, 0);
    gradient.addColorStop(0, "#6278ff");
    gradient.addColorStop(0.55, "#61d8f4");
    gradient.addColorStop(1, "#b263f4");
    context.fillStyle = gradient;
    const center = height / 2;
    const barWidth = width / audio.waveform.peaks.length;
    audio.waveform.peaks.forEach((peak, index) => {
      const barHeight = Math.max(1, peak * height * 0.9);
      context.fillRect(
        index * barWidth,
        center - barHeight / 2,
        Math.max(1, barWidth),
        barHeight,
      );
    });
  }, [audio]);

  return (
    <canvas className="waveform" ref={canvas} aria-label="Audio waveform" />
  );
}

export function AudioPlayer({ audio }: { audio: AudioState }) {
  const duration = audio.waveform.duration_seconds;

  return (
    <section className="audio-player">
      <div className="audio-player__heading">
        <div>
          <span className="eyebrow">Source track</span>
          <strong>{audio.asset.filename}</strong>
        </div>
        <span>
          {String(audio.asset.media_metadata.sample_rate)} Hz ·{" "}
          {formatTime(duration)}
        </span>
      </div>
      <Waveform audio={audio} />
      <AudioTransport audio={audio} />
    </section>
  );
}
