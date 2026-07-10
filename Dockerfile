# Use python base image for building stage
FROM python:3.12-slim AS builder

# Install uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Install git since we have a git dependency in pyproject.toml
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml to install dependencies
COPY pyproject.toml ./

# Create virtual environment and install CPU dependencies using uv pip
RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple -r pyproject.toml

# Final runtime image
FROM python:3.12-slim

# Install uv binary in the final stage
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install ffmpeg for runtime audio processing
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Ensure Python outputs directly to terminal (useful for docker logs)
ENV PYTHONUNBUFFERED=1

# Copy the application code
COPY src/ ./src
COPY main.py ./

# Run the app using uv run starting uvicorn
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
