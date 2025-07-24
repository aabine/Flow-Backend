from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, func, text
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import httpx
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import get_settings
from app.models.admin import AdminUser, AuditLog, AdminActionType
from app.schemas.admin import (
    UserManagementFilter, UserManagementResponse, UserActionRequest,
    AdminUserCreate, AdminUserResponse, AuditLogResponse
)
from shared.models import UserRole, APIResponse

settings = get_settings()


class UserManagementService:
    def __init__(self):
        self.settings = settings

    async def get_users(
        self, 
        db: AsyncSession, 
        filters: Optional[UserManagementFilter] = None,
        page: int = 1, 
        size: int = 20
    ) -> Tuple[List[UserManagementResponse], int]:
        """Get users with filtering and pagination."""
        
        try:
            # Build query parameters
            params = {
                "page": page,
                "size": size
            }
            
            if filters:
                if filters.role:
                    params["role"] = filters.role.value
                if filters.status:
                    params["status"] = filters.status
                if filters.registration_date_from:
                    params["registration_date_from"] = filters.registration_date_from.isoformat()
                if filters.registration_date_to:
                    params["registration_date_to"] = filters.registration_date_to.isoformat()
                if filters.search_term:
                    params["search"] = filters.search_term
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.settings.USER_SERVICE_URL}/admin/users",
                    params=params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    users = [
                        UserManagementResponse(**user) 
                        for user in data.get("items", [])
                    ]
                    total = data.get("total", 0)
                    return users, total
                else:
                    return [], 0
                    
        except Exception as e:
            print(f"Error fetching users: {e}")
            return [], 0

    async def get_user_details(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific user."""
        
        try:
            async with httpx.AsyncClient() as client:
                # Get user basic info
                user_response = await client.get(f"{self.settings.USER_SERVICE_URL}/users/{user_id}")
                
                if user_response.status_code != 200:
                    return None
                
                user_data = user_response.json()
                
                # Get additional data from other services
                order_response = await client.get(
                    f"{self.settings.ORDER_SERVICE_URL}/admin/users/{user_id}/summary"
                )
                review_response = await client.get(
                    f"{self.settings.REVIEW_SERVICE_URL}/admin/users/{user_id}/summary"
                )
                payment_response = await client.get(
                    f"{self.settings.PAYMENT_SERVICE_URL}/admin/users/{user_id}/summary"
                )
                
                # Combine data
                user_details = user_data.copy()
                
                if order_response.status_code == 200:
                    user_details.update(order_response.json())
                
                if review_response.status_code == 200:
                    user_details.update(review_response.json())
                
                if payment_response.status_code == 200:
                    user_details.update(payment_response.json())
                
                return user_details
                
        except Exception as e:
            print(f"Error fetching user details: {e}")
            return None

    async def perform_user_action(
        self, 
        db: AsyncSession,
        user_id: str, 
        action_request: UserActionRequest,
        admin_user_id: str
    ) -> bool:
        """Perform administrative action on a user."""
        
        try:
            # Get current user data for audit log
            current_user = await self.get_user_details(user_id)
            if not current_user:
                return False
            
            # Perform action via user service
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.settings.USER_SERVICE_URL}/admin/users/{user_id}/actions",
                    json={
                        "action": action_request.action,
                        "reason": action_request.reason,
                        "notify_user": action_request.notify_user
                    }
                )
                
                if response.status_code == 200:
                    # Log the action
                    await self._log_admin_action(
                        db,
                        admin_user_id,
                        AdminActionType.USER_UPDATED,
                        "user",
                        user_id,
                        f"Performed action: {action_request.action}",
                        current_user,
                        {"action": action_request.action, "reason": action_request.reason}
                    )
                    
                    # Send notification if requested
                    if action_request.notify_user:
                        await self._send_user_notification(user_id, action_request.action, action_request.reason)
                    
                    return True
                else:
                    return False
                    
        except Exception as e:
            print(f"Error performing user action: {e}")
            return False

    async def create_admin_user(
        self, 
        db: AsyncSession, 
        admin_data: AdminUserCreate,
        creator_admin_id: str
    ) -> Optional[AdminUser]:
        """Create a new admin user."""
        
        try:
            # Check if user exists and has appropriate role
            user_details = await self.get_user_details(admin_data.user_id)
            if not user_details:
                return None
            
            # Create admin user record
            admin_user = AdminUser(
                user_id=uuid.UUID(admin_data.user_id),
                admin_level=admin_data.admin_level,
                permissions=admin_data.permissions
            )
            
            db.add(admin_user)
            await db.commit()
            await db.refresh(admin_user)
            
            # Log the action
            await self._log_admin_action(
                db,
                creator_admin_id,
                AdminActionType.USER_CREATED,
                "admin_user",
                str(admin_user.id),
                f"Created admin user with level: {admin_data.admin_level}",
                None,
                {
                    "user_id": admin_data.user_id,
                    "admin_level": admin_data.admin_level,
                    "permissions": admin_data.permissions
                }
            )
            
            return admin_user
            
        except Exception as e:
            print(f"Error creating admin user: {e}")
            await db.rollback()
            return None

    async def get_admin_users(
        self, 
        db: AsyncSession,
        page: int = 1, 
        size: int = 20
    ) -> Tuple[List[AdminUserResponse], int]:
        """Get list of admin users."""
        
        try:
            # Count total
            count_query = select(func.count()).select_from(AdminUser)
            total_result = await db.execute(count_query)
            total = total_result.scalar()
            
            # Get paginated results
            query = select(AdminUser).offset((page - 1) * size).limit(size).order_by(AdminUser.created_at.desc())
            result = await db.execute(query)
            admin_users = result.scalars().all()
            
            # Convert to response format
            admin_user_responses = []
            for admin_user in admin_users:
                admin_user_responses.append(AdminUserResponse.from_orm(admin_user))
            
            return admin_user_responses, total
            
        except Exception as e:
            print(f"Error fetching admin users: {e}")
            return [], 0

    async def update_admin_user(
        self, 
        db: AsyncSession,
        admin_user_id: str,
        updates: Dict[str, Any],
        updater_admin_id: str
    ) -> Optional[AdminUser]:
        """Update admin user permissions and settings."""
        
        try:
            # Get current admin user
            result = await db.execute(
                select(AdminUser).where(AdminUser.id == uuid.UUID(admin_user_id))
            )
            admin_user = result.scalar_one_or_none()
            
            if not admin_user:
                return None
            
            # Store old values for audit
            old_values = {
                "admin_level": admin_user.admin_level,
                "permissions": admin_user.permissions,
                "is_active": admin_user.is_active
            }
            
            # Apply updates
            for key, value in updates.items():
                if hasattr(admin_user, key):
                    setattr(admin_user, key, value)
            
            admin_user.updated_at = datetime.utcnow()
            
            await db.commit()
            await db.refresh(admin_user)
            
            # Log the action
            await self._log_admin_action(
                db,
                updater_admin_id,
                AdminActionType.USER_UPDATED,
                "admin_user",
                admin_user_id,
                "Updated admin user settings",
                old_values,
                updates
            )
            
            return admin_user
            
        except Exception as e:
            print(f"Error updating admin user: {e}")
            await db.rollback()
            return None

    async def get_audit_logs(
        self, 
        db: AsyncSession,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1, 
        size: int = 20
    ) -> Tuple[List[AuditLogResponse], int]:
        """Get audit logs with filtering."""
        
        try:
            query = select(AuditLog)
            
            # Apply filters
            if filters:
                if filters.get("admin_user_id"):
                    query = query.where(AuditLog.admin_user_id == uuid.UUID(filters["admin_user_id"]))
                if filters.get("action_type"):
                    query = query.where(AuditLog.action_type == filters["action_type"])
                if filters.get("resource_type"):
                    query = query.where(AuditLog.resource_type == filters["resource_type"])
                if filters.get("date_from"):
                    query = query.where(AuditLog.created_at >= filters["date_from"])
                if filters.get("date_to"):
                    query = query.where(AuditLog.created_at <= filters["date_to"])
            
            # Count total
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await db.execute(count_query)
            total = total_result.scalar()
            
            # Get paginated results
            query = query.order_by(AuditLog.created_at.desc())
            query = query.offset((page - 1) * size).limit(size)
            
            result = await db.execute(query)
            audit_logs = result.scalars().all()
            
            # Convert to response format (would need to join with admin users for email)
            audit_log_responses = []
            for log in audit_logs:
                audit_log_responses.append(AuditLogResponse(
                    id=str(log.id),
                    admin_user_email="admin@example.com",  # Would fetch from user service
                    action_type=log.action_type,
                    resource_type=log.resource_type,
                    resource_id=log.resource_id,
                    description=log.description,
                    ip_address=log.ip_address,
                    created_at=log.created_at
                ))
            
            return audit_log_responses, total
            
        except Exception as e:
            print(f"Error fetching audit logs: {e}")
            return [], 0

    # Helper methods
    async def _log_admin_action(
        self,
        db: AsyncSession,
        admin_user_id: str,
        action_type: AdminActionType,
        resource_type: str,
        resource_id: str,
        description: str,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Log an admin action for audit purposes."""

        try:
            audit_log = AuditLog(
                admin_user_id=uuid.UUID(admin_user_id),
                action_type=action_type,
                resource_type=resource_type,
                resource_id=resource_id,
                description=description,
                old_values=old_values,
                new_values=new_values,
                ip_address=ip_address,
                user_agent=user_agent
            )

            db.add(audit_log)
            await db.commit()

        except Exception as e:
            print(f"Error logging admin action: {e}")

    async def _send_user_notification(self, user_id: str, action: str, reason: Optional[str] = None):
        """Send notification to user about admin action."""

        try:
            notification_data = {
                "user_id": user_id,
                "type": "in_app",
                "title": f"Account {action.title()}",
                "message": f"Your account has been {action}." + (f" Reason: {reason}" if reason else ""),
                "metadata": {
                    "action": action,
                    "reason": reason,
                    "source": "admin_action"
                }
            }

            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.settings.NOTIFICATION_SERVICE_URL}/notifications/",
                    json=notification_data
                )

        except Exception as e:
            print(f"Error sending user notification: {e}")

    async def bulk_user_action(
        self,
        db: AsyncSession,
        user_ids: List[str],
        action_request: UserActionRequest,
        admin_user_id: str
    ) -> Dict[str, Any]:
        """Perform bulk action on multiple users."""

        successful = []
        failed = []

        for user_id in user_ids:
            try:
                success = await self.perform_user_action(db, user_id, action_request, admin_user_id)
                if success:
                    successful.append(user_id)
                else:
                    failed.append(user_id)
            except Exception as e:
                print(f"Error processing user {user_id}: {e}")
                failed.append(user_id)

        # Log bulk action
        await self._log_admin_action(
            db,
            admin_user_id,
            AdminActionType.BULK_ACTION_PERFORMED,
            "user",
            ",".join(user_ids),
            f"Bulk action: {action_request.action} on {len(user_ids)} users",
            None,
            {
                "action": action_request.action,
                "total_users": len(user_ids),
                "successful": len(successful),
                "failed": len(failed),
                "reason": action_request.reason
            }
        )

        return {
            "total": len(user_ids),
            "successful": successful,
            "failed": failed,
            "success_count": len(successful),
            "failure_count": len(failed)
        }
