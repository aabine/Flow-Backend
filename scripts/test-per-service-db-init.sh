#!/bin/bash

# Test script for per-service database initialization
# Tests that each service can initialize its database independently

set -e

echo "🧪 Testing Per-Service Database Initialization"
echo "=============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to check if service is healthy
check_service_health() {
    local service_name=$1
    local port=$2
    local max_attempts=30
    local attempt=1
    
    print_status $BLUE "🔍 Checking health of $service_name on port $port..."
    
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "http://localhost:$port/health" > /dev/null 2>&1 || \
           curl -s -f "http://localhost:$port/" > /dev/null 2>&1; then
            print_status $GREEN "✅ $service_name is healthy"
            return 0
        fi
        
        echo "   Attempt $attempt/$max_attempts - waiting for $service_name..."
        sleep 2
        ((attempt++))
    done
    
    print_status $RED "❌ $service_name failed to become healthy"
    return 1
}

# Function to test individual service database initialization
test_service_db_init() {
    local service_name=$1
    local port=$2
    
    print_status $BLUE "🧪 Testing $service_name database initialization..."
    
    # Stop the service if it's running
    docker-compose stop $service_name > /dev/null 2>&1 || true
    
    # Start dependencies (postgres, redis)
    print_status $YELLOW "🔧 Starting dependencies for $service_name..."
    docker-compose up -d postgres redis > /dev/null 2>&1
    
    # Wait for postgres to be healthy
    print_status $YELLOW "⏳ Waiting for PostgreSQL to be ready..."
    while ! docker-compose exec -T postgres pg_isready -U user -d oxygen_platform > /dev/null 2>&1; do
        echo "   Waiting for PostgreSQL..."
        sleep 2
    done
    print_status $GREEN "✅ PostgreSQL is ready"
    
    # Start the service
    print_status $YELLOW "🚀 Starting $service_name..."
    docker-compose up -d $service_name
    
    # Check if service becomes healthy
    if check_service_health $service_name $port; then
        print_status $GREEN "✅ $service_name database initialization successful"
        
        # Check database tables were created
        print_status $BLUE "🔍 Verifying database tables for $service_name..."
        table_count=$(docker-compose exec -T postgres psql -U user -d oxygen_platform -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d ' ')
        print_status $GREEN "✅ Found $table_count tables in database"
        
        return 0
    else
        print_status $RED "❌ $service_name database initialization failed"
        
        # Show logs for debugging
        print_status $YELLOW "📋 Last 20 lines of $service_name logs:"
        docker-compose logs --tail=20 $service_name
        
        return 1
    fi
}

# Function to test all services together
test_all_services() {
    print_status $BLUE "🧪 Testing all services together..."
    
    # Stop all services
    print_status $YELLOW "🛑 Stopping all services..."
    docker-compose down > /dev/null 2>&1
    
    # Start all services
    print_status $YELLOW "🚀 Starting all services..."
    docker-compose up -d
    
    # Wait a bit for startup
    sleep 10
    
    # Check each service
    local services=(
        "user-service:8001"
        "inventory-service:8004"
        "order-service:8005"
        "payment-service:8008"
    )
    
    local success_count=0
    local total_count=${#services[@]}
    
    for service_port in "${services[@]}"; do
        IFS=':' read -r service port <<< "$service_port"
        if check_service_health $service $port; then
            ((success_count++))
        fi
    done
    
    print_status $BLUE "📊 Results: $success_count/$total_count services healthy"
    
    if [ $success_count -eq $total_count ]; then
        print_status $GREEN "✅ All services started successfully with per-service database initialization"
        return 0
    else
        print_status $RED "❌ Some services failed to start"
        return 1
    fi
}

# Function to test database schema isolation
test_database_schema() {
    print_status $BLUE "🧪 Testing database schema and tables..."
    
    # Connect to database and check tables
    print_status $YELLOW "🔍 Checking database tables..."
    
    # Get table list
    tables=$(docker-compose exec -T postgres psql -U user -d oxygen_platform -t -c "
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    " | tr -d ' ' | grep -v '^$')
    
    echo "📋 Database tables found:"
    echo "$tables" | while read -r table; do
        if [ -n "$table" ]; then
            echo "   - $table"
        fi
    done
    
    # Check for service-specific tables
    local expected_tables=(
        "users"
        "user_profiles"
        "user_sessions"
        "vendor_profiles"
        "hospital_profiles"
        "inventory_locations"
        "cylinder_stock"
        "cylinders"
        "orders"
        "order_items"
        "payments"
    )
    
    local found_count=0
    for table in "${expected_tables[@]}"; do
        if echo "$tables" | grep -q "^$table$"; then
            print_status $GREEN "✅ Found table: $table"
            ((found_count++))
        else
            print_status $YELLOW "⚠️  Missing table: $table"
        fi
    done
    
    print_status $BLUE "📊 Found $found_count/${#expected_tables[@]} expected tables"
    
    if [ $found_count -gt 0 ]; then
        print_status $GREEN "✅ Database schema validation passed"
        return 0
    else
        print_status $RED "❌ Database schema validation failed"
        return 1
    fi
}

# Main test execution
main() {
    print_status $BLUE "🚀 Starting Per-Service Database Initialization Tests"
    echo ""
    
    # Test individual services
    local individual_tests=(
        "user-service:8001"
        "inventory-service:8004"
        "order-service:8005"
        "payment-service:8008"
    )
    
    local individual_success=0
    for service_port in "${individual_tests[@]}"; do
        IFS=':' read -r service port <<< "$service_port"
        echo ""
        if test_service_db_init $service $port; then
            ((individual_success++))
        fi
    done
    
    echo ""
    print_status $BLUE "📊 Individual Service Tests: $individual_success/${#individual_tests[@]} passed"
    
    # Test database schema
    echo ""
    test_database_schema
    
    # Test all services together
    echo ""
    test_all_services
    
    # Final summary
    echo ""
    print_status $BLUE "🎯 Test Summary"
    print_status $BLUE "==============="
    
    if [ $individual_success -eq ${#individual_tests[@]} ]; then
        print_status $GREEN "✅ All individual service tests passed"
        print_status $GREEN "✅ Per-service database initialization is working correctly"
        print_status $GREEN "🎉 Migration to per-service initialization successful!"
        
        echo ""
        print_status $BLUE "📋 Next Steps:"
        echo "   1. Implement remaining services (location, notification, review, etc.)"
        echo "   2. Add comprehensive integration tests"
        echo "   3. Update deployment documentation"
        echo "   4. Consider removing old centralized init script"
        
        return 0
    else
        print_status $RED "❌ Some tests failed"
        print_status $YELLOW "🔧 Check the logs above for debugging information"
        return 1
    fi
}

# Run main function
main "$@"
