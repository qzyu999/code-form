<#
.SYNOPSIS
Creates code-form's local Python environment without installing packages.
.EXAMPLE
.\scripts\setup.ps1
.EXAMPLE
.\scripts\setup.ps1 -WithPip
#>
param([switch]$WithPip)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentPath = Join-Path $projectRoot '.venv'
if (-not (Test-Path -LiteralPath (Join-Path $environmentPath 'Scripts/python.exe'))) {
    python -m venv --without-pip $environmentPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
}
$environmentPython = Join-Path $environmentPath 'Scripts/python.exe'
& $environmentPython -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer is required'; assert sys.prefix != sys.base_prefix, 'A local virtual environment is required'; print('Ready:', sys.executable)"
if ($LASTEXITCODE -ne 0) { throw 'The local Python environment is not usable.' }
if ($WithPip) {
    & $environmentPython -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Optional pip setup failed; the application itself does not require pip.' }
}
Write-Output 'The app has no runtime dependencies.'
Write-Output 'Run: .\.venv\Scripts\python.exe -m codeform serve --demo'
