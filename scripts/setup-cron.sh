#!/bin/bash
# Setup cron jobs for security monitoring

# Add security monitoring to crontab
(crontab -l 2>/dev/null; echo "*/5 * * * * /path/to/oxygen-platform/scripts/security-monitor.sh") | crontab -

# Add log rotation
(crontab -l 2>/dev/null; echo "0 2 * * * /usr/sbin/logrotate /etc/logrotate.d/oxygen-platform") | crontab -
