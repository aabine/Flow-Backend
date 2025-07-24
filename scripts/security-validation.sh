#!/bin/bash

# Comprehensive Security Validation Script for Oxygen Supply Platform
# This script performs security checks, vulnerability scanning, and compliance validation

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PLATFORM_NAME="Oxygen Supply Platform"
REPORT_DIR="./security-reports"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_FILE="$REPORT_DIR/security_validation_$TIMESTAMP.json"

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

# Initialize report
init_report() {
    mkdir -p "$REPORT_DIR"
    
    cat > "$REPORT_FILE" <<EOF
{
    "platform": "$PLATFORM_NAME",
    "validation_timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "validation_version": "1.0",
    "checks": {},
    "summary": {
        "total_checks": 0,
        "passed": 0,
        "failed": 0,
        "warnings": 0
    },
    "recommendations": []
}
EOF
}

# Update report with check result
update_report() {
    local check_name="$1"
    local status="$2"
    local details="$3"
    
    # Use jq to update the JSON report
    if command -v jq >/dev/null 2>&1; then
        tmp_file=$(mktemp)
        jq --arg name "$check_name" --arg status "$status" --arg details "$details" \
           '.checks[$name] = {"status": $status, "details": $details, "timestamp": now | strftime("%Y-%m-%dT%H:%M:%SZ")}' \
           "$REPORT_FILE" > "$tmp_file" && mv "$tmp_file" "$REPORT_FILE"
    fi
}

# Check 1: SSL/TLS Configuration
check_ssl_configuration() {
    log_info "Checking SSL/TLS configuration..."
    
    local status="PASS"
    local details=""
    
    # Check if SSL certificates exist
    if [[ -f "./ssl/nginx/cert.pem" && -f "./ssl/nginx/key.pem" ]]; then
        # Check certificate validity
        if openssl x509 -in ./ssl/nginx/cert.pem -noout -checkend 2592000 >/dev/null 2>&1; then
            details="SSL certificates are valid and not expiring within 30 days"
            log_success "SSL certificates are valid"
        else
            status="WARNING"
            details="SSL certificates are expiring within 30 days"
            log_warning "SSL certificates are expiring soon"
        fi
    else
        status="FAIL"
        details="SSL certificates not found"
        log_error "SSL certificates not found"
    fi
    
    update_report "ssl_configuration" "$status" "$details"
}

# Check 2: Environment Security
check_environment_security() {
    log_info "Checking environment security..."
    
    local status="PASS"
    local details=""
    local issues=()
    
    # Check for .env files in version control
    if git ls-files | grep -q "\.env$"; then
        issues+=("Environment files found in version control")
        status="FAIL"
    fi
    
    # Check for hardcoded secrets in code
    if grep -r -i "password\s*=" --include="*.py" --include="*.js" --include="*.yml" . | grep -v "test" | grep -v "example" >/dev/null 2>&1; then
        issues+=("Potential hardcoded passwords found")
        status="WARNING"
    fi
    
    # Check file permissions
    if [[ -f ".env.security" ]]; then
        perm=$(stat -c "%a" .env.security 2>/dev/null || stat -f "%A" .env.security 2>/dev/null || echo "unknown")
        if [[ "$perm" != "600" ]]; then
            issues+=("Insecure permissions on .env.security file: $perm")
            status="WARNING"
        fi
    fi
    
    if [[ ${#issues[@]} -eq 0 ]]; then
        details="Environment security checks passed"
        log_success "Environment security is good"
    else
        details=$(IFS="; "; echo "${issues[*]}")
        log_warning "Environment security issues found: $details"
    fi
    
    update_report "environment_security" "$status" "$details"
}

# Check 3: Docker Security
check_docker_security() {
    log_info "Checking Docker security configuration..."
    
    local status="PASS"
    local details=""
    local issues=()
    
    # Check if docker-compose.security.yml exists
    if [[ ! -f "docker-compose.security.yml" ]]; then
        issues+=("Security Docker Compose file not found")
        status="FAIL"
    else
        # Check for security configurations
        if ! grep -q "no-new-privileges" docker-compose.security.yml; then
            issues+=("no-new-privileges not configured")
            status="WARNING"
        fi
        
        if ! grep -q "read_only: true" docker-compose.security.yml; then
            issues+=("Read-only containers not configured")
            status="WARNING"
        fi
        
        if ! grep -q "cap_drop:" docker-compose.security.yml; then
            issues+=("Capability dropping not configured")
            status="WARNING"
        fi
    fi
    
    if [[ ${#issues[@]} -eq 0 ]]; then
        details="Docker security configuration is good"
        log_success "Docker security is properly configured"
    else
        details=$(IFS="; "; echo "${issues[*]}")
        log_warning "Docker security issues: $details"
    fi
    
    update_report "docker_security" "$status" "$details"
}

# Check 4: Network Security
check_network_security() {
    log_info "Checking network security..."
    
    local status="PASS"
    local details=""
    local issues=()
    
    # Check Nginx configuration
    if [[ -f "nginx/nginx.conf" ]]; then
        if ! grep -q "ssl_protocols TLSv1.2 TLSv1.3" nginx/nginx.conf; then
            issues+=("Weak SSL protocols allowed")
            status="WARNING"
        fi
        
        if ! grep -q "add_header.*Strict-Transport-Security" nginx/nginx.conf; then
            issues+=("HSTS header not configured")
            status="WARNING"
        fi
        
        if ! grep -q "limit_req_zone" nginx/nginx.conf; then
            issues+=("Rate limiting not configured")
            status="WARNING"
        fi
    else
        issues+=("Nginx configuration not found")
        status="FAIL"
    fi
    
    if [[ ${#issues[@]} -eq 0 ]]; then
        details="Network security configuration is good"
        log_success "Network security is properly configured"
    else
        details=$(IFS="; "; echo "${issues[*]}")
        log_warning "Network security issues: $details"
    fi
    
    update_report "network_security" "$status" "$details"
}

# Check 5: Database Security
check_database_security() {
    log_info "Checking database security..."
    
    local status="PASS"
    local details=""
    local issues=()
    
    # Check for SSL configuration in environment
    if [[ -f ".env.security" ]]; then
        if ! grep -q "DB_SSL_MODE=require" .env.security; then
            issues+=("Database SSL not required")
            status="WARNING"
        fi
        
        if ! grep -q "DB_AUDIT_LOGGING=true" .env.security; then
            issues+=("Database audit logging not enabled")
            status="WARNING"
        fi
    else
        issues+=("Security environment file not found")
        status="FAIL"
    fi
    
    # Check for database credentials in code
    if grep -r -i "postgres://\|postgresql://" --include="*.py" --include="*.yml" . | grep -v "localhost" | grep -v "example" >/dev/null 2>&1; then
        issues+=("Hardcoded database URLs found")
        status="FAIL"
    fi
    
    if [[ ${#issues[@]} -eq 0 ]]; then
        details="Database security configuration is good"
        log_success "Database security is properly configured"
    else
        details=$(IFS="; "; echo "${issues[*]}")
        log_warning "Database security issues: $details"
    fi
    
    update_report "database_security" "$status" "$details"
}

# Check 6: API Security
check_api_security() {
    log_info "Checking API security..."
    
    local status="PASS"
    local details=""
    local issues=()
    
    # Check for security middleware
    if ! find . -name "*.py" -exec grep -l "SecurityHeadersMiddleware\|RateLimitMiddleware" {} \; | head -1 >/dev/null; then
        issues+=("Security middleware not found")
        status="WARNING"
    fi
    
    # Check for input validation
    if ! find . -name "*.py" -exec grep -l "SecureValidator\|validate_string" {} \; | head -1 >/dev/null; then
        issues+=("Input validation not implemented")
        status="FAIL"
    fi
    
    # Check for CORS configuration
    if grep -r "allow_origins.*\*" --include="*.py" . >/dev/null 2>&1; then
        issues+=("Wildcard CORS origins found")
        status="WARNING"
    fi
    
    if [[ ${#issues[@]} -eq 0 ]]; then
        details="API security implementation is good"
        log_success "API security is properly implemented"
    else
        details=$(IFS="; "; echo "${issues[*]}")
        log_warning "API security issues: $details"
    fi
    
    update_report "api_security" "$status" "$details"
}

# Check 7: Authentication Security
check_authentication_security() {
    log_info "Checking authentication security..."
    
    local status="PASS"
    local details=""
    local issues=()
    
    # Check for JWT implementation
    if ! find . -name "*.py" -exec grep -l "jwt_manager\|JWT" {} \; | head -1 >/dev/null; then
        issues+=("JWT implementation not found")
        status="FAIL"
    fi
    
    # Check for password hashing
    if ! find . -name "*.py" -exec grep -l "bcrypt\|password_manager" {} \; | head -1 >/dev/null; then
        issues+=("Secure password hashing not found")
        status="FAIL"
    fi
    
    # Check for MFA implementation
    if ! find . -name "*.py" -exec grep -l "mfa\|totp\|MFA" {} \; | head -1 >/dev/null; then
        issues+=("MFA implementation not found")
        status="WARNING"
    fi
    
    if [[ ${#issues[@]} -eq 0 ]]; then
        details="Authentication security is properly implemented"
        log_success "Authentication security is good"
    else
        details=$(IFS="; "; echo "${issues[*]}")
        log_warning "Authentication security issues: $details"
    fi
    
    update_report "authentication_security" "$status" "$details"
}

# Check 8: Data Protection
check_data_protection() {
    log_info "Checking data protection measures..."
    
    local status="PASS"
    local details=""
    local issues=()
    
    # Check for encryption implementation
    if ! find . -name "*.py" -exec grep -l "encryption_manager\|encrypt_field" {} \; | head -1 >/dev/null; then
        issues+=("Data encryption not implemented")
        status="FAIL"
    fi
    
    # Check for data masking
    if ! find . -name "*.py" -exec grep -l "data_masking\|mask_" {} \; | head -1 >/dev/null; then
        issues+=("Data masking not implemented")
        status="WARNING"
    fi
    
    # Check for GDPR compliance
    if ! find . -name "*.py" -exec grep -l "gdpr\|consent\|privacy" {} \; | head -1 >/dev/null; then
        issues+=("GDPR compliance features not found")
        status="WARNING"
    fi
    
    if [[ ${#issues[@]} -eq 0 ]]; then
        details="Data protection measures are properly implemented"
        log_success "Data protection is good"
    else
        details=$(IFS="; "; echo "${issues[*]}")
        log_warning "Data protection issues: $details"
    fi
    
    update_report "data_protection" "$status" "$details"
}

# Check 9: Security Monitoring
check_security_monitoring() {
    log_info "Checking security monitoring..."
    
    local status="PASS"
    local details=""
    local issues=()
    
    # Check for security monitoring implementation
    if ! find . -name "*.py" -exec grep -l "security_monitor\|SecurityEvent" {} \; | head -1 >/dev/null; then
        issues+=("Security monitoring not implemented")
        status="FAIL"
    fi
    
    # Check for logging configuration
    if ! find . -name "*.py" -exec grep -l "logging\|logger" {} \; | head -1 >/dev/null; then
        issues+=("Logging not properly configured")
        status="WARNING"
    fi
    
    # Check for audit logging
    if ! find . -name "*.py" -exec grep -l "audit\|_log_security_event" {} \; | head -1 >/dev/null; then
        issues+=("Audit logging not implemented")
        status="WARNING"
    fi
    
    if [[ ${#issues[@]} -eq 0 ]]; then
        details="Security monitoring is properly implemented"
        log_success "Security monitoring is good"
    else
        details=$(IFS="; "; echo "${issues[*]}")
        log_warning "Security monitoring issues: $details"
    fi
    
    update_report "security_monitoring" "$status" "$details"
}

# Run security tests
run_security_tests() {
    log_info "Running security test suite..."
    
    local status="PASS"
    local details=""
    
    if [[ -f "tests/security/test_security_suite.py" ]]; then
        if python -m pytest tests/security/test_security_suite.py -v --tb=short >/dev/null 2>&1; then
            details="All security tests passed"
            log_success "Security tests passed"
        else
            status="FAIL"
            details="Some security tests failed"
            log_error "Security tests failed"
        fi
    else
        status="WARNING"
        details="Security test suite not found"
        log_warning "Security test suite not found"
    fi
    
    update_report "security_tests" "$status" "$details"
}

# Generate final report
generate_final_report() {
    log_info "Generating final security validation report..."
    
    if command -v jq >/dev/null 2>&1; then
        # Calculate summary statistics
        local total_checks=$(jq '.checks | length' "$REPORT_FILE")
        local passed=$(jq '[.checks[] | select(.status == "PASS")] | length' "$REPORT_FILE")
        local failed=$(jq '[.checks[] | select(.status == "FAIL")] | length' "$REPORT_FILE")
        local warnings=$(jq '[.checks[] | select(.status == "WARNING")] | length' "$REPORT_FILE")
        
        # Update summary
        tmp_file=$(mktemp)
        jq --arg total "$total_checks" --arg passed "$passed" --arg failed "$failed" --arg warnings "$warnings" \
           '.summary.total_checks = ($total | tonumber) | .summary.passed = ($passed | tonumber) | .summary.failed = ($failed | tonumber) | .summary.warnings = ($warnings | tonumber)' \
           "$REPORT_FILE" > "$tmp_file" && mv "$tmp_file" "$REPORT_FILE"
        
        # Display summary
        echo
        log_info "Security Validation Summary:"
        echo "  Total Checks: $total_checks"
        echo "  Passed: $passed"
        echo "  Failed: $failed"
        echo "  Warnings: $warnings"
        echo
        
        if [[ $failed -eq 0 ]]; then
            log_success "Security validation completed successfully!"
            if [[ $warnings -gt 0 ]]; then
                log_warning "Please review warnings in the report: $REPORT_FILE"
            fi
        else
            log_error "Security validation failed! Please review: $REPORT_FILE"
            return 1
        fi
    fi
    
    log_info "Full report saved to: $REPORT_FILE"
}

# Main execution
main() {
    echo "🔒 Starting Security Validation for $PLATFORM_NAME"
    echo "=================================================="
    
    init_report
    
    # Run all security checks
    check_ssl_configuration
    check_environment_security
    check_docker_security
    check_network_security
    check_database_security
    check_api_security
    check_authentication_security
    check_data_protection
    check_security_monitoring
    run_security_tests
    
    # Generate final report
    generate_final_report
}

# Run main function
main "$@"
