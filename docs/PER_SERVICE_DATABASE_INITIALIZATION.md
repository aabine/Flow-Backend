# Per-Service Database Initialization

## Overview

The Flow-Backend microservices architecture has been refactored to use per-service database initialization instead of a centralized approach. Each microservice now handles its own database schema creation and management independently during startup.

## Architecture

### Previous Approach (Centralized)
- Single `scripts/init-database.py` file handled all database initialization
- All services depended on a separate database initialization container
- Schema creation was done before any service started

### New Approach (Per-Service)
- Each service initializes its own database schema during startup
- Services use a shared database initialization framework
- No separate database initialization container needed
- Services start independently and handle their own database setup

## Benefits

1. **Service Independence**: Each service manages its own database lifecycle
2. **Simplified Deployment**: No need for separate database initialization containers
3. **Better Error Handling**: Service-specific database issues don't affect other services
4. **Easier Development**: Developers can work on individual services without full system setup
5. **Scalability**: Services can be deployed and scaled independently
6. **Maintainability**: Database schema changes are co-located with service code

## Implementation Details

### Shared Framework

The shared database initialization framework is located in `shared/database/`:

- `shared/database/init.py`: Core database initialization framework
- `shared/database/service_init.py`: Service-specific utilities and helpers
- `shared/database/__init__.py`: Package exports

### Service-Specific Implementation

Each service has its own database initialization module:

- `{service}/app/core/db_init.py`: Service-specific database initialization
- Contains table definitions, indexes, constraints, and seed data
- Integrated into service startup in `main.py`

### Database Configuration

Services use environment variables for database configuration:

```bash
DATABASE_URL=postgresql+asyncpg://user:password@postgres:5432/oxygen_platform
DB_INIT_MAX_RETRIES=10
DB_INIT_INITIAL_DELAY=1.0
DB_INIT_MAX_DELAY=30.0
DB_INIT_TIMEOUT=30.0
```

## Service Implementation Status

### ✅ Implemented Services

1. **User Service** (`user-service/app/core/db_init.py`)
   - User accounts, profiles, sessions
   - Vendor and hospital profiles
   - Authentication and authorization tables

2. **Inventory Service** (`inventory-service/app/core/db_init.py`)
   - Inventory locations and stock management
   - Cylinder tracking and lifecycle management
   - Quality checks and maintenance records

3. **Order Service** (`order-service/app/core/db_init.py`)
   - Order management and tracking
   - Order items and status history
   - Delivery management

4. **Payment Service** (`payment-service/app/core/db_init.py`)
   - Payment processing and tracking
   - Paystack integration
   - Payment splits and webhooks

### 🔄 Pending Services

The following services need database initialization implementation:

- Location Service
- Notification Service
- Review Service
- Admin Service
- Delivery Service
- Pricing Service
- Supplier Onboarding Service
- WebSocket Service

## Database Schema Organization

### Single Database Approach

All services use the same PostgreSQL database (`oxygen_platform`) but maintain logical separation through:

1. **Table Naming**: Service-specific table prefixes where appropriate
2. **Indexes**: Service-specific indexes for optimal performance
3. **Constraints**: Service-specific business rules and data integrity
4. **Enum Types**: Service-specific enum types for type safety

### Schema Creation Process

Each service follows this initialization process:

1. **Wait for Database**: Retry connection until database is ready
2. **Create Extensions**: PostgreSQL extensions (uuid-ossp, postgis, etc.)
3. **Create Enum Types**: Service-specific enum types
4. **Create Tables**: SQLAlchemy model-based table creation
5. **Create Indexes**: Performance optimization indexes
6. **Create Constraints**: Business rule constraints
7. **Seed Data**: Initial data and reference tables
8. **Verify Setup**: Validation that initialization succeeded

## Startup Sequence

### Docker Compose Dependencies

Services have proper dependencies configured:

```yaml
depends_on:
  postgres:
    condition: service_healthy
  redis:
    condition: service_started
```

### Service Startup Flow

1. **Database Health Check**: Wait for PostgreSQL to be ready
2. **Database Initialization**: Run service-specific initialization
3. **Service Dependencies**: Initialize other service dependencies (Redis, RabbitMQ)
4. **Application Startup**: Start FastAPI application
5. **Health Check**: Service reports ready status

## Error Handling

### Database Connection Issues

- Exponential backoff retry logic
- Configurable retry attempts and delays
- Graceful degradation when database is unavailable
- Detailed logging for troubleshooting

### Initialization Failures

- Services continue startup even if database initialization fails
- Errors are logged but don't prevent service from starting
- Health checks can detect database connectivity issues
- Manual retry mechanisms available

## Development Workflow

### Adding New Tables

1. Create SQLAlchemy models in `{service}/app/models/`
2. Add table definitions to `{service}/app/core/db_init.py`
3. Add indexes and constraints as needed
4. Test initialization with `docker-compose up {service}`

### Database Migrations

For schema changes:

1. Update SQLAlchemy models
2. Update initialization script with new schema
3. Consider backward compatibility
4. Test with fresh database and existing data

## Testing

### Local Development

```bash
# Test individual service database initialization
docker-compose up postgres redis
docker-compose up user-service

# Test all services
docker-compose up
```

### Integration Testing

```bash
# Run database initialization tests
python -m pytest tests/test_database_init.py

# Test service startup
./scripts/test-service-startup.sh
```

## Monitoring and Observability

### Logging

Each service logs database initialization progress:

```
🚀 Starting {Service} Service...
🔧 Initializing database...
✅ Database initialization completed
🎉 {Service} Service startup completed successfully!
```

### Health Checks

Services expose health endpoints that include database connectivity:

```bash
curl http://localhost:8001/health
```

### Metrics

Database initialization metrics are available:

- Initialization duration
- Retry attempts
- Success/failure rates
- Connection pool status

## Migration from Centralized Approach

### Steps Taken

1. ✅ Created shared database initialization framework
2. ✅ Implemented per-service initialization modules
3. ✅ Updated service startup logic
4. ✅ Updated Docker Compose configuration
5. ✅ Added environment variable configuration

### Backward Compatibility

- The old `scripts/init-database.py` is preserved for reference
- Services can still use centralized initialization if needed
- Gradual migration approach allows testing individual services

## Troubleshooting

### Common Issues

1. **Database Connection Timeout**
   - Check PostgreSQL health
   - Verify connection string
   - Increase retry configuration

2. **Table Already Exists Errors**
   - Normal for subsequent startups
   - Uses `CREATE TABLE IF NOT EXISTS`
   - Check logs for actual errors

3. **Permission Issues**
   - Verify database user permissions
   - Check schema creation rights
   - Ensure proper authentication

### Debug Mode

Enable detailed logging:

```bash
export LOG_LEVEL=DEBUG
export DB_INIT_DEBUG=true
```

## Future Enhancements

1. **Database Migrations**: Implement proper migration system
2. **Schema Versioning**: Track schema versions per service
3. **Rollback Capability**: Ability to rollback schema changes
4. **Performance Monitoring**: Track initialization performance
5. **Automated Testing**: Comprehensive database initialization tests
