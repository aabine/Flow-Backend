#!/bin/bash
# Security monitoring script

LOG_FILE="/var/log/security/security-monitor.log"
ALERT_EMAIL="admin@oxygen-platform.com"

# Check for failed login attempts
check_failed_logins() {
    FAILED_LOGINS=$(grep "authentication_failure" /var/log/oxygen-platform/*.log | wc -l)
    if [ $FAILED_LOGINS -gt 10 ]; then
        echo "$(date): High number of failed logins detected: $FAILED_LOGINS" >> $LOG_FILE
        # Send alert email here
    fi
}

# Check for suspicious IP addresses
check_suspicious_ips() {
    # Check for IPs with high request rates
    tail -n 1000 /var/log/nginx/access.log | awk '{print $1}' | sort | uniq -c | sort -nr | head -10 | while read count ip; do
        if [ $count -gt 100 ]; then
            echo "$(date): Suspicious IP detected: $ip with $count requests" >> $LOG_FILE
        fi
    done
}

# Check SSL certificate expiry
check_ssl_expiry() {
    EXPIRY_DATE=$(openssl x509 -in ./ssl/nginx/cert.pem -noout -enddate | cut -d= -f2)
    EXPIRY_TIMESTAMP=$(date -d "$EXPIRY_DATE" +%s)
    CURRENT_TIMESTAMP=$(date +%s)
    DAYS_UNTIL_EXPIRY=$(( ($EXPIRY_TIMESTAMP - $CURRENT_TIMESTAMP) / 86400 ))
    
    if [ $DAYS_UNTIL_EXPIRY -lt 30 ]; then
        echo "$(date): SSL certificate expires in $DAYS_UNTIL_EXPIRY days" >> $LOG_FILE
    fi
}

# Run checks
check_failed_logins
check_suspicious_ips
check_ssl_expiry
