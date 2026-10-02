export type ExportPreset = "1080p" | "4k";

export const EXPORT_PRESETS = {
  "1080p": { label: "1080p", width: 1920, height: 1080, crf: 18 },
  "4k": { label: "4K UHD", width: 3840, height: 2160, crf: 16 },
} as const satisfies Record<
  ExportPreset,
  { label: string; width: number; height: number; crf: number }
>;
