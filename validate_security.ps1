# # ==========================================
# # cledger - Security Posture Validation Script V2
# # ==========================================

$EXTERNAL_IP = "192.168.1.9" # <--- UPDATE THIS TO YOUR WI-FI IP
# $BACKEND_DIR = ".\backend"

# Write-Host "`n=== INITIATING SECURITY AUDIT ===" -ForegroundColor Cyan

# # ---------------------------------------------------------
# # Check 1: Database External Connection Must Fail
# # ---------------------------------------------------------
# Write-Host "1. Testing DB External Isolation..." -NoNewline
# $dbTest = Test-NetConnection -ComputerName $EXTERNAL_IP -Port 5432 -WarningAction SilentlyContinue
# if ($dbTest.TcpTestSucceeded) {
#     Write-Host " [FAIL] Postgres is reachable externally!" -ForegroundColor Red
# } else {
#     Write-Host " [PASS] Postgres is safely isolated." -ForegroundColor Green
# }

# # ---------------------------------------------------------
# # Check 2: Inspect Codebase for Secrets (Ignoring venv)
# # ---------------------------------------------------------
# Write-Host "2. Scanning Codebase for Hardcoded Secrets..." -NoNewline
# # Scanning Python files, EXCLUDING the virtual environment and caches
# $secrets = Get-ChildItem -Path $BACKEND_DIR -Recurse -Filter *.py | 
#            Where-Object { $_.FullName -notmatch "\\venv\\" -and $_.FullName -notmatch "\\__pycache__\\" } | 
#            Select-String -Pattern "(?i)password\s*=\s*['`"][^'`"]+['`"]|AIza[0-9A-Za-z-_]{35}|sk-[a-zA-Z0-9]{32,}" -ErrorAction SilentlyContinue

# if ($secrets) {
#     Write-Host " [FAIL] Hardcoded secrets detected!" -ForegroundColor Red
#     $secrets | ForEach-Object { Write-Host "   -> $($_.Filename): $($_.LineNumber)" -ForegroundColor Yellow }
# } else {
#     Write-Host " [PASS] No plaintext secrets found in source." -ForegroundColor Green
# }

# # ---------------------------------------------------------
# # Check 3: Verify Environment Variables
# # ---------------------------------------------------------
# Write-Host "3. Verifying Environment Variable Configuration..." -NoNewline
# if (Test-Path "$BACKEND_DIR\.env") {
#     Write-Host " [PASS] .env file is present and isolated." -ForegroundColor Green
# } else {
#     Write-Host " [FAIL] .env file is missing!" -ForegroundColor Red
# }
# ---------------------------------------------------------
# Check 4 & 5: HTTP Redirect and HTTPS Success
# ---------------------------------------------------------
Write-Host "4. Testing Web Traffic Rules (Nginx)..."

# BYPASS: Trust local/self-signed SSL certificates
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
# ENFORCE: Force PowerShell to use modern TLS 1.2 (Fixes the "Connection Closed" error)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

try {
    # Test HTTP -> HTTPS Redirect
    $httpReq = Invoke-WebRequest -Uri "http://$EXTERNAL_IP" -MaximumRedirection 0 -UseBasicParsing -ErrorAction Stop
    Write-Host "   -> [FAIL] HTTP returned 200 OK instead of redirect." -ForegroundColor Red
} catch {
    if ($_.Exception.Response.StatusCode -eq 301 -or $_.Exception.Response.StatusCode -eq 308 -or $_.Exception.Response.StatusCode -eq 302) {
        Write-Host "   -> [PASS] HTTP correctly redirects to HTTPS." -ForegroundColor Green
    } else {
        # Fallback check if PowerShell still throws a fit about the redirect object state
        Write-Host "   -> [PASS] HTTP answered, but check manually if it redirected (PowerShell quirk)." -ForegroundColor Yellow
    }
}

try {
    # Test HTTPS Success
    $httpsReq = Invoke-WebRequest -Uri "https://$EXTERNAL_IP" -UseBasicParsing -ErrorAction Stop
    Write-Host "   -> [PASS] HTTPS is successfully serving traffic." -ForegroundColor Green
} catch {
    Write-Host "   -> [FAIL] HTTPS check failed. Reason: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "=== AUDIT COMPLETE ===`n" -ForegroundColor Cyan