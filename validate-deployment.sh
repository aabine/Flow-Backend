#!/bin/bash

# Oxygen Supply Platform - Deployment Validation Script
# This script validates that both development and production deployments work correctly

set -e

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

# Function to check if a service is responding
check_service() {
    local url=$1
    local name=$2
    local timeout=${3:-10}
    
    if curl -f -k --max-time $timeout "$url" > /dev/null 2>&1; then
        log_success "$name is responding"
        return 0
    else
        log_error "$name is not responding at $url"
        return 1
    fi
}

# Function to validate compose file syntax
validate_compose_files() {
    log_info "Validating Docker Compose files..."
    
    if docker-compose -f docker-compose.yml config > /dev/null 2>&1; then
        log_success "docker-compose.yml is valid"
    else
        log_error "docker-compose.yml has syntax errors"
        return 1
    fi
    
    if docker-compose -f docker-compose.yml -f docker-compose.security.yml config > /dev/null 2>&1; then
        log_success "docker-compose.security.yml integration is valid"
    else
        log_error "docker-compose.security.yml has syntax errors or conflicts"
        return 1
    fi
}

# Function to check if security files exist
check_security_files() {
    log_info "Checking security file structure..."
    
    local files=(
        "docker-compose.security.yml"
        "scripts/setup-security.sh"
        "scripts/security-validation.sh"
        "start-production.sh"
    )
    
    for file in "${files[@]}"; do
        if [ -f "$file" ]; then
            log_success "$file exists"
        else
            log_error "$file is missing"
            return 1
        fi
    done
}

# Function to test development deployment
test_development_deployment() {
    log_info "Testing development deployment..."
    
    # Stop any existing containers
    docker-compose down --remove-orphans 2>/dev/null || true
    
    # Start development deployment
    log_info "Starting development services..."
    docker-compose up -d
    
    # Wait for services to start
    sleep 30
    
    # Check basic services
    local dev_services=(
        "http://localhost:8000/health|API Gateway"
        "http://localhost:8001/health|User Service"
        "http://localhost:8005/health|Order Service"
    )
    
    local healthy=0
    for service in "${dev_services[@]}"; do
        IFS='|' read -r url name <<< "$service"
        if check_service "$url" "$name" 5; then
            ((healthy++))
        fi
    done
    
    # Stop development deployment
    docker-compose down
    
    if [ $healthy -eq ${#dev_services[@]} ]; then
        log_success "Development deployment test passed"
        return 0
    else
        log_error "Development deployment test failed ($healthy/${#dev_services[@]} services healthy)"
        return 1
    fi
}

# Function to test security deployment (without actually starting)
test_security_deployment() {
    log_info "Testing security deployment configuration..."
    
    # Check if security environment can be generated
    if [ ! -f .env.security ]; then
        log_info "Generating test security environment..."
        ./scripts/setup-security.sh
    fi
    
    # Test compose file with security
    if docker-compose -f docker-compose.yml -f docker-compose.security.yml config > /dev/null 2>&1; then
        log_success "Security deployment configuration is valid"
        return 0
    else
        log_error "Security deployment configuration has errors"
        return 1
    fi
}

# Function to check startup scripts
check_startup_scripts() {
    log_info "Checking startup scripts..."
    
    # Check if scripts are executable
    local scripts=(
        "start.sh"
        "start-production.sh"
        "scripts/setup-security.sh"
        "scripts/security-validation.sh"
    )
    
    for script in "${scripts[@]}"; do
        if [ -x "$script" ]; then
            log_success "$script is executable"
        else
            log_warning "$script is not executable, fixing..."
            chmod +x "$script"
        fi
    done
    
    # Check if start.sh includes security option
    if grep -q "docker-compose.*security" start.sh; then
        log_success "start.sh includes security compose file integration"
    else
        log_error "start.sh does not properly integrate security compose file"
        return 1
    fi
}

# Main validation function
main() {
    echo "🔍 Oxygen Supply Platform - Deployment Validation"
    echo "=================================================="
    echo ""
    
    local tests_passed=0
    local total_tests=5
    
    # Test 1: Validate compose files
    if validate_compose_files; then
        ((tests_passed++))
    fi
    echo ""
    
    # Test 2: Check security files
    if check_security_files; then
        ((tests_passed++))
    fi
    echo ""
    
    # Test 3: Check startup scripts
    if check_startup_scripts; then
        ((tests_passed++))
    fi
    echo ""
    
    # Test 4: Test development deployment
    if test_development_deployment; then
        ((tests_passed++))
    fi
    echo ""
    
    # Test 5: Test security deployment configuration
    if test_security_deployment; then
        ((tests_passed++))
    fi
    echo ""
    
    # Summary
    echo "=================================================="
    echo "Validation Summary: $tests_passed/$total_tests tests passed"
    echo ""
    
    if [ $tests_passed -eq $total_tests ]; then
        log_success "🎉 All deployment validation tests passed!"
        echo ""
        echo "✅ Development deployment: ./start.sh"
        echo "✅ Production deployment:  ./start-production.sh"
        echo "✅ Security integration:   Properly configured"
        echo ""
        return 0
    else
        log_error "❌ Some validation tests failed"
        echo ""
        echo "Please fix the issues above before deploying to production."
        echo ""
        return 1
    fi
}

# Run validation
main "$@"
