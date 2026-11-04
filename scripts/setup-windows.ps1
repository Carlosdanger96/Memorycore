<#!
.SYNOPSIS
Sets up Memorycore from a cloned Git repository on Windows.

.DESCRIPTION
Creates .venv, installs the MCP service dependencies, initializes a local
SQLite database, and can optionally start the central HTTP MCP service.

.EXAMPLE
./scripts/setup-windows.ps1
./scripts/setup-windows.ps1 -StartService
#>
[CmdletBinding()]
param(
    [string]$DatabasePath = "data\memorycore.db",
    [int]$Port = 8000,
    [switch]$StartService,
    [string]$TokenFile,
    [string]$PublicUrl
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$SystemPython = Get-Command python -ErrorAction SilentlyContinue
$Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $Uv) {
    foreach ($Candidate in @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "hermes\bin\uv.exe"),
        (Join-Path $env:APPDATA "uv\bin\uv.exe")
    )) {
        if (Test-Path -LiteralPath $Candidate) { $Uv = $Candidate; break }
    }
}
if (-not $SystemPython -and -not $Uv) {
    throw "Python 3.11+ or uv is required to create the virtual environment."
}
if ($SystemPython) {
    $Version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ([version]$Version -lt [version]"3.11") {
        throw "Python 3.11 or newer is required; found Python $Version."
    }
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    if ($SystemPython) { & python -m venv .venv }
    else { & $Uv venv --python 3.11 .venv }
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if ($Uv) { & $Uv pip install --python $Python -e ".[mcp]" }
else {
    & $Python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
    & $Python -m pip install -e ".[mcp]"
}
if ($LASTEXITCODE -ne 0) { throw "Memorycore dependency installation failed." }

$DatabaseDirectory = Split-Path -Parent $DatabasePath
if ($DatabaseDirectory) {
    New-Item -ItemType Directory -Force -Path $DatabaseDirectory | Out-Null
}
& $Python -m memorycore.cli --db $DatabasePath init
if ($LASTEXITCODE -ne 0) { throw "Memorycore initialization failed." }
& $Python -m memorycore.cli --db $DatabasePath doctor
if ($LASTEXITCODE -ne 0) { throw "Memorycore doctor failed." }

Write-Host ""
Write-Host "Memorycore is ready."
Write-Host "Database: $(Join-Path $Root $DatabasePath)"
Write-Host ""
Write-Host "To start the protected central MCP service later, configure a token file and public URL:"
Write-Host "  `$env:MEMORYCORE_HTTP_TOKENS_FILE = 'C:\Memorycore\secrets\http-clients.json'"
Write-Host "  `$env:MEMORYCORE_PUBLIC_URL = 'https://memory.example.com/mcp'"
Write-Host "  .\.venv\Scripts\python.exe -m memorycore.cli --db $DatabasePath serve-http --host 127.0.0.1 --port $Port"
Write-Host "MCP endpoint: http://127.0.0.1:$Port/mcp"

if ($StartService) {
    if (-not $TokenFile -or -not $PublicUrl) {
        throw "-StartService requires -TokenFile and -PublicUrl. See docs\WEB_MCP_DEPLOYMENT.md."
    }
    $env:MEMORYCORE_HTTP_TOKENS_FILE = $TokenFile
    $env:MEMORYCORE_PUBLIC_URL = $PublicUrl
    & $Python -m memorycore.cli --db $DatabasePath serve-http --host 127.0.0.1 --port $Port
}
