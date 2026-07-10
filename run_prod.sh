#!/bin/bash

# Exit on error
set -e

# Define color outputs
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Starfarm Production Environment Bootstrapper ===${NC}"

# Check if ffmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${RED}Error: ffmpeg is not installed. Please install it to run the transcription service.${NC}"
    exit 1
fi

# 1. Start MongoDB, Redis, and Qdrant in Docker
echo -e "${YELLOW}1. Starting MongoDB, Redis, and Qdrant services in Docker...${NC}"
docker compose up -d mongodb redis qdrant

# 2. Check if Docker services are running
echo -e "${GREEN}2. Verifying database container statuses...${NC}"
docker compose ps mongodb redis qdrant

# 3. Export Environment Variables for local production run
echo -e "${YELLOW}3. Configuring environment variables...${NC}"
export MONGO_URI="${MONGO_URI:-mongodb://localhost:27017/starfarm}"
export REDIS_HOST="${REDIS_HOST:-localhost}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export QDRANT_HOST="${QDRANT_HOST:-localhost}"
export QDRANT_PORT="${QDRANT_PORT:-6333}"
export QDRANT_GRPC_PORT="${QDRANT_GRPC_PORT:-6334}"
export QDRANT_PREFER_GRPC="${QDRANT_PREFER_GRPC:-false}"
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-adminpassword}"

# Determine number of workers
# Default to 4 workers for production concurrent processing
WORKERS=${WORKERS:-4}

# 4. Start production server using uv (no reload, multi-workers)
echo -e "${GREEN}4. Starting FastAPI app via Uvicorn in production mode (workers: $WORKERS) at http://0.0.0.0:8000...${NC}"
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --workers "$WORKERS"
