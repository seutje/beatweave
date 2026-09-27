import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import type { AudioState } from "../api/types";
import { formatTime, seekAudio } from "../lib/audioPlayback";

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
  const player = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const duration = audio.waveform.duration_seconds;
  const contentUrl = `${api.media.audioContentUrl}?asset=${audio.asset.sha256}`;

  const toggle = async () => {
    if (!player.current) return;
    if (player.current.paused) await player.current.play();
    else player.current.pause();
  };

  const seek = (seconds: number) => {
    if (!player.current) return;
    seekAudio(player.current, seconds);
    setCurrentTime(seconds);
  };

  return (
    <section className="audio-player">
      <audio
        key={audio.asset.id}
        ref={player}
        src={contentUrl}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(event) =>
          setCurrentTime(event.currentTarget.currentTime)
        }
      />
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
      <div className="audio-player__controls">
        <button onClick={() => void toggle()}>
          {playing ? "Pause" : "Play"}
        </button>
        <span>{formatTime(currentTime)}</span>
        <input
          aria-label="Playback position"
          type="range"
          min="0"
          max={duration}
          step="0.01"
          value={Math.min(currentTime, duration)}
          onChange={(event) => seek(Number(event.target.value))}
        />
        <span>{formatTime(duration)}</span>
      </div>
    </section>
  );
}
