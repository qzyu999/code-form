<#
.SYNOPSIS
Downloads the pinned Lean toolchain into this checkout without a global installation.
.EXAMPLE
.\scripts\setup-lean.ps1
#>
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$toolsDirectory = Join-Path $projectRoot '.codeform/tools'
$archivePath = Join-Path $toolsDirectory 'lean-4.19.0-windows.zip'
$leanExecutable = Join-Path $toolsDirectory 'lean-4.19.0-windows/bin/lean.exe'
if (-not (Test-Path -LiteralPath $leanExecutable)) {
    New-Item -ItemType Directory -Path $toolsDirectory -Force | Out-Null
    $downloadUrl = 'https://github.com/leanprover/lean4/releases/download/v4.19.0/lean-4.19.0-windows.zip'
    Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath
    Expand-Archive -LiteralPath $archivePath -DestinationPath $toolsDirectory -Force
}
& $leanExecutable --version
if ($LASTEXITCODE -ne 0) { throw 'The downloaded Lean toolchain could not run.' }
Write-Output "Lean executable: $leanExecutable"
