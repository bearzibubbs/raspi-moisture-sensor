FROM fedora:40

WORKDIR /app

# Install system dependencies including I2C tools
RUN dnf install -y \
    python3 \
    python3-pip \
    gcc \
    python3-devel \
    i2c-tools \
    libi2c-devel \
    && dnf clean all

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./

# Create data directory
RUN mkdir -p /data && \
    chmod 755 /data

# Create groups used by the application
RUN groupadd i2c

# Create non-root user (but still needs I2C access)
RUN useradd -m -u 1000 -G i2c appuser && \
    chown -R appuser:appuser /app /data

USER appuser

# Expose management API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:8080/health')"

# Run the agent
CMD ["python3", "agent.py"]
