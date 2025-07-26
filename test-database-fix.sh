#!/bin/bash

# Database Connectivity Fix Test Script
# Tests the improved database initialization and connectivity

set -e

echo "🚀 Testing Database Connectivity Fixes"
echo "======================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    case $status in
        "INFO")
            echo -e "${BLUE}ℹ️  $message${NC}"
            ;;
        "SUCCESS")
            echo -e "${GREEN}✅ $message${NC}"
            ;;
        "WARNING")
            echo -e "${YELLOW}⚠️  $message${NC}"
            ;;
        "ERROR")
            echo -e "${RED}❌ $message${NC}"
            ;;
    esac
}

# Function to check if Docker is running
check_docker() {
    print_status "INFO" "Checking Docker status..."
    if ! docker info >/dev/null 2>&1; then
        print_status "ERROR" "Docker is not running. Please start Docker first."
        exit 1
    fi
    print_status "SUCCESS" "Docker is running"
}

# Function to check if docker-compose is available
check_docker_compose() {
    print_status "INFO" "Checking Docker Compose availability..."
    if command -v docker-compose >/dev/null 2>&1; then
        DOCKER_COMPOSE_CMD="docker-compose"
    elif docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE_CMD="docker compose"
    else
        print_status "ERROR" "Docker Compose is not available"
        exit 1
    fi
    print_status "SUCCESS" "Docker Compose is available: $DOCKER_COMPOSE_CMD"
}

# Function to clean up existing containers
cleanup_containers() {
    print_status "INFO" "Cleaning up existing containers..."
    
    # Stop and remove containers
    $DOCKER_COMPOSE_CMD down --volumes --remove-orphans >/dev/null 2>&1 || true
    
    # Remove any dangling containers
    docker container prune -f >/dev/null 2>&1 || true
    
    print_status "SUCCESS" "Cleanup completed"
}

# Function to start PostgreSQL with health check
start_postgres() {
    print_status "INFO" "Starting PostgreSQL with health checks..."
    
    # Start only PostgreSQL first
    $DOCKER_COMPOSE_CMD up -d postgres
    
    # Wait for PostgreSQL to be healthy
    print_status "INFO" "Waiting for PostgreSQL to be healthy..."
    local max_wait=120
    local wait_time=0
    
    while [ $wait_time -lt $max_wait ]; do
        if $DOCKER_COMPOSE_CMD ps postgres | grep -q "healthy"; then
            print_status "SUCCESS" "PostgreSQL is healthy and ready"
            return 0
        fi
        
        sleep 2
        wait_time=$((wait_time + 2))
        echo -n "."
    done
    
    print_status "ERROR" "PostgreSQL failed to become healthy within $max_wait seconds"
    
    # Show logs for debugging
    print_status "INFO" "PostgreSQL logs:"
    $DOCKER_COMPOSE_CMD logs postgres
    
    return 1
}

# Function to test database connectivity
test_connectivity() {
    print_status "INFO" "Testing database connectivity..."
    
    # Install required Python packages if not available
    if ! python3 -c "import asyncpg" >/dev/null 2>&1; then
        print_status "INFO" "Installing asyncpg..."
        python3 -m pip install asyncpg >/dev/null 2>&1 || {
            print_status "WARNING" "Failed to install asyncpg globally, trying with --user"
            python3 -m pip install --user asyncpg >/dev/null 2>&1
        }
    fi
    
    # Run connectivity tests
    if python3 scripts/test-db-connectivity.py; then
        print_status "SUCCESS" "Database connectivity tests passed"
        return 0
    else
        print_status "ERROR" "Database connectivity tests failed"
        return 1
    fi
}

# Function to test database initialization
test_initialization() {
    print_status "INFO" "Testing database initialization..."
    
    # Run the improved database initialization script
    if python3 scripts/init-database.py; then
        print_status "SUCCESS" "Database initialization completed successfully"
        return 0
    else
        print_status "ERROR" "Database initialization failed"
        
        # Show PostgreSQL logs for debugging
        print_status "INFO" "PostgreSQL logs:"
        $DOCKER_COMPOSE_CMD logs postgres | tail -50
        
        return 1
    fi
}

# Function to test service startup
test_service_startup() {
    print_status "INFO" "Testing service startup with database dependencies..."
    
    # Start a few key services that depend on the database
    $DOCKER_COMPOSE_CMD up -d user-service order-service payment-service
    
    # Wait a bit for services to start
    sleep 10
    
    # Check if services are running
    local failed_services=()
    
    for service in user-service order-service payment-service; do
        if ! $DOCKER_COMPOSE_CMD ps $service | grep -q "Up"; then
            failed_services+=($service)
        fi
    done
    
    if [ ${#failed_services[@]} -eq 0 ]; then
        print_status "SUCCESS" "All test services started successfully"
        return 0
    else
        print_status "ERROR" "Failed services: ${failed_services[*]}"
        
        # Show logs for failed services
        for service in "${failed_services[@]}"; do
            print_status "INFO" "Logs for $service:"
            $DOCKER_COMPOSE_CMD logs $service | tail -20
        done
        
        return 1
    fi
}

# Function to run comprehensive tests
run_comprehensive_test() {
    print_status "INFO" "Running comprehensive database connectivity test..."

    local test_passed=true

    # Test 1: Database initialization (must be first to create schema)
    if ! test_initialization; then
        test_passed=false
    fi

    # Test 2: Full connectivity testing (after schema is created)
    if ! test_connectivity; then
        test_passed=false
    fi

    # Test 3: Service startup
    if ! test_service_startup; then
        test_passed=false
    fi

    if [ "$test_passed" = true ]; then
        return 0
    else
        return 1
    fi
}

# Main execution
main() {
    echo ""
    print_status "INFO" "Starting Database Connectivity Fix Validation"
    echo ""
    
    # Pre-flight checks
    check_docker
    check_docker_compose
    
    # Cleanup
    cleanup_containers
    
    # Start PostgreSQL
    if ! start_postgres; then
        print_status "ERROR" "Failed to start PostgreSQL"
        exit 1
    fi
    
    # Run comprehensive tests
    if run_comprehensive_test; then
        echo ""
        print_status "SUCCESS" "🎉 All database connectivity tests passed!"
        print_status "SUCCESS" "The database connectivity fixes are working correctly."
        echo ""
        
        # Cleanup
        print_status "INFO" "Cleaning up test environment..."
        cleanup_containers
        
        exit 0
    else
        echo ""
        print_status "ERROR" "❌ Some tests failed. Please check the logs above."
        echo ""
        
        # Keep containers running for debugging
        print_status "INFO" "Containers are left running for debugging."
        print_status "INFO" "Use '$DOCKER_COMPOSE_CMD logs <service>' to check logs."
        print_status "INFO" "Use '$DOCKER_COMPOSE_CMD down' to clean up when done."
        
        exit 1
    fi
}

# Run main function
main "$@"
