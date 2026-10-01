import json
import zipfile
from pathlib import Path
from typing import Any

from beatweave.errors import BeatweaveError
from beatweave.wan2gp.schemas import VideoQualityMode, VideoRenderRequest, Wan2GPConfig


def frame_count(request: VideoRenderRequest, config: Wan2GPConfig) -> int:
    profile = config.profile
    target = round(request.duration_seconds * request.frame_rate)
    steps = round((target - profile.minimum_frames) / profile.frame_step)
    return max(profile.minimum_frames, profile.minimum_frames + steps * profile.frame_step)


def build_queue_params(request: VideoRenderRequest, config: Wan2GPConfig) -> dict[str, Any]:
    profile = config.profile
    if request.model_profile != profile.name:
        raise BeatweaveError(
            "wan2gp_profile_unknown",
            "The requested Wan2GP model profile is not configured.",
            status_code=422,
        )
    resolution = (
        profile.preview_resolution
        if request.quality_mode == VideoQualityMode.PREVIEW
        else profile.final_resolution
    )
    lora = request.audio_reactive_lora
    trigger = lora.trigger
    if trigger is None:
        trigger = config.audio_reactive_profile.trigger_phrase
    prompt = f"{trigger.strip()} {request.prompt}".strip() if trigger else request.prompt
    params: dict[str, Any] = {
        "client_id": request.scene_id,
        "model_type": profile.model_type,
        "base_model_type": "ltx2_22B",
        "settings_version": profile.settings_version,
        "image_mode": 0,
        "prompt": prompt,
        "negative_prompt": "",
        "resolution": resolution,
        "video_length": frame_count(request, config),
        "force_fps": str(request.frame_rate),
        "num_inference_steps": profile.inference_steps,
        "seed": request.motion.seed,
        "motion_amplitude": request.motion.amplitude,
        "image_prompt_type": "SE",
        "image_start": "task1_image_start_0.png",
        "image_end": "task1_image_end_0.png",
        "repeat_generation": 1,
        "multi_prompts_gen_type": "FG",
        "prompt_enhancer": "",
        "output_filename": f"beatweave-{request.scene_id}",
        "activated_loras": [],
        "loras_multipliers": "",
    }
    if lora.enabled:
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
    end_image: Path,
    destination: Path,
) -> dict[str, Any]:
    params = build_queue_params(request, config)
    manifest = [{"id": 1, "params": params}]
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".zip.partial")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("queue.json", json.dumps(manifest, indent=4))
            archive.write(start_image, "task1_image_start_0.png")
            archive.write(end_image, "task1_image_end_0.png")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return params
