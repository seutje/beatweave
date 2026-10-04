param(
    [string]$InstallerPath = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $InstallerPath) {
    $bundleDirectory = Join-Path $repositoryRoot "src-tauri\target\release\bundle\nsis"
    $installer = Get-ChildItem -LiteralPath $bundleDirectory -Filter "Beatweave_*_x64-setup.exe" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($installer) {
        $InstallerPath = $installer.FullName
    }
}
if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
    throw "Beatweave installer not found: $InstallerPath"
}

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this smoke test from a non-elevated terminal."
}

$smokeRoot = Join-Path $repositoryRoot ".package-smoke"
$installDirectory = Join-Path $smokeRoot "Beatweave Install"
if (Test-Path -LiteralPath $smokeRoot) {
    throw "Refusing to overwrite the existing smoke-test directory: $smokeRoot"
}
New-Item -ItemType Directory -Path $smokeRoot | Out-Null

$application = Join-Path $installDirectory "Beatweave.exe"
$uninstaller = Join-Path $installDirectory "uninstall.exe"
$webviewDataDirectory = Join-Path $smokeRoot "WebView Data"
$process = $null

try {
    $install = Start-Process -FilePath $InstallerPath -ArgumentList @("/S", "/D=$installDirectory") -WindowStyle Hidden -Wait -PassThru
    if ($install.ExitCode -ne 0) {
        throw "Installer exited with code $($install.ExitCode)."
    }
    foreach ($file in @($application, (Join-Path $installDirectory "beatweave-backend.exe"), (Join-Path $installDirectory "beatweave-mcp.exe"), (Join-Path $installDirectory "ffmpeg.exe"), (Join-Path $installDirectory "ffprobe.exe"))) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "Installed file is missing: $file"
        }
    }

    [Environment]::SetEnvironmentVariable(
        "WEBVIEW2_USER_DATA_FOLDER",
        $webviewDataDirectory,
        "Process"
    )
    $process = Start-Process -FilePath $application -WindowStyle Hidden -PassThru
    $deadline = (Get-Date).AddSeconds(45)
    do {
        Start-Sleep -Milliseconds 500
        if ($process.HasExited) {
            throw "Installed Beatweave exited during startup with code $($process.ExitCode)."
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8420/health" -TimeoutSec 1
        } catch {
            $health = $null
        }
    } until ($health -or (Get-Date) -gt $deadline)
    if (-not $health -or $health.status -ne "ok") {
        throw "Installed Beatweave did not become healthy with external backends offline."
    }
    Write-Host "Per-user installer and installed app passed from a path with spaces without elevation."
} finally {
    [Environment]::SetEnvironmentVariable("WEBVIEW2_USER_DATA_FOLDER", $null, "Process")
    if ($process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        $process.WaitForExit(5000) | Out-Null
    }
    $backend = Join-Path $installDirectory "beatweave-backend.exe"
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        $backendProcesses = @(
            Get-Process -Name "beatweave-backend" -ErrorAction SilentlyContinue |
                Where-Object { $_.Path -eq $backend }
        )
        if ($backendProcesses.Count -eq 0) {
            break
        }
        $backendProcesses | Stop-Process -Force -ErrorAction SilentlyContinue
        foreach ($backendProcess in $backendProcesses) {
            $backendProcess.WaitForExit(1000) | Out-Null
        }
    }
    if (Test-Path -LiteralPath $uninstaller -PathType Leaf) {
        $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @("/S") -WindowStyle Hidden -Wait -PassThru
        if ($uninstall.ExitCode -ne 0) {
            Write-Warning "Uninstaller exited with code $($uninstall.ExitCode)."
        }
    }
    if (Test-Path -LiteralPath $smokeRoot) {
        $resolvedRoot = [System.IO.Path]::GetFullPath($repositoryRoot).TrimEnd('\')
        $resolvedSmoke = [System.IO.Path]::GetFullPath($smokeRoot)
        if (-not $resolvedSmoke.StartsWith("$resolvedRoot\", [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean a smoke-test directory outside the repository."
        }
        for ($attempt = 1; $attempt -le 10; $attempt++) {
            try {
                Remove-Item -LiteralPath $smokeRoot -Recurse -Force -ErrorAction Stop
                break
            } catch {
                if ($attempt -eq 10) {
                    throw
                }
                Start-Sleep -Milliseconds 250
            }
        }
    }
}
