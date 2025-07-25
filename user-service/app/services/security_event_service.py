"""
Security event logging and audit trail service.
Implements comprehensive security event tracking and monitoring.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from enum import Enum
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.user import User, SecurityEvent
from app.core.config import get_settings

settings = get_settings()


class SecurityEventType(Enum):
    """Security event types for categorization."""
    
    # Authentication events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGIN_BLOCKED = "login_blocked"
    LOGOUT = "logout"
    LOGOUT_ALL = "logout_all"
    
    # Password events
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET_COMPLETED = "password_reset_completed"
    PASSWORD_RESET_FAILED = "password_reset_failed"
    
    # Account events
    ACCOUNT_CREATED = "account_created"
    ACCOUNT_ACTIVATED = "account_activated"
    ACCOUNT_DEACTIVATED = "account_deactivated"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"
    
    # Email verification events
    EMAIL_VERIFICATION_SENT = "email_verification_sent"
    EMAIL_VERIFIED = "email_verified"
    EMAIL_VERIFICATION_FAILED = "email_verification_failed"
    
    # MFA events
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    MFA_CHALLENGE_SENT = "mfa_challenge_sent"
    MFA_VERIFICATION_SUCCESS = "mfa_verification_success"
    MFA_VERIFICATION_FAILED = "mfa_verification_failed"
    MFA_BACKUP_CODE_USED = "mfa_backup_code_used"
    
    # Session events
    SESSION_CREATED = "session_created"
    SESSION_EXPIRED = "session_expired"
    SESSION_REVOKED = "session_revoked"
    TOKEN_REFRESHED = "token_refreshed"
    
    # Profile events
    PROFILE_UPDATED = "profile_updated"
    PROFILE_VIEWED = "profile_viewed"
    
    # Security events
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    INVALID_TOKEN = "invalid_token"
    PERMISSION_DENIED = "permission_denied"
    
    # Admin events
    ADMIN_ACTION = "admin_action"
    USER_IMPERSONATION = "user_impersonation"
    BULK_OPERATION = "bulk_operation"


class SecurityEventSeverity(Enum):
    """Security event severity levels."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityEventService:
    """Security event logging and monitoring service."""
    
    def __init__(self):
        self.high_risk_events = {
            SecurityEventType.LOGIN_BLOCKED,
            SecurityEventType.ACCOUNT_LOCKED,
            SecurityEventType.MFA_DISABLED,
            SecurityEventType.SUSPICIOUS_ACTIVITY,
            SecurityEventType.ADMIN_ACTION,
            SecurityEventType.USER_IMPERSONATION
        }
    
    async def log_security_event(
        self,
        db: AsyncSession,
        event_type: SecurityEventType,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        severity: Optional[SecurityEventSeverity] = None
    ) -> SecurityEvent:
        """Log a security event."""
        
        try:
            # Determine severity if not provided
            if severity is None:
                if event_type in self.high_risk_events:
                    severity = SecurityEventSeverity.HIGH
                elif event_type.value.endswith('_failed'):
                    severity = SecurityEventSeverity.MEDIUM
                else:
                    severity = SecurityEventSeverity.LOW
            
            # Create security event
            security_event = SecurityEvent(
                user_id=user_id,
                event_type=event_type.value,
                event_data=json.dumps(details) if details else None,
                ip_address=ip_address,
                user_agent=user_agent,
                created_at=datetime.utcnow()
            )
            
            db.add(security_event)
            await db.commit()
            await db.refresh(security_event)
            
            # Log to console for immediate visibility
            self._log_to_console(event_type, user_id, ip_address, severity, details)
            
            # Check for suspicious patterns
            await self._check_suspicious_patterns(db, event_type, user_id, ip_address)
            
            return security_event
            
        except Exception as e:
            print(f"Failed to log security event: {e}")
            await db.rollback()
            raise
    
    def _log_to_console(
        self,
        event_type: SecurityEventType,
        user_id: Optional[str],
        ip_address: Optional[str],
        severity: SecurityEventSeverity,
        details: Optional[Dict[str, Any]]
    ):
        """Log security event to console."""
        
        severity_icons = {
            SecurityEventSeverity.LOW: "ℹ️",
            SecurityEventSeverity.MEDIUM: "⚠️",
            SecurityEventSeverity.HIGH: "🚨",
            SecurityEventSeverity.CRITICAL: "🔥"
        }
        
        icon = severity_icons.get(severity, "📝")
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        log_parts = [
            f"{icon} [{severity.value.upper()}]",
            f"[{timestamp}]",
            f"Security Event: {event_type.value}"
        ]
        
        if user_id:
            log_parts.append(f"User: {user_id}")
        
        if ip_address:
            log_parts.append(f"IP: {ip_address}")
        
        if details:
            log_parts.append(f"Details: {json.dumps(details, default=str)}")
        
        print(" | ".join(log_parts))
    
    async def _check_suspicious_patterns(
        self,
        db: AsyncSession,
        event_type: SecurityEventType,
        user_id: Optional[str],
        ip_address: Optional[str]
    ):
        """Check for suspicious activity patterns."""
        
        try:
            # Check for multiple failed logins
            if event_type == SecurityEventType.LOGIN_FAILED:
                await self._check_failed_login_pattern(db, user_id, ip_address)
            
            # Check for rapid successive events
            if ip_address:
                await self._check_rapid_events_pattern(db, ip_address)
            
            # Check for unusual access patterns
            if user_id and event_type == SecurityEventType.LOGIN_SUCCESS:
                await self._check_unusual_access_pattern(db, user_id, ip_address)
                
        except Exception as e:
            print(f"Error checking suspicious patterns: {e}")
    
    async def _check_failed_login_pattern(
        self,
        db: AsyncSession,
        user_id: Optional[str],
        ip_address: Optional[str]
    ):
        """Check for suspicious failed login patterns."""
        
        # Check failed logins from same IP in last 10 minutes
        if ip_address:
            recent_failures = await db.execute(
                select(func.count(SecurityEvent.id)).filter(
                    and_(
                        SecurityEvent.event_type == SecurityEventType.LOGIN_FAILED.value,
                        SecurityEvent.ip_address == ip_address,
                        SecurityEvent.created_at > datetime.utcnow() - timedelta(minutes=10)
                    )
                )
            )
            
            failure_count = recent_failures.scalar()
            if failure_count >= 10:  # 10 failures in 10 minutes
                await self.log_security_event(
                    db,
                    SecurityEventType.SUSPICIOUS_ACTIVITY,
                    user_id=user_id,
                    ip_address=ip_address,
                    details={
                        "pattern": "multiple_failed_logins",
                        "failure_count": failure_count,
                        "time_window": "10_minutes"
                    },
                    severity=SecurityEventSeverity.HIGH
                )
    
    async def _check_rapid_events_pattern(self, db: AsyncSession, ip_address: str):
        """Check for rapid successive events from same IP."""
        
        # Check events in last 1 minute
        recent_events = await db.execute(
            select(func.count(SecurityEvent.id)).filter(
                and_(
                    SecurityEvent.ip_address == ip_address,
                    SecurityEvent.created_at > datetime.utcnow() - timedelta(minutes=1)
                )
            )
        )
        
        event_count = recent_events.scalar()
        if event_count >= 50:  # 50 events in 1 minute
            await self.log_security_event(
                db,
                SecurityEventType.SUSPICIOUS_ACTIVITY,
                ip_address=ip_address,
                details={
                    "pattern": "rapid_events",
                    "event_count": event_count,
                    "time_window": "1_minute"
                },
                severity=SecurityEventSeverity.HIGH
            )
    
    async def _check_unusual_access_pattern(
        self,
        db: AsyncSession,
        user_id: str,
        ip_address: Optional[str]
    ):
        """Check for unusual access patterns for user."""
        
        if not ip_address:
            return
        
        # Check if this is a new IP for the user
        previous_logins = await db.execute(
            select(SecurityEvent).filter(
                and_(
                    SecurityEvent.user_id == user_id,
                    SecurityEvent.event_type == SecurityEventType.LOGIN_SUCCESS.value,
                    SecurityEvent.ip_address != ip_address,
                    SecurityEvent.created_at > datetime.utcnow() - timedelta(days=30)
                )
            ).limit(1)
        )
        
        has_previous_logins = previous_logins.scalar_one_or_none() is not None
        
        if has_previous_logins:
            # This is a new IP for an existing user
            await self.log_security_event(
                db,
                SecurityEventType.SUSPICIOUS_ACTIVITY,
                user_id=user_id,
                ip_address=ip_address,
                details={
                    "pattern": "new_ip_login",
                    "description": "Login from new IP address"
                },
                severity=SecurityEventSeverity.MEDIUM
            )
    
    async def get_user_security_events(
        self,
        db: AsyncSession,
        user_id: str,
        limit: int = 50,
        event_types: Optional[List[SecurityEventType]] = None
    ) -> List[Dict[str, Any]]:
        """Get security events for a user."""
        
        try:
            query = select(SecurityEvent).filter(SecurityEvent.user_id == user_id)
            
            if event_types:
                event_type_values = [et.value for et in event_types]
                query = query.filter(SecurityEvent.event_type.in_(event_type_values))
            
            query = query.order_by(desc(SecurityEvent.created_at)).limit(limit)
            
            result = await db.execute(query)
            events = result.scalars().all()
            
            return [
                {
                    "id": str(event.id),
                    "event_type": event.event_type,
                    "ip_address": event.ip_address,
                    "user_agent": event.user_agent,
                    "details": json.loads(event.event_data) if event.event_data else None,
                    "created_at": event.created_at
                }
                for event in events
            ]
            
        except Exception as e:
            print(f"Error getting user security events: {e}")
            return []
    
    async def get_security_summary(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get security summary for a user."""
        
        try:
            since_date = datetime.utcnow() - timedelta(days=days)
            
            # Get event counts by type
            result = await db.execute(
                select(
                    SecurityEvent.event_type,
                    func.count(SecurityEvent.id).label('count')
                ).filter(
                    and_(
                        SecurityEvent.user_id == user_id,
                        SecurityEvent.created_at > since_date
                    )
                ).group_by(SecurityEvent.event_type)
            )
            
            event_counts = {row.event_type: row.count for row in result}
            
            # Get recent suspicious activities
            suspicious_events = await db.execute(
                select(SecurityEvent).filter(
                    and_(
                        SecurityEvent.user_id == user_id,
                        SecurityEvent.event_type == SecurityEventType.SUSPICIOUS_ACTIVITY.value,
                        SecurityEvent.created_at > since_date
                    )
                ).order_by(desc(SecurityEvent.created_at)).limit(5)
            )
            
            suspicious_activities = [
                {
                    "event_type": event.event_type,
                    "details": json.loads(event.event_data) if event.event_data else None,
                    "ip_address": event.ip_address,
                    "created_at": event.created_at
                }
                for event in suspicious_events.scalars().all()
            ]
            
            return {
                "period_days": days,
                "event_counts": event_counts,
                "total_events": sum(event_counts.values()),
                "suspicious_activities": suspicious_activities,
                "security_score": self._calculate_security_score(event_counts, suspicious_activities)
            }
            
        except Exception as e:
            print(f"Error getting security summary: {e}")
            return {
                "period_days": days,
                "event_counts": {},
                "total_events": 0,
                "suspicious_activities": [],
                "security_score": 100
            }
    
    def _calculate_security_score(
        self,
        event_counts: Dict[str, int],
        suspicious_activities: List[Dict[str, Any]]
    ) -> int:
        """Calculate a security score (0-100) based on recent activity."""
        
        score = 100
        
        # Deduct points for failed events
        failed_logins = event_counts.get(SecurityEventType.LOGIN_FAILED.value, 0)
        score -= min(failed_logins * 2, 20)  # Max 20 points for failed logins
        
        # Deduct points for suspicious activities
        score -= len(suspicious_activities) * 10  # 10 points per suspicious activity
        
        # Deduct points for account lockouts
        lockouts = event_counts.get(SecurityEventType.ACCOUNT_LOCKED.value, 0)
        score -= lockouts * 15
        
        return max(score, 0)


# Global security event service instance
security_event_service = SecurityEventService()
