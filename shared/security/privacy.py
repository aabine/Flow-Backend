"""
Data protection and privacy utilities for GDPR compliance and data security.
Implements data encryption at rest, data masking, secure file uploads, and backup security.
"""

import os
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from enum import Enum
import logging
from pathlib import Path

from .encryption import encryption_manager, data_masking
from .auth import security_validator

logger = logging.getLogger(__name__)


class DataClassification(Enum):
    """Data classification levels for privacy protection."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    PII = "pii"  # Personally Identifiable Information
    PHI = "phi"  # Protected Health Information


class ConsentType(Enum):
    """Types of user consent for data processing."""
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    FUNCTIONAL = "functional"
    NECESSARY = "necessary"
    THIRD_PARTY = "third_party"


class DataRetentionPolicy:
    """Data retention policies for different data types."""
    
    RETENTION_PERIODS = {
        DataClassification.PII: timedelta(days=2555),  # 7 years
        DataClassification.PHI: timedelta(days=2555),  # 7 years
        DataClassification.CONFIDENTIAL: timedelta(days=1825),  # 5 years
        DataClassification.INTERNAL: timedelta(days=1095),  # 3 years
        DataClassification.PUBLIC: timedelta(days=365),  # 1 year
    }
    
    @classmethod
    def get_retention_period(cls, classification: DataClassification) -> timedelta:
        """Get retention period for data classification."""
        return cls.RETENTION_PERIODS.get(classification, timedelta(days=365))
    
    @classmethod
    def is_expired(cls, created_at: datetime, classification: DataClassification) -> bool:
        """Check if data has exceeded retention period."""
        retention_period = cls.get_retention_period(classification)
        expiry_date = created_at + retention_period
        return datetime.utcnow() > expiry_date


class GDPRCompliance:
    """GDPR compliance utilities for data protection."""
    
    def __init__(self):
        self.lawful_bases = [
            "consent", "contract", "legal_obligation", 
            "vital_interests", "public_task", "legitimate_interests"
        ]
    
    def validate_consent(self, consent_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate user consent according to GDPR requirements."""
        
        required_fields = ["user_id", "consent_type", "given_at", "lawful_basis"]
        
        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Check required fields
        for field in required_fields:
            if field not in consent_data:
                validation_result["is_valid"] = False
                validation_result["errors"].append(f"Missing required field: {field}")
        
        # Validate lawful basis
        lawful_basis = consent_data.get("lawful_basis")
        if lawful_basis and lawful_basis not in self.lawful_bases:
            validation_result["is_valid"] = False
            validation_result["errors"].append(f"Invalid lawful basis: {lawful_basis}")
        
        # Validate consent type
        consent_type = consent_data.get("consent_type")
        if consent_type:
            try:
                ConsentType(consent_type)
            except ValueError:
                validation_result["is_valid"] = False
                validation_result["errors"].append(f"Invalid consent type: {consent_type}")
        
        # Check consent timestamp
        given_at = consent_data.get("given_at")
        if given_at:
            try:
                consent_time = datetime.fromisoformat(given_at.replace('Z', '+00:00'))
                if consent_time > datetime.utcnow():
                    validation_result["warnings"].append("Consent timestamp is in the future")
            except ValueError:
                validation_result["is_valid"] = False
                validation_result["errors"].append("Invalid consent timestamp format")
        
        return validation_result
    
    def generate_consent_record(
        self,
        user_id: str,
        consent_type: ConsentType,
        lawful_basis: str,
        purpose: str,
        data_categories: List[str],
        retention_period: Optional[timedelta] = None
    ) -> Dict[str, Any]:
        """Generate a GDPR-compliant consent record."""
        
        consent_id = secrets.token_urlsafe(16)
        
        return {
            "consent_id": consent_id,
            "user_id": user_id,
            "consent_type": consent_type.value,
            "lawful_basis": lawful_basis,
            "purpose": purpose,
            "data_categories": data_categories,
            "given_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + retention_period).isoformat() if retention_period else None,
            "withdrawn_at": None,
            "is_active": True,
            "version": "1.0",
            "ip_address": None,  # To be filled by caller
            "user_agent": None   # To be filled by caller
        }
    
    def withdraw_consent(self, consent_record: Dict[str, Any]) -> Dict[str, Any]:
        """Withdraw user consent and update record."""
        
        consent_record["withdrawn_at"] = datetime.utcnow().isoformat()
        consent_record["is_active"] = False
        
        return consent_record


class DataAnonymizer:
    """Data anonymization utilities for privacy protection."""
    
    @staticmethod
    def anonymize_personal_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """Anonymize personal data while preserving utility."""
        
        anonymized = data.copy()
        
        # Email anonymization
        if "email" in anonymized:
            email = anonymized["email"]
            if "@" in email:
                local, domain = email.split("@", 1)
                anonymized["email"] = f"user_{hashlib.sha256(email.encode()).hexdigest()[:8]}@{domain}"
        
        # Phone number anonymization
        if "phone" in anonymized:
            phone = anonymized["phone"]
            anonymized["phone"] = f"+234{hashlib.sha256(phone.encode()).hexdigest()[:9]}"
        
        # Name anonymization
        for name_field in ["first_name", "last_name", "full_name"]:
            if name_field in anonymized:
                name = anonymized[name_field]
                anonymized[name_field] = f"User_{hashlib.sha256(name.encode()).hexdigest()[:8]}"
        
        # Address anonymization
        if "address" in anonymized:
            address = anonymized["address"]
            anonymized["address"] = f"Address_{hashlib.sha256(address.encode()).hexdigest()[:8]}"
        
        # IP address anonymization
        if "ip_address" in anonymized:
            ip = anonymized["ip_address"]
            if "." in ip:  # IPv4
                parts = ip.split(".")
                anonymized["ip_address"] = f"{parts[0]}.{parts[1]}.xxx.xxx"
            elif ":" in ip:  # IPv6
                parts = ip.split(":")
                anonymized["ip_address"] = f"{parts[0]}:{parts[1]}:xxxx:xxxx:xxxx:xxxx:xxxx:xxxx"
        
        return anonymized
    
    @staticmethod
    def pseudonymize_data(data: Dict[str, Any], salt: str = None) -> Dict[str, Any]:
        """Pseudonymize data using consistent hashing."""
        
        if not salt:
            salt = secrets.token_hex(16)
        
        pseudonymized = data.copy()
        
        # Fields to pseudonymize
        fields_to_pseudonymize = [
            "user_id", "email", "phone", "national_id", 
            "passport_number", "license_number"
        ]
        
        for field in fields_to_pseudonymize:
            if field in pseudonymized:
                value = str(pseudonymized[field])
                salted_value = f"{value}{salt}"
                pseudonymized[field] = hashlib.sha256(salted_value.encode()).hexdigest()
        
        return pseudonymized, salt


class SecureBackupManager:
    """Secure backup management with encryption and integrity checks."""
    
    def __init__(self, backup_dir: str = "/var/backups/oxygen-platform"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Backup encryption key
        self.backup_key = os.getenv("BACKUP_ENCRYPTION_KEY")
        if not self.backup_key:
            logger.warning("No backup encryption key found. Generating temporary key.")
            self.backup_key = encryption_manager.fernet.generate_key().decode()
    
    def create_secure_backup(
        self,
        data: Dict[str, Any],
        backup_name: str,
        classification: DataClassification = DataClassification.CONFIDENTIAL
    ) -> Dict[str, Any]:
        """Create a secure, encrypted backup."""
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{backup_name}_{timestamp}.backup"
        backup_path = self.backup_dir / backup_filename
        
        # Prepare backup metadata
        metadata = {
            "backup_name": backup_name,
            "created_at": datetime.utcnow().isoformat(),
            "classification": classification.value,
            "version": "1.0",
            "checksum": None,
            "encrypted": True
        }
        
        # Serialize data
        serialized_data = json.dumps(data, default=str, ensure_ascii=False)
        
        # Calculate checksum before encryption
        checksum = hashlib.sha256(serialized_data.encode()).hexdigest()
        metadata["checksum"] = checksum
        
        # Encrypt data
        encrypted_data = encryption_manager.encrypt_field(serialized_data, "backup")
        
        # Create backup package
        backup_package = {
            "metadata": metadata,
            "data": encrypted_data
        }
        
        # Write to file
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(backup_package, f, ensure_ascii=False, indent=2)
        
        # Set secure file permissions
        os.chmod(backup_path, 0o600)
        
        logger.info(f"Secure backup created: {backup_filename}")
        
        return {
            "backup_file": backup_filename,
            "backup_path": str(backup_path),
            "checksum": checksum,
            "created_at": metadata["created_at"]
        }
    
    def restore_secure_backup(self, backup_filename: str) -> Dict[str, Any]:
        """Restore data from a secure backup."""
        
        backup_path = self.backup_dir / backup_filename
        
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_filename}")
        
        # Read backup file
        with open(backup_path, 'r', encoding='utf-8') as f:
            backup_package = json.load(f)
        
        metadata = backup_package["metadata"]
        encrypted_data = backup_package["data"]
        
        # Decrypt data
        decrypted_data = encryption_manager.decrypt_field(encrypted_data, "backup")
        
        # Verify checksum
        calculated_checksum = hashlib.sha256(decrypted_data.encode()).hexdigest()
        stored_checksum = metadata["checksum"]
        
        if calculated_checksum != stored_checksum:
            raise ValueError("Backup integrity check failed - checksum mismatch")
        
        # Parse data
        restored_data = json.loads(decrypted_data)
        
        logger.info(f"Secure backup restored: {backup_filename}")
        
        return {
            "data": restored_data,
            "metadata": metadata,
            "verified": True
        }
    
    def cleanup_expired_backups(self, retention_days: int = 30):
        """Clean up expired backups based on retention policy."""
        
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        deleted_count = 0
        
        for backup_file in self.backup_dir.glob("*.backup"):
            # Get file creation time
            file_time = datetime.fromtimestamp(backup_file.stat().st_ctime)
            
            if file_time < cutoff_date:
                try:
                    backup_file.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted expired backup: {backup_file.name}")
                except Exception as e:
                    logger.error(f"Failed to delete backup {backup_file.name}: {str(e)}")
        
        logger.info(f"Cleanup completed. Deleted {deleted_count} expired backups.")
        
        return deleted_count


class DataSubjectRights:
    """Implementation of GDPR data subject rights."""
    
    def __init__(self):
        self.supported_rights = [
            "access", "rectification", "erasure", "restrict_processing",
            "data_portability", "object_processing", "withdraw_consent"
        ]
    
    def process_data_request(
        self,
        request_type: str,
        user_id: str,
        request_details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Process data subject rights request."""
        
        if request_type not in self.supported_rights:
            raise ValueError(f"Unsupported request type: {request_type}")
        
        request_id = secrets.token_urlsafe(16)
        
        request_record = {
            "request_id": request_id,
            "request_type": request_type,
            "user_id": user_id,
            "status": "pending",
            "submitted_at": datetime.utcnow().isoformat(),
            "details": request_details or {},
            "response": None,
            "completed_at": None
        }
        
        logger.info(f"Data subject rights request created: {request_id} ({request_type})")
        
        return request_record
    
    def generate_data_export(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate data export for data portability request."""
        
        export_data = {
            "export_id": secrets.token_urlsafe(16),
            "generated_at": datetime.utcnow().isoformat(),
            "format": "JSON",
            "user_data": user_data,
            "metadata": {
                "total_records": len(user_data),
                "data_categories": list(user_data.keys()),
                "export_version": "1.0"
            }
        }
        
        return export_data


# Global instances
gdpr_compliance = GDPRCompliance()
data_anonymizer = DataAnonymizer()
backup_manager = SecureBackupManager()
data_subject_rights = DataSubjectRights()
