param(
    [string]$TargetTriple = "x86_64-pc-windows-msvc",
    [string]$FfmpegPath = "",
    [string]$FfprobePath = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$binaryDirectory = Join-Path $repositoryRoot "src-tauri\binaries"
$backendDirectory = Join-Path $repositoryRoot "backend"
$backendEntry = Join-Path $backendDirectory "src\beatweave\main.py"

New-Item -ItemType Directory -Force -Path $binaryDirectory | Out-Null

if (-not $FfmpegPath) {
    $FfmpegPath = (Get-Command ffmpeg -ErrorAction Stop).Source
}
if (-not $FfprobePath) {
    $FfprobePath = (Get-Command ffprobe -ErrorAction Stop).Source
}

foreach ($tool in @($FfmpegPath, $FfprobePath)) {
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
        throw "Required media tool does not exist: $tool"
    }
}

$backendName = "beatweave-backend-$TargetTriple"
$workDirectory = Join-Path $backendDirectory "build"
$alembicConfig = Join-Path $backendDirectory "alembic.ini"
$migrations = Join-Path $backendDirectory "migrations"

& uv run --project $backendDirectory pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name $backendName `
    --distpath $binaryDirectory `
    --workpath $workDirectory `
    --specpath $backendDirectory `
    --paths (Join-Path $backendDirectory "src") `
    --add-data "${alembicConfig};." `
    --add-data "${migrations};migrations" `
    --collect-data beatweave `
    --collect-data gradio_client `
    --collect-all beat_this `
    $backendEntry
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

Copy-Item -LiteralPath $FfmpegPath -Destination (Join-Path $binaryDirectory "ffmpeg-$TargetTriple.exe") -Force
Copy-Item -LiteralPath $FfprobePath -Destination (Join-Path $binaryDirectory "ffprobe-$TargetTriple.exe") -Force

Write-Host "Prepared Windows sidecars in $binaryDirectory"
