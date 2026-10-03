param(
    [Parameter(Mandatory = $true)]
    [string]$TagName
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot

if ($TagName -notmatch '^v(?<version>(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*))$') {
    throw "Release tag '$TagName' must use the stable semantic-version format vMAJOR.MINOR.PATCH."
}
$releaseVersion = $Matches.version

function Read-JsonVersion {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $path = Join-Path $repositoryRoot $RelativePath
    $version = (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json).version
    if (-not $version) {
        throw "No version was found in $RelativePath."
    }
    return [string]$version
}

function Read-TomlVersion {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)][string]$Section
    )

    $path = Join-Path $repositoryRoot $RelativePath
    $content = Get-Content -LiteralPath $path -Raw
    $escapedSection = [regex]::Escape($Section)
    $sectionMatch = [regex]::Match($content, "(?ms)^\[$escapedSection\](?<body>.*?)(?=^\[|\z)")
    $match = [regex]::Match($sectionMatch.Groups['body'].Value, '^version\s*=\s*"(?<version>[^"]+)"', 'Multiline')
    if (-not $match.Success) {
        throw "No version was found in [$Section] in $RelativePath."
    }
    return $match.Groups['version'].Value
}

$manifestVersions = [ordered]@{
    'package.json' = Read-JsonVersion 'package.json'
    'frontend/package.json' = Read-JsonVersion 'frontend/package.json'
    'backend/pyproject.toml' = Read-TomlVersion 'backend/pyproject.toml' 'project'
    'src-tauri/Cargo.toml' = Read-TomlVersion 'src-tauri/Cargo.toml' 'package'
    'src-tauri/tauri.conf.json' = Read-JsonVersion 'src-tauri/tauri.conf.json'
}

$mismatches = @($manifestVersions.GetEnumerator() | Where-Object { $_.Value -ne $releaseVersion })
if ($mismatches.Count -gt 0) {
    $details = $mismatches | ForEach-Object { "$($_.Key) declares $($_.Value)" }
    throw "Tag $TagName does not match every release manifest: $($details -join '; ')."
}

Write-Host "Release tag $TagName matches all release manifests."
