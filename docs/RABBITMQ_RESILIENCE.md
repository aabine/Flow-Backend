# RabbitMQ Resilience Implementation

## Overview

The Flow-Backend microservices have been enhanced with robust RabbitMQ connectivity that allows services to start and operate even when RabbitMQ is unavailable. This ensures high availability and prevents cascading failures.

## Problem Solved

**Before**: Admin-service and other services would fail to start if RabbitMQ was unavailable, causing:
- Service startup failures
- Cascading dependency issues
- Poor development experience
- Production downtime risks

**After**: Services start gracefully with automatic RabbitMQ reconnection and fallback mechanisms.

## Key Features

### 🔄 Automatic Reconnection
- **Exponential Backoff**: Intelligent retry mechanism with increasing delays
- **Connection Monitoring**: Real-time connection state tracking
- **Automatic Recovery**: Services reconnect when RabbitMQ becomes available

### 🛡️ Graceful Degradation
- **Service Independence**: Services start without RabbitMQ dependency
- **Event Buffering**: Events stored locally when RabbitMQ is unavailable
- **Fallback Mechanisms**: Alternative event processing paths

### 📊 Monitoring & Observability
- **Health Checks**: Enhanced endpoints showing RabbitMQ status
- **Connection States**: Real-time connection state reporting
- **Event Metrics**: Pending events and processing statistics

## Implementation Details

### Connection States

```python
class ConnectionState(Enum):
    DISCONNECTED = "disconnected"  # No connection
    CONNECTING = "connecting"      # Attempting to connect
    CONNECTED = "connected"        # Successfully connected
    FAILED = "failed"             # Connection failed after retries
```

### Event Listener Service Enhancements

#### Resilient Connection Management
```python
async def _connect_with_retry(self):
    """Attempt to connect to RabbitMQ with exponential backoff."""
    retry_count = 0
    
    while self.is_running and retry_count < self.max_retries:
        try:
            self.connection = await aio_pika.connect_robust(
                self.settings.RABBITMQ_URL,
                timeout=10.0
            )
            # Setup infrastructure and start processing
            return  # Success
        except Exception as e:
            # Exponential backoff with max delay
            delay = min(self.retry_delay * (2 ** retry_count), 60)
            await asyncio.sleep(delay)
```

#### Event Buffering
```python
async def publish_event(self, event_type: str, event_data: Dict[str, Any]):
    """Publish event with fallback to local storage."""
    if self.connection_state == ConnectionState.CONNECTED:
        # Try RabbitMQ first
        try:
            await self._publish_to_rabbitmq(event_type, event_data)
            return
        except Exception:
            pass  # Fall through to local storage
    
    # Store locally when RabbitMQ unavailable
    self.pending_events.append({
        "type": event_type,
        "data": event_data,
        "timestamp": datetime.utcnow().isoformat()
    })
```

### Configuration Options

#### Environment Variables
```bash
# RabbitMQ Configuration
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
RABBITMQ_REQUIRED=false  # Allow service startup without RabbitMQ

# Connection Retry Settings
RABBITMQ_MAX_RETRIES=5
RABBITMQ_RETRY_DELAY=5
RABBITMQ_MAX_PENDING_EVENTS=1000
```

## Usage

### Development Mode (RabbitMQ Optional)

```bash
# Start with development overrides
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Or use the resilient startup script
./scripts/start-services.sh start
```

### Production Mode (RabbitMQ Required)

```bash
# Standard production deployment
docker-compose -f docker-compose.yml -f docker-compose.security.yml up

# Set RABBITMQ_REQUIRED=true for strict mode
export RABBITMQ_REQUIRED=true
```

### Using the Startup Script

```bash
# Start all services with dependency handling
./scripts/start-services.sh start

# Check service status
./scripts/start-services.sh status

# Stop all services
./scripts/start-services.sh stop

# Restart all services
./scripts/start-services.sh restart
```

## Health Check Endpoints

### Admin Service Health Check
```bash
curl http://localhost:8012/health
```

**Response with RabbitMQ Available:**
```json
{
  "status": "healthy",
  "service": "Admin Service",
  "dependencies": {
    "rabbitmq": {
      "status": "connected",
      "connected": true,
      "pending_events": 0,
      "url": "amqp://guest:guest@rabbitmq:5672/"
    }
  },
  "issues": []
}
```

**Response with RabbitMQ Unavailable:**
```json
{
  "status": "healthy",
  "service": "Admin Service",
  "dependencies": {
    "rabbitmq": {
      "status": "failed",
      "connected": false,
      "pending_events": 15,
      "url": "amqp://guest:guest@rabbitmq:5672/"
    }
  },
  "issues": ["RabbitMQ connection unavailable"]
}
```

## Monitoring

### Connection Status
```python
# Get current connection status
status = event_listener.get_connection_status()
print(f"RabbitMQ Status: {status['state']}")
print(f"Pending Events: {status['pending_events']}")
```

### Logs
```bash
# Monitor admin service logs
docker-compose logs -f admin-service

# Look for connection status messages
# ✅ Successfully connected to RabbitMQ
# ❌ Failed to connect to RabbitMQ: Connection refused
# 📝 Service will continue without RabbitMQ
```

## Troubleshooting

### Common Issues

#### 1. RabbitMQ Connection Refused
```
❌ Failed to connect to RabbitMQ: Connection refused [Errno 111]
```
**Solution**: RabbitMQ is not running. Service will continue without it.

#### 2. High Pending Events
```
⚠️ Pending events buffer full, dropping event order.created
```
**Solution**: Start RabbitMQ or increase `max_pending_events` setting.

#### 3. Service Won't Start
```
Failed to start event listener service: Connection timeout
```
**Solution**: Use development mode or set `RABBITMQ_REQUIRED=false`.

### Debug Commands

```bash
# Check RabbitMQ container status
docker-compose ps rabbitmq

# Check RabbitMQ logs
docker-compose logs rabbitmq

# Test RabbitMQ connectivity
docker-compose exec rabbitmq rabbitmq-diagnostics ping

# Check admin service connection status
curl http://localhost:8012/health | jq '.dependencies.rabbitmq'
```

## Best Practices

### Development
1. Use `docker-compose.dev.yml` for optional RabbitMQ
2. Monitor pending events during development
3. Test both connected and disconnected scenarios

### Production
1. Ensure RabbitMQ high availability
2. Monitor connection health continuously
3. Set up alerts for connection failures
4. Use `RABBITMQ_REQUIRED=true` for critical services

### Monitoring
1. Track pending event counts
2. Monitor connection state changes
3. Alert on prolonged disconnections
4. Log event processing failures

## Architecture Benefits

### Resilience
- **No Single Point of Failure**: Services operate independently
- **Graceful Degradation**: Reduced functionality vs. complete failure
- **Automatic Recovery**: Self-healing when dependencies return

### Scalability
- **Independent Scaling**: Services scale without coordination
- **Resource Efficiency**: No blocked resources waiting for dependencies
- **Flexible Deployment**: Services can be deployed in any order

### Maintainability
- **Clear Error Handling**: Explicit connection state management
- **Observable Behavior**: Rich logging and health checks
- **Testable Components**: Easy to test with/without RabbitMQ

This implementation ensures that the Flow-Backend microservices are production-ready with enterprise-grade resilience patterns.
