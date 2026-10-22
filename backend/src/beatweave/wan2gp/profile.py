import json
import math
import zipfile
from pathlib import Path
from typing import Any

from beatweave.errors import BeatweaveError
from beatweave.wan2gp.schemas import (
    LTX23DistilledProfile,
    MiniMaxH3PrunedProfile,
    VideoModelProfile,
    VideoQualityMode,
    VideoRenderRequest,
    Wan2GPConfig,
)


def resolve_profile(request: VideoRenderRequest, config: Wan2GPConfig) -> VideoModelProfile:
    try:
        return config.profile_for(request.model_profile)
    except ValueError as error:
        raise BeatweaveError(
            "wan2gp_profile_unknown",
            "The requested Wan2GP model profile is not configured.",
            status_code=422,
        ) from error


def frame_count(request: VideoRenderRequest, config: Wan2GPConfig) -> int:
    profile = resolve_profile(request, config)
    # Keep one unused frame after the timeline cut for the following scene.
    target = math.ceil(request.duration_seconds * request.frame_rate) + 1
    steps = math.ceil((target - profile.minimum_frames) / profile.frame_step)
    return max(profile.minimum_frames, profile.minimum_frames + steps * profile.frame_step)


def build_queue_params(request: VideoRenderRequest, config: Wan2GPConfig) -> dict[str, Any]:
    profile = resolve_profile(request, config)
    is_ltx = isinstance(profile, LTX23DistilledProfile)
    if not is_ltx and request.frame_rate != profile.default_frame_rate:
        raise BeatweaveError(
            "wan2gp_frame_rate_invalid",
            "MiniMax H3 profiles require 24 fps.",
            status_code=422,
        )
    quality = profile.preview if request.quality_mode == VideoQualityMode.PREVIEW else profile.final
    lora = request.audio_reactive_lora
    trigger = lora.trigger if is_ltx and lora.enabled else ""
    if trigger is None:
        trigger = config.audio_reactive_profile.trigger_phrase
    prompt = f"{trigger.strip()} {request.prompt}".strip() if trigger else request.prompt
    params: dict[str, Any] = {
        "client_id": request.scene_id,
        "model_type": profile.model_type,
        "base_model_type": (
            "ltx2_22B"
            if is_ltx
            else "minimax_h3_fl2va_pruned"
            if isinstance(profile, MiniMaxH3PrunedProfile)
            else profile.model_type
        ),
        "settings_version": profile.settings_version,
        "image_mode": 0,
        "prompt": prompt,
        "negative_prompt": "",
        "resolution": quality.resolution,
        "video_length": frame_count(request, config),
        "force_fps": str(request.frame_rate),
        "num_inference_steps": quality.inference_steps,
        "seed": request.motion.seed,
        "image_prompt_type": "SE" if request.end_keyframe_asset_id else "S",
        "image_start": "task1_image_start_0.png",
        "image_end": "task1_image_end_0.png" if request.end_keyframe_asset_id else None,
        "audio_prompt_type": "A",
        "audio_guide": "task1_audio_guide_0.wav",
        "repeat_generation": 1,
        "multi_prompts_gen_type": "FG",
        "prompt_enhancer": "",
        "output_filename": f"beatweave-{request.scene_id}",
        "activated_loras": [],
        "loras_multipliers": "",
    }
    if is_ltx:
        params["motion_amplitude"] = request.motion.amplitude
    else:
        # H3's native soundtrack conditioning needs no LTX LoRA or accelerator.
        params.update(
            sample_solver=profile.sample_solver,
            flow_shift=profile.flow_shift,
            guidance_scale=1.0,
            guidance_phases=1,
            denoising_strength=1.0,
            input_video_strength=1.0,
            video_prompt_type="",
            sliding_window_size=362,
            sliding_window_overlap=18,
            sliding_window_discard_last_frames=0,
        )
    if is_ltx and lora.enabled:
        params["activated_loras"] = [config.audio_reactive_profile.filename]
        multiplier = lora.multiplier
        if multiplier is None:
            multiplier = config.audio_reactive_profile.default_multiplier
        params["loras_multipliers"] = str(multiplier)
    return params


def write_queue_archive(
    request: VideoRenderRequest,
    config: Wan2GPConfig,
    start_image: Path,
    end_image: Path | None,
    audio_guide: Path,
    destination: Path,
    *,
    output_filename: str | None = None,
) -> dict[str, Any]:
    params = build_queue_params(request, config)
    if output_filename is not None:
        params["output_filename"] = output_filename
    manifest = [{"id": 1, "params": params}]
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".zip.partial")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("queue.json", json.dumps(manifest, indent=4))
            archive.write(start_image, "task1_image_start_0.png")
            if end_image is not None:
                archive.write(end_image, "task1_image_end_0.png")
            archive.write(audio_guide, "task1_audio_guide_0.wav")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return params
