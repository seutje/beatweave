# Beatweave Windows and Backend Setup

## Installed runtime

The Windows NSIS package installs for the current user and does not request administrator rights.
It contains:

- the Tauri desktop application;
- a PyInstaller-frozen CPython backend with the locked production dependencies, including Beat This;
- `ffmpeg.exe` and `ffprobe.exe` sidecars.

Application data is stored in the Windows per-user application-data directory. Projects remain in
the folders chosen by the user. ComfyUI, Wan2GP, and the planning LLM are external services and are
not started or stopped by Beatweave.

## Reproducible source setup

From a fresh checkout:

```powershell
npm ci --prefix frontend
uv sync --project backend --all-groups --locked
```

Development builds use `uv` to launch the backend and do not require prepared release sidecars:

```powershell
npm run dev
```

Prepare and verify the Windows sidecars:

```powershell
npm run prepare:windows
npm run test:package
```

Build the native development executable and the release installer:

```powershell
npm run build:desktop:dev
npm run build:desktop
```

The release command creates
`src-tauri/target/release/bundle/nsis/Beatweave_0.3.4_x64-setup.exe`. After building, run the
non-elevated install/start/uninstall smoke test with:

```powershell
npm run test:installer
```

## FFmpeg strategy

Release builds bundle FFmpeg and ffprobe, so installed users do not need to edit `PATH`.
`scripts/prepare-windows.ps1` copies the executables found on the build machine's `PATH`. When PATH
resolves to Chocolatey shims, preparation locates and copies the real package executables because
the redirecting shims are not relocatable Tauri sidecars. Exact paths can be supplied when needed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/prepare-windows.ps1 `
  -FfmpegPath C:\tools\ffmpeg\bin\ffmpeg.exe `
  -FfprobePath C:\tools\ffmpeg\bin\ffprobe.exe
```

The release builder is responsible for using an FFmpeg distribution whose license is suitable for
the intended distribution. Beatweave passes absolute sidecar paths to the packaged backend and does
not depend on the installed user's `PATH`.

## ComfyUI image backend

1. Install and start a user-managed ComfyUI instance.
2. Install nodes providing `TextEncodeQwenImage21` and `QwenImage21Cache`; the standard loader,
   sampler, image, VAE, and save nodes are also required.
3. Make the configured model files available to ComfyUI. The defaults are:
   - `qwen_image_2.1_int8_convrot.safetensors`
   - `qwen3vl_8b_int8_convrot.safetensors`
   - `qwen_image_2.1_vae_bf16.safetensors`
4. In Beatweave, open Settings > Image, enter the ComfyUI URL (default
   `http://127.0.0.1:8188`), save, and use **Test connection**.

Beatweave submits its packaged workflow through the ComfyUI HTTP API. It does not manage the
ComfyUI process or embed ComfyUI node identifiers in project data.

## Wan2GP video backend

1. Install and verify a user-managed
   [WanGP/Wan2GP](https://github.com/deepbeepmeep/Wan2GP) checkout.
2. Configure its LTX 2.3 Distilled 1.1 model (`ltx2_22B_distilled_1_1`).
3. For audio-reactive rendering, install
   `ltx2.3_audio_reactive_lora_v2.safetensors` in the location expected by Wan2GP.
4. Start Wan2GP's Gradio service yourself (normally `http://localhost:7860`).
5. In Beatweave, open Settings > Video, enter the URL, save, and use **Test connection**.

Beatweave generates and submits queue archives but never owns the Wan2GP process lifecycle.

## Local planning LLM

Beatweave uses an OpenAI-compatible HTTP endpoint. Ollama is the default local option:

```powershell
ollama pull qwen3:8b
ollama serve
```

In Settings > Planning, use:

- Base URL: `http://localhost:11434/v1`
- Model: `qwen3:8b`
- API key: blank for a default local Ollama installation

Save and test the connection. LM Studio, llama.cpp server, or another OpenAI-compatible local
server can be used by entering its base URL and model name. Planning is optional; an offline LLM
does not prevent opening a project or manually editing prompts.

## Offline behavior

Beatweave startup does not probe or require ComfyUI, Wan2GP, or the LLM. Their connection checks
are isolated to the Settings connectivity screen and render/planning actions. The Windows package
smoke tests cover startup with all three services offline, paths containing spaces, bundled media
tools, and non-elevated per-user installation.
