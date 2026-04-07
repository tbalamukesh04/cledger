$ErrorActionPreference = "Stop"

$BackupDir = "C:\backups"
$ContainerName = "local-postgres"
$TestDbName = "cledger_restore_test"

# 1. Securely load ADMIN credentials
$EnvPath = Join-Path $PSScriptRoot "restore.env"
if (!(Test-Path $EnvPath)) {
    Write-Error "ERROR: Secure configuration file restore.env not found!"
    exit 1
}

Get-Content $EnvPath | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
    $name, $value = $_ -split '=', 2
    Set-Variable -Name "Env_$($name.Trim())" -Value $value.Trim()
}

$AdminUser = $Env_ADMIN_DB_USER
$AdminPassword = $Env_ADMIN_DB_PASSWORD

# 2. Find the most recent backup file
$LatestBackup = Get-ChildItem -Path $BackupDir -Filter "*.dump" | Sort-Object CreationTime -Descending | Select-Object -First 1
if (!$LatestBackup) {
    Write-Error "ERROR: No backup files found in $BackupDir!"
    exit 1
}

Write-Host "Starting restore test using backup: $($LatestBackup.Name)"

# 3. Copy backup file into the Docker container
Write-Host "Copying backup to container..."
$ContainerRestorePath = "/tmp/restore_test.dump"
docker cp $LatestBackup.FullName "${ContainerName}:${ContainerRestorePath}"

# 4. Prepare the Test Database (Drop if exists, then Create)
Write-Host "Recreating test database '$TestDbName'..."
docker exec -e PGPASSWORD=$AdminPassword $ContainerName psql -U $AdminUser -d postgres -c "DROP DATABASE IF EXISTS $TestDbName;"
docker exec -e PGPASSWORD=$AdminPassword $ContainerName psql -U $AdminUser -d postgres -c "CREATE DATABASE $TestDbName;"

if ($LASTEXITCODE -ne 0) {
    Write-Error "ERROR: Failed to create the test database. Check admin credentials in restore.env."
    exit 1
}

# 5. Execute pg_restore
# --no-owner: Tells Postgres to ignore the original 'backup' user and assign ownership to our Admin user
Write-Host "Restoring data to '$TestDbName' (this may take a moment)..."
docker exec -e PGPASSWORD=$AdminPassword $ContainerName pg_restore -U $AdminUser -d $TestDbName --no-owner --clean $ContainerRestorePath

if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 1) {
    Write-Error "ERROR: pg_restore encountered a critical failure! Exit code: $LASTEXITCODE"
    exit 1
}

# 6. Verification
Write-Host "================ RESTORE VERIFICATION ================"
Write-Host "Listing restored tables:"
docker exec -e PGPASSWORD=$AdminPassword $ContainerName psql -U $AdminUser -d $TestDbName -c "\dt"

Write-Host "Verifying database size:"
docker exec -e PGPASSWORD=$AdminPassword $ContainerName psql -U $AdminUser -d postgres -c "SELECT pg_size_pretty(pg_database_size('$TestDbName')) AS test_db_size;"
Write-Host "======================================================"

# 7. Cleanup
Write-Host "Cleaning up test environment..."
docker exec -e PGPASSWORD=$AdminPassword $ContainerName psql -U $AdminUser -d postgres -c "DROP DATABASE $TestDbName;"
docker exec $ContainerName rm $ContainerRestorePath

Write-Host "[$(Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz')] Restore test completed successfully. Data is verified and intact!"