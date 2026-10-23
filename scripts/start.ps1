<#
.SYNOPSIS
Starts code-form in the foreground using the checkout's local Python environment.
.DESCRIPTION
Press Ctrl+C in this terminal to stop. Relative paths start at the checkout.
.EXAMPLE
.\scripts\start.ps1 -DataDir .codeform/demo
.EXAMPLE
.\scripts\start.ps1 -Workspace .. -DataDir .codeform/projects -Port 7332 -NoDemo
#>
param(
    [ValidateRange(0, 65535)][int]$Port = 7331,
    [string]$Workspace = '',
    [string]$DataDir = '',
    [switch]$NoDemo
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $environmentPython)) {
    & (Join-Path $PSScriptRoot 'setup.ps1')
}
if (-not $Workspace) { $Workspace = $projectRoot }
Push-Location $projectRoot
try {
    $serverArguments = @('-m', 'codeform', 'serve', '--port', $Port, '--workspace', $Workspace)
    if ($DataDir) { $serverArguments += @('--data-dir', $DataDir) }
    if (-not $NoDemo) { $serverArguments += '--demo' }
    & $environmentPython @serverArguments
    if ($LASTEXITCODE -ne 0) { throw "code-form exited with code $LASTEXITCODE." }
} finally {
    Pop-Location
}
