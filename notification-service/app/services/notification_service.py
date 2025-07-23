import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.orm import selectinload

from app.models.notification import (
    Notification, NotificationTemplate, NotificationPreference,
    NotificationStatus, NotificationType, NotificationChannel
)
from app.schemas.notification import (
    NotificationCreate, NotificationUpdate, NotificationResponse,
    NotificationTemplateCreate, NotificationTemplateResponse,
    NotificationPreferenceUpdate, NotificationPreferenceResponse,
    NotificationStats
)


logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self):
        pass

    async def create_notification(self, db: AsyncSession, notification_data: NotificationCreate) -> Notification:
        """Create a new notification."""
        notification = Notification(
            user_id=notification_data.user_id,
            title=notification_data.title,
            message=notification_data.message,
            notification_type=notification_data.notification_type,
            channel=notification_data.channel,
            metadata_=notification_data.metadata,
            template_id=notification_data.template_id
        )
        db.add(notification)
        await db.commit()
        await db.refresh(notification)
        return notification

    async def get_notification(self, db: AsyncSession, notification_id: str) -> Optional[Notification]:
        """Get a notification by ID."""
        result = await db.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def get_user_notifications(self, db: AsyncSession, 
        user_id: str,
        page: int = 1,
        size: int = 20,
        unread_only: bool = False
    ) -> tuple[List[Notification], int]:
        """Get notifications for a user with pagination."""
        query = select(Notification).where(Notification.user_id == user_id)
        
        if unread_only:
            query = query.where(Notification.is_read == False)
        
        # Count total
        count_result = await db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()
        
        # Get paginated results
        query = (
            query.order_by(Notification.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        
        result = await db.execute(query)
        notifications = result.scalars().all()
        
        return notifications, total

    async def mark_notification_read(self, db: AsyncSession, notification_id: str, user_id: str) -> Optional[Notification]:
        """Mark a notification as read."""
        notification = await self.get_notification(db, notification_id)
        if not notification or notification.user_id != user_id:
            return None
            
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        await db.commit()
        await db.refresh(notification)
        return notification

    async def mark_all_notifications_read(self, db: AsyncSession, user_id: str) -> int:
        """Mark all notifications as read for a user."""
        result = await db.execute(
            update(Notification)
            .where(and_(
                Notification.user_id == user_id,
                Notification.is_read == False
            ))
            .values(is_read=True, read_at=datetime.utcnow())
            .returning(Notification.id)
        )
        await db.commit()
        return len(result.scalars().all())

    async def delete_notification(self, db: AsyncSession, notification_id: str, user_id: str) -> bool:
        """Delete a notification."""
        result = await db.execute(
            delete(Notification)
            .where(and_(
                Notification.id == notification_id,
                Notification.user_id == user_id
            ))
        )
        await db.commit()
        return result.rowcount > 0

    # Notification Templates
    async def create_template(self, db: AsyncSession, template_data: NotificationTemplateCreate) -> NotificationTemplate:
        """Create a new notification template."""
        template = NotificationTemplate(
            name=template_data.name,
            subject=template_data.subject,
            body=template_data.body,
            notification_type=template_data.notification_type,
            channel=template_data.channel,
            variables=template_data.variables
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)
        return template

    async def get_template(self, db: AsyncSession, template_id: str) -> Optional[NotificationTemplate]:
        """Get a template by ID."""
        result = await db.execute(
            select(NotificationTemplate)
            .where(NotificationTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def get_template_by_name(self, db: AsyncSession, name: str) -> Optional[NotificationTemplate]:
        """Get a template by name."""
        result = await db.execute(
            select(NotificationTemplate)
            .where(NotificationTemplate.name == name)
        )
        return result.scalar_one_or_none()

    async def get_all_templates(self, db: AsyncSession) -> List[NotificationTemplate]:
        """Get all notification templates."""
        result = await db.execute(
            select(NotificationTemplate)
            .order_by(NotificationTemplate.name)
        )
        return result.scalars().all()

    # Notification Preferences
    async def get_users_by_role(self, db: AsyncSession, role: str) -> List[str]:
        """
        Get user IDs by role. This is a placeholder implementation.
        In a real system, this would query a user service or database.
        """
        # This is a placeholder - in production you would:
        # 1. Query the user service API
        # 2. Query a shared user database
        # 3. Use a service discovery mechanism
        
        # For now, return empty list to prevent errors
        # You can extend this to integrate with your user service
        logger.warning(f"User lookup by role '{role}' is not implemented. Returning empty list.")
        return []

    async def get_vendors_in_area(self, db: AsyncSession, lat: float, lon: float, radius: float) -> List[str]:
        """Get vendors in a specific area. Placeholder."""
        logger.warning("Vendor lookup by area is not implemented. Returning empty list.")
        return []

    async def get_unread_count(self, db: AsyncSession, user_id: str) -> int:
        """Get the count of unread notifications for a user."""
        result = await db.execute(
            select(func.count(Notification.id))
            .where(and_(
                Notification.user_id == user_id,
                Notification.is_read == False
            ))
        )
        return result.scalar_one() or 0

    async def get_user_preferences(self, db: AsyncSession, user_id: str) -> Optional[NotificationPreference]:
        """Get notification preferences for a user."""
        result = await db.execute(
            select(NotificationPreference)
            .where(NotificationPreference.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_preferences(
        self, db: AsyncSession,
        user_id: str,
        preferences: NotificationPreferenceUpdate
    ) -> Optional[NotificationPreference]:
        """Update notification preferences for a user."""
        existing = await self.get_user_preferences(db, user_id)
        
        if not existing:
            # Create new preferences if they don't exist
            pref_data = preferences.dict()
            pref_data['user_id'] = user_id
            new_pref = NotificationPreference(**pref_data)
            db.add(new_pref)
            await db.commit()
            await db.refresh(new_pref)
            return new_pref
        
        # Update existing preferences
        update_data = preferences.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(existing, key, value)
            
        await db.commit()
        await db.refresh(existing)
        return existing

    async def get_notification_stats(self, db: AsyncSession) -> NotificationStats:
        """Get notification statistics."""
        # Total notifications
        result = await db.execute(select(func.count(Notification.id)))
        total = result.scalar_one() or 0
        
        # Read notifications
        result = await db.execute(
            select(func.count(Notification.id))
            .where(Notification.is_read == True)
        )
        read = result.scalar_one() or 0
        
        # Notifications by type
        result = await db.execute(
            select(
                Notification.notification_type,
                func.count(Notification.id)
            )
            .group_by(Notification.notification_type)
        )
        by_type = {str(t[0]): t[1] for t in result.all()}
        
        # Notifications by channel
        result = await db.execute(
            select(
                Notification.channel,
                func.count(Notification.id)
            )
            .group_by(Notification.channel)
        )
        by_channel = {str(c[0]): c[1] for c in result.all()}
        
        return NotificationStats(
            total=total,
            read=read,
            unread=total - read,
            by_type=by_type,
            by_channel=by_channel
        )
    
    async def send_notification(
        self, db: AsyncSession,
        user_id: str,
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        channel: NotificationChannel = NotificationChannel.IN_APP,
        metadata: Optional[Dict[str, Any]] = None,
        template_id: Optional[str] = None
    ) -> Notification:
        """Send a notification to a user."""
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            channel=channel,
            metadata_=metadata,
            template_id=template_id,
            status=NotificationStatus.PENDING
        )
        
        db.add(notification)
        await db.commit()
        await db.refresh(notification)
        
        # Here you would typically integrate with actual notification channels
        # (email, SMS, push, etc.) and update the notification status accordingly
        
        return notification
    
    async def broadcast_notification(self, db: AsyncSession,
        user_ids: List[str],
        title: str,
        message: str,
        notification_type: NotificationType = NotificationType.INFO,
        channel: NotificationChannel = NotificationChannel.IN_APP,
        metadata: Optional[Dict[str, Any]] = None,
        template_id: Optional[str] = None
    ) -> List[Notification]:
        """Send a notification to multiple users."""
        notifications = []
        for user_id in user_ids:
            notification = Notification(
                user_id=user_id,
                title=title,
                message=message,
                notification_type=notification_type,
                channel=channel,
                metadata_=metadata,
                template_id=template_id,
                status=NotificationStatus.PENDING
            )
            db.add(notification)
            notifications.append(notification)
        
        await db.commit()
        
        # Refresh all notifications to get their IDs
        for notification in notifications:
            await db.refresh(notification)
        
        return notifications

    async def send_emergency_notification(self, db: AsyncSession, notification_id: str):
        """Send an emergency notification. Placeholder."""
        logger.info(f"Sending emergency notification {notification_id}. This is a placeholder.")
        # In a real implementation, this would have high-priority sending logic
        pass
