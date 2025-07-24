FROM python:3.11-slim

WORKDIR /app

# Add build dependencies for netifaces and other packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure /app is in PYTHONPATH so 'shared' can be imported
ENV PYTHONPATH=/app

EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"] 