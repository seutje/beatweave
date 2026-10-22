import json
import subprocess
from pathlib import Path
from typing import Any

from beatweave.errors import BeatweaveError
from beatweave.media.schemas import MediaMetadata


class MediaProcessError(BeatweaveError):
    def __init__(self, tool: str, stderr: str, return_code: int) -> None:
        super().__init__(
            "media_process_failed",
            f"{tool} could not process the media file.",
            status_code=422,
            details={"tool": tool, "return_code": return_code, "stderr": stderr[-4000:]},
        )


class MediaProcessRunner:
    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe") -> None:
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

    def run_ffmpeg(self, arguments: list[str]) -> bytes:
        return self._execute(self.ffmpeg_path, ["-hide_banner", "-nostdin", *arguments])

    def run_ffprobe(self, arguments: list[str]) -> bytes:
        return self._execute(self.ffprobe_path, ["-hide_banner", *arguments])

    def probe_audio(self, path: Path) -> MediaMetadata:
        output = self.run_ffprobe(
            [
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                "-select_streams",
                "a:0",
                str(path),
            ]
        )
        data: dict[str, Any] = json.loads(output)
        streams = data.get("streams", [])
        if not streams:
            raise BeatweaveError(
                "audio_stream_missing",
                "The selected file does not contain a readable audio stream.",
                status_code=422,
            )
        stream = streams[0]
        media_format = data.get("format", {})
        duration = stream.get("duration") or media_format.get("duration")
        if duration is None:
            raise BeatweaveError(
                "audio_duration_missing",
                "The duration of the selected audio file could not be determined.",
                status_code=422,
            )
        bit_rate = stream.get("bit_rate") or media_format.get("bit_rate")
        return MediaMetadata(
            duration_seconds=float(duration),
            sample_rate=int(stream["sample_rate"]),
            channels=int(stream["channels"]),
            codec=str(stream.get("codec_name", "unknown")),
            format_name=str(media_format.get("format_name", "unknown")),
            bit_rate=int(bit_rate) if bit_rate else None,
        )

    def probe_video(self, path: Path) -> dict[str, Any]:
        output = self.run_ffprobe(
            [
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                "-select_streams",
                "v:0",
                str(path),
            ]
        )
        data: dict[str, Any] = json.loads(output)
        streams = data.get("streams", [])
        if not streams:
            raise BeatweaveError(
                "video_stream_missing",
                "The selected file does not contain a readable video stream.",
                status_code=422,
            )
        stream = streams[0]
        media_format = data.get("format", {})
        duration = stream.get("duration") or media_format.get("duration")
        if duration is None:
            raise BeatweaveError(
                "video_duration_missing",
                "The duration of the selected video could not be determined.",
                status_code=422,
            )
        return {
            "duration_seconds": float(duration),
            "width": int(stream["width"]),
            "height": int(stream["height"]),
            "codec": str(stream.get("codec_name", "unknown")),
            "format_name": str(media_format.get("format_name", "unknown")),
        }

    def decode_mono_f32(self, path: Path, sample_rate: int) -> bytes:
        return self.run_ffmpeg(
            [
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-f",
                "f32le",
                "pipe:1",
            ]
        )

    def extract_audio_segment(
        self,
        source: Path,
        destination: Path,
        *,
        start_seconds: float,
        duration_seconds: float,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.run_ffmpeg(
            [
                "-y",
                "-v",
                "error",
                "-ss",
                f"{start_seconds:.6f}",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-af",
                f"apad=pad_dur={duration_seconds:.6f}",
                "-t",
                f"{duration_seconds:.6f}",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ]
        )

    def normalize_video_clip(
        self,
        source: Path,
        destination: Path,
        *,
        duration_seconds: float,
        width: int,
        height: int,
        frame_rate: int,
        codec: str,
        crf: int,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        video_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"fps={frame_rate},format=yuv420p"
        )
        self.run_ffmpeg(
            [
                "-y",
                "-v",
                "error",
                "-i",
                str(source),
                "-t",
                f"{duration_seconds:.6f}",
                "-an",
                "-vf",
                video_filter,
                "-c:v",
                codec,
                "-preset",
                "medium",
                "-crf",
                str(crf),
                "-movflags",
                "+faststart",
                str(destination),
            ]
        )

    def concatenate_video_clips(self, sources: list[Path], destination: Path) -> None:
        if not sources:
            raise BeatweaveError("export_clips_missing", "No video clips were provided.")
        manifest = destination.with_suffix(".concat.txt")
        lines = []
        for source in sources:
            escaped = source.resolve().as_posix().replace("'", "'\\''")
            lines.append(f"file '{escaped}'")
        manifest.write_text("\n".join(lines), encoding="utf-8")
        self.run_ffmpeg(
            [
                "-y",
                "-v",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(manifest),
                "-an",
                "-c:v",
                "copy",
                str(destination),
            ]
        )

    def mux_audio(
        self,
        video: Path,
        audio: Path,
        destination: Path,
        *,
        duration_seconds: float,
    ) -> None:
        self.run_ffmpeg(
            [
                "-y",
                "-v",
                "error",
                "-i",
                str(video),
                "-i",
                str(audio),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "320k",
                "-t",
                f"{duration_seconds:.6f}",
                "-movflags",
                "+faststart",
                str(destination),
            ]
        )

    def _execute(self, executable: str, arguments: list[str]) -> bytes:
        try:
            result = subprocess.run(
                [executable, *arguments],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                shell=False,
            )
        except FileNotFoundError as error:
            raise BeatweaveError(
                "media_tool_missing",
                f"{executable} is not installed or is not available on PATH.",
                status_code=503,
                details={"tool": executable},
            ) from error
        if result.returncode != 0:
            raise MediaProcessError(
                executable,
                result.stderr.decode("utf-8", errors="replace"),
                result.returncode,
            )
        return result.stdout
