# Stop on any error
$ErrorActionPreference = "Stop"

Write-Host "Setting up LLM Web Bridge..." -ForegroundColor Green

# Create and activate virtual environment if it doesn't exist
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
. .\venv\Scripts\Activate.ps1

# Install requirements if needed
if (-not (Test-Path "venv\Lib\site-packages\fastapi")) {
    Write-Host "Installing API requirements..." -ForegroundColor Yellow
    pip install -r requirements.txt
    Write-Host "Installing Playwright..." -ForegroundColor Yellow
    playwright install chromium
}

if (-not (Test-Path "venv\Lib\site-packages\rich")) {
    Write-Host "Installing CLI requirements..." -ForegroundColor Yellow
    pip install -r examples/requirements.txt
}

# Check if config files exist, create from examples if they don't
if (-not (Test-Path "config/config.yaml")) {
    Write-Host "Creating config files from examples..." -ForegroundColor Yellow
    Copy-Item "config/config.yaml.example" "config/config.yaml"
    Copy-Item "config/.env.example" "config/.env"
    Write-Host "Please configure your credentials in config/config.yaml and config/.env" -ForegroundColor Red
    Write-Host "Press any key to continue..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

# Start the API server in a new window
Write-Host "Starting API server..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit -Command cd '$PWD'; .\venv\Scripts\Activate.ps1; python src/main.py"

# Wait a bit for the server to start
Start-Sleep -Seconds 3

# Start the CLI chat
Write-Host "Starting CLI chat..." -ForegroundColor Green
python examples/cli_chat.py