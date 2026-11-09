# Reset demo data: drop platform volumes, restart, re-seed knowledge base.
# Usage:
#   .\scripts\reset_demo.ps1            # platform only
#   .\scripts\reset_demo.ps1 -Agent     # platform + agent profile
# WARNING: removes MySQL / Redis / MinIO / Mongo / Qdrant volumes.

param(
    [switch]$Agent,
    [switch]$SkipKb
)

$ErrorActionPreference = 'Stop'
$harness = Split-Path -Parent $PSScriptRoot
$root = Split-Path -Parent $harness
$platform = Join-Path $root 'smart-procurement-platform'

function Invoke-Docker {
    param([string[]]$DockerArgs)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & docker @DockerArgs
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    return $code
}

if (-not (Test-Path $platform)) {
    throw "Platform repo not found at $platform"
}

Set-Location $platform
$files = @('-f', 'compose.yml')
if (Test-Path '.demo-override.yml') { $files += @('-f', '.demo-override.yml') }
$profileArgs = @()
if ($Agent) { $profileArgs = @('--profile', 'agent') }

Write-Host 'Resetting platform volumes (keeping hf-cache)...'
$code = Invoke-Docker (@('compose') + $files + $profileArgs + @('down'))
if ($code -ne 0) { exit $code }

foreach ($volume in @('mysql-data', 'minio-data', 'mongo-data', 'qdrant-data')) {
    Invoke-Docker @('volume', 'rm', "procuremind_$volume") | Out-Null
}

Write-Host 'Starting platform...'
$startArgs = @{}
if ($Agent) { $startArgs['Agent'] = $true }
& (Join-Path $platform 'scripts\demo-up.ps1') @startArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host 'Waiting for backend health...'
$healthy = $false
for ($i = 0; $i -lt 120; $i++) {
    try {
        $response = Invoke-WebRequest 'http://localhost:8080/actuator/health' -UseBasicParsing -TimeoutSec 3
        $text = [System.Text.Encoding]::UTF8.GetString($response.Content)
        if ($text -match 'UP') { $healthy = $true; break }
    } catch { }
    Start-Sleep -Seconds 3
}
if (-not $healthy) { throw 'Backend did not become healthy in time' }

if ($SkipKb) { exit 0 }

$conda = (Get-Command conda -ErrorAction SilentlyContinue).Source
if (-not $conda -and (Test-Path 'E:\develop\anaconda3\Scripts\conda.exe')) {
    $conda = 'E:\develop\anaconda3\Scripts\conda.exe'
}
if (-not $conda) { throw 'conda not found; activate the procurement env or install conda' }

Set-Location $harness
$previous = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

Write-Host 'Seeding knowledge base documents...'
& $conda run --no-capture-output -n procurement python scripts/seed_kb_documents.py
$code = $LASTEXITCODE
if ($code -ne 0) { $ErrorActionPreference = $previous; exit $code }

Write-Host 'Rebuilding Qdrant index...'
Remove-Item 'data\kb_state.json' -ErrorAction SilentlyContinue
& $conda run --no-capture-output -n procurement python scripts/kb_ingest.py
$code = $LASTEXITCODE
$ErrorActionPreference = $previous
exit $code
