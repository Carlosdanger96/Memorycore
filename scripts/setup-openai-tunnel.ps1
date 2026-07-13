<#!
.SYNOPSIS
Prepares and validates an OpenAI Secure MCP Tunnel for local Memorycore.

.DESCRIPTION
Keeps Memorycore and SQLite on this computer. The script reads the selected
connector token from the private registry, exports it only to this process, and
writes a tunnel-client profile containing environment references rather than
secret values.

Before running, set CONTROL_PLANE_API_KEY to an OpenAI runtime API key and
obtain a tunnel ID from the OpenAI Platform tunnel settings page.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^tunnel_[A-Za-z0-9]+$')]
    [string]$TunnelId,

    [string]$TokenRegistry = "C:\Memorycore\secrets\http-clients.production.json",
    [string]$ClientId = "chatgpt-web",
    [string]$MemorycoreUrl = "http://127.0.0.1:8000/mcp",
    [string]$ProfileFile = "C:\Memorycore\secrets\openai-memorycore-tunnel.yaml",
    [string]$TunnelClient = "tunnel-client",
    [switch]$Run
)

$ErrorActionPreference = "Stop"

if (-not $env:CONTROL_PLANE_API_KEY) {
    $secureKey = Read-Host "OpenAI tunnel runtime API key" -AsSecureString
    $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try {
        $env:CONTROL_PLANE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
    }
    if (-not $env:CONTROL_PLANE_API_KEY) {
        throw "A runtime API key is required."
    }
}

if (-not (Test-Path -LiteralPath $TokenRegistry)) {
    throw "Token registry not found: $TokenRegistry"
}

$registry = Get-Content -LiteralPath $TokenRegistry -Raw | ConvertFrom-Json
$clients = if ($registry.clients) { $registry.clients } else { $registry }
$identity = @($clients | Where-Object { $_.client_id -eq $ClientId })
if ($identity.Count -ne 1) {
    throw "Expected exactly one '$ClientId' identity in the token registry; found $($identity.Count)."
}
if (-not $identity[0].token -or $identity[0].token.Length -lt 24) {
    throw "The '$ClientId' token is missing or too short."
}

# Secret exists only in the environment inherited by tunnel-client. The YAML
# profile stores an env reference, never the bearer token itself.
$env:MEMORYCORE_TUNNEL_MCP_TOKEN = [string]$identity[0].token

$command = Get-Command $TunnelClient -ErrorAction SilentlyContinue
if (-not $command) {
    throw "tunnel-client was not found. Download the current Windows release from OpenAI Platform tunnel settings, then rerun."
}

$profileDirectory = Split-Path -Parent $ProfileFile
if ($profileDirectory) {
    New-Item -ItemType Directory -Force -Path $profileDirectory | Out-Null
}

$profile = @"
config_version: 1
control_plane:
  base_url: https://api.openai.com
  tunnel_id: $TunnelId
  api_key: env:CONTROL_PLANE_API_KEY
log:
  level: info
  format: json
health:
  listen_addr: 127.0.0.1:8080
admin_ui:
  open_browser: false
mcp:
  server_urls:
    - channel: main
      url: $MemorycoreUrl
  extra_headers:
    Authorization: env:MEMORYCORE_TUNNEL_MCP_TOKEN
  discovery_extra_headers:
    Authorization: env:MEMORYCORE_TUNNEL_MCP_TOKEN
"@

Set-Content -LiteralPath $ProfileFile -Value $profile -Encoding UTF8

Write-Host "Validating local Memorycore authentication..."
try {
    Invoke-WebRequest -Uri $MemorycoreUrl -Method Post -Body '{}' -ContentType 'application/json' -UseBasicParsing | Out-Null
    throw "Memorycore unexpectedly accepted an anonymous request. Stop and inspect the HTTP authentication configuration."
} catch {
    if ([int]$_.Exception.Response.StatusCode -ne 401) {
        throw "Memorycore is not ready at $MemorycoreUrl or did not return 401 to an anonymous request: $($_.Exception.Message)"
    }
}

Write-Host "Running tunnel-client diagnostics..."
& $command.Source doctor --profile-file $ProfileFile --explain
if ($LASTEXITCODE -ne 0) {
    throw "tunnel-client doctor failed with exit code $LASTEXITCODE."
}

Write-Host ""
Write-Host "OpenAI Secure MCP Tunnel profile is valid."
Write-Host "Profile: $ProfileFile"
Write-Host "Local MCP: $MemorycoreUrl"
Write-Host "Admin UI after start: http://127.0.0.1:8080/ui"

if ($Run) {
    & $command.Source run --profile-file $ProfileFile
    exit $LASTEXITCODE
}

Write-Host "Start it with:"
Write-Host "  .\scripts\setup-openai-tunnel.ps1 -TunnelId $TunnelId -Run"
