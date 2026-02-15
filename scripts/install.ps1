# FiestaBoard Installation Script for Windows
# Run this script in PowerShell to set up FiestaBoard

Write-Host "╔═══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                           ║" -ForegroundColor Cyan
Write-Host "║   Welcome to FiestaBoard Setup! 🎉       ║" -ForegroundColor Cyan
Write-Host "║                                           ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Get the project directory
$ProjectDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectDir) {
    $ProjectDir = Split-Path -Parent $PSCommandPath
    $ProjectDir = Split-Path -Parent $ProjectDir
}

Write-Host "Installation directory: $ProjectDir"
Write-Host ""

# Step 1: Check Prerequisites
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "Step 1: Checking prerequisites..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host ""

# Check for Docker
try {
    $null = docker --version
    Write-Host "✓ Docker is installed" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker is not installed!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Docker Desktop first:"
    Write-Host "  https://www.docker.com/products/docker-desktop/"
    Write-Host ""
    exit 1
}

# Check if Docker is running
try {
    $null = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Docker not running"
    }
    Write-Host "✓ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker is installed but not running!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please start Docker Desktop and try again."
    Write-Host ""
    exit 1
}

# Check for Docker Compose
# Try docker-compose (v1) first, then docker compose (v2 plugin)
$ComposeCmd = $null
try {
    $null = docker-compose --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $ComposeCmd = "docker-compose"
    }
} catch {}

if (-not $ComposeCmd) {
    try {
        $null = docker compose version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $ComposeCmd = "docker compose"
        }
    } catch {}
}

if (-not $ComposeCmd) {
    Write-Host "✗ Docker Compose is not installed!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Docker Compose usually comes with Docker Desktop."
    Write-Host "Please reinstall Docker Desktop."
    Write-Host ""
    exit 1
}

Write-Host "✓ Docker Compose is installed" -ForegroundColor Green

Write-Host ""

# Step 2: Configure API Keys
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "Step 2: Configure API Keys" -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host ""

$envPath = Join-Path $ProjectDir ".env"
$skipConfig = $false

# Check if .env already exists
if (Test-Path $envPath) {
    Write-Host "⚠ A .env file already exists" -ForegroundColor Yellow
    Write-Host ""
    $keepConfig = Read-Host "Do you want to keep your existing configuration? (y/n)"
    if ($keepConfig -eq "y" -or $keepConfig -eq "Y") {
        Write-Host "✓ Keeping existing configuration" -ForegroundColor Green
        $skipConfig = $true
    } else {
        Write-Host ""
        Write-Host "Creating a backup of your existing .env file..."
        $backupName = ".env.backup.$(Get-Date -Format 'yyyyMMddHHmmss')"
        Copy-Item $envPath (Join-Path $ProjectDir $backupName)
        Write-Host "✓ Backup created" -ForegroundColor Green
        $skipConfig = $false
    }
}

if (-not $skipConfig) {
    # Copy env.example to .env
    $envExample = Join-Path $ProjectDir "env.example"
    Copy-Item $envExample $envPath
    Write-Host "✓ Created .env file from template" -ForegroundColor Green
    Write-Host ""
    
    # Get Board API Key
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Board API Key Setup" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To get your Board API Key:"
    Write-Host "  1. Go to: https://web.vestaboard.com"
    Write-Host "  2. Log in and click on your board"
    Write-Host "  3. Go to Settings > API"
    Write-Host "  4. Enable 'Read/Write API'"
    Write-Host "  5. Copy the API key"
    Write-Host ""
    $boardKey = Read-Host "Enter your Board API Key"
    
    if ([string]::IsNullOrWhiteSpace($boardKey)) {
        Write-Host "✗ Board API Key is required!" -ForegroundColor Red
        exit 1
    }
    
    # Update .env with Board API Key
    $envContent = Get-Content $envPath
    $envContent = $envContent -replace "^BOARD_READ_WRITE_KEY=.*", "BOARD_READ_WRITE_KEY=$boardKey"
    Set-Content $envPath $envContent
    
    Write-Host "✓ Board API Key configured" -ForegroundColor Green
    Write-Host ""
    
    # Get Weather API Key
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Weather API Key Setup" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To get a Weather API Key (free):"
    Write-Host "  1. Go to: https://www.weatherapi.com/"
    Write-Host "  2. Click 'Sign Up' (no credit card required)"
    Write-Host "  3. After signing in, copy your API key from the dashboard"
    Write-Host ""
    $weatherKey = Read-Host "Enter your Weather API Key"
    
    if ([string]::IsNullOrWhiteSpace($weatherKey)) {
        Write-Host "✗ Weather API Key is required!" -ForegroundColor Red
        exit 1
    }
    
    # Update .env with Weather API Key
    $envContent = Get-Content $envPath
    $envContent = $envContent -replace "^WEATHER_API_KEY=.*", "WEATHER_API_KEY=$weatherKey"
    Set-Content $envPath $envContent
    
    Write-Host "✓ Weather API Key configured" -ForegroundColor Green
    Write-Host ""
    
    # Optional: Configure Location
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Location Setup (Optional)" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    $location = Read-Host "Enter your location (or press Enter for 'San Francisco, CA')"
    
    if (-not [string]::IsNullOrWhiteSpace($location)) {
        $envContent = Get-Content $envPath
        $envContent = $envContent -replace "^WEATHER_LOCATION=.*", "WEATHER_LOCATION=$location"
        Set-Content $envPath $envContent
        Write-Host "✓ Location set to: $location" -ForegroundColor Green
    } else {
        Write-Host "✓ Using default location: San Francisco, CA" -ForegroundColor Green
    }
    Write-Host ""
}

# Step 3: Create config.json and data directory
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "Step 3: Setting up project files..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host ""

# Create config.json if it doesn't exist
$configPath = Join-Path $ProjectDir "config.json"
$configExample = Join-Path $ProjectDir "config.example.json"
if (-not (Test-Path $configPath)) {
    Copy-Item $configExample $configPath
    Write-Host "✓ Created config.json from template" -ForegroundColor Green
} else {
    Write-Host "✓ config.json already exists" -ForegroundColor Green
}

# Create data directory if it doesn't exist
$dataDir = Join-Path $ProjectDir "data"
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    Write-Host "✓ Created data directory" -ForegroundColor Green
} else {
    Write-Host "✓ data directory already exists" -ForegroundColor Green
}

Write-Host ""

# Step 4: Start FiestaBoard
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "Step 4: Starting FiestaBoard..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host ""

Set-Location $ProjectDir

# Helper function to run compose commands
function Invoke-Compose {
    param([string[]]$Args)
    if ($ComposeCmd -eq "docker-compose") {
        & docker-compose @Args
    } else {
        & docker compose @Args
    }
}

Write-Host "Building and starting Docker containers..."
Write-Host "(This may take a few minutes the first time)"
Write-Host ""

# Start in background
Invoke-Compose @("up", "-d", "--build")

# Wait for services to be ready
Write-Host ""
Write-Host "Waiting for services to start..."

# Poll for healthy containers (up to 60 seconds)
$maxWait = 60
$waited = 0
$healthy = $false
while ($waited -lt $maxWait) {
    $services = Invoke-Compose @("ps") 2>&1 | Out-String
    if ($services -imatch "Up|running") {
        $healthy = $true
        break
    }
    Start-Sleep -Seconds 5
    $waited += 5
    Write-Host "  Still starting... (${waited}s)"
}

# Check if services are running
if ($healthy) {
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
    Write-Host "✓ FiestaBoard is running!" -ForegroundColor Green
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
    Write-Host ""
    Write-Host "🌐 Access FiestaBoard at:"
    Write-Host ""
    Write-Host "   Web UI:   http://localhost:8080"
    Write-Host "   API:      http://localhost:8000"
    Write-Host "   API Docs: http://localhost:8000/docs"
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Next Steps:" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. Open http://localhost:8080 in your browser"
    Write-Host "2. Click the '▶ Start Service' button"
    Write-Host "3. Watch your board update! 🎉"
    Write-Host ""
    Write-Host "To stop FiestaBoard later, run:"
    Write-Host "  $ComposeCmd down"
    Write-Host ""
    Write-Host "To start it again, run:"
    Write-Host "  $ComposeCmd up -d"
    Write-Host ""
    Write-Host "View logs with:"
    Write-Host "  $ComposeCmd logs -f"
    Write-Host ""
} else {
    Write-Host "✗ Something went wrong starting the services" -ForegroundColor Red
    Write-Host ""
    Write-Host "Check the logs with:"
    Write-Host "  $ComposeCmd logs"
    Write-Host ""
    exit 1
}

