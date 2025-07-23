from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from app.models.notification import NotificationType, NotificationChannel, NotificationStatus


class NotificationBase(BaseModel):
    title: str
    message: str
    notification_type: NotificationType = NotificationType.INFO
    metadata: Optional[Dict[str, Any]] = None


class NotificationCreate(NotificationBase):
    user_id: str
    channel: NotificationChannel = NotificationChannel.IN_APP
    template_id: Optional[str] = None


class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None
    status: Optional[NotificationStatus] = None


class NotificationResponse(NotificationBase):
    id: str
    user_id: str
    status: NotificationStatus
    channel: NotificationChannel
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    template_id: Optional[str] = None

    class Config:
        from_attributes = True


class NotificationTemplateBase(BaseModel):
    name: str
    subject: str
    body: str
    notification_type: NotificationType
    channel: NotificationChannel
    variables: Optional[Dict[str, str]] = None


class NotificationTemplateCreate(NotificationTemplateBase):
    pass


class NotificationTemplateResponse(NotificationTemplateBase):
    id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotificationPreferenceBase(BaseModel):
    email_enabled: bool = True
    sms_enabled: bool = True
    push_enabled: bool = True
    in_app_enabled: bool = True
    marketing_emails: bool = True
    order_updates: bool = True
    payment_updates: bool = True
    delivery_updates: bool = True
    emergency_alerts: bool = True


class NotificationPreferenceUpdate(NotificationPreferenceBase):
    pass


class NotificationPreferenceResponse(NotificationPreferenceBase):
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotificationStats(BaseModel):
    total: int = 0
    read: int = 0
    unread: int = 0
    by_type: Dict[str, int] = {}
    by_channel: Dict[str, int] = {}


class BroadcastNotification(NotificationBase):
    user_ids: Optional[List[str]] = None
    user_role: Optional[str] = None
    channel: NotificationChannel = NotificationChannel.IN_APP


class EmergencyAlert(BaseModel):
    title: str
    message: str
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    radius_km: Optional[float] = None
