import { create } from "zustand";

interface PlaybackState {
  element?: HTMLAudioElement;
  currentTime: number;
  duration: number;
  playing: boolean;
  attach: (element: HTMLAudioElement, duration: number) => void;
  detach: (element: HTMLAudioElement) => void;
  updateTime: (time: number) => void;
  setPlaying: (playing: boolean) => void;
  toggle: () => Promise<void>;
  seek: (time: number) => void;
}

export const usePlaybackStore = create<PlaybackState>((set, get) => ({
  currentTime: 0,
  duration: 0,
  playing: false,
  attach: (element, duration) => {
    element.currentTime = Math.min(get().currentTime, duration);
    set({ element, duration, playing: !element.paused });
  },
  detach: (element) => {
    if (get().element === element) set({ element: undefined, playing: false });
  },
  updateTime: (currentTime) => set({ currentTime }),
  setPlaying: (playing) => set({ playing }),
  toggle: async () => {
    const element = get().element;
    if (!element) return;
    if (element.paused) await element.play();
    else element.pause();
  },
  seek: (time) => {
    const clamped = Math.max(0, Math.min(time, get().duration));
    const element = get().element;
    if (element) element.currentTime = clamped;
    set({ currentTime: clamped });
  },
}));
