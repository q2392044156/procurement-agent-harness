# Build agent/mcp images with host network.
# Docker Desktop's default build network often stalls on the 209MB CPU torch wheel.
param(
    [string]$Prefix = 'procuremind'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Building $Prefix-agent:latest ..."
docker build --network=host -t "$Prefix-agent:latest" .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Building $Prefix-mcp:latest ..."
docker build --network=host -t "$Prefix-mcp:latest" .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done. Start with: cd ..\smart-procurement-platform; .\scripts\demo-up.ps1 -Agent"
