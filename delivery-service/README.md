# Delivery Service

The Delivery Service is a microservice responsible for managing oxygen delivery operations in the Flow-Backend oxygen supply platform. It handles delivery tracking, ETA calculations, route optimization, and driver assignment.

## Features

### Core Functionality
- **Delivery Tracking System** - Track delivery status from dispatch to completion with real-time updates
- **ETA Calculations** - Calculate estimated time of arrival based on distance, traffic, and delivery route optimization
- **Route Management** - Optimize delivery routes for multiple orders and track driver locations
- **Delivery Assignment** - Assign deliveries to available drivers based on location and capacity

### Technical Features
- FastAPI framework with async/await patterns
- PostgreSQL database with SQLAlchemy ORM
- Docker containerization with health checks
- Comprehensive API documentation
- Real-time tracking updates via WebSocket integration
- Integration with external services (Order, Location, Notification, etc.)
- Route optimization algorithms
- Automated driver assignment based on multiple factors

## API Endpoints

### Deliveries
- `POST /api/v1/deliveries/` - Create a new delivery
- `GET /api/v1/deliveries/` - Get deliveries with filtering and pagination
- `GET /api/v1/deliveries/{delivery_id}` - Get delivery by ID
- `PUT /api/v1/deliveries/{delivery_id}` - Update delivery
- `POST /api/v1/deliveries/{delivery_id}/assign` - Assign delivery to driver
- `POST /api/v1/deliveries/{delivery_id}/auto-assign` - Auto-assign delivery to best driver
- `POST /api/v1/deliveries/{delivery_id}/tracking` - Add tracking update
- `GET /api/v1/deliveries/{delivery_id}/tracking` - Get tracking history
- `POST /api/v1/deliveries/calculate-eta` - Calculate ETA for delivery

### Drivers
- `POST /api/v1/drivers/` - Create a new driver
- `GET /api/v1/drivers/` - Get all drivers with filtering
- `GET /api/v1/drivers/{driver_id}` - Get driver by ID
- `PUT /api/v1/drivers/{driver_id}` - Update driver
- `POST /api/v1/drivers/{driver_id}/location` - Update driver location
- `GET /api/v1/drivers/{driver_id}/stats` - Get driver statistics
- `GET /api/v1/drivers/available/near` - Get available drivers near location
- `GET /api/v1/drivers/user/{user_id}` - Get driver by user ID

### Routes
- `POST /api/v1/routes/` - Create optimized route
- `GET /api/v1/routes/{route_id}` - Get route by ID
- `POST /api/v1/routes/{route_id}/start` - Start route execution
- `POST /api/v1/routes/{route_id}/complete` - Complete route execution
- `GET /api/v1/routes/driver/{driver_id}` - Get routes for driver
- `GET /api/v1/routes/{route_id}/progress` - Get route progress

## Database Models

### Delivery
- Delivery information (order, customer, driver)
- Pickup and delivery addresses with coordinates
- Status tracking and timing information
- Priority levels and special instructions
- Distance and cost calculations

### Driver
- Driver profile and vehicle information
- Current location and availability status
- Performance metrics (rating, total deliveries)
- Vehicle capacity and type

### DeliveryTracking
- Real-time tracking updates
- Location coordinates and timestamps
- Status changes and notes

### DeliveryRoute
- Optimized delivery routes
- Multiple delivery assignments
- Distance and duration calculations
- Route progress tracking

## Configuration

### Environment Variables
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `RABBITMQ_URL` - RabbitMQ connection string
- `SECRET_KEY` - JWT secret key
- Service URLs for integration (USER_SERVICE_URL, ORDER_SERVICE_URL, etc.)
- Delivery configuration (radius, speed, pricing)
- Route optimization settings

### Docker Configuration
The service runs on port 8007 and requires:
- PostgreSQL database (delivery-db)
- Redis for caching
- RabbitMQ for messaging
- Network connectivity to other microservices

## Integration Points

### External Services
- **Order Service** - Receive delivery requests and update order status
- **Location Service** - Address validation and geocoding
- **Notification Service** - Send delivery status notifications
- **WebSocket Service** - Real-time tracking updates
- **Inventory Service** - Check availability and reserve items
- **User Service** - Get customer and driver information

### Message Queues
- Delivery status updates
- Driver assignment notifications
- Route optimization requests

## Development

### Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Set up environment variables
3. Run database migrations: `alembic upgrade head`
4. Start the service: `uvicorn app.main:app --reload`

### Testing
Run tests with pytest:
```bash
pytest tests/ -v
```

### Database Migrations
Create new migration:
```bash
alembic revision --autogenerate -m "Description"
```

Apply migrations:
```bash
alembic upgrade head
```

## Deployment

### Docker
Build and run with Docker Compose:
```bash
docker-compose up delivery-service
```

### Health Checks
- `/health` - Service health status
- Database connectivity check
- External service availability

## Monitoring

### Metrics
- Delivery completion rates
- Average delivery times
- Driver performance metrics
- Route optimization efficiency

### Logging
- Structured logging with correlation IDs
- Error tracking and alerting
- Performance monitoring

## Security

- JWT-based authentication
- Input validation and sanitization
- Rate limiting
- CORS configuration
- Secure database connections

## Performance

### Optimization Features
- Database connection pooling
- Async/await for non-blocking operations
- Efficient route optimization algorithms
- Caching for frequently accessed data
- Background task processing

### Scalability
- Horizontal scaling support
- Load balancing ready
- Database read replicas support
- Message queue integration for async processing
