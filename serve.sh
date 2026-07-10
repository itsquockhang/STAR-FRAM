#!/bin/bash

# Exit on error
set -e

# Define color outputs
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Starfarm Local Dev Environment Bootstrapper ===${NC}"

# 1. Start MongoDB and Redis in Docker
echo -e "${YELLOW}1. Starting MongoDB and Redis services in Docker...${NC}"
docker-compose up -d mongodb redis

# 2. Check if Docker services are running
echo -e "${GREEN}2. Verifying database container statuses...${NC}"
docker-compose ps mongodb redis

# 3. Export Environment Variables for local run
echo -e "${YELLOW}3. Configuring environment variables...${NC}"
export MONGO_URI="mongodb://localhost:27017/starfarm"
export REDIS_HOST="localhost"
export REDIS_PORT="6379"
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="adminpassword"

# 4. Start local development server using uv
echo -e "${GREEN}4. Starting FastAPI app via Uvicorn in reload mode at http://127.0.0.1:8000...${NC}"
uv run uvicorn main:app --reload --host 127.0.0.1 --port 8000
