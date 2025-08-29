#!/usr/bin/env pwsh
# Script to reset wallet address cache and force rescan

Write-Host "🔄 Resetting wallet address cache..." -ForegroundColor Yellow

# Stop the service (if running locally, skip this)
# Stop-Service -Name "mempaper" -ErrorAction SilentlyContinue

# Delete cache files
$cacheFiles = @(
    "async_wallet_address_cache.json",
    "async_wallet_address_cache.secure.json", 
    "cache_metadata.json",
    "wallet_address_cache.secure.json"
)

foreach ($file in $cacheFiles) {
    if (Test-Path $file) {
        Remove-Item $file -Force
        Write-Host "✅ Deleted: $file" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Not found: $file" -ForegroundColor Yellow
    }
}

# Clear any temporary files
if (Test-Path "current.png") { Remove-Item "current.png" -Force; Write-Host "✅ Deleted: current.png" }
if (Test-Path "current_eink.png") { Remove-Item "current_eink.png" -Force; Write-Host "✅ Deleted: current_eink.png" }

Write-Host ""
Write-Host "🎯 Cache reset complete! Next steps:" -ForegroundColor Cyan
Write-Host "1. Restart the mempaper service" -ForegroundColor White
Write-Host "2. The system will perform a fresh scan with proper gap limit detection" -ForegroundColor White
Write-Host "3. Bootstrap search will check up to 200 addresses initially" -ForegroundColor White
Write-Host "4. Gap limit will continue until 20 consecutive empty addresses" -ForegroundColor White
