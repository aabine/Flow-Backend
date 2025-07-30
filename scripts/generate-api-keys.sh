#!/bin/bash

# Flow-Backend API Key Generation Script
# Generates secure API keys for service-to-service authentication

set -e

echo "🔐 Flow-Backend API Key Generation"
echo "=================================="

# Check if openssl is available
if ! command -v openssl &> /dev/null; then
    echo "❌ Error: openssl is required but not installed."
    echo "   Please install openssl and try again."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📄 Creating .env file from .env.example..."
    cp .env.example .env
fi

# Generate secure API keys
echo "🔑 Generating secure API keys..."

ORDER_SERVICE_KEY="sk_order_service_$(openssl rand -hex 32)"
INVENTORY_SERVICE_KEY="sk_inventory_service_$(openssl rand -hex 32)"
PRICING_SERVICE_KEY="sk_pricing_service_$(openssl rand -hex 32)"
NOTIFICATION_SERVICE_KEY="sk_notification_service_$(openssl rand -hex 32)"

# Generate JWT secret key
JWT_SECRET="$(openssl rand -base64 64 | tr -d '\n')"

# Generate encryption key
ENCRYPTION_KEY="$(openssl rand -base64 32 | tr -d '\n')"

echo "✅ Generated secure keys:"
echo "   - Order Service API Key: ${ORDER_SERVICE_KEY:0:20}..."
echo "   - Inventory Service API Key: ${INVENTORY_SERVICE_KEY:0:20}..."
echo "   - Pricing Service API Key: ${PRICING_SERVICE_KEY:0:20}..."
echo "   - Notification Service API Key: ${NOTIFICATION_SERVICE_KEY:0:20}..."
echo "   - JWT Secret Key: ${JWT_SECRET:0:20}..."
echo "   - Encryption Key: ${ENCRYPTION_KEY:0:20}..."

# Update .env file
echo "📝 Updating .env file with generated keys..."

# Function to update or add environment variable
update_env_var() {
    local key=$1
    local value=$2
    local file=".env"
    
    if grep -q "^${key}=" "$file"; then
        # Update existing variable
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        # Add new variable
        echo "${key}=${value}" >> "$file"
    fi
}

# Update API keys
update_env_var "ORDER_SERVICE_API_KEY" "$ORDER_SERVICE_KEY"
update_env_var "INVENTORY_SERVICE_API_KEY" "$INVENTORY_SERVICE_KEY"
update_env_var "PRICING_SERVICE_API_KEY" "$PRICING_SERVICE_KEY"
update_env_var "NOTIFICATION_SERVICE_API_KEY" "$NOTIFICATION_SERVICE_KEY"

# Update security keys
update_env_var "JWT_SECRET_KEY" "$JWT_SECRET"
update_env_var "ENCRYPTION_KEY" "$ENCRYPTION_KEY"

echo "✅ .env file updated successfully!"

# Create production secrets file
echo "🏭 Creating production secrets template..."
cat > .env.production.template << EOF
# Production Environment Configuration
# CRITICAL: Update all values before deploying to production

# Database Configuration (Use production database)
DATABASE_URL=postgresql+asyncpg://prod_user:CHANGE_ME@prod-db:5432/oxygen_platform_prod

# Redis Configuration (Use production Redis)
REDIS_URL=redis://prod-redis:6379/0

# RabbitMQ Configuration (Use production RabbitMQ)
RABBITMQ_URL=amqp://prod_user:CHANGE_ME@prod-rabbitmq:5672/

# Service URLs (Update with production URLs)
API_GATEWAY_URL=https://api.yourdomain.com
USER_SERVICE_URL=http://user-service:8001
INVENTORY_SERVICE_URL=http://inventory-service:8004
LOCATION_SERVICE_URL=http://location-service:8003
NOTIFICATION_SERVICE_URL=http://notification-service:8010
PRICING_SERVICE_URL=http://pricing-service:8006

# Service API Keys (Generated securely)
ORDER_SERVICE_API_KEY=$ORDER_SERVICE_KEY
INVENTORY_SERVICE_API_KEY=$INVENTORY_SERVICE_KEY
PRICING_SERVICE_API_KEY=$PRICING_SERVICE_KEY
NOTIFICATION_SERVICE_API_KEY=$NOTIFICATION_SERVICE_KEY

# Security Configuration
JWT_SECRET_KEY=$JWT_SECRET
ENCRYPTION_KEY=$ENCRYPTION_KEY

# Production Security Settings
ENVIRONMENT=production
DEBUG=false
HTTPS_ONLY=true
SECURE_COOKIES=true
CSRF_PROTECTION=true
RATE_LIMIT_ENABLED=true
MAX_REQUESTS_PER_MINUTE=100

# Monitoring and Logging
LOG_LEVEL=INFO
ENABLE_METRICS=true
METRICS_PORT=9090

# External Services (Configure for production)
SMTP_HOST=smtp.yourdomain.com
SMTP_PORT=587
SMTP_USERNAME=noreply@yourdomain.com
SMTP_PASSWORD=CHANGE_ME

# Secrets Management
SECRETS_BACKEND=vault
VAULT_URL=https://vault.yourdomain.com
VAULT_TOKEN=CHANGE_ME
EOF

echo "✅ Production secrets template created: .env.production.template"

# Security recommendations
echo ""
echo "🛡️  SECURITY RECOMMENDATIONS:"
echo "================================"
echo "1. 🔒 Store API keys securely (use HashiCorp Vault, AWS Secrets Manager, etc.)"
echo "2. 🔄 Implement key rotation strategy (rotate keys every 90 days)"
echo "3. 🚫 Never commit .env files to version control"
echo "4. 📊 Monitor API key usage and set up alerts"
echo "5. 🔐 Use HTTPS/TLS in production"
echo "6. 🛡️  Enable rate limiting and request size limits"
echo "7. 📝 Audit API key access regularly"
echo ""
echo "📋 Next Steps:"
echo "1. Review and update .env file with your specific configuration"
echo "2. For production: Use .env.production.template and update all CHANGE_ME values"
echo "3. Set up secrets management system for production deployment"
echo "4. Configure monitoring and alerting for security events"
echo ""
echo "✅ API key generation completed successfully!"
