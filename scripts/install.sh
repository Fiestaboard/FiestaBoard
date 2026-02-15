#!/bin/bash

# FiestaBoard Installation Script
# This script helps you set up FiestaBoard quickly and easily

set -e

echo "╔═══════════════════════════════════════════╗"
echo "║                                           ║"
echo "║   Welcome to FiestaBoard Setup! 🎉       ║"
echo "║                                           ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "Installation directory: $PROJECT_DIR"
echo ""

# Step 1: Check Prerequisites
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 1: Checking prerequisites..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker is not installed!${NC}"
    echo ""
    echo "Please install Docker Desktop first:"
    echo "  Mac:     https://www.docker.com/products/docker-desktop/"
    echo "  Windows: https://www.docker.com/products/docker-desktop/"
    echo "  Linux:   https://docs.docker.com/desktop/install/linux-install/"
    echo ""
    exit 1
fi

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo -e "${RED}✗ Docker is installed but not running!${NC}"
    echo ""
    echo "Please start Docker Desktop and try again."
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ Docker is installed and running${NC}"

# Check for Docker Compose
# Try docker-compose (v1) first, then docker compose (v2 plugin)
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    echo -e "${RED}✗ Docker Compose is not installed!${NC}"
    echo ""
    echo "Docker Compose usually comes with Docker Desktop."
    echo "Please reinstall Docker Desktop or install Docker Compose separately."
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ Docker Compose is installed${NC}"
echo ""

# Step 2: Configure API Keys
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Configure API Keys"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if .env already exists
if [ -f "$PROJECT_DIR/.env" ]; then
    echo -e "${YELLOW}⚠ A .env file already exists${NC}"
    echo ""
    read -p "Do you want to keep your existing configuration? (y/n): " keep_config
    if [[ $keep_config =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}✓ Keeping existing configuration${NC}"
        SKIP_CONFIG=true
    else
        echo ""
        echo "Creating a backup of your existing .env file..."
        cp "$PROJECT_DIR/.env" "$PROJECT_DIR/.env.backup.$(date +%Y%m%d%H%M%S)"
        echo -e "${GREEN}✓ Backup created${NC}"
        SKIP_CONFIG=false
    fi
else
    SKIP_CONFIG=false
fi

if [ "$SKIP_CONFIG" = false ]; then
    # Copy env.example to .env
    cp "$PROJECT_DIR/env.example" "$PROJECT_DIR/.env"
    echo -e "${GREEN}✓ Created .env file from template${NC}"
    echo ""
    
    # Get Board API Key
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Board API Key Setup"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "To get your Board API Key:"
    echo "  1. Go to: https://web.vestaboard.com"
    echo "  2. Log in and click on your board"
    echo "  3. Go to Settings > API"
    echo "  4. Enable 'Read/Write API'"
    echo "  5. Copy the API key"
    echo ""
    read -p "Enter your Board API Key: " BOARD_KEY
    
    if [ -z "$BOARD_KEY" ]; then
        echo -e "${RED}✗ Board API Key is required!${NC}"
        exit 1
    fi
    
    # Update .env with Board API Key
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s|^BOARD_READ_WRITE_KEY=.*|BOARD_READ_WRITE_KEY=$BOARD_KEY|" "$PROJECT_DIR/.env"
    else
        # Linux
        sed -i "s|^BOARD_READ_WRITE_KEY=.*|BOARD_READ_WRITE_KEY=$BOARD_KEY|" "$PROJECT_DIR/.env"
    fi
    
    echo -e "${GREEN}✓ Board API Key configured${NC}"
    echo ""
    
    # Get Weather API Key
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Weather API Key Setup"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "To get a Weather API Key (free):"
    echo "  1. Go to: https://www.weatherapi.com/"
    echo "  2. Click 'Sign Up' (no credit card required)"
    echo "  3. After signing in, copy your API key from the dashboard"
    echo ""
    read -p "Enter your Weather API Key: " WEATHER_KEY
    
    if [ -z "$WEATHER_KEY" ]; then
        echo -e "${RED}✗ Weather API Key is required!${NC}"
        exit 1
    fi
    
    # Update .env with Weather API Key
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|^WEATHER_API_KEY=.*|WEATHER_API_KEY=$WEATHER_KEY|" "$PROJECT_DIR/.env"
    else
        sed -i "s|^WEATHER_API_KEY=.*|WEATHER_API_KEY=$WEATHER_KEY|" "$PROJECT_DIR/.env"
    fi
    
    echo -e "${GREEN}✓ Weather API Key configured${NC}"
    echo ""
    
    # Optional: Configure Location
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Location Setup (Optional)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    read -p "Enter your location (or press Enter for 'San Francisco, CA'): " LOCATION
    
    if [ ! -z "$LOCATION" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^WEATHER_LOCATION=.*|WEATHER_LOCATION=$LOCATION|" "$PROJECT_DIR/.env"
        else
            sed -i "s|^WEATHER_LOCATION=.*|WEATHER_LOCATION=$LOCATION|" "$PROJECT_DIR/.env"
        fi
        echo -e "${GREEN}✓ Location set to: $LOCATION${NC}"
    else
        echo -e "${GREEN}✓ Using default location: San Francisco, CA${NC}"
    fi
    echo ""
fi

# Step 3: Create config.json and data directory
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Setting up project files..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Create config.json if it doesn't exist
if [ ! -f "$PROJECT_DIR/config.json" ]; then
    cp "$PROJECT_DIR/config.example.json" "$PROJECT_DIR/config.json"
    echo -e "${GREEN}✓ Created config.json from template${NC}"
else
    echo -e "${GREEN}✓ config.json already exists${NC}"
fi

# Create data directory if it doesn't exist
if [ ! -d "$PROJECT_DIR/data" ]; then
    mkdir -p "$PROJECT_DIR/data"
    echo -e "${GREEN}✓ Created data directory${NC}"
else
    echo -e "${GREEN}✓ data directory already exists${NC}"
fi
echo ""

# Step 4: Start FiestaBoard
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 4: Starting FiestaBoard..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$PROJECT_DIR"

echo "Building and starting Docker containers..."
echo "(This may take a few minutes the first time)"
echo ""

# Start in background
$COMPOSE_CMD up -d --build

# Wait for services to be ready
echo ""
echo "Waiting for services to start..."

# Poll for healthy containers (up to 60 seconds)
MAX_WAIT=60
WAITED=0
HEALTHY=false
while [ $WAITED -lt $MAX_WAIT ]; do
    # Check for "Up" (v1) or "running" (v2) in container status
    if $COMPOSE_CMD ps 2>/dev/null | grep -qiE "(Up|running)"; then
        HEALTHY=true
        break
    fi
    sleep 5
    WAITED=$((WAITED + 5))
    echo "  Still starting... (${WAITED}s)"
done

# Check if services are running
if [ "$HEALTHY" = true ]; then
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✓ FiestaBoard is running!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "🌐 Access FiestaBoard at:"
    echo ""
    echo "   Web UI:   http://localhost:8080"
    echo "   API:      http://localhost:8000"
    echo "   API Docs: http://localhost:8000/docs"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Next Steps:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "1. Open http://localhost:8080 in your browser"
    echo "2. Click the '▶ Start Service' button"
    echo "3. Watch your board update! 🎉"
    echo ""
    echo "To stop FiestaBoard later, run:"
    echo "  $COMPOSE_CMD down"
    echo ""
    echo "To start it again, run:"
    echo "  $COMPOSE_CMD up -d"
    echo ""
    echo "View logs with:"
    echo "  $COMPOSE_CMD logs -f"
    echo ""
else
    echo -e "${RED}✗ Something went wrong starting the services${NC}"
    echo ""
    echo "Check the logs with:"
    echo "  $COMPOSE_CMD logs"
    echo ""
    exit 1
fi

