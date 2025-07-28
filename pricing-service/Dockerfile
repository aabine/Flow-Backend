FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy shared directory first for better caching
COPY shared/ /app/shared/

# Copy pricing service requirements and install dependencies
COPY pricing-service/requirements.txt /app/pricing-service/
RUN pip install --no-cache-dir -r pricing-service/requirements.txt

# Copy pricing service code
COPY pricing-service/ /app/pricing-service/

# Set working directory to pricing service
WORKDIR /app/pricing-service

# Expose port
EXPOSE 8006

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8006/health')" || exit 1

# Run the application
CMD ["python", "main.py"]
