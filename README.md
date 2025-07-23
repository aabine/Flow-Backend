# Oxygen Supply Platform - Microservices Backend

A scalable FastAPI-based microservices platform connecting hospitals with oxygen suppliers for efficient cylinder delivery and management.

## Architecture Overview

This platform uses a microservices architecture where each service is independently deployable with its own database:

### Core Services

1. **User Service** (`user-service/`) - Authentication, roles, user profiles
2. Implementation Plan for supplier-onboarding-service
Directory structure:
Apply to README.md
Key Features
Supplier KYC Data: Store and manage KYC information (business name, registration, tax ID, contact, etc.)
Document Upload: Allow suppliers to upload required documents (e.g., business registration, tax certificate, ID)
Verification Workflow: Admins can review and approve/reject supplier applications
Status Tracking: Track onboarding status (pending_verification, verified, rejected, etc.)
3. **Location Service** (`location-service/`) - Geospatial queries, supplier/hospital locations
4. **Inventory Service** (`inventory-service/`) - Oxygen cylinder stock management
5. **Order Service** (`order-service/`) - Order lifecycle management
6. **Pricing Service** (`pricing-service/`) - Quote management, bidding system
7. **Delivery Service** (`delivery-service/`) - Delivery tracking, ETA calculations
8. **Payment Service** (`payment-service/`) - Paystack integration, split payments
9. **Review Service** (`review-service/`) - Rating and feedback system
10. **Notification Service** (`notification-service/`) - Email/SMS/Push notifications
11. **Admin Service** (`admin-service/`) - Admin dashboard, analytics

### Supplier Onboarding Service Implementation Plan

**Directory structure:**
```
supplier-onboarding-service/
  app/
    api/
      onboarding.py
    core/
      config.py
      database.py
    models/
      supplier.py
      document.py
    schemas/
      onboarding.py
      document.py
    services/
      onboarding_service.py
      document_service.py
    utils/
      file_utils.py
    __init__.py
  Dockerfile
  main.py
  requirements.txt
```

**Key Features:**
- **Supplier KYC Data:** Store and manage KYC information (business name, registration, tax ID, contact, etc.)
- **Document Upload:** Allow suppliers to upload required documents (e.g., business registration, tax certificate, ID)
- **Verification Workflow:** Admins can review and approve/reject supplier applications
- **Status Tracking:** Track onboarding status (`pending_verification`, `verified`, `rejected`, etc.)

### Shared Components

- **API Gateway** (`api-gateway/`) - Central entry point, routing, authentication
- **Event Bus** (`event-bus/`) - Inter-service communication
- **Shared Models** (`shared/`) - Common data models and utilities

## Features

- 🏥 **Multi-role Authentication** - Hospital, Vendor, Admin roles
- 📦 **Real-time Inventory** - Live cylinder stock updates
- 🚚 **Order Management** - Complete order lifecycle tracking
- 💰 **Split Payments** - Automatic vendor payouts via Paystack
- ⭐ **Review System** - Bidirectional rating system
- 🚨 **Emergency Orders** - Priority handling for urgent requests
- 📊 **Analytics Dashboard** - Comprehensive admin insights
- 🔍 **Multi-supplier Quotes** - Competitive bidding system

## Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up Environment Variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start Services**
   ```bash
   # Start all services
   docker-compose up -d
   
   # Or start individual services
   cd user-service && uvicorn main:app --port 8001
   cd order-service && uvicorn main:app --port 8002
   # ... etc
   ```

4. **Access API Documentation**
   - API Gateway: http://localhost:8000/docs
   - Individual services: http://localhost:800X/docs

## Technology Stack

- **Framework**: FastAPI
- **Databases**: PostgreSQL, MongoDB, Redis
- **Message Broker**: RabbitMQ
- **Payment**: Paystack API
- **Authentication**: JWT
- **Documentation**: OpenAPI/Swagger

## Development

Each service follows the same structure:
```
service-name/
├── app/
│   ├── api/          # API routes
│   ├── core/         # Configuration, security
│   ├── models/       # Database models
│   ├── schemas/      # Pydantic schemas
│   ├── services/     # Business logic
│   └── utils/        # Utilities
├── tests/
├── Dockerfile
└── requirements.txt
```

## API Documentation

Comprehensive API documentation is available at `/docs` for each service and the main gateway.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
