#!/bin/bash

# Exit on error
set -e

# Define color outputs
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Starfarm Docker Bootstrapper ===${NC}"

# 1. Stop any existing running containers from this compose
echo -e "${YELLOW}1. Cleaning up any existing containers...${NC}"
docker compose down

# 2. Build and start all services in detached mode
echo -e "${YELLOW}2. Building and starting MongoDB, Redis, Qdrant, and App in Docker...${NC}"
docker compose up --build -d

# 3. Check status
echo -e "${GREEN}3. Verifying container statuses...${NC}"
docker compose ps

echo -e "\n${GREEN}App has been started in the background!${NC}"
echo -e "Access the web app at: http://127.0.0.1:8000"
echo -e "To view logs, run: ${YELLOW}docker compose logs -f app${NC}"
echo -e "${BLUE}=== Success ===${NC}\n"
