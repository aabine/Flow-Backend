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

services=("api-gateway" "user-service" "order-service" "inventory-service" "payment-service" "notification-service" "location-service" "websocket-service")

for service in "${services[@]}"; do
    if [ ! -f "$service/Dockerfile" ]; then
        echo "Creating Dockerfile for $service..."
        cp Dockerfile.template "$service/Dockerfile"
        
        # Update port in Dockerfile based on service
        case $service in
            "api-gateway")
                sed -i 's/EXPOSE 8000/EXPOSE 8000/' "$service/Dockerfile"
                sed -i 's/localhost:8000/localhost:8000/' "$service/Dockerfile"
                ;;
            "user-service")
                sed -i 's/EXPOSE 8000/EXPOSE 8001/' "$service/Dockerfile"
                sed -i 's/localhost:8000/localhost:8001/' "$service/Dockerfile"
                ;;
            "order-service")
                sed -i 's/EXPOSE 8000/EXPOSE 8005/' "$service/Dockerfile"
                sed -i 's/localhost:8000/localhost:8005/' "$service/Dockerfile"
                ;;
            "inventory-service")
                sed -i 's/EXPOSE 8000/EXPOSE 8004/' "$service/Dockerfile"
                sed -i 's/localhost:8000/localhost:8004/' "$service/Dockerfile"
                ;;
            "payment-service")
                sed -i 's/EXPOSE 8000/EXPOSE 8008/' "$service/Dockerfile"
                sed -i 's/localhost:8000/localhost:8008/' "$service/Dockerfile"
                ;;
            "notification-service")
                sed -i 's/EXPOSE 8000/EXPOSE 8010/' "$service/Dockerfile"
                sed -i 's/localhost:8000/localhost:8010/' "$service/Dockerfile"
                ;;
            "location-service")
                sed -i 's/EXPOSE 8000/EXPOSE 8003/' "$service/Dockerfile"
                sed -i 's/localhost:8000/localhost:8003/' "$service/Dockerfile"
                ;;
            "websocket-service")
                sed -i 's/EXPOSE 8000/EXPOSE 8012/' "$service/Dockerfile"
                sed -i 's/localhost:8000/localhost:8012/' "$service/Dockerfile"
                ;;
            "supplier-onboarding-service")
                sed -i 's/EXPOSE 8000/EXPOSE 8002/' "$service/Dockerfile"
                sed -i 's/localhost:8000/localhost:8002/' "$service/Dockerfile"
                ;;
        esac

        # Update CMD in Dockerfile based on service port
        case $service in
            "api-gateway") sed -i 's/--port", "8000"/--port", "8000"/' "$service/Dockerfile" ;;
            "user-service") sed -i 's/--port", "8000"/--port", "8001"/' "$service/Dockerfile" ;;
            "location-service") sed -i 's/--port", "8000"/--port", "8003"/' "$service/Dockerfile" ;;
            "inventory-service") sed -i 's/--port", "8000"/--port", "8004"/' "$service/Dockerfile" ;;
            "order-service") sed -i 's/--port", "8000"/--port", "8005"/' "$service/Dockerfile" ;;
            "payment-service") sed -i 's/--port", "8000"/--port", "8008"/' "$service/Dockerfile" ;;
            "notification-service") sed -i 's/--port", "8000"/--port", "8010"/' "$service/Dockerfile" ;;
            "websocket-service") sed -i 's/--port", "8000"/--port", "8012"/' "$service/Dockerfile" ;;
            "supplier-onboarding-service") sed -i 's/--port", "8000"/--port", "8002"/' "$service/Dockerfile" ;;
        esac
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

# Build and start services
docker-compose up --build -d

echo "⏳ Waiting for services to be ready..."
sleep 30

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
