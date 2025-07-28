"""
Multi-Factor Authentication (MFA) service with TOTP support.
Implements TOTP-based 2FA, backup codes, and MFA device management.
"""

import pyotp
import qrcode
import io
import base64
import secrets
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update, delete
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.user import User, MFADevice
from app.core.config import get_settings
from shared.security.encryption import encryption_manager

settings = get_settings()


class MFAService:
    """Multi-Factor Authentication service."""
    
    def __init__(self):
        self.issuer_name = "Oxygen Supply Platform"
        self.backup_codes_count = 10
    
    def generate_secret_key(self) -> str:
        """Generate a new TOTP secret key."""
        return pyotp.random_base32()
    
    def generate_backup_codes(self) -> List[str]:
        """Generate backup codes for MFA recovery."""
        codes = []
        for _ in range(self.backup_codes_count):
            # Generate 8-character alphanumeric codes
            code = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))
            codes.append(code)
        return codes
    
    def create_qr_code(self, secret_key: str, user_email: str, device_name: str = None) -> str:
        """
        Create QR code for TOTP setup.
        Returns base64-encoded PNG image.
        """
        # Create TOTP URI
        account_name = f"{user_email}"
        if device_name:
            account_name += f" ({device_name})"
        
        totp_uri = pyotp.totp.TOTP(secret_key).provisioning_uri(
            name=account_name,
            issuer_name=self.issuer_name
        )
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(totp_uri)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return f"data:image/png;base64,{img_str}"
    
    def verify_totp_code(self, secret_key: str, code: str, window: int = 1) -> bool:
        """
        Verify TOTP code.
        Window allows for time drift (±30 seconds per window).
        """
        try:
            totp = pyotp.TOTP(secret_key)
            return totp.verify(code, valid_window=window)
        except Exception:
            return False
    
    def verify_backup_code(self, backup_codes: List[str], code: str) -> Tuple[bool, List[str]]:
        """
        Verify backup code and remove it from the list.
        Returns (is_valid, updated_codes_list).
        """
        code_upper = code.upper().strip()
        
        if code_upper in backup_codes:
            # Remove used code
            updated_codes = [c for c in backup_codes if c != code_upper]
            return True, updated_codes
        
        return False, backup_codes
    
    async def setup_mfa_device(
        self,
        db: AsyncSession,
        user_id: str,
        device_name: str = "Authenticator App",
        device_type: str = "totp"
    ) -> Dict[str, any]:
        """
        Setup new MFA device for user.
        Returns setup information including QR code.
        """
        try:
            # Check if user already has MFA enabled
            existing_device = await db.execute(
                select(MFADevice).filter(
                    and_(
                        MFADevice.user_id == user_id,
                        MFADevice.is_active == True
                    )
                )
            )
            
            if existing_device.scalar_one_or_none():
                raise ValueError("MFA is already enabled for this user")
            
            # Get user info
            user_result = await db.execute(
                select(User).filter(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                raise ValueError("User not found")
            
            # Generate secret key and backup codes
            secret_key = self.generate_secret_key()
            backup_codes = self.generate_backup_codes()
            
            # Encrypt sensitive data
            encrypted_secret = encryption_manager.encrypt_field(secret_key, "mfa_secret")
            encrypted_backup_codes = encryption_manager.encrypt_field(json.dumps(backup_codes), "mfa_backup")
            
            # Create MFA device record
            mfa_device = MFADevice(
                user_id=user_id,
                device_type=device_type,
                device_name=device_name,
                secret_key=encrypted_secret,
                backup_codes=encrypted_backup_codes,
                is_active=False  # Will be activated after verification
            )
            
            db.add(mfa_device)
            await db.commit()
            await db.refresh(mfa_device)
            
            # Generate QR code
            qr_code = self.create_qr_code(secret_key, user.email, device_name)
            
            return {
                "device_id": str(mfa_device.id),
                "secret_key": secret_key,  # Only return during setup
                "qr_code": qr_code,
                "backup_codes": backup_codes,  # Only return during setup
                "device_name": device_name,
                "setup_complete": False
            }
            
        except Exception as e:
            await db.rollback()
            raise ValueError(f"MFA setup failed: {str(e)}")
    
    async def verify_and_activate_mfa(
        self,
        db: AsyncSession,
        user_id: str,
        device_id: str,
        verification_code: str
    ) -> bool:
        """
        Verify setup code and activate MFA device.
        """
        try:
            # Get MFA device
            device_result = await db.execute(
                select(MFADevice).filter(
                    and_(
                        MFADevice.id == device_id,
                        MFADevice.user_id == user_id,
                        MFADevice.is_active == False
                    )
                )
            )
            
            device = device_result.scalar_one_or_none()
            if not device:
                raise ValueError("MFA device not found or already activated")
            
            # Decrypt secret key
            secret_key = encryption_manager.decrypt_field(device.secret_key, "mfa_secret")
            
            # Verify code
            if not self.verify_totp_code(secret_key, verification_code):
                raise ValueError("Invalid verification code")
            
            # Activate device and enable MFA for user
            device.is_active = True
            device.last_used = datetime.utcnow()
            
            # Update user MFA status
            await db.execute(
                update(User).where(User.id == user_id).values(mfa_enabled=True)
            )
            
            await db.commit()
            
            return True
            
        except Exception as e:
            await db.rollback()
            raise ValueError(f"MFA activation failed: {str(e)}")
    
    async def verify_mfa_code(
        self,
        db: AsyncSession,
        user_id: str,
        code: str,
        device_type: str = "totp"
    ) -> bool:
        """
        Verify MFA code for authentication.
        Supports both TOTP codes and backup codes.
        """
        try:
            # Get active MFA device
            device_result = await db.execute(
                select(MFADevice).filter(
                    and_(
                        MFADevice.user_id == user_id,
                        MFADevice.device_type == device_type,
                        MFADevice.is_active == True
                    )
                )
            )
            
            device = device_result.scalar_one_or_none()
            if not device:
                return False
            
            # Try TOTP verification first
            secret_key = encryption_manager.decrypt_field(device.secret_key, "mfa_secret")
            if self.verify_totp_code(secret_key, code):
                # Update last used
                device.last_used = datetime.utcnow()
                await db.commit()
                return True
            
            # Try backup code verification
            backup_codes_json = encryption_manager.decrypt_field(device.backup_codes, "mfa_backup")
            backup_codes = json.loads(backup_codes_json)

            is_valid, updated_codes = self.verify_backup_code(backup_codes, code)
            if is_valid:
                # Update backup codes
                device.backup_codes = encryption_manager.encrypt_field(json.dumps(updated_codes), "mfa_backup")
                device.last_used = datetime.utcnow()
                await db.commit()
                return True
            
            return False
            
        except Exception:
            return False
    
    async def disable_mfa(
        self,
        db: AsyncSession,
        user_id: str,
        verification_code: str
    ) -> bool:
        """
        Disable MFA for user after verification.
        """
        try:
            # Verify current MFA code
            if not await self.verify_mfa_code(db, user_id, verification_code):
                raise ValueError("Invalid verification code")
            
            # Disable all MFA devices
            await db.execute(
                update(MFADevice).where(
                    MFADevice.user_id == user_id
                ).values(is_active=False)
            )
            
            # Update user MFA status
            await db.execute(
                update(User).where(User.id == user_id).values(mfa_enabled=False)
            )
            
            await db.commit()
            return True
            
        except Exception as e:
            await db.rollback()
            raise ValueError(f"MFA disable failed: {str(e)}")
    
    async def get_user_mfa_devices(
        self,
        db: AsyncSession,
        user_id: str
    ) -> List[Dict[str, any]]:
        """Get user's MFA devices."""
        try:
            devices_result = await db.execute(
                select(MFADevice).filter(
                    MFADevice.user_id == user_id
                ).order_by(MFADevice.created_at.desc())
            )
            
            devices = devices_result.scalars().all()
            
            return [
                {
                    "id": str(device.id),
                    "device_type": device.device_type,
                    "device_name": device.device_name,
                    "is_active": device.is_active,
                    "last_used": device.last_used,
                    "created_at": device.created_at
                }
                for device in devices
            ]
            
        except Exception:
            return []
    
    async def regenerate_backup_codes(
        self,
        db: AsyncSession,
        user_id: str,
        verification_code: str
    ) -> List[str]:
        """
        Regenerate backup codes after verification.
        """
        try:
            # Verify current MFA code
            if not await self.verify_mfa_code(db, user_id, verification_code):
                raise ValueError("Invalid verification code")
            
            # Get active device
            device_result = await db.execute(
                select(MFADevice).filter(
                    and_(
                        MFADevice.user_id == user_id,
                        MFADevice.is_active == True
                    )
                )
            )
            
            device = device_result.scalar_one_or_none()
            if not device:
                raise ValueError("No active MFA device found")
            
            # Generate new backup codes
            new_backup_codes = self.generate_backup_codes()
            
            # Update device
            device.backup_codes = encryption_manager.encrypt_field(json.dumps(new_backup_codes), "mfa_backup")
            await db.commit()
            
            return new_backup_codes
            
        except Exception as e:
            await db.rollback()
            raise ValueError(f"Backup code regeneration failed: {str(e)}")


# Global MFA service instance
mfa_service = MFAService()
