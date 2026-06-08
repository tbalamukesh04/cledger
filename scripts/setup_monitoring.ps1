# Filepath: C:\Projects\cledger\scripts\setup_system_monitoring.ps1

$ErrorActionPreference = 'Continue'
$collectorName = "CLedgerMetrics"
$logDir = "C:\Projects\cledger\logs"
$logFileBase = "$logDir\system_metrics.csv"

# Ensure log directory exists
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

# Halt and remove existing collector to allow clean redeployment
$existing = logman query $collectorName 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Output "Stopping and removing existing $collectorName..."
    logman stop $collectorName 2>$null
    logman delete $collectorName 2>$null
}

Write-Output "Registering new data collector set: $collectorName"
logman create counter $collectorName -c "\Processor(_Total)\% Processor Time" "\Memory\% Committed Bytes In Use" "\LogicalDisk(C:)\% Free Space" -f csv -si 60 -o $logFileBase

Write-Output "Starting $collectorName..."
logman start $collectorName

Write-Output "Baseline monitoring active. Data logging to $logDir"