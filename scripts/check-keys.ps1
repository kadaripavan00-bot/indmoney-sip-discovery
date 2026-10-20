#Requires -Version 5.1
$ErrorActionPreference = "Stop"

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
}
catch {
    # Older PowerShell versions may not support this; continue.
}

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

function Read-DotEnv {
    param([string]$Path)
    $result = @{}
    if (-not (Test-Path $Path)) { return $result }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { return }

        $idx = $line.IndexOf("=")
        if ($idx -gt 0) {
            $key = $line.Substring(0, $idx).Trim()
            $value = $line.Substring($idx + 1).Trim()
            $result[$key] = $value
        }
    }
    return $result
}

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Uri,
        [hashtable]$Headers
    )

    if ($null -eq $Headers -or $Headers.Count -eq 0) {
        return [pscustomobject]@{ Provider = $Name; Status = "not set"; Detail = "optional" }
    }

    try {
        $response = Invoke-RestMethod -Uri $Uri -Method Get -Headers $Headers -TimeoutSec 30
        $count = ""
        if ($null -ne $response.data) { $count = " ($($response.data.Count) models)" }
        elseif ($null -ne $response.models) { $count = " ($($response.models.Count) models)" }
        return [pscustomobject]@{ Provider = $Name; Status = "OK"; Detail = "key valid$count" }
    }
    catch {
        $statusCode = ""
        if ($null -ne $_.Exception.Response -and $null -ne $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        $detail = if ($statusCode) { "HTTP $statusCode" } else { "network or parse error" }
        return [pscustomobject]@{ Provider = $Name; Status = "FAILED"; Detail = $detail }
    }
}

$envVars = Read-DotEnv (Join-Path $projectRoot ".env")
if ($envVars.Count -eq 0) {
    Write-Host "No .env file found. Run setup-key.bat first." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Checking API keys..." -ForegroundColor Cyan
Write-Host ""

$results = @()

$geminiHeaders = @{}
if ($envVars.ContainsKey("GEMINI_API_KEY") -and -not [string]::IsNullOrWhiteSpace($envVars["GEMINI_API_KEY"])) {
    $geminiHeaders["x-goog-api-key"] = $envVars["GEMINI_API_KEY"]
}
$results += Test-Endpoint -Name "Google AI Studio (Gemini)" -Uri "https://generativelanguage.googleapis.com/v1beta/models" -Headers $geminiHeaders

$groqHeaders = @{}
if ($envVars.ContainsKey("GROQ_API_KEY") -and -not [string]::IsNullOrWhiteSpace($envVars["GROQ_API_KEY"])) {
    $groqHeaders["Authorization"] = "Bearer $($envVars["GROQ_API_KEY"])"
}
$results += Test-Endpoint -Name "Groq Cloud" -Uri "https://api.groq.com/openai/v1/models" -Headers $groqHeaders

$mistralHeaders = @{}
if ($envVars.ContainsKey("MISTRAL_API_KEY") -and -not [string]::IsNullOrWhiteSpace($envVars["MISTRAL_API_KEY"])) {
    $mistralHeaders["Authorization"] = "Bearer $($envVars["MISTRAL_API_KEY"])"
}
$results += Test-Endpoint -Name "Mistral AI" -Uri "https://api.mistral.ai/v1/models" -Headers $mistralHeaders

$cohereHeaders = @{}
if ($envVars.ContainsKey("COHERE_API_KEY") -and -not [string]::IsNullOrWhiteSpace($envVars["COHERE_API_KEY"])) {
    $cohereHeaders["Authorization"] = "Bearer $($envVars["COHERE_API_KEY"])"
}
$results += Test-Endpoint -Name "Cohere" -Uri "https://api.cohere.com/v1/models" -Headers $cohereHeaders

$results | Format-Table -AutoSize

$geminiResult = $results | Where-Object { $_.Provider -eq "Google AI Studio (Gemini)" }
if ($null -eq $geminiResult -or $geminiResult.Status -ne "OK") {
    Write-Host "Gemini is the primary provider and did not validate." -ForegroundColor Red
    Write-Host "Create a new key at https://aistudio.google.com/apikey and run setup-key.bat again." -ForegroundColor Yellow
    exit 1
}

Write-Host "Primary key is valid. You are ready for the extraction run." -ForegroundColor Green
exit 0
