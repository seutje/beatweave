import json
from copy import deepcopy
from importlib.resources import files
from typing import Any

from beatweave.comfyui.schemas import ImageRenderRequest, QwenWorkflowProfile
from beatweave.errors import BeatweaveError

NODE_IDS = {
    "model": "1",
    "clip": "2",
    "vae": "3",
    "conditioning": "4",
    "latent": "5",
    "cache": "6",
    "sampler": "7",
    "decode": "8",
    "save": "9",
}

REQUIRED_NODE_CLASSES = {
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "TextEncodeQwenImage21",
    "EmptyLatentImage",
    "QwenImage21Cache",
    "KSampler",
    "VAEDecode",
    "SaveImage",
}


def load_workflow_template() -> dict[str, Any]:
    resource = files("beatweave.comfyui").joinpath("workflows/qwen_image_2_1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def build_workflow(
    request: ImageRenderRequest, profile: QwenWorkflowProfile, job_id: str
) -> dict[str, Any]:
    workflow = deepcopy(load_workflow_template())
    workflow[NODE_IDS["model"]]["inputs"].update(
        {"unet_name": profile.diffusion_model, "weight_dtype": profile.weight_dtype}
    )
    workflow[NODE_IDS["clip"]]["inputs"].update(
        {"clip_name": profile.text_encoder, "type": "qwen_image", "device": "default"}
    )
    workflow[NODE_IDS["vae"]]["inputs"]["vae_name"] = profile.vae
    workflow[NODE_IDS["conditioning"]]["inputs"].update(
        {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "resolution": max(request.width, request.height),
        }
    )
    workflow[NODE_IDS["latent"]]["inputs"].update(
        {"width": request.width, "height": request.height, "batch_size": 1}
    )
    workflow[NODE_IDS["cache"]]["inputs"].update(
        {"device": profile.cache_device, "dtype": profile.cache_dtype}
    )
    workflow[NODE_IDS["sampler"]]["inputs"].update(
        {
            "seed": request.seed,
            "steps": request.steps or profile.default_steps,
            "cfg": request.cfg if request.cfg is not None else profile.default_cfg,
            "sampler_name": profile.sampler,
            "scheduler": profile.scheduler,
            "denoise": 1,
        }
    )
    workflow[NODE_IDS["save"]]["inputs"]["filename_prefix"] = (
        f"beatweave/{request.output_name}-{job_id[:8]}"
    )
    return workflow


def validate_installation(object_info: dict[str, Any], profile: QwenWorkflowProfile) -> None:
    missing_nodes = sorted(REQUIRED_NODE_CLASSES - object_info.keys())
    if missing_nodes:
        raise BeatweaveError(
            "comfyui_nodes_missing",
            "ComfyUI is missing nodes required by the Qwen Image 2.1 profile.",
            status_code=409,
            details={"nodes": missing_nodes},
        )
    required_models = {
        "UNETLoader": ("unet_name", profile.diffusion_model),
        "CLIPLoader": ("clip_name", profile.text_encoder),
        "VAELoader": ("vae_name", profile.vae),
    }
    missing_models = []
    for node_name, (input_name, model_name) in required_models.items():
        choices = object_info[node_name]["input"]["required"][input_name][0]
        if model_name not in choices:
            missing_models.append(model_name)
    if missing_models:
        raise BeatweaveError(
            "comfyui_models_missing",
            "ComfyUI is missing models required by the configured Qwen profile.",
            status_code=409,
            details={"models": missing_models},
        )


def validate_workflow_inputs(workflow: dict[str, Any], object_info: dict[str, Any]) -> None:
    missing: list[str] = []
    for node_id, node in workflow.items():
        class_type = node.get("class_type")
        inputs = node.get("inputs", {})
        required = object_info.get(class_type, {}).get("input", {}).get("required", {})
        for input_name in required:
            if input_name not in inputs:
                missing.append(f"{node_id}:{class_type}.{input_name}")
    if missing:
        raise BeatweaveError(
            "comfyui_workflow_inputs_missing",
            "The configured workflow is missing required ComfyUI inputs.",
            status_code=422,
            details={"inputs": missing},
        )
