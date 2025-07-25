#!/bin/bash

# Resilient startup script for Flow-Backend microservices
# This script starts services with proper dependency handling and graceful fallbacks

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.yml"
DEV_COMPOSE_FILE="docker-compose.dev.yml"
SECURITY_COMPOSE_FILE="docker-compose.security.yml"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if a service is running
check_service() {
    local service_name=$1
    local port=$2
    local max_attempts=30
    local attempt=1
    
    print_status "Checking if $service_name is ready on port $port..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "http://localhost:$port/health" > /dev/null 2>&1; then
            print_success "$service_name is ready!"
            return 0
        fi
        
        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    print_warning "$service_name is not responding on port $port (this may be normal)"
    return 1
}

# Function to start core infrastructure
start_infrastructure() {
    print_status "Starting core infrastructure (PostgreSQL, Redis)..."
    
    docker-compose -f $COMPOSE_FILE up -d postgres redis
    
    # Wait for PostgreSQL
    print_status "Waiting for PostgreSQL to be ready..."
    while ! docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; do
        echo -n "."
        sleep 2
    done
    print_success "PostgreSQL is ready!"
    
    # Wait for Redis
    print_status "Waiting for Redis to be ready..."
    while ! docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; do
        echo -n "."
        sleep 2
    done
    print_success "Redis is ready!"
}

# Function to start RabbitMQ (optional)
start_rabbitmq() {
    print_status "Starting RabbitMQ (optional)..."
    
    if docker-compose -f $COMPOSE_FILE up -d rabbitmq; then
        print_status "Waiting for RabbitMQ to be ready..."
        local attempt=1
        local max_attempts=15
        
        while [ $attempt -le $max_attempts ]; do
            if docker-compose exec -T rabbitmq rabbitmq-diagnostics ping > /dev/null 2>&1; then
                print_success "RabbitMQ is ready!"
                return 0
            fi
            echo -n "."
            sleep 3
            attempt=$((attempt + 1))
        done
        
        print_warning "RabbitMQ is not responding (services will start without it)"
        return 1
    else
        print_warning "Failed to start RabbitMQ (services will start without it)"
        return 1
    fi
}

# Function to start core services
start_core_services() {
    print_status "Starting core services..."
    
    # Start user service first (other services depend on it)
    print_status "Starting User Service..."
    docker-compose -f $COMPOSE_FILE -f $DEV_COMPOSE_FILE up -d user-service
    check_service "User Service" 8001
    
    # Start other core services
    print_status "Starting core business services..."
    docker-compose -f $COMPOSE_FILE -f $DEV_COMPOSE_FILE up -d \
        order-service \
        inventory-service \
        payment-service \
        location-service \
        pricing-service
    
    # Check core services
    check_service "Order Service" 8005
    check_service "Inventory Service" 8004
    check_service "Payment Service" 8007
    check_service "Location Service" 8003
    check_service "Pricing Service" 8006
}

# Function to start supporting services
start_supporting_services() {
    print_status "Starting supporting services..."
    
    docker-compose -f $COMPOSE_FILE -f $DEV_COMPOSE_FILE up -d \
        review-service \
        notification-service \
        websocket-service \
        delivery-service \
        supplier-onboarding-service
    
    # Check supporting services
    check_service "Review Service" 8008
    check_service "Notification Service" 8010
    check_service "WebSocket Service" 8009
    check_service "Delivery Service" 8011
    check_service "Supplier Onboarding Service" 8002
}

# Function to start admin and gateway services
start_admin_services() {
    print_status "Starting admin and gateway services..."
    
    docker-compose -f $COMPOSE_FILE -f $DEV_COMPOSE_FILE up -d \
        admin-service \
        api-gateway
    
    # Check admin services
    check_service "Admin Service" 8012
    check_service "API Gateway" 8000
}

# Function to show service status
show_status() {
    print_status "Service Status Summary:"
    echo ""
    
    services=(
        "postgres:5432:PostgreSQL Database"
        "redis:6379:Redis Cache"
        "rabbitmq:15672:RabbitMQ Management"
        "user-service:8001:User Service"
        "supplier-onboarding-service:8002:Supplier Onboarding"
        "location-service:8003:Location Service"
        "inventory-service:8004:Inventory Service"
        "order-service:8005:Order Service"
        "pricing-service:8006:Pricing Service"
        "payment-service:8007:Payment Service"
        "review-service:8008:Review Service"
        "websocket-service:8009:WebSocket Service"
        "notification-service:8010:Notification Service"
        "delivery-service:8011:Delivery Service"
        "admin-service:8012:Admin Service"
        "api-gateway:8000:API Gateway"
    )
    
    for service_info in "${services[@]}"; do
        IFS=':' read -r service port description <<< "$service_info"
        
        if docker-compose ps | grep -q "$service.*Up"; then
            if curl -s -f "http://localhost:$port/health" > /dev/null 2>&1 || \
               curl -s -f "http://localhost:$port" > /dev/null 2>&1; then
                echo -e "✅ $description (http://localhost:$port)"
            else
                echo -e "🟡 $description (starting...)"
            fi
        else
            echo -e "❌ $description (not running)"
        fi
    done
    
    echo ""
    print_success "Flow-Backend services startup completed!"
    echo ""
    print_status "Key URLs:"
    echo "  🌐 API Gateway: http://localhost:8000"
    echo "  👥 User Service: http://localhost:8001"
    echo "  🛒 Order Service: http://localhost:8005"
    echo "  📦 Inventory Service: http://localhost:8004"
    echo "  🔧 Admin Service: http://localhost:8012"
    echo "  🐰 RabbitMQ Management: http://localhost:15672 (guest/guest)"
    echo ""
}

# Main execution
main() {
    print_status "🚀 Starting Flow-Backend Microservices..."
    echo ""
    
    # Check if Docker is running
    if ! docker info > /dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    
    # Start infrastructure
    start_infrastructure
    
    # Start RabbitMQ (optional)
    start_rabbitmq
    
    # Start services in order
    start_core_services
    start_supporting_services
    start_admin_services
    
    # Show final status
    show_status
    
    print_status "To view logs: docker-compose logs -f [service-name]"
    print_status "To stop all services: docker-compose down"
}

# Handle script arguments
case "${1:-start}" in
    "start")
        main
        ;;
    "stop")
        print_status "Stopping all services..."
        docker-compose -f $COMPOSE_FILE down
        print_success "All services stopped!"
        ;;
    "restart")
        print_status "Restarting all services..."
        docker-compose -f $COMPOSE_FILE down
        main
        ;;
    "status")
        show_status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        echo ""
        echo "  start   - Start all services with graceful dependency handling"
        echo "  stop    - Stop all services"
        echo "  restart - Stop and start all services"
        echo "  status  - Show current service status"
        exit 1
        ;;
esac
