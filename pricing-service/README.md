# Pricing Service

The Pricing Service is a comprehensive microservice that enables hospitals to browse available vendors, view product catalogs, compare pricing across multiple vendors, and place direct orders. It serves as the core component for vendor discovery and product pricing in the Flow-Backend platform.

## Features

### 🏥 For Hospitals
- **Vendor Discovery**: Find medical supply vendors in your geographical area
- **Product Catalog Browsing**: Access real-time product inventory with pricing and availability
- **Price Comparison**: Compare prices across multiple vendors for informed purchasing decisions
- **Direct Order Placement**: Place orders directly without quote/bidding processes
- **Advanced Search**: Filter products by category, specifications, price range, and location
- **Real-time Availability**: Check current stock levels and delivery estimates

### 🏢 For Vendors
- **Vendor Profile Management**: Create and manage comprehensive business profiles
- **Product Catalog Management**: Add and manage product listings with detailed specifications
- **Pricing Management**: Set flexible pricing tiers with quantity-based discounts
- **Service Area Configuration**: Define geographical coverage areas and delivery zones
- **Performance Analytics**: Track ratings, orders, and delivery performance

### 🔧 Technical Features
- **Geographical Filtering**: Location-based vendor and product discovery
- **Real-time Pricing**: Dynamic pricing with bulk discounts and promotional offers
- **Multi-tier Pricing**: Quantity-based pricing with emergency surcharges
- **Event-driven Architecture**: Real-time notifications for price changes and availability
- **Comprehensive API**: RESTful APIs with OpenAPI documentation
- **Security**: JWT authentication with role-based access control

## API Endpoints

### Vendor Discovery
```
GET /api/v1/vendors/nearby
GET /api/v1/vendors/{vendor_id}
GET /api/v1/vendors/{vendor_id}/service-areas
POST /api/v1/vendors/
PUT /api/v1/vendors/{vendor_id}
```

### Product Catalog
```
GET /api/v1/products/catalog
POST /api/v1/products/search
POST /api/v1/products/availability/check
GET /api/v1/products/vendors/{vendor_id}/products
GET /api/v1/products/{product_id}
POST /api/v1/products/
PUT /api/v1/products/{product_id}
```

### Price Comparison
```
POST /api/v1/pricing/compare
POST /api/v1/pricing/bulk
GET /api/v1/pricing/products/{product_id}/vendors
POST /api/v1/pricing/products
GET /api/v1/pricing/products
PUT /api/v1/pricing/products/{pricing_id}
DELETE /api/v1/pricing/products/{pricing_id}
```

## Database Schema

### Core Tables
- **vendors**: Vendor business information and verification status
- **vendor_profiles**: Extended vendor profiles with capabilities and certifications
- **service_areas**: Geographical coverage areas with delivery details
- **product_catalogs**: Product listings with specifications and compliance info
- **pricing_tiers**: Flexible pricing with quantity tiers and discounts
- **price_history**: Historical pricing data for analytics
- **price_alerts**: User-configured price monitoring alerts

## Installation & Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 13+
- Redis 6+
- RabbitMQ 3.8+

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/oxygen_platform

# Security
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key
ENCRYPTION_KEY=your-encryption-key

# External Services
USER_SERVICE_URL=http://localhost:8001
INVENTORY_SERVICE_URL=http://localhost:8004
LOCATION_SERVICE_URL=http://localhost:8003
ORDER_SERVICE_URL=http://localhost:8005

# Pricing Configuration
DEFAULT_SEARCH_RADIUS_KM=50.0
MAX_SEARCH_RADIUS_KM=200.0
PRICE_CACHE_TTL_SECONDS=300
VENDOR_CACHE_TTL_SECONDS=1800

# Message Broker
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
REDIS_URL=redis://localhost:6379/0
```

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the service
python main.py
```

### Docker Deployment
```bash
# Build and run with docker-compose
docker-compose up pricing-service
```

## Usage Examples

### Hospital: Find Nearby Vendors
```python
import httpx

async def find_vendors():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8006/api/v1/vendors/nearby",
            params={
                "latitude": 6.5244,
                "longitude": 3.3792,
                "radius_km": 50.0,
                "business_type": "medical_supplier",
                "verification_status": "verified"
            },
            headers={"Authorization": "Bearer YOUR_JWT_TOKEN"}
        )
        return response.json()
```

### Hospital: Compare Prices
```python
async def compare_prices():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8006/api/v1/pricing/compare",
            json={
                "product_category": "oxygen_cylinder",
                "cylinder_size": "medium",
                "quantity": 10,
                "latitude": 6.5244,
                "longitude": 3.3792,
                "radius_km": 50.0,
                "sort_by": "price"
            },
            headers={"Authorization": "Bearer YOUR_JWT_TOKEN"}
        )
        return response.json()
```

### Vendor: Add Product
```python
async def add_product():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8006/api/v1/products/",
            json={
                "product_code": "OXY-MED-001",
                "product_name": "Medical Oxygen Cylinder - Medium",
                "product_category": "oxygen_cylinder",
                "cylinder_size": "medium",
                "capacity_liters": 10.0,
                "base_price": 5000.0,
                "minimum_order_quantity": 1,
                "description": "High-quality medical oxygen cylinder"
            },
            headers={"Authorization": "Bearer YOUR_JWT_TOKEN"}
        )
        return response.json()
```

## Testing

### Run Unit Tests
```bash
pytest tests/ -v
```

### Run Integration Tests
```bash
pytest tests/test_api_* -v
```

### Run with Coverage
```bash
pytest --cov=app tests/
```

## Architecture

### Service Integration
- **User Service**: Authentication and user management
- **Inventory Service**: Real-time stock levels and availability
- **Location Service**: Geographical data and distance calculations
- **Order Service**: Order placement and fulfillment
- **Notification Service**: Price alerts and vendor notifications

### Event-Driven Communication
- **Price Updates**: Notify when vendor prices change
- **Vendor Registration**: Alert when new vendors join
- **Product Availability**: Update when stock levels change
- **Price Alerts**: Trigger when user-defined price thresholds are met

## Security

### Authentication
- JWT-based authentication with role-based access control
- Integration with shared security modules
- Rate limiting and request validation

### Data Protection
- Input validation and sanitization
- SQL injection prevention
- Encrypted sensitive data storage
- Audit logging for all operations

## Monitoring & Logging

### Health Checks
- Database connectivity monitoring
- External service health verification
- Performance metrics tracking

### Logging
- Structured logging with correlation IDs
- Security event logging
- Performance monitoring
- Error tracking and alerting

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add comprehensive tests
4. Ensure all tests pass
5. Submit a pull request

## License

This project is part of the Flow-Backend platform and follows the same licensing terms.
