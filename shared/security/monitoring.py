"""
Comprehensive security monitoring, logging, and alerting system.
Implements real-time threat detection, incident response, and security analytics.
"""

import json
import logging
import smtplib
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
import redis
import os

from .encryption import data_masking

logger = logging.getLogger(__name__)


class SecurityEventSeverity(Enum):
    """Security event severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityEventType(Enum):
    """Types of security events."""
    AUTHENTICATION_FAILURE = "authentication_failure"
    AUTHORIZATION_FAILURE = "authorization_failure"
    BRUTE_FORCE_ATTACK = "brute_force_attack"
    SQL_INJECTION_ATTEMPT = "sql_injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    SUSPICIOUS_USER_AGENT = "suspicious_user_agent"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    PAYMENT_FRAUD = "payment_fraud"
    DATA_BREACH_ATTEMPT = "data_breach_attempt"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    MALWARE_DETECTED = "malware_detected"
    UNUSUAL_ACTIVITY = "unusual_activity"


class SecurityMonitor:
    """Real-time security monitoring and alerting system."""
    
    def __init__(self):
        self.redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        self.alert_handlers = []
        self.event_processors = {}
        
        # Thresholds for different event types
        self.thresholds = {
            SecurityEventType.AUTHENTICATION_FAILURE: {"count": 5, "window": 300},  # 5 failures in 5 minutes
            SecurityEventType.RATE_LIMIT_EXCEEDED: {"count": 3, "window": 600},     # 3 rate limits in 10 minutes
            SecurityEventType.PAYMENT_FRAUD: {"count": 1, "window": 60},           # 1 fraud attempt in 1 minute
            SecurityEventType.SQL_INJECTION_ATTEMPT: {"count": 1, "window": 60},   # 1 SQL injection in 1 minute
        }
        
        # Setup default event processors
        self._setup_default_processors()
    
    def _setup_default_processors(self):
        """Setup default event processors."""
        
        self.event_processors[SecurityEventType.AUTHENTICATION_FAILURE] = self._process_auth_failure
        self.event_processors[SecurityEventType.BRUTE_FORCE_ATTACK] = self._process_brute_force
        self.event_processors[SecurityEventType.PAYMENT_FRAUD] = self._process_payment_fraud
        self.event_processors[SecurityEventType.SQL_INJECTION_ATTEMPT] = self._process_sql_injection
    
    async def log_security_event(
        self,
        event_type: SecurityEventType,
        severity: SecurityEventSeverity,
        source_service: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Dict[str, Any] = None,
        raw_data: Dict[str, Any] = None
    ) -> str:
        """Log a security event and trigger processing."""
        
        event_id = f"sec_{int(datetime.utcnow().timestamp())}_{hash(str(details))}"
        
        # Create event record
        event = {
            "event_id": event_id,
            "event_type": event_type.value,
            "severity": severity.value,
            "source_service": source_service,
            "user_id": user_id,
            "ip_address": ip_address,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {},
            "raw_data": raw_data or {},
            "processed": False
        }
        
        # Mask sensitive data for logging
        masked_event = data_masking.mask_sensitive_dict(event)
        
        # Log to application logger
        log_message = f"Security Event [{severity.value.upper()}]: {event_type.value}"
        if severity in [SecurityEventSeverity.HIGH, SecurityEventSeverity.CRITICAL]:
            logger.warning(f"{log_message} - {json.dumps(masked_event)}")
        else:
            logger.info(f"{log_message} - {json.dumps(masked_event)}")
        
        # Store in Redis for real-time processing
        await self._store_event(event)
        
        # Process event
        await self._process_event(event)
        
        return event_id
    
    async def _store_event(self, event: Dict[str, Any]):
        """Store event in Redis for analysis."""
        
        event_key = f"security_event:{event['event_id']}"
        
        # Store individual event
        self.redis_client.setex(event_key, 86400, json.dumps(event))  # Keep for 24 hours
        
        # Add to event type timeline
        timeline_key = f"security_timeline:{event['event_type']}"
        self.redis_client.zadd(timeline_key, {event['event_id']: event['timestamp']})
        self.redis_client.expire(timeline_key, 86400)
        
        # Add to IP-based timeline if IP is available
        if event.get('ip_address'):
            ip_key = f"security_ip:{event['ip_address']}"
            self.redis_client.zadd(ip_key, {event['event_id']: event['timestamp']})
            self.redis_client.expire(ip_key, 86400)
        
        # Add to user-based timeline if user is available
        if event.get('user_id'):
            user_key = f"security_user:{event['user_id']}"
            self.redis_client.zadd(user_key, {event['event_id']: event['timestamp']})
            self.redis_client.expire(user_key, 86400)
    
    async def _process_event(self, event: Dict[str, Any]):
        """Process security event and trigger alerts if needed."""
        
        event_type = SecurityEventType(event['event_type'])
        
        # Check if we have a specific processor for this event type
        if event_type in self.event_processors:
            await self.event_processors[event_type](event)
        
        # Check thresholds for alerting
        await self._check_thresholds(event)
        
        # Mark event as processed
        event['processed'] = True
        event_key = f"security_event:{event['event_id']}"
        self.redis_client.setex(event_key, 86400, json.dumps(event))
    
    async def _check_thresholds(self, event: Dict[str, Any]):
        """Check if event triggers threshold-based alerts."""
        
        event_type = SecurityEventType(event['event_type'])
        
        if event_type not in self.thresholds:
            return
        
        threshold_config = self.thresholds[event_type]
        window_seconds = threshold_config['window']
        max_count = threshold_config['count']
        
        # Check event count in time window
        current_time = datetime.utcnow().timestamp()
        window_start = current_time - window_seconds
        
        timeline_key = f"security_timeline:{event_type.value}"
        event_count = self.redis_client.zcount(timeline_key, window_start, current_time)
        
        if event_count >= max_count:
            await self._trigger_alert(
                f"Security threshold exceeded: {event_type.value}",
                SecurityEventSeverity.HIGH,
                {
                    "event_type": event_type.value,
                    "count": event_count,
                    "threshold": max_count,
                    "window_seconds": window_seconds,
                    "latest_event": event
                }
            )
    
    async def _process_auth_failure(self, event: Dict[str, Any]):
        """Process authentication failure events."""
        
        ip_address = event.get('ip_address')
        user_id = event.get('user_id')
        
        if ip_address:
            # Check for brute force from IP
            ip_key = f"security_ip:{ip_address}"
            recent_failures = self.redis_client.zcount(
                ip_key,
                datetime.utcnow().timestamp() - 300,  # Last 5 minutes
                datetime.utcnow().timestamp()
            )
            
            if recent_failures >= 10:  # 10 failures from same IP
                await self.log_security_event(
                    SecurityEventType.BRUTE_FORCE_ATTACK,
                    SecurityEventSeverity.HIGH,
                    event['source_service'],
                    user_id,
                    ip_address,
                    {"failure_count": recent_failures, "detection_method": "ip_analysis"}
                )
    
    async def _process_brute_force(self, event: Dict[str, Any]):
        """Process brute force attack events."""
        
        await self._trigger_alert(
            "Brute force attack detected",
            SecurityEventSeverity.HIGH,
            event
        )
        
        # Automatically block IP if configured
        ip_address = event.get('ip_address')
        if ip_address and os.getenv('AUTO_BLOCK_SUSPICIOUS_IPS', 'false').lower() == 'true':
            await self._block_ip_address(ip_address, duration=3600)  # Block for 1 hour
    
    async def _process_payment_fraud(self, event: Dict[str, Any]):
        """Process payment fraud events."""
        
        await self._trigger_alert(
            "Payment fraud detected",
            SecurityEventSeverity.CRITICAL,
            event
        )
        
        # Additional fraud-specific processing
        user_id = event.get('user_id')
        if user_id:
            # Flag user for manual review
            self.redis_client.setex(f"fraud_flag:{user_id}", 86400, "payment_fraud")
    
    async def _process_sql_injection(self, event: Dict[str, Any]):
        """Process SQL injection attempt events."""
        
        await self._trigger_alert(
            "SQL injection attempt detected",
            SecurityEventSeverity.CRITICAL,
            event
        )
        
        # Block IP immediately for SQL injection attempts
        ip_address = event.get('ip_address')
        if ip_address:
            await self._block_ip_address(ip_address, duration=86400)  # Block for 24 hours
    
    async def _trigger_alert(
        self,
        message: str,
        severity: SecurityEventSeverity,
        event_data: Dict[str, Any]
    ):
        """Trigger security alert through configured channels."""
        
        alert = {
            "alert_id": f"alert_{int(datetime.utcnow().timestamp())}",
            "message": message,
            "severity": severity.value,
            "timestamp": datetime.utcnow().isoformat(),
            "event_data": event_data
        }
        
        # Send through all configured alert handlers
        for handler in self.alert_handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error(f"Alert handler failed: {str(e)}")
    
    async def _block_ip_address(self, ip_address: str, duration: int = 3600):
        """Block IP address for specified duration."""
        
        block_key = f"blocked_ip:{ip_address}"
        self.redis_client.setex(block_key, duration, "blocked")
        
        logger.warning(f"IP address blocked: {ip_address} for {duration} seconds")
    
    def add_alert_handler(self, handler: Callable):
        """Add an alert handler function."""
        self.alert_handlers.append(handler)
    
    async def get_security_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """Get security metrics for the specified time period."""
        
        end_time = datetime.utcnow().timestamp()
        start_time = end_time - (hours * 3600)
        
        metrics = {
            "time_period_hours": hours,
            "total_events": 0,
            "events_by_type": {},
            "events_by_severity": {},
            "top_source_ips": [],
            "affected_users": 0
        }
        
        # Count events by type
        for event_type in SecurityEventType:
            timeline_key = f"security_timeline:{event_type.value}"
            count = self.redis_client.zcount(timeline_key, start_time, end_time)
            if count > 0:
                metrics["events_by_type"][event_type.value] = count
                metrics["total_events"] += count
        
        # Get top source IPs
        all_ips = set()
        for key in self.redis_client.scan_iter(match="security_ip:*"):
            ip = key.decode().split(":")[-1]
            count = self.redis_client.zcount(key, start_time, end_time)
            if count > 0:
                all_ips.add((ip, count))
        
        metrics["top_source_ips"] = sorted(all_ips, key=lambda x: x[1], reverse=True)[:10]
        
        # Count affected users
        affected_users = set()
        for key in self.redis_client.scan_iter(match="security_user:*"):
            user_id = key.decode().split(":")[-1]
            count = self.redis_client.zcount(key, start_time, end_time)
            if count > 0:
                affected_users.add(user_id)
        
        metrics["affected_users"] = len(affected_users)
        
        return metrics


class EmailAlertHandler:
    """Email alert handler for security notifications."""
    
    def __init__(self, smtp_server: str, smtp_port: int, username: str, password: str, recipients: List[str]):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.recipients = recipients
    
    async def __call__(self, alert: Dict[str, Any]):
        """Send email alert."""
        
        subject = f"[SECURITY ALERT] {alert['severity'].upper()}: {alert['message']}"
        
        # Create email content
        body = f"""
Security Alert Details:

Alert ID: {alert['alert_id']}
Severity: {alert['severity'].upper()}
Timestamp: {alert['timestamp']}
Message: {alert['message']}

Event Data:
{json.dumps(alert['event_data'], indent=2)}

This is an automated security alert from the Oxygen Supply Platform.
Please investigate immediately if this is a HIGH or CRITICAL severity alert.
        """
        
        # Send email
        try:
            msg = MimeMultipart()
            msg['From'] = self.username
            msg['To'] = ', '.join(self.recipients)
            msg['Subject'] = subject
            
            msg.attach(MimeText(body, 'plain'))
            
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Security alert email sent: {alert['alert_id']}")
            
        except Exception as e:
            logger.error(f"Failed to send security alert email: {str(e)}")


class SlackAlertHandler:
    """Slack alert handler for security notifications."""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def __call__(self, alert: Dict[str, Any]):
        """Send Slack alert."""
        
        severity_colors = {
            "low": "#36a64f",
            "medium": "#ff9500", 
            "high": "#ff0000",
            "critical": "#8B0000"
        }
        
        color = severity_colors.get(alert['severity'], "#808080")
        
        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"Security Alert: {alert['message']}",
                    "fields": [
                        {
                            "title": "Severity",
                            "value": alert['severity'].upper(),
                            "short": True
                        },
                        {
                            "title": "Alert ID",
                            "value": alert['alert_id'],
                            "short": True
                        },
                        {
                            "title": "Timestamp",
                            "value": alert['timestamp'],
                            "short": False
                        }
                    ],
                    "footer": "Oxygen Supply Platform Security",
                    "ts": int(datetime.utcnow().timestamp())
                }
            ]
        }
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(self.webhook_url, json=payload)
                if response.status_code == 200:
                    logger.info(f"Security alert sent to Slack: {alert['alert_id']}")
                else:
                    logger.error(f"Failed to send Slack alert: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {str(e)}")


# Global security monitor instance
security_monitor = SecurityMonitor()

# Setup alert handlers if configured
if os.getenv('SMTP_SERVER'):
    email_handler = EmailAlertHandler(
        smtp_server=os.getenv('SMTP_SERVER'),
        smtp_port=int(os.getenv('SMTP_PORT', '587')),
        username=os.getenv('SMTP_USERNAME'),
        password=os.getenv('SMTP_PASSWORD'),
        recipients=os.getenv('SECURITY_ALERT_EMAILS', '').split(',')
    )
    security_monitor.add_alert_handler(email_handler)

if os.getenv('SLACK_WEBHOOK_URL'):
    slack_handler = SlackAlertHandler(os.getenv('SLACK_WEBHOOK_URL'))
    security_monitor.add_alert_handler(slack_handler)
