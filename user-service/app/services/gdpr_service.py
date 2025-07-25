"""
GDPR compliance service for data export and deletion.
Implements user data export and right to be forgotten functionality.
"""

import json
import zipfile
import io
from datetime import datetime
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.user import (User, UserProfile, VendorProfile, HospitalProfile, 
                            UserSession, SecurityEvent, LoginAttempt, 
                            PasswordResetToken, EmailVerificationToken, MFADevice)
from app.core.config import get_settings

settings = get_settings()


class GDPRService:
    """GDPR compliance service for data export and deletion."""
    
    def __init__(self):
        self.export_format_version = "1.0"
    
    async def export_user_data(
        self,
        db: AsyncSession,
        user_id: str,
        include_security_logs: bool = True
    ) -> bytes:
        """
        Export all user data in GDPR-compliant format.
        Returns ZIP file containing JSON data.
        """
        try:
            # Collect all user data
            user_data = await self._collect_user_data(db, user_id, include_security_logs)
            
            # Create ZIP file in memory
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Add main user data
                zip_file.writestr(
                    "user_data.json",
                    json.dumps(user_data, indent=2, default=str)
                )
                
                # Add data export metadata
                metadata = {
                    "export_date": datetime.utcnow().isoformat(),
                    "export_format_version": self.export_format_version,
                    "user_id": user_id,
                    "data_categories": list(user_data.keys()),
                    "gdpr_notice": "This export contains all personal data we have about you as required by GDPR Article 20."
                }
                
                zip_file.writestr(
                    "export_metadata.json",
                    json.dumps(metadata, indent=2, default=str)
                )
                
                # Add human-readable summary
                summary = self._generate_data_summary(user_data)
                zip_file.writestr("data_summary.txt", summary)
            
            zip_buffer.seek(0)
            return zip_buffer.getvalue()
            
        except Exception as e:
            raise Exception(f"Failed to export user data: {str(e)}")
    
    async def _collect_user_data(
        self,
        db: AsyncSession,
        user_id: str,
        include_security_logs: bool
    ) -> Dict[str, Any]:
        """Collect all user data from database."""
        
        import uuid
        user_uuid = uuid.UUID(user_id)
        
        data = {}
        
        # Basic user information
        user_result = await db.execute(
            select(User).filter(User.id == user_uuid)
        )
        user = user_result.scalar_one_or_none()
        
        if user:
            data["user_account"] = {
                "id": str(user.id),
                "email": user.email,
                "role": user.role.value,
                "is_active": user.is_active,
                "email_verified": user.email_verified,
                "mfa_enabled": user.mfa_enabled,
                "created_at": user.created_at,
                "last_login": user.last_login,
                "password_changed_at": user.password_changed_at,
                "failed_login_attempts": user.failed_login_attempts,
                "account_locked_until": user.account_locked_until
            }
        
        # User profile
        profile_result = await db.execute(
            select(UserProfile).filter(UserProfile.user_id == user_uuid)
        )
        profile = profile_result.scalar_one_or_none()
        
        if profile:
            data["user_profile"] = {
                "first_name": profile.first_name,
                "last_name": profile.last_name,
                "phone_number": profile.phone_number,
                "address": profile.address,
                "date_of_birth": profile.date_of_birth,
                "avatar_url": profile.avatar_url,
                "created_at": profile.created_at,
                "updated_at": profile.updated_at
            }
        
        # Vendor profile (if applicable)
        vendor_result = await db.execute(
            select(VendorProfile).filter(VendorProfile.user_id == user_uuid)
        )
        vendor = vendor_result.scalar_one_or_none()
        
        if vendor:
            data["vendor_profile"] = {
                "business_name": vendor.business_name,
                "registration_number": vendor.registration_number,
                "tax_identification_number": vendor.tax_identification_number,
                "contact_person": vendor.contact_person,
                "contact_phone": vendor.contact_phone,
                "business_address": vendor.business_address,
                "delivery_radius_km": vendor.delivery_radius_km,
                "operating_hours": vendor.operating_hours,
                "emergency_service": vendor.emergency_service,
                "minimum_order_value": vendor.minimum_order_value,
                "payment_terms": vendor.payment_terms,
                "supplier_onboarding_status": vendor.supplier_onboarding_status.value if vendor.supplier_onboarding_status else None,
                "supplier_onboarding_response_time": vendor.supplier_onboarding_response_time,
                "created_at": vendor.created_at,
                "updated_at": vendor.updated_at
            }
        
        # Hospital profile (if applicable)
        hospital_result = await db.execute(
            select(HospitalProfile).filter(HospitalProfile.user_id == user_uuid)
        )
        hospital = hospital_result.scalar_one_or_none()
        
        if hospital:
            data["hospital_profile"] = {
                "hospital_name": hospital.hospital_name,
                "registration_number": hospital.registration_number,
                "license_number": hospital.license_number,
                "contact_person": hospital.contact_person,
                "contact_phone": hospital.contact_phone,
                "emergency_contact": hospital.emergency_contact,
                "bed_capacity": hospital.bed_capacity,
                "hospital_type": hospital.hospital_type,
                "services_offered": hospital.services_offered,
                "created_at": hospital.created_at,
                "updated_at": hospital.updated_at
            }
        
        # User sessions
        sessions_result = await db.execute(
            select(UserSession).filter(UserSession.user_id == user_uuid)
        )
        sessions = sessions_result.scalars().all()
        
        data["user_sessions"] = [
            {
                "id": str(session.id),
                "ip_address": session.ip_address,
                "user_agent": session.user_agent,
                "is_active": session.is_active,
                "created_at": session.created_at,
                "last_activity": session.last_activity,
                "expires_at": session.expires_at,
                "logged_out_at": session.logged_out_at
            }
            for session in sessions
        ]
        
        # MFA devices
        mfa_result = await db.execute(
            select(MFADevice).filter(MFADevice.user_id == user_uuid)
        )
        mfa_devices = mfa_result.scalars().all()
        
        data["mfa_devices"] = [
            {
                "id": str(device.id),
                "device_type": device.device_type,
                "device_name": device.device_name,
                "is_active": device.is_active,
                "created_at": device.created_at,
                "last_used": device.last_used
                # Note: Secret keys and backup codes are not included for security
            }
            for device in mfa_devices
        ]
        
        # Login attempts
        login_attempts_result = await db.execute(
            select(LoginAttempt).filter(LoginAttempt.user_id == user_uuid)
        )
        login_attempts = login_attempts_result.scalars().all()
        
        data["login_attempts"] = [
            {
                "id": str(attempt.id),
                "email": attempt.email,
                "ip_address": attempt.ip_address,
                "user_agent": attempt.user_agent,
                "success": attempt.success,
                "failure_reason": attempt.failure_reason,
                "attempted_at": attempt.attempted_at
            }
            for attempt in login_attempts
        ]
        
        # Security events (if requested)
        if include_security_logs:
            security_events_result = await db.execute(
                select(SecurityEvent).filter(SecurityEvent.user_id == user_uuid)
            )
            security_events = security_events_result.scalars().all()
            
            data["security_events"] = [
                {
                    "id": str(event.id),
                    "event_type": event.event_type,
                    "ip_address": event.ip_address,
                    "user_agent": event.user_agent,
                    "success": event.success,
                    "details": event.details,
                    "created_at": event.created_at
                }
                for event in security_events
            ]
        
        # Password reset tokens (active ones only)
        reset_tokens_result = await db.execute(
            select(PasswordResetToken).filter(
                and_(
                    PasswordResetToken.user_id == user_uuid,
                    PasswordResetToken.used_at.is_(None),
                    PasswordResetToken.expires_at > datetime.utcnow()
                )
            )
        )
        reset_tokens = reset_tokens_result.scalars().all()
        
        data["active_password_reset_tokens"] = [
            {
                "id": str(token.id),
                "expires_at": token.expires_at,
                "created_at": token.created_at,
                "ip_address": token.ip_address
                # Note: Token hash is not included for security
            }
            for token in reset_tokens
        ]
        
        # Email verification tokens (active ones only)
        email_tokens_result = await db.execute(
            select(EmailVerificationToken).filter(
                and_(
                    EmailVerificationToken.user_id == user_uuid,
                    EmailVerificationToken.used_at.is_(None),
                    EmailVerificationToken.expires_at > datetime.utcnow()
                )
            )
        )
        email_tokens = email_tokens_result.scalars().all()
        
        data["active_email_verification_tokens"] = [
            {
                "id": str(token.id),
                "expires_at": token.expires_at,
                "created_at": token.created_at,
                "ip_address": token.ip_address
                # Note: Token hash is not included for security
            }
            for token in email_tokens
        ]
        
        return data
    
    def _generate_data_summary(self, user_data: Dict[str, Any]) -> str:
        """Generate human-readable summary of exported data."""
        
        summary_lines = [
            "GDPR DATA EXPORT SUMMARY",
            "=" * 50,
            "",
            f"Export Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Export Format Version: {self.export_format_version}",
            "",
            "DATA CATEGORIES INCLUDED:",
            "-" * 30
        ]
        
        for category, data in user_data.items():
            if isinstance(data, list):
                count = len(data)
                summary_lines.append(f"• {category.replace('_', ' ').title()}: {count} records")
            elif isinstance(data, dict):
                summary_lines.append(f"• {category.replace('_', ' ').title()}: 1 record")
            else:
                summary_lines.append(f"• {category.replace('_', ' ').title()}: Available")
        
        summary_lines.extend([
            "",
            "GDPR RIGHTS INFORMATION:",
            "-" * 30,
            "• Right to Access: This export provides all personal data we hold about you",
            "• Right to Rectification: Contact support to correct any inaccurate data",
            "• Right to Erasure: Contact support to request account deletion",
            "• Right to Portability: This data is provided in machine-readable JSON format",
            "• Right to Object: Contact support to object to data processing",
            "",
            "For questions about this export or to exercise your GDPR rights,",
            "please contact our Data Protection Officer at: dpo@oxygen-platform.com",
            "",
            "Files included in this export:",
            "• user_data.json - Complete data in JSON format",
            "• export_metadata.json - Export metadata and information",
            "• data_summary.txt - This human-readable summary"
        ])
        
        return "\n".join(summary_lines)
    
    async def anonymize_user_data(
        self,
        db: AsyncSession,
        user_id: str
    ) -> Dict[str, int]:
        """
        Anonymize user data for GDPR compliance.
        Returns count of records affected.
        """
        # This would implement data anonymization
        # For now, return placeholder
        return {
            "user_profile_anonymized": 0,
            "security_events_anonymized": 0,
            "login_attempts_anonymized": 0
        }


# Global GDPR service instance
gdpr_service = GDPRService()
