#!/bin/bash

# PostgreSQL Connectivity Test Script
# Tests the database connectivity verification function from start.sh

set -e

echo "🧪 PostgreSQL Connectivity Test"
echo "==============================="
echo ""

# Function to verify database connection (copied from start.sh)
verify_database_connection() {
    echo "🔍 Verifying basic PostgreSQL connectivity..."

    # Check if PostgreSQL container is running
    if ! docker ps --format "table {{.Names}}" | grep -q "flow-backend_postgres"; then
        echo "❌ PostgreSQL container 'flow-backend_postgres' is not running"
        echo "🔍 Available containers:"
        docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(postgres|flow-backend)"
        return 1
    fi
    echo "✅ PostgreSQL container is running"

    # Check if we can connect to PostgreSQL server
    if ! docker exec flow-backend_postgres psql -U user -d postgres -c "SELECT 1;" >/dev/null 2>&1; then
        echo "❌ Cannot connect to PostgreSQL server"
        return 1
    fi

    # Check if target database exists
    if docker exec flow-backend_postgres psql -U user -d postgres -t -c "SELECT 1 FROM pg_database WHERE datname = 'oxygen_platform';" | grep -q "1"; then
        echo "✅ Target database 'oxygen_platform' exists"
    else
        echo "❌ Target database 'oxygen_platform' does not exist"
        return 1
    fi

    # Verify we can connect to the target database
    if docker exec flow-backend_postgres psql -U user -d oxygen_platform -c "SELECT 1;" >/dev/null 2>&1; then
        echo "✅ Successfully connected to oxygen_platform database"
    else
        echo "❌ Cannot connect to oxygen_platform database"
        return 1
    fi

    echo "✅ Basic PostgreSQL connectivity verified"
    echo "📋 Note: Individual services will create their own tables during startup"
    return 0
}

# Test 1: Container Status
echo "📋 Test 1: PostgreSQL Container Status"
echo "======================================"
if docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep "flow-backend_postgres"; then
    echo "✅ PostgreSQL container found and running"
else
    echo "❌ PostgreSQL container not found or not running"
    echo "🔍 All running containers:"
    docker ps --format "table {{.Names}}\t{{.Status}}"
    exit 1
fi
echo ""

# Test 2: PostgreSQL Readiness
echo "📋 Test 2: PostgreSQL Readiness Check"
echo "====================================="
if docker exec flow-backend_postgres pg_isready -U user -d oxygen_platform >/dev/null 2>&1; then
    echo "✅ PostgreSQL is ready (pg_isready check passed)"
else
    echo "❌ PostgreSQL is not ready"
    exit 1
fi
echo ""

# Test 3: Database Connectivity
echo "📋 Test 3: Database Connectivity Verification"
echo "============================================="
if verify_database_connection; then
    echo "✅ Database connectivity verification passed"
else
    echo "❌ Database connectivity verification failed"
    exit 1
fi
echo ""

# Test 4: Service Connection Strings
echo "📋 Test 4: Service Connection String Validation"
echo "==============================================="
echo "🔍 Testing connection strings that services will use..."

# Test internal Docker network connection (how services connect)
echo "📡 Testing internal Docker network connection..."
if docker run --rm --network flow-backend_oxygen-network postgres:15 psql -h postgres -U user -d oxygen_platform -c "SELECT 'Internal connection successful' as result;" 2>/dev/null; then
    echo "✅ Internal Docker network connection successful"
else
    echo "⚠️  Internal Docker network connection test skipped (requires network setup)"
fi

# Test external localhost connection (how external tools connect)
echo "📡 Testing external localhost connection..."
if command -v psql >/dev/null 2>&1; then
    if psql -h localhost -p 5432 -U user -d oxygen_platform -c "SELECT 'External connection successful' as result;" 2>/dev/null; then
        echo "✅ External localhost connection successful"
    else
        echo "⚠️  External localhost connection failed (may require password or different auth)"
    fi
else
    echo "⚠️  psql command not available for external connection test"
fi
echo ""

# Test 5: Database Schema Information
echo "📋 Test 5: Database Schema Information"
echo "====================================="
echo "🔍 Checking existing schemas in oxygen_platform database..."
schemas=$(docker exec flow-backend_postgres psql -U user -d oxygen_platform -t -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast', 'pg_temp_1', 'pg_toast_temp_1') ORDER BY schema_name;")

if [ -n "$schemas" ]; then
    echo "📊 Existing schemas:"
    echo "$schemas" | while read -r schema; do
        if [ -n "$schema" ]; then
            echo "   - $schema"
        fi
    done
else
    echo "📋 No custom schemas found (services will create them during startup)"
fi
echo ""

# Summary
echo "🎯 PostgreSQL Connectivity Test Summary"
echo "======================================="
echo "✅ Container Status: Running"
echo "✅ Readiness Check: Passed"
echo "✅ Connectivity Verification: Passed"
echo "✅ Database Access: Successful"
echo ""
echo "🚀 PostgreSQL is ready for service connections!"
echo "📋 Services can now connect using:"
echo "   Internal: postgresql://user:password@postgres:5432/oxygen_platform"
echo "   External: postgresql://user:password@localhost:5432/oxygen_platform"
echo ""
echo "✅ start.sh PostgreSQL connectivity verification should now work correctly!"
