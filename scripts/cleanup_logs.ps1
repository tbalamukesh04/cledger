$ErrorActionPreference = 'Continue'
$logPath = "C:\Projects\cledger\logs"
$daysToKeep = 7
$cutoffDate = (Get-Date).AddDays(-$daysToKeep)

if (Test-Path $logPath) {
    Get-ChildItem -Path $logPath -File | Where-Object { 
        $_.LastWriteTime -lt $cutoffDate 
    } | ForEach-Object {
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
    }
}
