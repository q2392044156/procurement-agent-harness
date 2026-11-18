# Build the shared agent image with host network.
# MCP reuses the same image; this avoids building/exporting a second ~3GB image.
param(
    [string]$Prefix = 'procuremind'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Building $Prefix-agent:latest (MCP reuses this image) ..."
docker build --network=host -t "$Prefix-agent:latest" .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done. Start with: cd ..\smart-procurement-platform; .\scripts\demo-up.ps1 -Agent"
