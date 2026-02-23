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
    echo "  Mac:     https://docs.docker.com/desktop/setup/install/mac-install/"
    echo "  Windows: https://docs.docker.com/desktop/setup/install/windows-install/"
    echo "  Linux:   https://docs.docker.com/desktop/setup/install/linux/"
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

# Check for Docker Compose (supports both 'docker compose' plugin and standalone 'docker-compose')
DOCKER_COMPOSE=""
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
else
    echo -e "${RED}✗ Docker Compose is not installed!${NC}"
    echo ""
    echo "Docker Compose usually comes with Docker Desktop."
    echo "Please reinstall Docker Desktop or install Docker Compose separately."
    echo ""
    exit 1
fi

echo -e "${GREEN}✓ Docker Compose is available${NC}"
echo ""

# Step 2: Configure Board Connection
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Configure Board Connection"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Helper: cross-platform sed -i
sed_inplace() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

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
    
    # Board API Mode Selection
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Board API Mode"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "How do you want to connect to your board?"
    echo ""
    echo "  1) Local API (recommended)"
    echo "     - Faster updates, supports transition animations"
    echo "     - Board must be on the same network"
    echo "     - Get the key from the board's mobile app (Settings → Local API)"
    echo ""
    echo "  2) Cloud API"
    echo "     - Works from anywhere with internet"
    echo "     - No transition animation support"
    echo "     - Get the key from https://web.vestaboard.com (Settings → API)"
    echo ""
    echo "  3) Skip for now"
    echo "     - You can configure the board later in the web UI"
    echo ""
    read -p "Enter your choice (1/2/3): " API_MODE_CHOICE
    
    case $API_MODE_CHOICE in
        1)
            # Local API setup
            sed_inplace "s|^BOARD_API_MODE=.*|BOARD_API_MODE=local|" "$PROJECT_DIR/.env"
            echo ""
            echo "To get your Local API key:"
            echo "  1. Open the board's mobile app"
            echo "  2. Go to Settings → Local API"
            echo "  3. Copy the API key and note the board's IP address"
            echo ""
            read -p "Enter your Local API Key: " LOCAL_KEY
            
            if [ -z "$LOCAL_KEY" ]; then
                echo -e "${RED}✗ Local API Key is required for local mode!${NC}"
                exit 1
            fi
            
            sed_inplace "s|^BOARD_LOCAL_API_KEY=.*|BOARD_LOCAL_API_KEY=$LOCAL_KEY|" "$PROJECT_DIR/.env"
            echo -e "${GREEN}✓ Local API Key configured${NC}"
            echo ""
            
            read -p "Enter your board's IP address (e.g., 192.168.0.11): " BOARD_IP
            
            if [ -z "$BOARD_IP" ]; then
                echo -e "${RED}✗ Board IP address is required for local mode!${NC}"
                exit 1
            fi
            
            sed_inplace "s|^BOARD_HOST=.*|BOARD_HOST=$BOARD_IP|" "$PROJECT_DIR/.env"
            echo -e "${GREEN}✓ Board host set to: $BOARD_IP${NC}"
            ;;
        2)
            # Cloud API setup
            sed_inplace "s|^BOARD_API_MODE=.*|BOARD_API_MODE=cloud|" "$PROJECT_DIR/.env"
            echo ""
            echo "To get your Cloud API key:"
            echo "  1. Go to: https://web.vestaboard.com"
            echo "  2. Log in and click on your board"
            echo "  3. Go to Settings → API"
            echo "  4. Enable 'Read/Write API'"
            echo "  5. Copy the API key"
            echo ""
            read -p "Enter your Read/Write API Key: " CLOUD_KEY
            
            if [ -z "$CLOUD_KEY" ]; then
                echo -e "${RED}✗ Cloud API Key is required for cloud mode!${NC}"
                exit 1
            fi
            
            sed_inplace "s|^BOARD_READ_WRITE_KEY=.*|BOARD_READ_WRITE_KEY=$CLOUD_KEY|" "$PROJECT_DIR/.env"
            echo -e "${GREEN}✓ Cloud API Key configured${NC}"
            ;;
        3|"")
            echo -e "${GREEN}✓ Skipping board setup — you can configure it later at http://localhost:4420${NC}"
            ;;
        *)
            echo -e "${YELLOW}⚠ Invalid choice, skipping board setup — you can configure it later in the web UI${NC}"
            ;;
    esac
    echo ""
    
    # Optional: Configure Location
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Location & Timezone (Optional)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    read -p "Enter your location (or press Enter for 'San Francisco, CA'): " LOCATION
    
    if [ ! -z "$LOCATION" ]; then
        sed_inplace "s|^WEATHER_LOCATION=.*|WEATHER_LOCATION=$LOCATION|" "$PROJECT_DIR/.env"
        echo -e "${GREEN}✓ Location set to: $LOCATION${NC}"
    else
        echo -e "${GREEN}✓ Using default location: San Francisco, CA${NC}"
    fi
    
    read -p "Enter your timezone (or press Enter for 'America/Los_Angeles'): " TIMEZONE_INPUT
    
    if [ ! -z "$TIMEZONE_INPUT" ]; then
        sed_inplace "s|^TIMEZONE=.*|TIMEZONE=$TIMEZONE_INPUT|" "$PROJECT_DIR/.env"
        echo -e "${GREEN}✓ Timezone set to: $TIMEZONE_INPUT${NC}"
    else
        echo -e "${GREEN}✓ Using default timezone: America/Los_Angeles${NC}"
    fi
    echo ""
    
    echo -e "${GREEN}✓ Configuration complete!${NC}"
    echo ""
    echo "  Tip: Plugins like Weather, Stocks, and Transit can be enabled and"
    echo "  configured later through the web UI's Integrations page."
    echo "  No additional API keys are needed to start."
    echo ""
fi

# Step 3: Start FiestaBoard
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Starting FiestaBoard..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$PROJECT_DIR"

# Choose between pre-built image (faster) or building from source
COMPOSE_FILE="docker-compose.yml"
if [ -f "$PROJECT_DIR/docker-compose.hub.yml" ]; then
    echo "How would you like to install?"
    echo ""
    echo "  1) Use pre-built image from Docker Hub (faster, recommended)"
    echo "  2) Build from source (slower, for development)"
    echo ""
    read -p "Enter your choice (1/2): " BUILD_CHOICE
    
    case $BUILD_CHOICE in
        2)
            COMPOSE_FILE="docker-compose.yml"
            echo -e "${GREEN}✓ Will build from source${NC}"
            ;;
        *)
            COMPOSE_FILE="docker-compose.hub.yml"
            echo -e "${GREEN}✓ Will use pre-built image from Docker Hub${NC}"
            ;;
    esac
    echo ""
fi

echo "Building and starting Docker containers..."
echo "(This may take a few minutes the first time)"
echo ""

# Start in background
if [ "$COMPOSE_FILE" = "docker-compose.hub.yml" ]; then
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d
else
    $DOCKER_COMPOSE -f "$COMPOSE_FILE" up -d --build
fi

# Wait for services to be ready
echo ""
echo "Waiting for services to start..."
sleep 10

# Check if services are running
if $DOCKER_COMPOSE -f "$COMPOSE_FILE" ps | grep -q "Up\|running"; then
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✓ FiestaBoard is running!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "🌐 Access FiestaBoard at:"
    echo ""
    echo "   Web UI:   http://localhost:4420"
    echo "   API Docs: http://localhost:4420/docs"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Next Steps:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "1. Open http://localhost:4420 in your browser"
    echo "2. Click the '▶ Start Service' button"
    echo "3. Go to the Integrations page to enable plugins"
    echo "   (Weather, Stocks, Transit, and more)"
    echo "4. Watch your board update! 🎉"
    echo ""
    echo "To stop FiestaBoard later, run:"
    echo "  $DOCKER_COMPOSE -f $COMPOSE_FILE down"
    echo ""
    echo "To start it again, run:"
    echo "  $DOCKER_COMPOSE -f $COMPOSE_FILE up -d"
    echo ""
    echo "View logs with:"
    echo "  $DOCKER_COMPOSE -f $COMPOSE_FILE logs -f"
    echo ""
else
    echo -e "${RED}✗ Something went wrong starting the services${NC}"
    echo ""
    echo "Check the logs with:"
    echo "  $DOCKER_COMPOSE -f $COMPOSE_FILE logs"
    echo ""
    exit 1
fi

