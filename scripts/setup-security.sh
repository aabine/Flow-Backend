#!/bin/bash

# Security setup script for Oxygen Supply Platform
# This script sets up SSL certificates, secrets, and security configurations

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PLATFORM_NAME="Oxygen Supply Platform"
DOMAIN="oxygen-platform.com"
ADMIN_DOMAIN="admin.oxygen-platform.com"
SSL_DIR="./ssl"
SECRETS_DIR="./secrets"
ENV_FILE=".env.security"

# Functions
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

generate_random_secret() {
    openssl rand -base64 32
}

generate_jwt_secret() {
    openssl rand -base64 64
}

generate_encryption_key() {
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}

create_directories() {
    log_info "Creating security directories..."
    
    mkdir -p "$SSL_DIR"/{nginx,postgres,rabbitmq}
    mkdir -p "$SECRETS_DIR"
    mkdir -p ./nginx
    mkdir -p ./fluentd
    mkdir -p /var/log/oxygen-platform
    mkdir -p /var/lib/oxygen-platform/{postgres,redis,rabbitmq}
    
    # Set proper permissions
    chmod 700 "$SSL_DIR"
    chmod 700 "$SECRETS_DIR"
    chmod 755 /var/log/oxygen-platform
    chmod 700 /var/lib/oxygen-platform/{postgres,redis,rabbitmq}
    
    log_success "Directories created"
}

generate_ssl_certificates() {
    log_info "Generating SSL certificates..."
    
    # Create CA key and certificate
    openssl genrsa -out "$SSL_DIR/ca-key.pem" 4096
    openssl req -new -x509 -days 365 -key "$SSL_DIR/ca-key.pem" -sha256 -out "$SSL_DIR/ca.pem" -subj "/C=NG/ST=Lagos/L=Lagos/O=$PLATFORM_NAME/CN=CA"
    
    # Create server key
    openssl genrsa -out "$SSL_DIR/server-key.pem" 4096
    
    # Create server certificate signing request
    openssl req -subj "/C=NG/ST=Lagos/L=Lagos/O=$PLATFORM_NAME/CN=$DOMAIN" -sha256 -new -key "$SSL_DIR/server-key.pem" -out "$SSL_DIR/server.csr"
    
    # Create extensions file
    cat > "$SSL_DIR/server-extfile.cnf" <<EOF
subjectAltName = DNS:$DOMAIN,DNS:www.$DOMAIN,DNS:$ADMIN_DOMAIN,DNS:localhost,IP:127.0.0.1
extendedKeyUsage = serverAuth
EOF
    
    # Generate server certificate
    openssl x509 -req -days 365 -sha256 -in "$SSL_DIR/server.csr" -CA "$SSL_DIR/ca.pem" -CAkey "$SSL_DIR/ca-key.pem" -out "$SSL_DIR/server-cert.pem" -extfile "$SSL_DIR/server-extfile.cnf" -CAcreateserial
    
    # Copy certificates for different services
    cp "$SSL_DIR/server-cert.pem" "$SSL_DIR/nginx/cert.pem"
    cp "$SSL_DIR/server-key.pem" "$SSL_DIR/nginx/key.pem"
    cp "$SSL_DIR/ca.pem" "$SSL_DIR/nginx/ca.pem"
    
    # Admin certificates
    cp "$SSL_DIR/server-cert.pem" "$SSL_DIR/nginx/admin-cert.pem"
    cp "$SSL_DIR/server-key.pem" "$SSL_DIR/nginx/admin-key.pem"
    
    # PostgreSQL certificates
    cp "$SSL_DIR/server-cert.pem" "$SSL_DIR/postgres/server.crt"
    cp "$SSL_DIR/server-key.pem" "$SSL_DIR/postgres/server.key"
    cp "$SSL_DIR/ca.pem" "$SSL_DIR/postgres/ca.crt"
    
    # RabbitMQ certificates
    cp "$SSL_DIR/server-cert.pem" "$SSL_DIR/rabbitmq/cert.pem"
    cp "$SSL_DIR/server-key.pem" "$SSL_DIR/rabbitmq/key.pem"
    cp "$SSL_DIR/ca.pem" "$SSL_DIR/rabbitmq/ca.pem"
    
    # Set proper permissions
    chmod 600 "$SSL_DIR"/*-key.pem
    chmod 644 "$SSL_DIR"/*.pem
    chmod 600 "$SSL_DIR"/*/key.pem "$SSL_DIR"/postgres/server.key
    chmod 644 "$SSL_DIR"/*/*.pem "$SSL_DIR"/*/*.crt
    
    # Clean up
    rm "$SSL_DIR/server.csr" "$SSL_DIR/server-extfile.cnf"
    
    log_success "SSL certificates generated"
}

generate_secrets() {
    log_info "Generating application secrets..."
    
    # Generate secrets
    JWT_SECRET=$(generate_jwt_secret)
    ENCRYPTION_KEY=$(generate_encryption_key)
    REDIS_PASSWORD=$(generate_random_secret)
    RABBITMQ_USER="oxygen_platform"
    RABBITMQ_PASSWORD=$(generate_random_secret)
    PAYSTACK_SECRET_KEY="sk_test_$(generate_random_secret | tr -d '=' | head -c 32)"
    PAYSTACK_WEBHOOK_SECRET=$(generate_random_secret)
    DB_PASSWORD=$(generate_random_secret)
    
    # Create environment file
    cat > "$ENV_FILE" <<EOF
# Security Environment Variables for Oxygen Supply Platform
# Generated on $(date)

# JWT and Encryption
JWT_SECRET_KEY=$JWT_SECRET
ENCRYPTION_KEY=$ENCRYPTION_KEY

# Database
DB_PASSWORD=$DB_PASSWORD
DB_SSL_MODE=require
DB_AUDIT_LOGGING=true

# Redis
REDIS_PASSWORD=$REDIS_PASSWORD

# RabbitMQ
RABBITMQ_USER=$RABBITMQ_USER
RABBITMQ_PASSWORD=$RABBITMQ_PASSWORD

# Payment (Paystack)
PAYSTACK_SECRET_KEY=$PAYSTACK_SECRET_KEY
PAYSTACK_WEBHOOK_SECRET=$PAYSTACK_WEBHOOK_SECRET

# Security Settings
ENVIRONMENT=production
ALLOWED_ORIGINS=https://$DOMAIN,https://$ADMIN_DOMAIN
ADMIN_IP_WHITELIST=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16

# Monitoring
ENABLE_SECURITY_MONITORING=true
LOG_LEVEL=INFO
EOF
    
    # Set proper permissions
    chmod 600 "$ENV_FILE"
    
    # Store secrets securely
    echo "$JWT_SECRET" > "$SECRETS_DIR/jwt_secret"
    echo "$ENCRYPTION_KEY" > "$SECRETS_DIR/encryption_key"
    echo "$REDIS_PASSWORD" > "$SECRETS_DIR/redis_password"
    echo "$RABBITMQ_PASSWORD" > "$SECRETS_DIR/rabbitmq_password"
    echo "$PAYSTACK_SECRET_KEY" > "$SECRETS_DIR/paystack_secret"
    echo "$PAYSTACK_WEBHOOK_SECRET" > "$SECRETS_DIR/paystack_webhook_secret"
    echo "$DB_PASSWORD" > "$SECRETS_DIR/db_password"
    
    chmod 600 "$SECRETS_DIR"/*
    
    log_success "Secrets generated and stored"
}

create_security_configs() {
    log_info "Creating security configuration files..."
    
    # Nginx security configuration
    cat > "./nginx/security.conf" <<EOF
# Additional security configurations for Nginx

# Block common attack patterns
location ~* \.(git|svn|hg) {
    deny all;
}

location ~* \.(env|log|ini|conf|bak|old|tmp)$ {
    deny all;
}

# Block user agents
if (\$http_user_agent ~* (bot|crawler|spider|scraper)) {
    return 403;
}

# Block suspicious requests
if (\$request_method !~ ^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$) {
    return 405;
}

# Rate limiting for specific patterns
location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
    add_header Vary Accept-Encoding;
}
EOF
    
    # Fluentd configuration for security monitoring
    cat > "./fluentd/fluent.conf" <<EOF
<source>
  @type tail
  path /var/log/nginx/access.log
  pos_file /var/log/fluentd/nginx.log.pos
  tag nginx.access
  format nginx
</source>

<source>
  @type tail
  path /var/log/nginx/error.log
  pos_file /var/log/fluentd/nginx-error.log.pos
  tag nginx.error
  format /^(?<time>[^ ]+ [^ ]+) \[(?<log_level>\w+)\] (?<message>.*)$/
</source>

<filter nginx.**>
  @type record_transformer
  <record>
    service nginx
    environment production
  </record>
</filter>

<match nginx.**>
  @type file
  path /var/log/security/nginx
  append true
  time_slice_format %Y%m%d
  time_slice_wait 10m
  time_format %Y%m%dT%H%M%S%z
</match>
EOF
    
    log_success "Security configurations created"
}

setup_firewall() {
    log_info "Setting up firewall rules..."
    
    # Create iptables rules script
    cat > "./scripts/firewall-rules.sh" <<EOF
#!/bin/bash
# Firewall rules for Oxygen Supply Platform

# Flush existing rules
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X

# Default policies
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# Allow loopback
iptables -A INPUT -i lo -j ACCEPT

# Allow established connections
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow SSH (change port as needed)
iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow HTTP and HTTPS
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Allow WebSocket
iptables -A INPUT -p tcp --dport 8080 -j ACCEPT

# Rate limiting for HTTP/HTTPS
iptables -A INPUT -p tcp --dport 80 -m limit --limit 25/minute --limit-burst 100 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -m limit --limit 25/minute --limit-burst 100 -j ACCEPT

# Block common attack ports
iptables -A INPUT -p tcp --dport 23 -j DROP  # Telnet
iptables -A INPUT -p tcp --dport 135 -j DROP # RPC
iptables -A INPUT -p tcp --dport 445 -j DROP # SMB

# Log dropped packets
iptables -A INPUT -j LOG --log-prefix "DROPPED: "

# Save rules
iptables-save > /etc/iptables/rules.v4
EOF
    
    chmod +x "./scripts/firewall-rules.sh"
    
    log_success "Firewall rules created"
}

create_monitoring_scripts() {
    log_info "Creating security monitoring scripts..."
    
    # Security monitoring script
    cat > "./scripts/security-monitor.sh" <<EOF
#!/bin/bash
# Security monitoring script

LOG_FILE="/var/log/security/security-monitor.log"
ALERT_EMAIL="admin@oxygen-platform.com"

# Check for failed login attempts
check_failed_logins() {
    FAILED_LOGINS=\$(grep "authentication_failure" /var/log/oxygen-platform/*.log | wc -l)
    if [ \$FAILED_LOGINS -gt 10 ]; then
        echo "\$(date): High number of failed logins detected: \$FAILED_LOGINS" >> \$LOG_FILE
        # Send alert email here
    fi
}

# Check for suspicious IP addresses
check_suspicious_ips() {
    # Check for IPs with high request rates
    tail -n 1000 /var/log/nginx/access.log | awk '{print \$1}' | sort | uniq -c | sort -nr | head -10 | while read count ip; do
        if [ \$count -gt 100 ]; then
            echo "\$(date): Suspicious IP detected: \$ip with \$count requests" >> \$LOG_FILE
        fi
    done
}

# Check SSL certificate expiry
check_ssl_expiry() {
    EXPIRY_DATE=\$(openssl x509 -in ./ssl/nginx/cert.pem -noout -enddate | cut -d= -f2)
    EXPIRY_TIMESTAMP=\$(date -d "\$EXPIRY_DATE" +%s)
    CURRENT_TIMESTAMP=\$(date +%s)
    DAYS_UNTIL_EXPIRY=\$(( (\$EXPIRY_TIMESTAMP - \$CURRENT_TIMESTAMP) / 86400 ))
    
    if [ \$DAYS_UNTIL_EXPIRY -lt 30 ]; then
        echo "\$(date): SSL certificate expires in \$DAYS_UNTIL_EXPIRY days" >> \$LOG_FILE
    fi
}

# Run checks
check_failed_logins
check_suspicious_ips
check_ssl_expiry
EOF
    
    chmod +x "./scripts/security-monitor.sh"
    
    # Create cron job for monitoring
    cat > "./scripts/setup-cron.sh" <<EOF
#!/bin/bash
# Setup cron jobs for security monitoring

# Add security monitoring to crontab
(crontab -l 2>/dev/null; echo "*/5 * * * * /path/to/oxygen-platform/scripts/security-monitor.sh") | crontab -

# Add log rotation
(crontab -l 2>/dev/null; echo "0 2 * * * /usr/sbin/logrotate /etc/logrotate.d/oxygen-platform") | crontab -
EOF
    
    chmod +x "./scripts/setup-cron.sh"
    
    log_success "Monitoring scripts created"
}

main() {
    log_info "Starting security setup for $PLATFORM_NAME"
    
    # Check if running as root for some operations
    if [[ $EUID -eq 0 ]]; then
        log_warning "Running as root. Some operations will create system directories."
    fi
    
    create_directories
    generate_ssl_certificates
    generate_secrets
    create_security_configs
    setup_firewall
    create_monitoring_scripts
    
    log_success "Security setup completed!"
    log_info "Next steps:"
    echo "1. Review and source the environment file: source $ENV_FILE"
    echo "2. Update your DNS to point to this server"
    echo "3. Run the firewall rules: sudo ./scripts/firewall-rules.sh"
    echo "4. Setup monitoring cron jobs: ./scripts/setup-cron.sh"
    echo "5. Start the platform with security:"
    echo "   Option A (Recommended): ./start-production.sh"
    echo "   Option B (Manual): docker-compose -f docker-compose.yml -f docker-compose.security.yml up -d"
    
    log_warning "Important: Keep the secrets directory secure and backup your SSL certificates!"
}

# Run main function
main "$@"
