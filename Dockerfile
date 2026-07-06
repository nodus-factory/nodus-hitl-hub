FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy source code and install
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir . && pip install --no-cache-dir uvicorn

# Expose port
EXPOSE 3000

# Run server
CMD ["uvicorn", "nodus_hitl_hub.server:app", "--host", "0.0.0.0", "--port", "3000"]
