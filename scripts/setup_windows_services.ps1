# Requires Run as Administrator
$ErrorActionPreference = 'Stop'

# Define strict, hardcoded paths
$nssmPath = "C:\Projects\cledger\nssm\nssm.exe"
$pythonExe = "C:\Projects\cledger\backend\venv\Scripts\python.exe"
$backendDir = "C:\Projects\cledger\backend"

$backendServiceName = "CLedgerBackend"
$workerServiceName = "CLedgerWorker"

# ==========================================
# STEP 1: FAIL-FAST VALIDATIONS
# ==========================================
if (-Not (Test-Path $nssmPath)) {
    Write-Error "CRITICAL: NSSM not found at $nssmPath. Please pre-install NSSM and place it in the exact specified directory before running this script."
    exit 1
}

if (-Not (Test-Path $pythonExe)) {
    Write-Error "CRITICAL: Python virtual environment not found at $pythonExe. Please configure the venv first."
    exit 1
}

if (-Not (Test-Path $backendDir)) {
    Write-Error "CRITICAL: Backend directory not found at $backendDir."
    exit 1
}

Write-Host "All dependencies verified. Proceeding with deterministic service installation..."

# ==========================================
# HELPER: IDEMPOTENT SERVICE INSTALLATION
# ==========================================
function Setup-NSSMService {
    param (
        [string]$ServiceName,
        [string]$ExePath,
        [string]$AppParams,
        [string]$AppDir
    )

    # Clean slate: Remove existing service if it's already there
    $existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existingService) {
        Write-Host "Service $ServiceName exists. Stopping and removing for a clean install..."
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        & $nssmPath remove $ServiceName confirm
        Start-Sleep -Seconds 2
    }

    Write-Host "Registering $ServiceName..."
    
    # 1. Install Service pointing to Python Executable
    & $nssmPath install $ServiceName $ExePath
    
    # 2. Set Arguments and Working Directory
    & $nssmPath set $ServiceName AppParameters $AppParams
    & $nssmPath set $ServiceName AppDirectory $AppDir
    
    # 3. Configure Auto-Start on Boot
    & $nssmPath set $ServiceName Start SERVICE_AUTO_START
    
    # 4. Configure Crash Recovery (Restart on Failure)
    # NSSM intercepts all unexpected exits and forcefully restarts the process
    & $nssmPath set $ServiceName AppExit Default Restart
    & $nssmPath set $ServiceName AppRestartDelay 0
    & $nssmPath set $ServiceName AppThrottle 1500
}

# ==========================================
# STEP 2: REGISTER BACKEND SERVICE
# ==========================================
# Note: Gunicorn is Unix-only. Using Uvicorn's built-in multiprocessing for Windows.
$backendArgs = "-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 120"
Setup-NSSMService -ServiceName $backendServiceName -ExePath $pythonExe -AppParams $backendArgs -AppDir $backendDir

# Route crash logs to file for visibility
& $nssmPath set $backendServiceName AppStdout "C:\Projects\cledger\logs\backend.out.log"
& $nssmPath set $backendServiceName AppStderr "C:\Projects\cledger\logs\backend.err.log"
# Enable NSSM native daily rotation (86400 seconds)
& $nssmPath set $backendServiceName AppRotateFiles 1
& $nssmPath set $backendServiceName AppRotateOnline 1
& $nssmPath set $backendServiceName AppRotateSeconds 86400

# ==========================================
# STEP 3: REGISTER WORKER SERVICE
# ==========================================
$workerArgs = "-m app.workers.worker_service"
Setup-NSSMService -ServiceName $workerServiceName -ExePath $pythonExe -AppParams $workerArgs -AppDir $backendDir

# Route crash logs to file for visibility
& $nssmPath set $workerServiceName AppStdout "C:\Projects\cledger\logs\worker.out.log"
& $nssmPath set $workerServiceName AppStderr "C:\Projects\cledger\logs\worker.err.log"
# Enable NSSM native daily rotation (86400 seconds)
& $nssmPath set $workerServiceName AppRotateFiles 1
& $nssmPath set $workerServiceName AppRotateOnline 1
& $nssmPath set $workerServiceName AppRotateSeconds 86400
# ==========================================
# STEP 4: START SERVICES
# ==========================================
Write-Host "Starting services automatically..."
Start-Service -Name $backendServiceName
Start-Service -Name $workerServiceName

# ==========================================
# STEP 5: VERIFICATION SUMMARY
# ==========================================
Write-Host "`nInstallation Complete. Service Statuses:"
Get-Service -Name CLedger* | Format-Table -Property Name, Status, StartType

Write-Host "`nBackend and Worker are now running as persistent Windows services."