#!/bin/bash
set -e

echo "==> Installing Python dependencies..."
pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt
pip install --no-cache-dir supervisor

echo "==> Configuring nginx..."
cp nginx.conf /etc/nginx/nginx.conf

echo "==> Installing web dependencies..."
cd web && npm install --legacy-peer-deps --no-audit && cd ..

echo "==> Creating data directory..."
mkdir -p data/logs

# Create .env from example if it doesn't exist
if [ ! -f .env ]; then
    cp env.example .env
    echo "==> Created .env from env.example — update it with your API keys"
fi

echo "==> Dev container ready!"
