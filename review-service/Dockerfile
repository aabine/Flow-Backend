FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY review-service/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared directory
COPY shared/ /app/shared/

# Copy application code
COPY review-service/ /app/review-service/

# Set working directory to review-service
WORKDIR /app/review-service

# Expose port
EXPOSE 8009

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8009"]
