$ErrorActionPreference = "Stop"

$BackupDir = "C:\backups"
$LogFile = "$BackupDir\backup_execution.log"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ContainerName = "local-postgres"

# Ensure host backup directory exists early for logging
if (!(Test-Path -Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
}

# Start logging all console output to the log file (equivalent to cron logging)
Start-Transcript -Path $LogFile -Append

$EnvPath = Join-Path $PSScriptRoot "backup.env"
if (!(Test-path $EnvPath)) {
    Write-Error "ERROR: Secure configuration file backup.env not found!"
    exit 1
}

Get-Content $EnvPath | Where-Object {$_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
    $name, $value = $_ -split '=', 2
    Set-Variable -Name "Env_$($name.Trim())" -Value $value.Trim()
}

$DbUser = $Env_DB_USER
$DbPassword = $Env_DB_PASSWORD
$DbName = $Env_DB_NAME

$DayOfWeek = (Get-Date).DayOfWeek
$BackupType = if ($DayOfWeek -eq [System.DayOfWeek]::Sunday) { "weekly" } else { "daily" }

$ContainerBackupPath = "/tmp/${DbName}_backup_${BackupType}_${Timestamp}.dump"
$HostBackupPath = "$BackupDir\${DbName}_backup_${BackupType}_${Timestamp}.dump"

Write-Host "[$(Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')] Starting backup of database '${DbName}'..."

# 1. Run pg_dump inside the container
Write-Host "Running pg_dump inside container..."
docker exec -e PGPASSWORD=$DbPassword $ContainerName pg_dump -U $DbUser -d $DbName -F c -f $ContainerBackupPath

# 2. Extract the file from the container to the Windows host
Write-Host "Extracting backup to Windows host ($HostBackupPath)..."
docker cp "${ContainerName}:${ContainerBackupPath}" $HostBackupPath

# 3. Clean up the temporary file inside the container
Write-Host "Cleaning up container..."
docker exec $ContainerName rm $ContainerBackupPath

# Verify the file was created and has size greater than 0
if (Test-Path $HostBackupPath) {
    $FileInfo = Get-Item $HostBackupPath
    if ($FileInfo.Length -gt 0) {
        Write-Host "[$(Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')] Backup completed successfully: $HostBackupPath"
    } else {
        Write-Error "ERROR: Backup file is empty!"
        exit 1
    }
} else {
    Write-Error "ERROR: Backup file is missing!"
    exit 1
}

Write-Host "Backup type: $BackupType"

# 4. Retention Policy Cleanup
$DailyBackups = Get-ChildItem -Path $BackupDir -Filter "${Dbname}_backup_daily_*.dump" | Sort-Object CreationTime -Descending
if ($DailyBackups.Count -gt 7) {
    $DailyBackups | Select-Object -Skip 7 | ForEach-Object {
        Write-Host "Deleting old daily backup: $($_.Name)"
        Remove-Item $_.FullName -Force
    }
}

$WeeklyBackups = Get-ChildItem -Path $BackupDir -Filter "${DbName}_backup_weekly_*.dump" | Sort-Object CreationTime -Descending
if ($WeeklyBackups.Count -gt 4) {
    $WeeklyBackups | Select-Object -Skip 4 | ForEach-Object {
        Write-Host "Deleting old weekly backup: $($_.Name)"
        Remove-Item $_.FullName -Force
    }
}

# 5. Offsite Sync to Cloud Storage
Write-Host "Starting offsite sync via Rclone..."
rclone sync $BackupDir "gdrive_remote:/cledger_prod_backups" -v

if ($LASTEXITCODE -eq 0) {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')] Offsite sync completed successfully."
} else {
    Write-Error "ERROR: Offsite sync failed with exit code $LASTEXITCODE"
}

Write-Host "[$(Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')] Backup, cleanup, and sync process finished."

# Stop logging
Stop-Transcript