param(
    [string]$TargetTriple = "x86_64-pc-windows-msvc"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$binaryDirectory = Join-Path $repositoryRoot "src-tauri\binaries"
$backend = Join-Path $binaryDirectory "beatweave-backend-$TargetTriple.exe"
$ffmpeg = Join-Path $binaryDirectory "ffmpeg-$TargetTriple.exe"
$ffprobe = Join-Path $binaryDirectory "ffprobe-$TargetTriple.exe"

foreach ($tool in @($backend, $ffmpeg, $ffprobe)) {
    if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
        throw "Packaging sidecar is missing: $tool. Run npm run prepare:windows first."
    }
}

$spaceRoot = Join-Path ([System.IO.Path]::GetTempPath()) "Beatweave package smoke test $([guid]::NewGuid())"
$dataDirectory = Join-Path $spaceRoot "User Data"
New-Item -ItemType Directory -Force -Path $dataDirectory | Out-Null
$port = 18420
$process = $null
$backendProcessName = [System.IO.Path]::GetFileNameWithoutExtension($backend)
$existingBackendProcessIds = @(
    Get-Process -Name $backendProcessName -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $backend } |
        ForEach-Object { $_.Id }
)

try {
    $environment = @{
        BEATWEAVE_DATA_DIR = $dataDirectory
        BEATWEAVE_PORT = "$port"
        BEATWEAVE_FFMPEG_PATH = $ffmpeg
        BEATWEAVE_FFPROBE_PATH = $ffprobe
    }
    foreach ($item in $environment.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($item.Key, $item.Value, "Process")
    }
    $process = Start-Process -FilePath $backend -WindowStyle Hidden -PassThru
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 250
        if ($process.HasExited) {
            throw "Packaged backend exited during startup with code $($process.ExitCode)."
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 1
        } catch {
            $health = $null
        }
    } until ($health -or (Get-Date) -gt $deadline)
    if (-not $health) {
        throw "Packaged backend did not become healthy within 30 seconds."
    }
    if ($health.status -ne "ok") {
        throw "Unexpected health response from packaged backend."
    }
    $ffmpegVersion = & $ffmpeg -version
    if ($LASTEXITCODE -ne 0) { throw "Bundled FFmpeg could not run." }
    Write-Host ($ffmpegVersion | Select-Object -First 1)
    $ffprobeVersion = & $ffprobe -version
    if ($LASTEXITCODE -ne 0) { throw "Bundled ffprobe could not run." }
    Write-Host ($ffprobeVersion | Select-Object -First 1)
    Write-Host "Packaged backend starts from a path with spaces with external services offline."
} finally {
    # A PyInstaller one-file executable has both a launcher and a worker. Stop
    # every matching process created by this test so the worker cannot retain
    # the SQLite database after the launcher exits.
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        $spawnedBackendProcesses = @(
            Get-Process -Name $backendProcessName -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.Path -eq $backend -and $_.Id -notin $existingBackendProcessIds
                }
        )
        if ($spawnedBackendProcesses.Count -eq 0) {
            break
        }
        $spawnedBackendProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
        foreach ($spawnedProcess in $spawnedBackendProcesses) {
            $spawnedProcess.WaitForExit(1000) | Out-Null
        }
    }
    foreach ($key in @("BEATWEAVE_DATA_DIR", "BEATWEAVE_PORT", "BEATWEAVE_FFMPEG_PATH", "BEATWEAVE_FFPROBE_PATH")) {
        [Environment]::SetEnvironmentVariable($key, $null, "Process")
    }
    if (Test-Path -LiteralPath $spaceRoot) {
        # Retry for any final delay between process exit and Windows releasing
        # the database handle.
        $cleanupAttempts = 10
        for ($attempt = 1; $attempt -le $cleanupAttempts; $attempt++) {
            try {
                Remove-Item -LiteralPath $spaceRoot -Recurse -Force -ErrorAction Stop
                break
            } catch {
                if ($attempt -eq $cleanupAttempts) {
                    throw
                }
                Start-Sleep -Milliseconds 250
            }
        }
    }
}
