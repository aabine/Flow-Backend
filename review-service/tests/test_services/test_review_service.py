import pytest
from unittest.mock import AsyncMock, patch
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.services.review_service import ReviewService
from app.schemas.review import ReviewCreate, ReviewUpdate
from app.models.review import Review, ReviewStatus, ReviewType
from shared.models import UserRole


class TestReviewService:
    
    @pytest.fixture
    def review_service(self):
        return ReviewService()
    
    @pytest.mark.asyncio
    async def test_create_review_success(self, review_service, db_session, sample_review_data):
        """Test successful review creation."""
        with patch.object(review_service, '_validate_review_eligibility') as mock_validate, \
             patch.object(review_service, '_get_existing_review', return_value=None) as mock_existing, \
             patch.object(review_service, '_get_order_details', return_value={
                 'vendor_id': 'vendor-123',
                 'hospital_id': 'hospital-123'
             }) as mock_order, \
             patch.object(review_service, '_update_review_summary') as mock_summary:
            
            review_data = ReviewCreate(**sample_review_data)
            reviewer_id = "hospital-123"
            reviewer_role = UserRole.HOSPITAL
            
            review = await review_service.create_review(
                db_session, review_data, reviewer_id, reviewer_role
            )
            
            assert review is not None
            assert review.rating == sample_review_data["rating"]
            assert review.comment == sample_review_data["comment"]
            assert review.review_type == ReviewType.HOSPITAL_TO_VENDOR
            assert review.status == ReviewStatus.ACTIVE
    
    @pytest.mark.asyncio
    async def test_create_review_duplicate(self, review_service, db_session, sample_review_data):
        """Test creating duplicate review raises error."""
        existing_review = Review(
            id=uuid.uuid4(),
            order_id=uuid.UUID(sample_review_data["order_id"]),
            reviewer_id=uuid.uuid4(),
            reviewee_id=uuid.uuid4(),
            rating=5,
            review_type=ReviewType.HOSPITAL_TO_VENDOR
        )
        
        with patch.object(review_service, '_validate_review_eligibility'), \
             patch.object(review_service, '_get_existing_review', return_value=existing_review):
            
            review_data = ReviewCreate(**sample_review_data)
            reviewer_id = "hospital-123"
            reviewer_role = UserRole.HOSPITAL
            
            with pytest.raises(ValueError, match="Review already exists"):
                await review_service.create_review(
                    db_session, review_data, reviewer_id, reviewer_role
                )
    
    @pytest.mark.asyncio
    async def test_update_review_success(self, review_service, db_session):
        """Test successful review update."""
        review_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        
        # Mock existing review
        existing_review = Review(
            id=uuid.UUID(review_id),
            reviewer_id=uuid.UUID(user_id),
            rating=4,
            comment="Good service",
            created_at=pytest.datetime.utcnow()
        )
        
        with patch.object(review_service, 'get_review', return_value=existing_review), \
             patch.object(review_service, '_update_review_summary_on_edit'):
            
            update_data = ReviewUpdate(rating=5, comment="Excellent service!")
            
            updated_review = await review_service.update_review(
                db_session, review_id, update_data, user_id
            )
            
            assert updated_review.rating == 5
            assert updated_review.comment == "Excellent service!"
    
    @pytest.mark.asyncio
    async def test_update_review_unauthorized(self, review_service, db_session):
        """Test updating review by non-reviewer raises error."""
        review_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        different_user_id = str(uuid.uuid4())
        
        # Mock existing review with different reviewer
        existing_review = Review(
            id=uuid.UUID(review_id),
            reviewer_id=uuid.UUID(different_user_id),
            rating=4,
            comment="Good service"
        )
        
        with patch.object(review_service, 'get_review', return_value=existing_review):
            update_data = ReviewUpdate(rating=5)
            
            with pytest.raises(ValueError, match="Only the reviewer can update"):
                await review_service.update_review(
                    db_session, review_id, update_data, user_id
                )
    
    @pytest.mark.asyncio
    async def test_get_reviews_for_user(self, review_service, db_session):
        """Test getting reviews for a user."""
        user_id = str(uuid.uuid4())
        
        with patch('sqlalchemy.ext.asyncio.AsyncSession.execute') as mock_execute:
            # Mock the query results
            mock_result = AsyncMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_execute.return_value = mock_result
            
            reviews, total = await review_service.get_reviews_for_user(
                db_session, user_id, page=1, size=20
            )
            
            assert isinstance(reviews, list)
            assert isinstance(total, int)
    
    def test_determine_reviewee(self, review_service):
        """Test determining reviewee based on order details and reviewer role."""
        order_details = {
            'vendor_id': 'vendor-123',
            'hospital_id': 'hospital-123'
        }
        
        # Hospital reviewing vendor
        reviewee = review_service._determine_reviewee(
            order_details, 'hospital-123', UserRole.HOSPITAL
        )
        assert reviewee == 'vendor-123'
        
        # Vendor reviewing hospital
        reviewee = review_service._determine_reviewee(
            order_details, 'vendor-123', UserRole.VENDOR
        )
        assert reviewee == 'hospital-123'
    
    def test_determine_review_type(self, review_service):
        """Test determining review type based on reviewer role."""
        assert review_service._determine_review_type(UserRole.HOSPITAL) == ReviewType.HOSPITAL_TO_VENDOR
        assert review_service._determine_review_type(UserRole.VENDOR) == ReviewType.VENDOR_TO_HOSPITAL
        
        with pytest.raises(ValueError, match="Invalid reviewer role"):
            review_service._determine_review_type(UserRole.ADMIN)
