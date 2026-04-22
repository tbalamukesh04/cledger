# Requires Run as Administrator
$ErrorActionPreference = 'Stop'

# Hardcoded Paths
$nssmPath = "C:\Projects\cledger\nssm\nssm.exe"
$envFilePath = "C:\Projects\cledger\backend\.env"

$backendServiceName = "CLedgerBackend"
$workerServiceName = "CLedgerWorker"

# ==========================================
# STEP 1: VALIDATE ENV FILE
# ==========================================
if (-Not (Test-Path $envFilePath)) {
    Write-Error "CRITICAL: .env file not found at $envFilePath. Please create it before running this script."
    exit 1
}

if (-Not (Test-Path $nssmPath)) {
    Write-Error "CRITICAL: NSSM not found at $nssmPath."
    exit 1
}

# ==========================================
# STEP 2: PARSE .ENV FILE
# ==========================================
Write-Host "Parsing $envFilePath..."
# Read lines, trim whitespace, ignore empty lines and comment lines
$envVars = Get-Content $envFilePath | Where-Object { 
    $_.Trim() -ne "" -and -not $_.Trim().StartsWith("#") 
}

if ($envVars.Count -eq 0) {
    Write-Host "Warning: No valid environment variables found in $envFilePath."
    exit 0
}

Write-Host "Found $($envVars.Count) environment variables. Injecting into services..."

# ==========================================
# STEP 3: STOP SERVICES FOR CONFIGURATION
# ==========================================
Stop-Service -Name $backendServiceName -Force -ErrorAction SilentlyContinue
Stop-Service -Name $workerServiceName -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# ==========================================
# STEP 4: INJECT ENVIRONMENT VARIABLES
# ==========================================
# NSSM accepts an array of strings for AppEnvironmentExtra
& $nssmPath set $backendServiceName AppEnvironmentExtra $envVars
& $nssmPath set $workerServiceName AppEnvironmentExtra $envVars

# ==========================================
# STEP 5: RESTART SERVICES
# ==========================================
Write-Host "Restarting services with new environment context..."
Start-Service -Name $backendServiceName
Start-Service -Name $workerServiceName

Write-Host "`nEnvironment Configuration Complete! Services are running with injected variables."
