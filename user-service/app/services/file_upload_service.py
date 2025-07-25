"""
File upload service for profile pictures and document management.
Implements secure file upload with validation and storage.
"""

import os
import uuid
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from PIL import Image
import aiofiles
from fastapi import UploadFile, HTTPException, status
import sys

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import get_settings

settings = get_settings()


class FileUploadConfig:
    """File upload configuration."""
    
    # Profile picture settings
    PROFILE_PICTURE_MAX_SIZE = 5 * 1024 * 1024  # 5MB
    PROFILE_PICTURE_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
    PROFILE_PICTURE_MAX_DIMENSIONS = (1024, 1024)
    
    # Document settings
    DOCUMENT_MAX_SIZE = 10 * 1024 * 1024  # 10MB
    DOCUMENT_ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png"}
    
    # Storage settings
    UPLOAD_DIR = "uploads"
    PROFILE_PICTURES_DIR = "profile_pictures"
    DOCUMENTS_DIR = "documents"


class FileUploadService:
    """File upload and management service."""
    
    def __init__(self):
        self.config = FileUploadConfig()
        self.base_upload_dir = Path(self.config.UPLOAD_DIR)
        self.profile_pictures_dir = self.base_upload_dir / self.config.PROFILE_PICTURES_DIR
        self.documents_dir = self.base_upload_dir / self.config.DOCUMENTS_DIR
        
        # Create directories if they don't exist
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure upload directories exist."""
        self.base_upload_dir.mkdir(exist_ok=True)
        self.profile_pictures_dir.mkdir(exist_ok=True)
        self.documents_dir.mkdir(exist_ok=True)
    
    def _validate_file_type(self, file: UploadFile, allowed_types: set) -> bool:
        """Validate file content type."""
        return file.content_type in allowed_types
    
    def _validate_file_size(self, file: UploadFile, max_size: int) -> bool:
        """Validate file size."""
        # Note: This is approximate as we can't get exact size without reading
        # We'll do a more thorough check during upload
        return True  # Will be checked during upload
    
    def _generate_filename(self, user_id: str, original_filename: str, file_type: str) -> str:
        """Generate secure filename."""
        # Get file extension
        ext = Path(original_filename).suffix.lower()
        
        # Generate unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        
        return f"{user_id}_{file_type}_{timestamp}_{unique_id}{ext}"
    
    def _calculate_file_hash(self, file_content: bytes) -> str:
        """Calculate SHA-256 hash of file content."""
        return hashlib.sha256(file_content).hexdigest()
    
    async def _resize_image(self, image_path: Path, max_dimensions: Tuple[int, int]) -> None:
        """Resize image if it exceeds maximum dimensions."""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary (for PNG with transparency)
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                # Calculate new dimensions maintaining aspect ratio
                img.thumbnail(max_dimensions, Image.Resampling.LANCZOS)
                
                # Save optimized image
                img.save(image_path, format='JPEG', quality=85, optimize=True)
                
        except Exception as e:
            print(f"Error resizing image: {e}")
            # If resize fails, we'll keep the original
    
    async def upload_profile_picture(
        self,
        user_id: str,
        file: UploadFile
    ) -> Dict[str, str]:
        """
        Upload and process profile picture.
        Returns dict with file info.
        """
        try:
            # Validate file type
            if not self._validate_file_type(file, self.config.PROFILE_PICTURE_ALLOWED_TYPES):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid file type. Allowed types: {', '.join(self.config.PROFILE_PICTURE_ALLOWED_TYPES)}"
                )
            
            # Read file content
            file_content = await file.read()
            
            # Validate file size
            if len(file_content) > self.config.PROFILE_PICTURE_MAX_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File too large. Maximum size: {self.config.PROFILE_PICTURE_MAX_SIZE // (1024*1024)}MB"
                )
            
            # Generate filename
            filename = self._generate_filename(user_id, file.filename, "profile")
            file_path = self.profile_pictures_dir / filename
            
            # Save file
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(file_content)
            
            # Resize image if necessary
            await self._resize_image(file_path, self.config.PROFILE_PICTURE_MAX_DIMENSIONS)
            
            # Calculate file hash
            file_hash = self._calculate_file_hash(file_content)
            
            # Get file stats
            file_stats = file_path.stat()
            
            return {
                "filename": filename,
                "original_filename": file.filename,
                "file_path": str(file_path),
                "file_size": file_stats.st_size,
                "file_hash": file_hash,
                "content_type": file.content_type,
                "upload_date": datetime.utcnow().isoformat(),
                "url": f"/uploads/profile_pictures/{filename}"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload profile picture: {str(e)}"
            )
    
    async def upload_document(
        self,
        user_id: str,
        file: UploadFile,
        document_type: str = "general"
    ) -> Dict[str, str]:
        """
        Upload document file.
        Returns dict with file info.
        """
        try:
            # Validate file type
            if not self._validate_file_type(file, self.config.DOCUMENT_ALLOWED_TYPES):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid file type. Allowed types: {', '.join(self.config.DOCUMENT_ALLOWED_TYPES)}"
                )
            
            # Read file content
            file_content = await file.read()
            
            # Validate file size
            if len(file_content) > self.config.DOCUMENT_MAX_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File too large. Maximum size: {self.config.DOCUMENT_MAX_SIZE // (1024*1024)}MB"
                )
            
            # Generate filename
            filename = self._generate_filename(user_id, file.filename, document_type)
            file_path = self.documents_dir / filename
            
            # Save file
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(file_content)
            
            # Calculate file hash
            file_hash = self._calculate_file_hash(file_content)
            
            # Get file stats
            file_stats = file_path.stat()
            
            return {
                "filename": filename,
                "original_filename": file.filename,
                "file_path": str(file_path),
                "file_size": file_stats.st_size,
                "file_hash": file_hash,
                "content_type": file.content_type,
                "document_type": document_type,
                "upload_date": datetime.utcnow().isoformat(),
                "url": f"/uploads/documents/{filename}"
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload document: {str(e)}"
            )
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete a file from storage."""
        try:
            path = Path(file_path)
            if path.exists() and path.is_file():
                path.unlink()
                return True
            return False
        except Exception as e:
            print(f"Error deleting file {file_path}: {e}")
            return False
    
    def get_file_url(self, filename: str, file_type: str = "profile_pictures") -> str:
        """Get URL for accessing uploaded file."""
        return f"/uploads/{file_type}/{filename}"
    
    def validate_image_file(self, file: UploadFile) -> bool:
        """Validate if uploaded file is a valid image."""
        try:
            # Check content type
            if file.content_type not in self.config.PROFILE_PICTURE_ALLOWED_TYPES:
                return False
            
            # Additional validation could be added here
            # (e.g., checking file headers, using python-magic)
            
            return True
        except Exception:
            return False
    
    def get_upload_stats(self) -> Dict[str, any]:
        """Get upload directory statistics."""
        try:
            profile_pics_count = len(list(self.profile_pictures_dir.glob("*")))
            documents_count = len(list(self.documents_dir.glob("*")))
            
            # Calculate total size
            total_size = 0
            for file_path in self.base_upload_dir.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
            
            return {
                "profile_pictures_count": profile_pics_count,
                "documents_count": documents_count,
                "total_files": profile_pics_count + documents_count,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }
        except Exception as e:
            print(f"Error getting upload stats: {e}")
            return {
                "profile_pictures_count": 0,
                "documents_count": 0,
                "total_files": 0,
                "total_size_bytes": 0,
                "total_size_mb": 0
            }


# Global file upload service instance
file_upload_service = FileUploadService()
