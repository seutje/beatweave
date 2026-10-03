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

function Resolve-MediaToolPath {
    param(
        [Parameter(Mandatory = $true)][string]$ToolName,
        [string]$ConfiguredPath = ""
    )

    if ($ConfiguredPath) {
        return [System.IO.Path]::GetFullPath($ConfiguredPath)
    }

    $commandPath = (
        Get-Command $ToolName -CommandType Application -ErrorAction Stop |
            Select-Object -First 1
    ).Source
    $commandDirectory = Split-Path -Parent $commandPath
    $chocolateyRoot = if ($env:ChocolateyInstall) {
        [System.IO.Path]::GetFullPath($env:ChocolateyInstall)
    } elseif (
        (Split-Path -Leaf $commandDirectory) -ieq "bin" -and
        (Test-Path -LiteralPath (Join-Path $commandDirectory "choco.exe") -PathType Leaf)
    ) {
        Split-Path -Parent $commandDirectory
    }

    if ($chocolateyRoot) {
        $chocolateyBin = [System.IO.Path]::GetFullPath((Join-Path $chocolateyRoot "bin"))
        if ([System.IO.Path]::GetFullPath($commandDirectory) -ieq $chocolateyBin) {
            $packageDirectories = Get-ChildItem -LiteralPath (Join-Path $chocolateyRoot "lib") `
                -Filter "ffmpeg*" -Directory -ErrorAction Stop
            $packageTool = $packageDirectories |
                Get-ChildItem -Filter "$ToolName.exe" -File -Recurse -ErrorAction Stop |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
            if (-not $packageTool) {
                throw "Could not resolve the Chocolatey $ToolName shim to its package executable."
            }
            Write-Host "Resolved Chocolatey $ToolName shim to $($packageTool.FullName)"
            return $packageTool.FullName
        }
    }

    return $commandPath
}

$FfmpegPath = Resolve-MediaToolPath -ToolName "ffmpeg" -ConfiguredPath $FfmpegPath
$FfprobePath = Resolve-MediaToolPath -ToolName "ffprobe" -ConfiguredPath $FfprobePath

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

$ffmpegDestination = Join-Path $binaryDirectory "ffmpeg-$TargetTriple.exe"
$ffprobeDestination = Join-Path $binaryDirectory "ffprobe-$TargetTriple.exe"
Copy-Item -LiteralPath $FfmpegPath -Destination $ffmpegDestination -Force
Copy-Item -LiteralPath $FfprobePath -Destination $ffprobeDestination -Force

foreach ($tool in @($ffmpegDestination, $ffprobeDestination)) {
    $validation = Start-Process -FilePath $tool -ArgumentList "-version" -NoNewWindow -Wait -PassThru
    if ($validation.ExitCode -ne 0) {
        throw "Bundled media tool validation failed with exit code $($validation.ExitCode): $tool"
    }
}

Write-Host "Prepared Windows sidecars in $binaryDirectory"
