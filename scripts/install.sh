#!/bin/bash

# FiestaBoard Installation Script
# Gets FiestaBoard running and opens the setup wizard in your browser

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

# Step 2: Prepare configuration
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 2: Preparing configuration..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ -f "$PROJECT_DIR/.env" ]; then
    echo -e "${GREEN}✓ Using existing .env configuration${NC}"
else
    cp "$PROJECT_DIR/env.example" "$PROJECT_DIR/.env"
    echo -e "${GREEN}✓ Created .env file from template${NC}"
fi
echo ""

# Step 3: Start FiestaBoard
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Step 3: Starting FiestaBoard..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

cd "$PROJECT_DIR"

# Use pre-built image from Docker Hub if available (faster), otherwise build from source
COMPOSE_FILE="docker-compose.yml"
COMPOSE_ARGS="up -d --build"
if [ -f "$PROJECT_DIR/docker-compose.hub.yml" ]; then
    COMPOSE_FILE="docker-compose.hub.yml"
    COMPOSE_ARGS="up -d"
fi

echo "Pulling and starting FiestaBoard..."
echo "(This may take a few minutes the first time)"
echo ""

$DOCKER_COMPOSE -f "$COMPOSE_FILE" $COMPOSE_ARGS

# Wait for services to be ready
echo ""
echo "Waiting for services to start..."
sleep 10

# Check if services are running
if $DOCKER_COMPOSE -f "$COMPOSE_FILE" ps | grep -qE "Up|running"; then
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✓ FiestaBoard is running!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Opening the setup wizard in your browser..."
    echo ""

    # Open browser (cross-platform)
    URL="http://localhost:4420"
    if command -v open &> /dev/null; then
        open "$URL"
    elif command -v xdg-open &> /dev/null; then
        xdg-open "$URL"
    else
        echo "Could not open browser automatically."
    fi

    echo "🌐 FiestaBoard is ready at: $URL"
    echo ""
    echo "   The setup wizard will walk you through connecting"
    echo "   your board and choosing your data sources."
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Useful commands:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  Stop:    $DOCKER_COMPOSE -f $COMPOSE_FILE down"
    echo "  Start:   $DOCKER_COMPOSE -f $COMPOSE_FILE up -d"
    echo "  Logs:    $DOCKER_COMPOSE -f $COMPOSE_FILE logs -f"
    echo ""
else
    echo -e "${RED}✗ Something went wrong starting the services${NC}"
    echo ""
    echo "Check the logs with:"
    echo "  $DOCKER_COMPOSE -f $COMPOSE_FILE logs"
    echo ""
    exit 1
fi

