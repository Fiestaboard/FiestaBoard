# FiestaBoard Installation Script for Windows
# Gets FiestaBoard running and opens the setup wizard in your browser

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

# Step 2: Prepare configuration
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "Step 2: Preparing configuration..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host ""

$envPath = Join-Path $ProjectDir ".env"

if (Test-Path $envPath) {
    Write-Host "✓ Using existing .env configuration" -ForegroundColor Green
    $existingEnv = $true
} else {
    $envExample = Join-Path $ProjectDir "env.example"
    Copy-Item $envExample $envPath
    Write-Host "✓ Created .env file from template" -ForegroundColor Green
    $existingEnv = $false
}

# ---------------------------------------------------------------------------
# Self-update sidecar (FiestaUpdater) - opt-in for fresh installs.
# ---------------------------------------------------------------------------
if (-not $existingEnv) {
    Write-Host ""
    Write-Host "FiestaBoard 5.0 can update itself in-place when you click"
    Write-Host "`"Update Now`" in Settings.  This runs a tiny companion container"
    Write-Host "(``fiestaupdater``) that pulls the new image and restarts the app."
    Write-Host ""
    $resp = Read-Host "Enable in-app updates? [Y/n]"
    if ([string]::IsNullOrEmpty($resp)) { $resp = "Y" }
    if ($resp -match '^[nN]') {
        Write-Host "  Skipping. You can enable later by setting COMPOSE_PROFILES=fiestaupdater in .env" -ForegroundColor Yellow
    } else {
        # Generate a 64-hex-char token (32 bytes).
        $bytes = New-Object byte[] 32
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        $token = -join ($bytes | ForEach-Object { $_.ToString("x2") })

        $envContent = Get-Content $envPath
        if ($envContent -match "^COMPOSE_PROFILES=") {
            $envContent = $envContent -replace "^COMPOSE_PROFILES=.*", "COMPOSE_PROFILES=fiestaupdater"
        } else {
            $envContent += "COMPOSE_PROFILES=fiestaupdater"
        }
        if ($envContent -match "^FIESTAUPDATER_TOKEN=") {
            $envContent = $envContent -replace "^FIESTAUPDATER_TOKEN=.*", "FIESTAUPDATER_TOKEN=$token"
        } else {
            $envContent += "FIESTAUPDATER_TOKEN=$token"
        }
        Set-Content -Path $envPath -Value $envContent
        Write-Host "✓ In-app updates enabled (sidecar will be started)" -ForegroundColor Green
    }
}
Write-Host ""

# Step 3: Start FiestaBoard
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host "Step 3: Starting FiestaBoard..." -ForegroundColor Yellow
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Yellow
Write-Host ""

Set-Location $ProjectDir

# Use pre-built image from Docker Hub if available (faster), otherwise build from source
$composeFile = "docker-compose.yml"
$composeArgs = @("-f", $composeFile, "up", "-d", "--build")
$hubComposePath = Join-Path $ProjectDir "docker-compose.hub.yml"
if (Test-Path $hubComposePath) {
    $composeFile = "docker-compose.hub.yml"
    $composeArgs = @("-f", $composeFile, "up", "-d")
    Write-Host "Pulling and starting FiestaBoard..."
} else {
    Write-Host "Building and starting FiestaBoard..."
}
Write-Host "(This may take a few minutes the first time)"
Write-Host ""

Invoke-DockerCompose $composeArgs

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
    Write-Host "Opening the setup wizard in your browser..."
    Write-Host ""

    # Open browser
    Start-Process "http://localhost:4420"

    Write-Host "🌐 FiestaBoard is ready at: http://localhost:4420"
    Write-Host ""
    Write-Host "   The setup wizard will walk you through connecting"
    Write-Host "   your board and choosing your data sources."
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "Useful commands:" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Stop:    $DockerCompose -f $composeFile down"
    Write-Host "  Start:   $DockerCompose -f $composeFile up -d"
    Write-Host "  Logs:    $DockerCompose -f $composeFile logs -f"
    Write-Host ""
} else {
    Write-Host "✗ Something went wrong starting the services" -ForegroundColor Red
    Write-Host ""
    Write-Host "Check the logs with:"
    Write-Host "  $DockerCompose -f $composeFile logs"
    Write-Host ""
    exit 1
}

