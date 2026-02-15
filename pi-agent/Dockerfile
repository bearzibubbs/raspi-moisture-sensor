FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including I2C tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    i2c-tools \
    libi2c-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./

# Create data directory
RUN mkdir -p /data && \
    chmod 755 /data

# Create non-root user (but still needs I2C access)
RUN useradd -m -u 1000 -G i2c appuser && \
    chown -R appuser:appuser /app /data

USER appuser

# Expose management API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')"

# Run the agent
CMD ["python", "agent.py"]
