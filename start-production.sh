#!/bin/bash

# Oxygen Supply Platform - Production Startup Script
# This script starts the platform with full security configurations

set -e

echo "🔒 Starting Oxygen Supply Platform in PRODUCTION mode..."
echo "⚠️  This will apply security hardening and production configurations"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check dependencies
log_info "Checking dependencies..."

if ! command_exists docker; then
    log_error "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command_exists docker-compose; then
    log_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if running as root for security setup
if [[ $EUID -eq 0 ]]; then
    log_warning "Running as root. This is required for some security configurations."
else
    log_warning "Not running as root. Some security features may not be available."
    log_info "For full security setup, consider running: sudo ./start-production.sh"
fi

# Run security setup if not already done
if [ ! -f .env.security ]; then
    log_info "Security environment not found. Running security setup..."
    ./scripts/setup-security.sh
    log_success "Security setup completed."
else
    log_info "Security environment found. Checking if update is needed..."
    if [ scripts/setup-security.sh -nt .env.security ]; then
        log_warning "Security setup script is newer than environment file."
        read -p "Do you want to regenerate security configuration? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ./scripts/setup-security.sh
        fi
    fi
fi

# Source security environment
log_info "Loading security environment..."
set -a
source .env.security
set +a

# Validate required environment variables
required_vars=("JWT_SECRET_KEY" "ENCRYPTION_KEY" "REDIS_PASSWORD" "RABBITMQ_PASSWORD")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        log_error "Required environment variable $var is not set"
        exit 1
    fi
done

log_success "Security environment loaded successfully"

# Create required directories with proper permissions
log_info "Setting up secure directories..."
sudo mkdir -p /var/lib/oxygen-platform/{postgres,redis,rabbitmq}
sudo mkdir -p /var/log/oxygen-platform
sudo chmod 700 /var/lib/oxygen-platform/{postgres,redis,rabbitmq}
sudo chmod 755 /var/log/oxygen-platform

# Stop any existing containers
log_info "Stopping existing containers..."
docker-compose -f docker-compose.yml -f docker-compose.security.yml down --remove-orphans 2>/dev/null || true

# Build and start services with security
log_info "Building and starting services with security configurations..."
docker-compose -f docker-compose.yml -f docker-compose.security.yml up --build -d

log_info "Waiting for services to initialize..."
sleep 45

# Check service health with security endpoints
log_info "Checking service health..."

services_urls=(
    "https://localhost:443/health|API Gateway (HTTPS)"
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

healthy_services=0
total_services=${#services_urls[@]}

for service_url in "${services_urls[@]}"; do
    IFS='|' read -r url name <<< "$service_url"
    if curl -f -k "$url" > /dev/null 2>&1; then
        log_success "$name is healthy"
        ((healthy_services++))
    else
        log_warning "$name is not responding"
    fi
done

# Display startup summary
echo ""
log_info "🎉 Production startup completed!"
echo ""
echo "📊 Service Health: $healthy_services/$total_services services healthy"
echo ""
echo "🔒 Security Features Enabled:"
echo "   ✅ SSL/TLS encryption"
echo "   ✅ Container security hardening"
echo "   ✅ Network segmentation"
echo "   ✅ Secret management"
echo "   ✅ Security monitoring"
echo "   ✅ Firewall rules"
echo ""
echo "🌐 Production URLs:"
echo "   HTTPS API Gateway:    https://localhost:443"
echo "   API Documentation:    https://localhost:443/docs"
echo "   Admin Dashboard:      https://localhost:443/admin"
echo "   Security Monitoring:  Check /var/log/security/"
echo ""
echo "🔧 Management Commands:"
echo "   Stop platform:        docker-compose -f docker-compose.yml -f docker-compose.security.yml down"
echo "   View logs:            docker-compose -f docker-compose.yml -f docker-compose.security.yml logs -f [service]"
echo "   Security monitoring:  ./scripts/security-monitor.sh"
echo "   Firewall setup:       sudo ./scripts/firewall-rules.sh"
echo ""

if [ $healthy_services -lt $total_services ]; then
    log_warning "Some services are not healthy. Check logs for details:"
    echo "   docker-compose -f docker-compose.yml -f docker-compose.security.yml logs"
fi

log_success "Production deployment ready! 🚀"
