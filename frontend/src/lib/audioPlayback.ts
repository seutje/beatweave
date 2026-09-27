export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0")}`;
}

export function seekAudio(
  audio: Pick<HTMLAudioElement, "currentTime">,
  seconds: number,
): void {
  audio.currentTime = seconds;
}
