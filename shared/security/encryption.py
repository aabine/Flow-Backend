"""
Data encryption and protection utilities for the Oxygen Supply Platform.
Implements field-level encryption, data masking, and secure storage.
"""

import os
import base64
import hashlib
import secrets
from typing import Any, Dict, Optional, Union, List
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import json
import logging
import re

logger = logging.getLogger(__name__)


class EncryptionManager:
    """Manages encryption and decryption of sensitive data."""
    
    def __init__(self, master_key: str = None):
        self.master_key = master_key or os.getenv("MASTER_ENCRYPTION_KEY")
        if not self.master_key:
            self.master_key = Fernet.generate_key().decode()
            logger.warning("No master encryption key provided. Generated temporary key.")
        
        self.fernet = Fernet(self.master_key.encode())
    
    def encrypt_field(self, data: str, field_type: str = "general") -> str:
        """Encrypt a single field with type-specific handling."""
        
        if not data:
            return data
        
        try:
            # Add field type prefix for identification
            prefixed_data = f"{field_type}:{data}"
            encrypted = self.fernet.encrypt(prefixed_data.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Encryption error for field type {field_type}: {str(e)}")
            raise
    
    def decrypt_field(self, encrypted_data: str, expected_type: str = None) -> str:
        """Decrypt a single field with type validation."""
        
        if not encrypted_data:
            return encrypted_data
        
        try:
            # Decode from base64
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = self.fernet.decrypt(encrypted_bytes).decode()
            
            # Extract field type and data
            if ":" in decrypted:
                field_type, data = decrypted.split(":", 1)
                
                # Validate field type if expected
                if expected_type and field_type != expected_type:
                    raise ValueError(f"Field type mismatch. Expected {expected_type}, got {field_type}")
                
                return data
            else:
                return decrypted
                
        except Exception as e:
            logger.error(f"Decryption error: {str(e)}")
            raise
    
    def encrypt_pii(self, pii_data: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt personally identifiable information."""
        
        pii_fields = {
            "email", "phone", "address", "full_name", "first_name", 
            "last_name", "national_id", "passport_number", "license_number"
        }
        
        encrypted_data = {}
        
        for key, value in pii_data.items():
            if key.lower() in pii_fields and isinstance(value, str):
                encrypted_data[key] = self.encrypt_field(value, "pii")
            else:
                encrypted_data[key] = value
        
        return encrypted_data
    
    def decrypt_pii(self, encrypted_pii: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt personally identifiable information."""
        
        pii_fields = {
            "email", "phone", "address", "full_name", "first_name", 
            "last_name", "national_id", "passport_number", "license_number"
        }
        
        decrypted_data = {}
        
        for key, value in encrypted_pii.items():
            if key.lower() in pii_fields and isinstance(value, str):
                try:
                    decrypted_data[key] = self.decrypt_field(value, "pii")
                except:
                    # If decryption fails, might be unencrypted data
                    decrypted_data[key] = value
            else:
                decrypted_data[key] = value
        
        return decrypted_data
    
    def encrypt_payment_data(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt payment-related sensitive data."""
        
        payment_fields = {
            "card_number", "cvv", "account_number", "routing_number",
            "bank_account", "payment_token"
        }
        
        encrypted_data = {}
        
        for key, value in payment_data.items():
            if key.lower() in payment_fields and isinstance(value, str):
                encrypted_data[key] = self.encrypt_field(value, "payment")
            else:
                encrypted_data[key] = value
        
        return encrypted_data
    
    def hash_sensitive_data(self, data: str, salt: str = None) -> Dict[str, str]:
        """Create a one-way hash of sensitive data for searching/indexing."""
        
        if not salt:
            salt = secrets.token_hex(16)
        
        # Use PBKDF2 for key stretching
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt.encode(),
            iterations=100000,
        )
        
        key = kdf.derive(data.encode())
        hash_value = base64.urlsafe_b64encode(key).decode()
        
        return {
            "hash": hash_value,
            "salt": salt
        }


class DataMasking:
    """Data masking utilities for logs and non-production environments."""
    
    @staticmethod
    def mask_email(email: str) -> str:
        """Mask email address."""
        if not email or "@" not in email:
            return email
        
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            masked_local = "*" * len(local)
        else:
            masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
        
        return f"{masked_local}@{domain}"
    
    @staticmethod
    def mask_phone(phone: str) -> str:
        """Mask phone number."""
        if not phone:
            return phone
        
        # Remove non-digit characters
        digits = re.sub(r'\D', '', phone)
        
        if len(digits) < 4:
            return "*" * len(digits)
        
        # Show first 2 and last 2 digits
        return digits[:2] + "*" * (len(digits) - 4) + digits[-2:]
    
    @staticmethod
    def mask_card_number(card_number: str) -> str:
        """Mask credit card number."""
        if not card_number:
            return card_number
        
        # Remove non-digit characters
        digits = re.sub(r'\D', '', card_number)
        
        if len(digits) < 8:
            return "*" * len(digits)
        
        # Show first 4 and last 4 digits
        return digits[:4] + "*" * (len(digits) - 8) + digits[-4:]
    
    @staticmethod
    def mask_account_number(account_number: str) -> str:
        """Mask bank account number."""
        if not account_number:
            return account_number
        
        if len(account_number) <= 4:
            return "*" * len(account_number)
        
        # Show last 4 digits only
        return "*" * (len(account_number) - 4) + account_number[-4:]
    
    @staticmethod
    def mask_sensitive_dict(data: Dict[str, Any], mask_fields: List[str] = None) -> Dict[str, Any]:
        """Mask sensitive fields in a dictionary."""
        
        if mask_fields is None:
            mask_fields = [
                "password", "token", "secret", "key", "email", "phone",
                "card_number", "cvv", "account_number", "ssn", "national_id"
            ]
        
        masked_data = {}
        
        for key, value in data.items():
            if any(field in key.lower() for field in mask_fields):
                if "email" in key.lower():
                    masked_data[key] = DataMasking.mask_email(str(value))
                elif "phone" in key.lower():
                    masked_data[key] = DataMasking.mask_phone(str(value))
                elif "card" in key.lower():
                    masked_data[key] = DataMasking.mask_card_number(str(value))
                elif "account" in key.lower():
                    masked_data[key] = DataMasking.mask_account_number(str(value))
                else:
                    masked_data[key] = "*" * min(len(str(value)), 8)
            else:
                masked_data[key] = value
        
        return masked_data


class SecureFileHandler:
    """Secure file upload and storage utilities."""
    
    ALLOWED_EXTENSIONS = {
        'image': {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'},
        'document': {'pdf', 'doc', 'docx', 'txt', 'rtf'},
        'spreadsheet': {'xls', 'xlsx', 'csv'},
        'archive': {'zip', 'tar', 'gz'}
    }
    
    DANGEROUS_EXTENSIONS = {
        'exe', 'bat', 'cmd', 'com', 'pif', 'scr', 'vbs', 'js', 'jar',
        'php', 'asp', 'aspx', 'jsp', 'py', 'rb', 'pl', 'sh'
    }
    
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    
    @staticmethod
    def validate_file_upload(filename: str, content: bytes, allowed_types: List[str] = None) -> Dict[str, Any]:
        """Validate uploaded file for security."""
        
        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "file_info": {}
        }
        
        # Check filename
        if not filename:
            validation_result["is_valid"] = False
            validation_result["errors"].append("Filename is required")
            return validation_result
        
        # Check file size
        if len(content) > SecureFileHandler.MAX_FILE_SIZE:
            validation_result["is_valid"] = False
            validation_result["errors"].append(f"File size exceeds maximum allowed size of {SecureFileHandler.MAX_FILE_SIZE} bytes")
        
        # Get file extension
        file_extension = filename.lower().split('.')[-1] if '.' in filename else ''
        
        # Check for dangerous extensions
        if file_extension in SecureFileHandler.DANGEROUS_EXTENSIONS:
            validation_result["is_valid"] = False
            validation_result["errors"].append(f"File type '{file_extension}' is not allowed")
        
        # Check allowed types
        if allowed_types:
            allowed_extensions = set()
            for file_type in allowed_types:
                allowed_extensions.update(SecureFileHandler.ALLOWED_EXTENSIONS.get(file_type, set()))
            
            if file_extension not in allowed_extensions:
                validation_result["is_valid"] = False
                validation_result["errors"].append(f"File type '{file_extension}' is not allowed for this upload")
        
        # Check file content (magic bytes)
        content_validation = SecureFileHandler._validate_file_content(content, file_extension)
        if not content_validation["is_valid"]:
            validation_result["is_valid"] = False
            validation_result["errors"].extend(content_validation["errors"])
        
        # Scan for malicious content
        malware_scan = SecureFileHandler._scan_for_malware(content)
        if not malware_scan["is_safe"]:
            validation_result["is_valid"] = False
            validation_result["errors"].extend(malware_scan["threats"])
        
        validation_result["file_info"] = {
            "filename": filename,
            "extension": file_extension,
            "size": len(content),
            "content_type": content_validation.get("content_type", "unknown")
        }
        
        return validation_result
    
    @staticmethod
    def _validate_file_content(content: bytes, expected_extension: str) -> Dict[str, Any]:
        """Validate file content matches extension."""
        
        # Magic byte signatures for common file types
        magic_bytes = {
            'jpg': [b'\xff\xd8\xff'],
            'jpeg': [b'\xff\xd8\xff'],
            'png': [b'\x89\x50\x4e\x47'],
            'gif': [b'\x47\x49\x46\x38'],
            'pdf': [b'\x25\x50\x44\x46'],
            'zip': [b'\x50\x4b\x03\x04', b'\x50\x4b\x05\x06', b'\x50\x4b\x07\x08']
        }
        
        if expected_extension in magic_bytes:
            file_signatures = magic_bytes[expected_extension]
            
            for signature in file_signatures:
                if content.startswith(signature):
                    return {
                        "is_valid": True,
                        "content_type": expected_extension
                    }
            
            return {
                "is_valid": False,
                "errors": [f"File content does not match {expected_extension} format"]
            }
        
        # For unknown extensions, just check it's not executable
        if content.startswith(b'MZ') or content.startswith(b'\x7fELF'):
            return {
                "is_valid": False,
                "errors": ["Executable files are not allowed"]
            }
        
        return {"is_valid": True}
    
    @staticmethod
    def _scan_for_malware(content: bytes) -> Dict[str, Any]:
        """Basic malware scanning (can be enhanced with external scanners)."""
        
        # Check for suspicious patterns
        suspicious_patterns = [
            b'<script',
            b'javascript:',
            b'vbscript:',
            b'<?php',
            b'<%',
            b'eval(',
            b'exec(',
            b'system(',
            b'shell_exec('
        ]
        
        threats = []
        
        for pattern in suspicious_patterns:
            if pattern in content.lower():
                threats.append(f"Suspicious pattern detected: {pattern.decode('utf-8', errors='ignore')}")
        
        return {
            "is_safe": len(threats) == 0,
            "threats": threats
        }
    
    @staticmethod
    def generate_secure_filename(original_filename: str) -> str:
        """Generate a secure filename for storage."""
        
        # Extract extension
        extension = ""
        if '.' in original_filename:
            extension = '.' + original_filename.split('.')[-1].lower()
        
        # Generate secure random filename
        secure_name = secrets.token_urlsafe(16)
        
        return secure_name + extension


# Global instances
encryption_manager = EncryptionManager()
data_masking = DataMasking()
secure_file_handler = SecureFileHandler()
