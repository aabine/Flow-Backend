import pytest
from unittest.mock import AsyncMock, patch
import json
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.review import Review, ReviewType, ReviewStatus
from shared.models import UserRole


class TestReviewsAPI:
    
    @pytest.mark.asyncio
    async def test_create_review_success(self, client, sample_review_data, sample_user_data):
        """Test successful review creation via API."""
        headers = {
            "X-User-ID": sample_user_data["user_id"],
            "X-User-Role": sample_user_data["role"]
        }
        
        with patch('app.services.review_service.ReviewService.create_review') as mock_create, \
             patch('app.services.event_service.event_service.emit_review_created') as mock_emit:
            
            # Mock successful review creation
            mock_review = Review(
                id="review-123",
                order_id=sample_review_data["order_id"],
                reviewer_id=sample_user_data["user_id"],
                reviewee_id="vendor-123",
                rating=sample_review_data["rating"],
                comment=sample_review_data["comment"],
                review_type=ReviewType.HOSPITAL_TO_VENDOR,
                status=ReviewStatus.ACTIVE
            )
            mock_create.return_value = mock_review
            
            response = await client.post(
                "/reviews/",
                json=sample_review_data,
                headers=headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "review_id" in data["data"]
            mock_create.assert_called_once()
            mock_emit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_review_duplicate(self, client, sample_review_data, sample_user_data):
        """Test creating duplicate review returns error."""
        headers = {
            "X-User-ID": sample_user_data["user_id"],
            "X-User-Role": sample_user_data["role"]
        }
        
        with patch('app.services.review_service.ReviewService.create_review') as mock_create:
            mock_create.side_effect = ValueError("Review already exists for this order")
            
            response = await client.post(
                "/reviews/",
                json=sample_review_data,
                headers=headers
            )
            
            assert response.status_code == 400
            assert "Review already exists" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_get_review_success(self, client, sample_user_data):
        """Test getting a review by ID."""
        review_id = "review-123"
        headers = {
            "X-User-ID": sample_user_data["user_id"],
            "X-User-Role": sample_user_data["role"]
        }
        
        with patch('app.services.review_service.ReviewService.get_review') as mock_get:
            mock_review = Review(
                id=review_id,
                order_id="order-123",
                reviewer_id=sample_user_data["user_id"],
                reviewee_id="vendor-123",
                rating=5,
                comment="Great service!",
                review_type=ReviewType.HOSPITAL_TO_VENDOR,
                status=ReviewStatus.ACTIVE
            )
            mock_get.return_value = mock_review
            
            response = await client.get(f"/reviews/{review_id}", headers=headers)
            
            assert response.status_code == 200
            mock_get.assert_called_once_with(mock_get.call_args[0][0], review_id)
    
    @pytest.mark.asyncio
    async def test_get_review_not_found(self, client, sample_user_data):
        """Test getting non-existent review returns 404."""
        review_id = "non-existent"
        headers = {
            "X-User-ID": sample_user_data["user_id"],
            "X-User-Role": sample_user_data["role"]
        }
        
        with patch('app.services.review_service.ReviewService.get_review') as mock_get:
            mock_get.return_value = None
            
            response = await client.get(f"/reviews/{review_id}", headers=headers)
            
            assert response.status_code == 404
            assert "Review not found" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_update_review_success(self, client, sample_user_data):
        """Test updating a review."""
        review_id = "review-123"
        headers = {
            "X-User-ID": sample_user_data["user_id"],
            "X-User-Role": sample_user_data["role"]
        }
        update_data = {
            "rating": 4,
            "comment": "Updated comment"
        }
        
        with patch('app.services.review_service.ReviewService.update_review') as mock_update, \
             patch('app.services.event_service.event_service.emit_review_updated') as mock_emit:
            
            mock_review = Review(
                id=review_id,
                order_id="order-123",
                reviewer_id=sample_user_data["user_id"],
                reviewee_id="vendor-123",
                rating=4,
                comment="Updated comment",
                review_type=ReviewType.HOSPITAL_TO_VENDOR,
                status=ReviewStatus.ACTIVE
            )
            mock_update.return_value = mock_review
            
            response = await client.put(
                f"/reviews/{review_id}",
                json=update_data,
                headers=headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            mock_update.assert_called_once()
            mock_emit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_vote_helpfulness(self, client, sample_user_data):
        """Test voting on review helpfulness."""
        review_id = "review-123"
        headers = {
            "X-User-ID": sample_user_data["user_id"],
            "X-User-Role": sample_user_data["role"]
        }
        vote_data = {"is_helpful": True}
        
        with patch('app.services.review_service.ReviewService.vote_helpfulness') as mock_vote:
            mock_vote.return_value = True
            
            response = await client.post(
                f"/reviews/{review_id}/vote",
                json=vote_data,
                headers=headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            mock_vote.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_report_review(self, client, sample_user_data):
        """Test reporting a review."""
        review_id = "review-123"
        headers = {
            "X-User-ID": sample_user_data["user_id"],
            "X-User-Role": sample_user_data["role"]
        }
        report_data = {
            "reason": "spam",
            "description": "This is spam content"
        }
        
        with patch('app.services.review_service.ReviewService.report_review') as mock_report, \
             patch('app.services.event_service.event_service.emit_review_reported') as mock_emit:
            
            mock_report_obj = type('MockReport', (), {
                'id': 'report-123',
                'reporter_id': sample_user_data["user_id"],
                'reason': 'spam'
            })()
            mock_report.return_value = mock_report_obj
            
            response = await client.post(
                f"/reviews/{review_id}/report",
                json=report_data,
                headers=headers
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "report_id" in data["data"]
            mock_report.assert_called_once()
            mock_emit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_moderate_review_admin_only(self, client, sample_user_data):
        """Test that only admins can moderate reviews."""
        review_id = "review-123"
        headers = {
            "X-User-ID": sample_user_data["user_id"],
            "X-User-Role": "hospital"  # Not admin
        }
        action_data = {
            "action": "flag",
            "reason": "inappropriate content"
        }
        
        response = await client.post(
            f"/reviews/{review_id}/moderate",
            json=action_data,
            headers=headers
        )
        
        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]
