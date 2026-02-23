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
    Write-Host "  https://docs.docker.com/desktop/setup/install/windows-install/"
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

# Check for Docker Compose (supports both 'docker compose' plugin and standalone 'docker-compose')
$DockerCompose = ""
try {
    $null = docker compose version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $DockerCompose = "docker compose"
    } else {
        throw "not available"
    }
} catch {
    try {
        $null = docker-compose --version
        $DockerCompose = "docker-compose"
    } catch {
        Write-Host "✗ Docker Compose is not installed!" -ForegroundColor Red
        Write-Host ""
        Write-Host "Docker Compose usually comes with Docker Desktop."
        Write-Host "Please reinstall Docker Desktop."
        Write-Host ""
        exit 1
    }
}

Write-Host "✓ Docker Compose is available" -ForegroundColor Green
Write-Host ""

# Helper function to run docker compose commands
function Invoke-DockerCompose {
    param([string[]]$Args)
    if ($DockerCompose -eq "docker compose") {
        & docker compose @Args
    } else {
        & docker-compose @Args
    }
}

# Step 2: Configure Board Connection
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "Step 2: Configure Board Connection" -ForegroundColor Yellow
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
    
    # Board API Mode Selection
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Board API Mode" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "How do you want to connect to your board?"
    Write-Host ""
    Write-Host "  1) Local API (recommended)"
    Write-Host "     - Faster updates, supports transition animations"
    Write-Host "     - Board must be on the same network"
    Write-Host "     - Get the key from the board's mobile app (Settings -> Local API)"
    Write-Host ""
    Write-Host "  2) Cloud API"
    Write-Host "     - Works from anywhere with internet"
    Write-Host "     - No transition animation support"
    Write-Host "     - Get the key from https://web.vestaboard.com (Settings -> API)"
    Write-Host ""
    Write-Host "  3) Skip for now"
    Write-Host "     - You can configure the board later in the web UI"
    Write-Host ""
    $apiModeChoice = Read-Host "Enter your choice (1/2/3)"
    
    switch ($apiModeChoice) {
        "1" {
            # Local API setup
            $envContent = Get-Content $envPath
            $envContent = $envContent -replace "^BOARD_API_MODE=.*", "BOARD_API_MODE=local"
            Set-Content $envPath $envContent
            Write-Host ""
            Write-Host "To get your Local API key:"
            Write-Host "  1. Open the board's mobile app"
            Write-Host "  2. Go to Settings -> Local API"
            Write-Host "  3. Copy the API key and note the board's IP address"
            Write-Host ""
            $localKey = Read-Host "Enter your Local API Key"
            
            if ([string]::IsNullOrWhiteSpace($localKey)) {
                Write-Host "✗ Local API Key is required for local mode!" -ForegroundColor Red
                exit 1
            }
            
            $envContent = Get-Content $envPath
            $envContent = $envContent -replace "^BOARD_LOCAL_API_KEY=.*", "BOARD_LOCAL_API_KEY=$localKey"
            Set-Content $envPath $envContent
            Write-Host "✓ Local API Key configured" -ForegroundColor Green
            Write-Host ""
            
            $boardIP = Read-Host "Enter your board's IP address (e.g., 192.168.0.11)"
            
            if ([string]::IsNullOrWhiteSpace($boardIP)) {
                Write-Host "✗ Board IP address is required for local mode!" -ForegroundColor Red
                exit 1
            }
            
            $envContent = Get-Content $envPath
            $envContent = $envContent -replace "^BOARD_HOST=.*", "BOARD_HOST=$boardIP"
            Set-Content $envPath $envContent
            Write-Host "✓ Board host set to: $boardIP" -ForegroundColor Green
        }
        "2" {
            # Cloud API setup
            $envContent = Get-Content $envPath
            $envContent = $envContent -replace "^BOARD_API_MODE=.*", "BOARD_API_MODE=cloud"
            Set-Content $envPath $envContent
            Write-Host ""
            Write-Host "To get your Cloud API key:"
            Write-Host "  1. Go to: https://web.vestaboard.com"
            Write-Host "  2. Log in and click on your board"
            Write-Host "  3. Go to Settings -> API"
            Write-Host "  4. Enable 'Read/Write API'"
            Write-Host "  5. Copy the API key"
            Write-Host ""
            $cloudKey = Read-Host "Enter your Read/Write API Key"
            
            if ([string]::IsNullOrWhiteSpace($cloudKey)) {
                Write-Host "✗ Cloud API Key is required for cloud mode!" -ForegroundColor Red
                exit 1
            }
            
            $envContent = Get-Content $envPath
            $envContent = $envContent -replace "^BOARD_READ_WRITE_KEY=.*", "BOARD_READ_WRITE_KEY=$cloudKey"
            Set-Content $envPath $envContent
            Write-Host "✓ Cloud API Key configured" -ForegroundColor Green
        }
        "3" {
            Write-Host "✓ Skipping board setup - you can configure it later at http://localhost:4420" -ForegroundColor Green
        }
        default {
            Write-Host "⚠ Invalid choice, skipping board setup - you can configure it later in the web UI" -ForegroundColor Yellow
        }
    }
    Write-Host ""
    
    # Optional: Configure Location & Timezone
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Location & Timezone (Optional)" -ForegroundColor Cyan
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
    
    $timezoneInput = Read-Host "Enter your timezone (or press Enter for 'America/Los_Angeles')"
    
    if (-not [string]::IsNullOrWhiteSpace($timezoneInput)) {
        $envContent = Get-Content $envPath
        $envContent = $envContent -replace "^TIMEZONE=.*", "TIMEZONE=$timezoneInput"
        Set-Content $envPath $envContent
        Write-Host "✓ Timezone set to: $timezoneInput" -ForegroundColor Green
    } else {
        Write-Host "✓ Using default timezone: America/Los_Angeles" -ForegroundColor Green
    }
    Write-Host ""
    
    Write-Host "✓ Configuration complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Tip: Plugins like Weather, Stocks, and Transit can be enabled and"
    Write-Host "  configured later through the web UI's Integrations page."
    Write-Host "  No additional API keys are needed to start."
    Write-Host ""
}

# Step 3: Start FiestaBoard
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "Step 3: Starting FiestaBoard..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host ""

Set-Location $ProjectDir

# Choose between pre-built image (faster) or building from source
$composeFile = "docker-compose.yml"
$hubComposePath = Join-Path $ProjectDir "docker-compose.hub.yml"
if (Test-Path $hubComposePath) {
    Write-Host "How would you like to install?"
    Write-Host ""
    Write-Host "  1) Use pre-built image from Docker Hub (faster, recommended)"
    Write-Host "  2) Build from source (slower, for development)"
    Write-Host ""
    $buildChoice = Read-Host "Enter your choice (1/2)"
    
    switch ($buildChoice) {
        "2" {
            $composeFile = "docker-compose.yml"
            Write-Host "✓ Will build from source" -ForegroundColor Green
        }
        default {
            $composeFile = "docker-compose.hub.yml"
            Write-Host "✓ Will use pre-built image from Docker Hub" -ForegroundColor Green
        }
    }
    Write-Host ""
}

Write-Host "Building and starting Docker containers..."
Write-Host "(This may take a few minutes the first time)"
Write-Host ""

# Start in background
if ($composeFile -eq "docker-compose.hub.yml") {
    Invoke-DockerCompose @("-f", $composeFile, "up", "-d")
} else {
    Invoke-DockerCompose @("-f", $composeFile, "up", "-d", "--build")
}

# Wait for services to be ready
Write-Host ""
Write-Host "Waiting for services to start..."
Start-Sleep -Seconds 10

# Check if services are running
$services = Invoke-DockerCompose @("-f", $composeFile, "ps") 2>&1 | Out-String
if ($services -match "Up|running") {
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
    Write-Host "✓ FiestaBoard is running!" -ForegroundColor Green
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
    Write-Host ""
    Write-Host "🌐 Access FiestaBoard at:"
    Write-Host ""
    Write-Host "   Web UI:   http://localhost:4420"
    Write-Host "   API Docs: http://localhost:4420/docs"
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Next Steps:" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. Open http://localhost:4420 in your browser"
    Write-Host "2. Click the '▶ Start Service' button"
    Write-Host "3. Go to the Integrations page to enable plugins"
    Write-Host "   (Weather, Stocks, Transit, and more)"
    Write-Host "4. Watch your board update! 🎉"
    Write-Host ""
    Write-Host "To stop FiestaBoard later, run:"
    Write-Host "  $DockerCompose -f $composeFile down"
    Write-Host ""
    Write-Host "To start it again, run:"
    Write-Host "  $DockerCompose -f $composeFile up -d"
    Write-Host ""
    Write-Host "View logs with:"
    Write-Host "  $DockerCompose -f $composeFile logs -f"
    Write-Host ""
} else {
    Write-Host "✗ Something went wrong starting the services" -ForegroundColor Red
    Write-Host ""
    Write-Host "Check the logs with:"
    Write-Host "  $DockerCompose -f $composeFile logs"
    Write-Host ""
    exit 1
}

