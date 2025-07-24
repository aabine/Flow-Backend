from fastapi import FastAPI, HTTPException, Depends, status, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional, List
import logging
import os
import sys

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings
from app.core.database import get_db
from app.models.notification import Notification, NotificationTemplate, NotificationPreference, NotificationType
from app.schemas.notification import (
    NotificationCreate, NotificationResponse, NotificationUpdate,
    NotificationTemplateCreate, NotificationPreferenceUpdate, NotificationTemplateResponse,
    NotificationPreferenceResponse, NotificationStats
)
from app.services.notification_service import NotificationService
from app.services.email_service import EmailService
from app.services.sms_service import SMSService

# Define missing models locally
from enum import Enum
from pydantic import BaseModel
from typing import Any, Optional

class UserRole(str, Enum):
    ADMIN = "admin"
    HOSPITAL = "hospital"
    VENDOR = "vendor"

class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None

class NotificationPage(BaseModel):
    notifications: List[NotificationResponse]
    total: int
    page: int
    size: int
    pages: int
    unread_count: int


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Notification Service",
    description="Multi-channel notification service (Email, SMS, Push, In-App)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

notification_service = NotificationService()
email_service = EmailService()
sms_service = SMSService()


def get_current_user(
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None)
) -> dict:
    """Get current user from headers (set by API Gateway)."""
    if not x_user_id or not x_user_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User authentication required"
        )
    return {"user_id": x_user_id, "role": x_user_role}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Notification Service",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/notifications", response_model=APIResponse)
async def send_notification(
    notification_data: NotificationCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send notification to user."""
    try:
        # Create notification record in the database
        notification = await notification_service.create_notification(db, notification_data)

        # Dispatch to the correct sender based on channel
        if notification.channel == NotificationChannel.EMAIL:
            # In a real app, you'd fetch user details first
            # For now, we assume the user_id is an email or can be resolved to one
            background_tasks.add_task(
                email_service.send_email,
                recipient_email=notification.user_id, 
                subject=notification.title,
                body=notification.message
            )
        elif notification.channel == NotificationChannel.SMS:
            # Similarly, resolve user_id to a phone number
            background_tasks.add_task(
                sms_service.send_sms,
                phone_number=notification.user_id,
                message=f"{notification.title}: {notification.message}"
            )
        else: # IN_APP or PUSH
            logger.info(f"In-app notification {notification.id} created. No sender task needed.")
        
        return APIResponse(
            success=True,
            message="Notification queued for delivery",
            data={
                "notification_id": str(notification.id),
                "type": notification.type,
                "recipient": notification.user_id
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send notification: {str(e)}"
        )


@app.get("/notifications", response_model=NotificationPage)
async def get_user_notifications(
    page: int = 1,
    size: int = 20,
    unread_only: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get notifications for current user."""
    try:
        notifications, total = await notification_service.get_user_notifications(
            db, current_user["user_id"], page, size, unread_only
        )
        
        unread_count = await notification_service.get_unread_count(db, current_user["user_id"])
        return {
            "notifications": [NotificationResponse.from_orm(n) for n in notifications],
            "total": total,
            "page": page,
            "size": size,
            "pages": (total + size - 1) // size if size > 0 else 0,
            "unread_count": unread_count
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get notifications: {str(e)}"
        )


@app.put("/notifications/{notification_id}/read", response_model=APIResponse)
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark notification as read."""
    try:
        updated_notification = await notification_service.mark_notification_read(
            db, notification_id, current_user["user_id"]
        )
        if not updated_notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found or access denied"
            )
        
        return APIResponse(
            success=True,
            message="Notification marked as read"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark notification as read: {str(e)}"
        )


@app.put("/notifications/read-all", response_model=APIResponse)
async def mark_all_notifications_read(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark all notifications as read for current user."""
    try:
        count = await notification_service.mark_all_notifications_read(db, current_user["user_id"])
        
        return APIResponse(
            success=True,
            message=f"Marked {count} notifications as read"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark notifications as read: {str(e)}"
        )


@app.delete("/notifications/{notification_id}", response_model=APIResponse)
async def delete_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete notification."""
    try:
        success = await notification_service.delete_notification(
            db, notification_id, current_user["user_id"]
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found or access denied"
            )
        
        return APIResponse(
            success=True,
            message="Notification deleted successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete notification: {str(e)}"
        )


@app.get("/preferences")
async def get_notification_preferences(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's notification preferences."""
    try:
        preferences = await notification_service.get_user_preferences(
            db, current_user["user_id"]
        )
        
        if not preferences:
            # Return default preferences if none are set
            return APIResponse(
                success=True,
                message="User preferences not found, returning defaults.",
                data=NotificationPreferenceResponse().dict()
            )

        return APIResponse(
            success=True,
            message="Preferences retrieved successfully",
            data=NotificationPreferenceResponse.from_orm(preferences).dict()
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get preferences: {str(e)}"
        )


@app.put("/preferences", response_model=APIResponse)
async def update_notification_preferences(
    preferences_update: NotificationPreferenceUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user's notification preferences."""
    try:
        await notification_service.update_preferences(
            db, current_user["user_id"], preferences_update
        )
        
        return APIResponse(
            success=True,
            message="Notification preferences updated successfully"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update preferences: {str(e)}"
        )


@app.post("/broadcast", response_model=APIResponse)
async def broadcast_notification(
    notification_data: NotificationCreate,
    background_tasks: BackgroundTasks,
    user_role: Optional[UserRole] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Broadcast notification to multiple users (admin only)."""
    try:
        if current_user["role"] != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        # Get target user IDs
        target_user_ids = await notification_service.get_users_by_role(db, user_role.value if user_role else 'all')
        
        if not target_user_ids:
            return APIResponse(success=True, message="No users found for the specified role.")

        # The broadcast_notification service method handles creating notifications for all users
        notifications = await notification_service.broadcast_notification(
            db,
            user_ids=target_user_ids,
            title=notification_data.title,
            message=notification_data.message,
            notification_type=notification_data.notification_type,
            channel=notification_data.channel,
            metadata=notification_data.metadata
        )

        # Add background tasks for sending
        for n in notifications:
            if n.channel == NotificationChannel.EMAIL:
                background_tasks.add_task(email_service.send_email, recipient_email=n.user_id, subject=n.title, body=n.message)
            elif n.channel == NotificationChannel.SMS:
                background_tasks.add_task(sms_service.send_sms, phone_number=n.user_id, message=f"{n.title}: {n.message}")
        
        notification_ids = [str(n.id) for n in notifications]
        
        return APIResponse(
            success=True,
            message=f"Broadcast notification queued for {len(target_user_ids)} users",
            data={
                "target_count": len(target_user_ids),
                "notification_ids": notification_ids
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to broadcast notification: {str(e)}"
        )


@app.post("/emergency-alert", response_model=APIResponse)
async def send_emergency_alert(
    title: str,
    message: str,
    background_tasks: BackgroundTasks,
    location_lat: Optional[float] = None,
    location_lon: Optional[float] = None,
    radius_km: Optional[float] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Send emergency alert to vendors in area."""
    try:
        if current_user["role"] not in [UserRole.HOSPITAL, UserRole.ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only hospitals and admins can send emergency alerts"
            )
        
        # Get vendors in area (if location specified)
        if location_lat and location_lon and radius_km:
            target_vendor_ids = await notification_service.get_vendors_in_area(
                db, location_lat, location_lon, radius_km
            )
        else:
            # Send to all vendors
            target_vendor_ids = await notification_service.get_users_by_role(db, UserRole.VENDOR)

        if not target_vendor_ids:
            return APIResponse(success=True, message="No vendors found to alert.")

        # Use broadcast for simplicity, but force SMS channel
        notifications = await notification_service.broadcast_notification(
            db,
            user_ids=target_vendor_ids,
            title=f"🚨 EMERGENCY: {title}",
            message=message,
            notification_type=NotificationType.ALERT,
            channel=NotificationChannel.SMS, # Emergency alerts should be SMS
            metadata={
                "emergency": True,
                "location": {"lat": location_lat, "lon": location_lon} if location_lat else None,
                "sender_id": current_user["user_id"]
            }
        )

        # Send emergency notifications immediately (high priority)
        for n in notifications:
            background_tasks.add_task(sms_service.send_sms, phone_number=n.user_id, message=f"{n.title}: {n.message}")

        notification_ids = [str(n.id) for n in notifications]
        
        return APIResponse(
            success=True,
            message=f"Emergency alert queued for {len(target_vendor_ids)} vendors",
            data={
                "target_count": len(target_vendor_ids),
                "notification_ids": notification_ids
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send emergency alert: {str(e)}"
        )

@app.get("/templates", response_model=APIResponse)
async def get_notification_templates(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get notification templates (admin only)."""
    try:
        if current_user["role"] != UserRole.ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
        
        templates = await notification_service.get_all_templates(db)
        return APIResponse(
            success=True, 
            message="Templates retrieved successfully", 
            data=[NotificationTemplateResponse.from_orm(t).dict() for t in templates]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get templates: {str(e)}"
        )


@app.post("/templates", response_model=APIResponse)
async def create_notification_template(
    template_data: NotificationTemplateCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create notification template (admin only)."""
    try:
        if current_user["role"] != UserRole.ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
        
        template = await notification_service.create_template(db, template_data)
        
        return APIResponse(
            success=True, 
            message="Template created successfully", 
            data=NotificationTemplateResponse.from_orm(template).dict()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create template: {str(e)}"
        )


@app.get("/stats", response_model=APIResponse)
async def get_notification_stats(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get notification statistics (admin only)."""
    try:
        if current_user["role"] != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        stats = await notification_service.get_notification_stats(db)
        
        return stats
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get notification stats: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
