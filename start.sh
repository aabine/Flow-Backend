#!/bin/bash

# Oxygen Supply Platform - Startup Script
# This script helps you get the platform running quickly

set -e

echo "🚀 Starting Oxygen Supply Platform..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "📋 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your configuration before proceeding!"
    echo "   Required: DATABASE_URL, PAYSTACK keys, SMTP settings, etc."
    read -p "Press Enter after updating .env file..."
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check dependencies
echo "🔍 Checking dependencies..."

if ! command_exists docker; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command_exists docker-compose; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create Dockerfiles for each service
echo "📦 Creating Dockerfiles for services..."

services=("api-gateway" "user-service" "order-service" "inventory-service" "payment-service" "notification-service" "location-service" "websocket-service" "supplier-onboarding-service" "pricing-service" "review-service" "admin-service")

declare -A service_ports=(
    ["api-gateway"]=8000
    ["user-service"]=8001
    ["order-service"]=8005
    ["inventory-service"]=8004
    ["payment-service"]=8008
    ["notification-service"]=8010
    ["location-service"]=8003
    ["websocket-service"]=8012
    ["supplier-onboarding-service"]=8002
    ["pricing-service"]=8006
    ["review-service"]=8009
    ["admin-service"]=8011
)

for service in "${services[@]}"; do
    if [ ! -f "$service/Dockerfile" ]; then
        echo "Creating Dockerfile for $service..."
        port="${service_ports[$service]}"
        sed "s/{{PORT}}/$port/g" Dockerfile.template > "$service/Dockerfile"
    fi
done

# Create requirements.txt for each service if it doesn't exist
for service in "${services[@]}"; do
    if [ ! -f "$service/requirements.txt" ]; then
        echo "Creating requirements.txt for $service..."
        cp requirements.txt "$service/requirements.txt"
    fi
done

# Start the platform
echo "🐳 Starting Docker containers..."

# Check if security mode is requested
if [ "$1" = "--security" ] || [ "$1" = "--production" ]; then
    echo "🔒 Starting with security enhancements..."

    # Check if security environment file exists
    if [ ! -f .env.security ]; then
        echo "⚠️  Security environment file not found. Running security setup..."
        ./scripts/setup-security.sh
        echo "📋 Security setup completed. Please review .env.security file."
        read -p "Press Enter to continue with secure startup..."
    fi

    # Source security environment
    set -a
    source .env.security
    set +a

    # Build and start services with security compose file
    docker-compose -f docker-compose.yml -f docker-compose.security.yml up --build -d
else
    echo "🚀 Starting in development mode..."
    echo "💡 For production deployment with security, use: ./start.sh --security"

    # Build and start services (development mode)
    docker-compose up --build -d
fi

echo "⏳ Waiting for services to be ready..."
sleep 45

# Check service health
echo "🏥 Checking service health..."

services_urls=(
    "http://localhost:8000/health|API Gateway"
    "http://localhost:8001/health|User Service"
    "http://localhost:8004/health|Inventory Service"
    "http://localhost:8005/health|Order Service"
    "http://localhost:8008/health|Payment Service"
    "http://localhost:8010/health|Notification Service"
    "http://localhost:8012/health|WebSocket Service"
    "http://localhost:8002/health|Supplier Onboarding Service"
    "http://localhost:8006/health|Pricing Service"
    "http://localhost:8009/health|Review Service"
    "http://localhost:8011/health|Admin Service"
    "http://localhost:8003/health|Location Service"
)

for service_url in "${services_urls[@]}"; do
    IFS='|' read -r url name <<< "$service_url"
    if curl -f "$url" > /dev/null 2>&1; then
        echo "✅ $name is healthy"
    else
        echo "⚠️  $name is not responding"
    fi
done

echo ""
echo "🎉 Oxygen Supply Platform is running!"
echo ""
echo "📊 Service URLs:"
echo "   API Gateway:        http://localhost:8000"
echo "   API Documentation:  http://localhost:8000/docs"
echo "   User Service:       http://localhost:8001"
echo "   Order Service:      http://localhost:8005"
echo "   Inventory Service:  http://localhost:8004"
echo "   Payment Service:    http://localhost:8008"
echo "   Notification Service: http://localhost:8010"
echo "   WebSocket Service:  http://localhost:8012"
echo "   Supplier Onboarding Service: http://localhost:8002"
echo "   Pricing Service:     http://localhost:8006"
echo "   Review Service:      http://localhost:8009"
echo "   Admin Service:       http://localhost:8011"
echo "   Location Service:    http://localhost:8003"
echo ""
echo "🗄️  Database URLs:"
echo "   PostgreSQL:         localhost:5432"
echo "   Redis:              localhost:6379"
echo "   MongoDB:            localhost:27017"
echo "   RabbitMQ:           localhost:15672 (guest/guest)"
echo ""
echo "📚 Next Steps:"
echo "   1. Visit http://localhost:8000/docs for API documentation"
echo "   2. Create your first admin user via the API"
echo "   3. Set up vendor and hospital accounts"
echo "   4. Test the order flow"
echo ""
echo "🛑 To stop the platform: docker-compose down"
echo "🔄 To restart: docker-compose restart"
echo "📋 To view logs: docker-compose logs -f [service-name]"
