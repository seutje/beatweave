import { useEffect, useRef } from "react";

import { api } from "../api/client";
import type { AudioState } from "../api/types";
import { formatTime } from "../lib/audioPlayback";
import { usePlaybackStore } from "../stores/playbackStore";

export function AudioTransport({
  audio,
  active = true,
}: {
  audio: AudioState;
  active?: boolean;
}) {
  const player = useRef<HTMLAudioElement>(null);
  const {
    currentTime,
    playing,
    attach,
    detach,
    updateTime,
    setPlaying,
    toggle,
    seek,
  } = usePlaybackStore();
  const duration = audio.waveform.duration_seconds;
  const contentUrl = `${api.media.audioContentUrl}?asset=${audio.asset.sha256}`;

  useEffect(() => {
    if (!active) return;
    const element = player.current;
    if (!element) return;
    attach(element, duration);
    return () => detach(element);
  }, [active, attach, audio.asset.id, detach, duration]);

  return (
    <div className="audio-player__controls">
      <audio
        key={audio.asset.id}
        ref={player}
        src={contentUrl}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onTimeUpdate={(event) => updateTime(event.currentTarget.currentTime)}
      />
      <button disabled={!active} onClick={() => void toggle()}>
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
  );
}
