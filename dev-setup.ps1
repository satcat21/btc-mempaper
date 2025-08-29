# Mempaper Development Environment Setup Script for Windows
# This script sets up and starts the development environment

param(
    [switch]$Mock,
    [switch]$Help,
    [string]$Config = "config.dev.json",
    [int]$Port = 5000
)

if ($Help) {
    Write-Host "🚀 Mempaper Development Setup" -ForegroundColor Cyan
    Write-Host "=" * 50
    Write-Host "Usage: .\dev-setup.ps1 [OPTIONS]" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Green
    Write-Host "  -Mock        Use mock mempool data (offline development)"
    Write-Host "  -Config      Configuration file (default: config.dev.json)"
    Write-Host "  -Port        Server port (default: 5000)"
    Write-Host "  -Help        Show this help message"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Green
    Write-Host "  .\dev-setup.ps1              # Normal development"
    Write-Host "  .\dev-setup.ps1 -Mock        # Offline development"
    Write-Host "  .\dev-setup.ps1 -Port 8080   # Custom port"
    exit 0
}

Write-Host "🚀 Setting up Mempaper Development Environment" -ForegroundColor Cyan
Write-Host "=" * 60

# Check if virtual environment exists
if (Test-Path ".venv") {
    Write-Host "✅ Virtual environment found" -ForegroundColor Green
} else {
    Write-Host "⚠️  Virtual environment not found. Creating..." -ForegroundColor Yellow
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Virtual environment created" -ForegroundColor Green
}

# Activate virtual environment
Write-Host "🔄 Activating virtual environment..." -ForegroundColor Blue
& ".venv\Scripts\Activate.ps1"

# Install/upgrade requirements
Write-Host "📦 Installing Python dependencies..." -ForegroundColor Blue
pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to install dependencies" -ForegroundColor Red
    exit 1
}

# Check configuration
$configFile = $Config
if (-not (Test-Path $configFile)) {
    $configFile = "config.json"
    Write-Host "⚠️  $Config not found, using $configFile" -ForegroundColor Yellow
}

Write-Host "📂 Configuration: $configFile" -ForegroundColor Blue

# Display startup information
Write-Host ""
Write-Host "🎯 Development Server Configuration:" -ForegroundColor Green
Write-Host "   • Port: $Port" -ForegroundColor White
Write-Host "   • Host: 127.0.0.1" -ForegroundColor White
Write-Host "   • Config: $configFile" -ForegroundColor White

if ($Mock) {
    Write-Host "   • Mode: Offline (Mock Data)" -ForegroundColor Yellow
} else {
    Write-Host "   • Mode: Online (Real Data)" -ForegroundColor White
}

Write-Host ""
Write-Host "🌐 Access your application at: http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "🔧 Press Ctrl+C to stop the server" -ForegroundColor Blue
Write-Host ""

# Start the development server
try {
    if ($Mock) {
        python dev_enhanced.py --mock --config $configFile --port $Port
    } else {
        python dev_enhanced.py --config $configFile --port $Port
    }
} catch {
    Write-Host "❌ Failed to start development server" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    Write-Host ""
    Write-Host "👋 Development session ended" -ForegroundColor Blue
}
