# Cledger Unified Test Runner
# Usage:
#   .\tests\run_tests.ps1             -> Runs Unit, Integration, and Failure tests
#   .\tests\run_tests.ps1 -Full        -> Runs everything INCLUDING Performance
#   .\tests\run_tests.ps1 -Performance -> Runs ONLY Performance tests

param (
    [switch]$Full,
    [switch]$Performance
)

Write-Host "--- Starting Cledger Test Suite ---" -ForegroundColor Cyan

if ($Full) {
    Write-Host "Mode: Full Suite (All layers)" -ForegroundColor Yellow
    pytest -v
} elseif ($Performance) {
    Write-Host "Mode: Performance & Stress Only" -ForegroundColor Red
    pytest -m performance -v
} else {
    Write-Host "Mode: Standard (Excluding Performance)" -ForegroundColor Green
    pytest -m "not performance" -v
}

Write-Host "--- Execution Complete ---" -ForegroundColor Cyan
