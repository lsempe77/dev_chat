# DevChat v2.0 - Railway Production Dockerfile
# Slim image for API-only deployment (no PDF processing)

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only production requirements
COPY requirements-prod.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-prod.txt

# Copy application code
COPY api/ api/
COPY src/ src/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose port (Railway provides PORT env var)
EXPOSE 8000

# Run the application - use shell to expand $PORT
CMD ["/bin/sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
