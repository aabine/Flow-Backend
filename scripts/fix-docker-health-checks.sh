#!/bin/bash

# Docker Health Check Fix Script
# This script rebuilds all services with corrected health check configurations

set -e

echo "🔧 Docker Health Check Fix Script"
echo "=================================="
echo ""

# List of services to rebuild
SERVICES=(
    "user-service"
    "api-gateway"
    "inventory-service"
    "order-service"
    "pricing-service"
    "location-service"
    "payment-service"
    "notification-service"
    "review-service"
    "admin-service"
    "websocket-service"
)

echo "📋 Services to rebuild with fixed health checks:"
for service in "${SERVICES[@]}"; do
    echo "   - $service"
done
echo ""

# Function to rebuild and restart a service
rebuild_service() {
    local service=$1
    echo "🔨 Building $service..."
    
    if docker-compose build "$service"; then
        echo "✅ Build successful for $service"
        
        echo "🔄 Restarting $service..."
        docker-compose stop "$service" 2>/dev/null || true
        docker-compose rm -f "$service" 2>/dev/null || true
        
        if docker-compose up -d "$service"; then
            echo "✅ $service restarted successfully"
            echo ""
        else
            echo "❌ Failed to restart $service"
            return 1
        fi
    else
        echo "❌ Build failed for $service"
        return 1
    fi
}

# Rebuild all services
echo "🚀 Starting rebuild process..."
echo ""

FAILED_SERVICES=()
SUCCESSFUL_SERVICES=()

for service in "${SERVICES[@]}"; do
    if rebuild_service "$service"; then
        SUCCESSFUL_SERVICES+=("$service")
    else
        FAILED_SERVICES+=("$service")
        echo "⚠️  Continuing with next service..."
        echo ""
    fi
done

echo "📊 Rebuild Summary:"
echo "=================="
echo "✅ Successful: ${#SUCCESSFUL_SERVICES[@]} services"
for service in "${SUCCESSFUL_SERVICES[@]}"; do
    echo "   - $service"
done

if [ ${#FAILED_SERVICES[@]} -gt 0 ]; then
    echo ""
    echo "❌ Failed: ${#FAILED_SERVICES[@]} services"
    for service in "${FAILED_SERVICES[@]}"; do
        echo "   - $service"
    done
fi

echo ""
echo "⏳ Waiting 60 seconds for health checks to complete..."
sleep 60

echo ""
echo "🏥 Final Health Check Status:"
echo "============================="
docker-compose ps

echo ""
echo "🎯 Health Check Fix Summary:"
echo "============================"
echo "✅ Fixed health check commands to use urllib.request instead of curl"
echo "✅ Corrected port numbers in health check URLs"
echo "✅ Updated all ${#SERVICES[@]} microservices"
echo ""

# Count healthy services
HEALTHY_COUNT=$(docker-compose ps | grep "Up (healthy)" | wc -l)
TOTAL_SERVICES=$(docker-compose ps | grep -E "(user-service|api-gateway|inventory-service|order-service|pricing-service|location-service|payment-service|notification-service|review-service|admin-service|websocket-service)" | wc -l)

echo "📈 Health Status Results:"
echo "   Healthy Services: $HEALTHY_COUNT"
echo "   Total Services: $TOTAL_SERVICES"

if [ "$HEALTHY_COUNT" -eq "$TOTAL_SERVICES" ]; then
    echo "🎉 SUCCESS: All services are now healthy!"
    exit 0
else
    echo "⚠️  Some services may still need attention"
    echo ""
    echo "🔍 Services that may need manual inspection:"
    docker-compose ps | grep -v "Up (healthy)" | grep -E "(user-service|api-gateway|inventory-service|order-service|pricing-service|location-service|payment-service|notification-service|review-service|admin-service|websocket-service)"
    exit 1
fi
