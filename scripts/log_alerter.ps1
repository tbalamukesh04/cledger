$ErrorActionPreference = 'Continue'
$logPath = "C:\Projects\cledger\logs\app.log"
$alertLogPath = "C:\Projects\cledger\logs\alerts.log"

$timeWindowMin = 5
$errorThreshold = 5
$queueThreshold = 50

if (-not (Test-Path $logPath)) { exit }

$rawLogs = Get-Content $logPath -Tail 2000 2>$null
$logs = $rawLogs | ConvertFrom-Json -ErrorAction SilentlyContinue

$cutoff = (Get-Date).ToUniversalTime().AddMinutes(-$timeWindowMin)
$recentLogs = $logs | Where-Object { $_.timestamp -and ([datetime]$_.timestamp -ge $cutoff) }

$errorCount = ($recentLogs | Where-Object { $_.level -eq 'ERROR' }).Count
if ($errorCount -ge $errorThreshold) {
    $alertMsg = "CRITICAL: $errorCount errors detected in the last $timeWindowMin minutes."
    Add-Content -Path $alertLogPath -Value "$(Get-Date -Format 'o') - $alertMsg"
    Write-EventLog -LogName Application -Source Application -EventID 2001 -EntryType Error -Message $alertMsg
}

$queueLogs = $recentLogs | Where-Object { $_.event -eq 'queue_depth_checked' }
if ($queueLogs) {
    $latestDepth = [int]($queueLogs[-1].queue_depth)
    if ($latestDepth -ge $queueThreshold) {
        $alertMsg = "WARNING: Queue depth is $latestDepth (Threshold: $queueThreshold)."
        Add-Content -Path $alertLogPath -Value "$(Get-Date -Format 'o') - $alertMsg"
        Write-EventLog -LogName Application -Source Application -EventID 2002 -EntryType Warning -Message $alertMsg
    }
}
