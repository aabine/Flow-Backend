import pytest
from unittest.mock import AsyncMock, patch
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.services.user_management_service import UserManagementService
from app.schemas.admin import UserManagementFilter, UserActionRequest, AdminUserCreate
from app.models.admin import AdminUser, AuditLog, AdminActionType
from shared.models import UserRole


class TestUserManagementService:
    
    @pytest.fixture
    def user_management_service(self):
        return UserManagementService()
    
    @pytest.mark.asyncio
    async def test_get_users_success(self, user_management_service, db_session, mock_service_responses):
        """Test successful users retrieval."""
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "items": mock_service_responses["user_service"]["users"],
                "total": mock_service_responses["user_service"]["total"]
            }
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            filters = UserManagementFilter(role=UserRole.HOSPITAL)
            users, total = await user_management_service.get_users(db_session, filters, 1, 20)
            
            assert len(users) == 2
            assert total == 2
    
    @pytest.mark.asyncio
    async def test_get_users_service_error(self, user_management_service, db_session):
        """Test users retrieval when service returns error."""
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            users, total = await user_management_service.get_users(db_session, None, 1, 20)
            
            assert users == []
            assert total == 0
    
    @pytest.mark.asyncio
    async def test_get_user_details_success(self, user_management_service, sample_user_data):
        """Test successful user details retrieval."""
        
        with patch('httpx.AsyncClient') as mock_client:
            # Mock user service response
            user_response = AsyncMock()
            user_response.status_code = 200
            user_response.json.return_value = sample_user_data
            
            # Mock other service responses
            order_response = AsyncMock()
            order_response.status_code = 200
            order_response.json.return_value = {"order_count": 25, "total_spent": 125000}
            
            review_response = AsyncMock()
            review_response.status_code = 200
            review_response.json.return_value = {"average_rating": 4.5}
            
            payment_response = AsyncMock()
            payment_response.status_code = 200
            payment_response.json.return_value = {"payment_history": []}
            
            mock_client.return_value.__aenter__.return_value.get.side_effect = [
                user_response, order_response, review_response, payment_response
            ]
            
            user_details = await user_management_service.get_user_details("user-123")
            
            assert user_details is not None
            assert user_details["id"] == "user-123"
            assert user_details["order_count"] == 25
            assert user_details["average_rating"] == 4.5
    
    @pytest.mark.asyncio
    async def test_get_user_details_not_found(self, user_management_service):
        """Test user details retrieval when user not found."""
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 404
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            user_details = await user_management_service.get_user_details("nonexistent-user")
            
            assert user_details is None
    
    @pytest.mark.asyncio
    async def test_perform_user_action_success(self, user_management_service, db_session, sample_user_data):
        """Test successful user action performance."""
        
        action_request = UserActionRequest(
            action="suspend",
            reason="Policy violation",
            notify_user=True
        )
        
        with patch.object(user_management_service, 'get_user_details', return_value=sample_user_data), \
             patch('httpx.AsyncClient') as mock_client, \
             patch.object(user_management_service, '_log_admin_action') as mock_log, \
             patch.object(user_management_service, '_send_user_notification') as mock_notify:
            
            mock_response = AsyncMock()
            mock_response.status_code = 200
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            success = await user_management_service.perform_user_action(
                db_session, "user-123", action_request, "admin-123"
            )
            
            assert success is True
            mock_log.assert_called_once()
            mock_notify.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_perform_user_action_user_not_found(self, user_management_service, db_session):
        """Test user action when user not found."""
        
        action_request = UserActionRequest(action="suspend", reason="Test")
        
        with patch.object(user_management_service, 'get_user_details', return_value=None):
            success = await user_management_service.perform_user_action(
                db_session, "nonexistent-user", action_request, "admin-123"
            )
            
            assert success is False
    
    @pytest.mark.asyncio
    async def test_create_admin_user_success(self, user_management_service, db_session, sample_user_data):
        """Test successful admin user creation."""
        
        admin_data = AdminUserCreate(
            user_id="user-123",
            admin_level="admin",
            permissions=["user_management", "order_management"]
        )
        
        with patch.object(user_management_service, 'get_user_details', return_value=sample_user_data), \
             patch.object(user_management_service, '_log_admin_action'):
            
            admin_user = await user_management_service.create_admin_user(
                db_session, admin_data, "creator-admin-123"
            )
            
            assert admin_user is not None
            assert admin_user.admin_level == "admin"
            assert admin_user.permissions == ["user_management", "order_management"]
    
    @pytest.mark.asyncio
    async def test_create_admin_user_invalid_user(self, user_management_service, db_session):
        """Test admin user creation with invalid user."""
        
        admin_data = AdminUserCreate(user_id="nonexistent-user")
        
        with patch.object(user_management_service, 'get_user_details', return_value=None):
            admin_user = await user_management_service.create_admin_user(
                db_session, admin_data, "creator-admin-123"
            )
            
            assert admin_user is None
    
    @pytest.mark.asyncio
    async def test_get_admin_users_success(self, user_management_service, db_session):
        """Test successful admin users retrieval."""
        
        # Mock database query results
        with patch('sqlalchemy.ext.asyncio.AsyncSession.execute') as mock_execute:
            # Mock count query
            count_result = AsyncMock()
            count_result.scalar.return_value = 2
            
            # Mock admin users query
            admin_users_result = AsyncMock()
            admin_user1 = AdminUser(
                id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                admin_level="admin",
                permissions=["user_management"]
            )
            admin_user2 = AdminUser(
                id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                admin_level="moderator",
                permissions=["review_moderation"]
            )
            admin_users_result.scalars.return_value.all.return_value = [admin_user1, admin_user2]
            
            mock_execute.side_effect = [count_result, admin_users_result]
            
            admin_users, total = await user_management_service.get_admin_users(db_session, 1, 20)
            
            assert len(admin_users) == 2
            assert total == 2
    
    @pytest.mark.asyncio
    async def test_update_admin_user_success(self, user_management_service, db_session):
        """Test successful admin user update."""
        
        admin_user_id = str(uuid.uuid4())
        updates = {
            "admin_level": "super_admin",
            "permissions": ["full_access"],
            "is_active": True
        }
        
        # Mock existing admin user
        existing_admin = AdminUser(
            id=uuid.UUID(admin_user_id),
            user_id=uuid.uuid4(),
            admin_level="admin",
            permissions=["user_management"],
            is_active=True
        )
        
        with patch('sqlalchemy.ext.asyncio.AsyncSession.execute') as mock_execute, \
             patch.object(user_management_service, '_log_admin_action'):
            
            result = AsyncMock()
            result.scalar_one_or_none.return_value = existing_admin
            mock_execute.return_value = result
            
            updated_admin = await user_management_service.update_admin_user(
                db_session, admin_user_id, updates, "updater-admin-123"
            )
            
            assert updated_admin is not None
            assert updated_admin.admin_level == "super_admin"
            assert updated_admin.permissions == ["full_access"]
    
    @pytest.mark.asyncio
    async def test_update_admin_user_not_found(self, user_management_service, db_session):
        """Test admin user update when user not found."""
        
        admin_user_id = str(uuid.uuid4())
        updates = {"admin_level": "super_admin"}
        
        with patch('sqlalchemy.ext.asyncio.AsyncSession.execute') as mock_execute:
            result = AsyncMock()
            result.scalar_one_or_none.return_value = None
            mock_execute.return_value = result
            
            updated_admin = await user_management_service.update_admin_user(
                db_session, admin_user_id, updates, "updater-admin-123"
            )
            
            assert updated_admin is None
    
    @pytest.mark.asyncio
    async def test_bulk_user_action_success(self, user_management_service, db_session):
        """Test successful bulk user action."""
        
        user_ids = ["user-1", "user-2", "user-3"]
        action_request = UserActionRequest(action="activate", reason="Bulk activation")
        
        with patch.object(user_management_service, 'perform_user_action') as mock_action, \
             patch.object(user_management_service, '_log_admin_action'):
            
            # Mock successful actions for first two users, failure for third
            mock_action.side_effect = [True, True, False]
            
            result = await user_management_service.bulk_user_action(
                db_session, user_ids, action_request, "admin-123"
            )
            
            assert result["total"] == 3
            assert result["success_count"] == 2
            assert result["failure_count"] == 1
            assert len(result["successful"]) == 2
            assert len(result["failed"]) == 1
    
    @pytest.mark.asyncio
    async def test_get_audit_logs_success(self, user_management_service, db_session):
        """Test successful audit logs retrieval."""
        
        with patch('sqlalchemy.ext.asyncio.AsyncSession.execute') as mock_execute:
            # Mock count query
            count_result = AsyncMock()
            count_result.scalar.return_value = 1
            
            # Mock audit logs query
            logs_result = AsyncMock()
            audit_log = AuditLog(
                id=uuid.uuid4(),
                admin_user_id=uuid.uuid4(),
                action_type=AdminActionType.USER_UPDATED,
                resource_type="user",
                resource_id="user-123",
                description="User suspended",
                ip_address="192.168.1.1"
            )
            logs_result.scalars.return_value.all.return_value = [audit_log]
            
            mock_execute.side_effect = [count_result, logs_result]
            
            filters = {"action_type": AdminActionType.USER_UPDATED}
            audit_logs, total = await user_management_service.get_audit_logs(db_session, filters, 1, 20)
            
            assert len(audit_logs) == 1
            assert total == 1
            assert audit_logs[0].action_type == AdminActionType.USER_UPDATED
