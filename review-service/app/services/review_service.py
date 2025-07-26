from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, func, desc
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import uuid
import httpx
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.review import Review, ReviewSummary, ReviewReport, ReviewHelpfulness, ReviewStatus, ReviewType
from app.schemas.review import (
    ReviewCreate, ReviewUpdate, ReviewResponse, ReviewReport as ReviewReportSchema,
    ReviewHelpfulnessVote, ReviewFilters, AdminReviewUpdate, ReviewModerationAction
)
from app.core.config import get_settings
from shared.models import UserRole

settings = get_settings()


class ReviewService:
    def __init__(self):
        self.settings = settings

    async def create_review(
        self, 
        db: AsyncSession, 
        review_data: ReviewCreate, 
        reviewer_id: str,
        reviewer_role: UserRole
    ) -> Review:
        """Create a new review."""
        
        # Validate that user can review this order
        await self._validate_review_eligibility(db, review_data.order_id, reviewer_id)
        
        # Check if review already exists for this order and reviewer
        existing_review = await self._get_existing_review(db, review_data.order_id, reviewer_id)
        if existing_review:
            raise ValueError("Review already exists for this order")
        
        # Get order details to determine reviewee
        order_details = await self._get_order_details(review_data.order_id)
        reviewee_id = self._determine_reviewee(order_details, reviewer_id, reviewer_role)
        review_type = self._determine_review_type(reviewer_role)
        
        # Create review
        review = Review(
            order_id=uuid.UUID(review_data.order_id),
            reviewer_id=uuid.UUID(reviewer_id),
            reviewee_id=uuid.UUID(reviewee_id),
            rating=review_data.rating,
            comment=review_data.comment,
            review_type=review_type,
            is_anonymous=review_data.is_anonymous,
            status=ReviewStatus.ACTIVE
        )
        
        db.add(review)
        await db.commit()
        await db.refresh(review)
        
        # Update review summary for reviewee
        await self._update_review_summary(db, reviewee_id, review.rating)
        
        return review

    async def get_review(self, db: AsyncSession, review_id: str) -> Optional[Review]:
        """Get a review by ID."""
        result = await db.execute(
            select(Review).where(Review.id == uuid.UUID(review_id))
        )
        return result.scalar_one_or_none()

    async def get_reviews(
        self,
        db: AsyncSession,
        filters: Optional[ReviewFilters] = None,
        page: int = 1,
        size: int = 20
    ) -> tuple[List[Review], int]:
        """Get all reviews with pagination and filtering."""
        query = select(Review)

        # Apply filters
        if filters:
            if filters.rating:
                query = query.where(Review.rating == filters.rating)
            if filters.review_type:
                query = query.where(Review.review_type == filters.review_type)

        # Count total
        count_result = await db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        # Get paginated results
        query = (
            query.order_by(Review.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )

        result = await db.execute(query)
        reviews = result.scalars().all()

        return list(reviews), total

    async def get_reviews_for_user(
        self, 
        db: AsyncSession, 
        user_id: str, 
        filters: Optional[ReviewFilters] = None,
        page: int = 1, 
        size: int = 20
    ) -> Tuple[List[Review], int]:
        """Get reviews for a specific user (as reviewee)."""
        
        query = select(Review).where(
            and_(
                Review.reviewee_id == uuid.UUID(user_id),
                Review.status == ReviewStatus.ACTIVE
            )
        )
        
        # Apply filters
        if filters:
            query = self._apply_filters(query, filters)
        
        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination and ordering
        query = query.order_by(desc(Review.created_at))
        query = query.offset((page - 1) * size).limit(size)
        
        result = await db.execute(query)
        reviews = result.scalars().all()
        
        return list(reviews), total

    async def get_reviews_by_user(
        self, 
        db: AsyncSession, 
        user_id: str, 
        page: int = 1, 
        size: int = 20
    ) -> Tuple[List[Review], int]:
        """Get reviews written by a specific user (as reviewer)."""
        
        query = select(Review).where(Review.reviewer_id == uuid.UUID(user_id))
        
        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination and ordering
        query = query.order_by(desc(Review.created_at))
        query = query.offset((page - 1) * size).limit(size)
        
        result = await db.execute(query)
        reviews = result.scalars().all()
        
        return list(reviews), total

    async def update_review(
        self, 
        db: AsyncSession, 
        review_id: str, 
        review_data: ReviewUpdate,
        user_id: str
    ) -> Optional[Review]:
        """Update a review (only by the reviewer within edit window)."""
        
        review = await self.get_review(db, review_id)
        if not review:
            return None
        
        # Check if user is the reviewer
        if str(review.reviewer_id) != user_id:
            raise ValueError("Only the reviewer can update this review")
        
        # Check edit window
        edit_deadline = review.created_at + timedelta(hours=self.settings.REVIEW_EDIT_WINDOW_HOURS)
        if datetime.utcnow() > edit_deadline:
            raise ValueError("Review edit window has expired")
        
        # Update fields
        old_rating = review.rating
        if review_data.rating is not None:
            review.rating = review_data.rating
        if review_data.comment is not None:
            review.comment = review_data.comment
        if review_data.is_anonymous is not None:
            review.is_anonymous = review_data.is_anonymous
        
        review.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(review)
        
        # Update review summary if rating changed
        if old_rating != review.rating:
            await self._update_review_summary_on_edit(
                db, str(review.reviewee_id), old_rating, review.rating
            )
        
        return review

    async def respond_to_review(
        self,
        db: AsyncSession,
        review_id: str,
        response_data: ReviewResponse,
        user_id: str
    ) -> Optional[Review]:
        """Add a response to a review (only by the reviewee)."""

        review = await self.get_review(db, review_id)
        if not review:
            return None

        # Check if user is the reviewee
        if str(review.reviewee_id) != user_id:
            raise ValueError("Only the reviewee can respond to this review")

        # Check if response already exists
        if review.response:
            raise ValueError("Response already exists for this review")

        review.response = response_data.response
        review.response_at = datetime.utcnow()

        await db.commit()
        await db.refresh(review)

        return review

    async def vote_helpfulness(
        self,
        db: AsyncSession,
        review_id: str,
        vote_data: ReviewHelpfulnessVote,
        user_id: str
    ) -> bool:
        """Vote on review helpfulness."""

        # Check if user already voted
        existing_vote = await db.execute(
            select(ReviewHelpfulness).where(
                and_(
                    ReviewHelpfulness.review_id == uuid.UUID(review_id),
                    ReviewHelpfulness.user_id == uuid.UUID(user_id)
                )
            )
        )
        existing = existing_vote.scalar_one_or_none()

        if existing:
            # Update existing vote
            old_vote = existing.is_helpful
            existing.is_helpful = vote_data.is_helpful
            existing.updated_at = datetime.utcnow()
        else:
            # Create new vote
            vote = ReviewHelpfulness(
                review_id=uuid.UUID(review_id),
                user_id=uuid.UUID(user_id),
                is_helpful=vote_data.is_helpful
            )
            db.add(vote)
            old_vote = None

        await db.commit()

        # Update review helpfulness counts
        await self._update_helpfulness_counts(db, review_id, vote_data.is_helpful, old_vote)

        return True

    async def report_review(
        self,
        db: AsyncSession,
        review_id: str,
        report_data: ReviewReportSchema,
        reporter_id: str
    ) -> ReviewReport:
        """Report a review for moderation."""

        # Check if user already reported this review
        existing_report = await db.execute(
            select(ReviewReport).where(
                and_(
                    ReviewReport.review_id == uuid.UUID(review_id),
                    ReviewReport.reporter_id == uuid.UUID(reporter_id)
                )
            )
        )
        if existing_report.scalar_one_or_none():
            raise ValueError("You have already reported this review")

        report = ReviewReport(
            review_id=uuid.UUID(review_id),
            reporter_id=uuid.UUID(reporter_id),
            reason=report_data.reason,
            description=report_data.description,
            status="pending"
        )

        db.add(report)
        await db.commit()
        await db.refresh(report)

        return report

    async def get_review_summary(self, db: AsyncSession, user_id: str) -> Optional[ReviewSummary]:
        """Get review summary for a user."""
        result = await db.execute(
            select(ReviewSummary).where(ReviewSummary.user_id == uuid.UUID(user_id))
        )
        return result.scalar_one_or_none()

    async def moderate_review(
        self,
        db: AsyncSession,
        review_id: str,
        action_data: ReviewModerationAction,
        admin_id: str
    ) -> Optional[Review]:
        """Moderate a review (admin only)."""

        review = await self.get_review(db, review_id)
        if not review:
            return None

        if action_data.action == "approve":
            review.status = ReviewStatus.ACTIVE
        elif action_data.action == "flag":
            review.status = ReviewStatus.FLAGGED
            review.flagged_at = datetime.utcnow()
            review.flagged_by = uuid.UUID(admin_id)
            review.flag_reason = action_data.reason
        elif action_data.action == "hide":
            review.status = ReviewStatus.HIDDEN
        elif action_data.action == "delete":
            review.status = ReviewStatus.DELETED

        await db.commit()
        await db.refresh(review)

        return review

    # Helper methods
    async def _validate_review_eligibility(self, db: AsyncSession, order_id: str, user_id: str):
        """Validate that user can review this order."""
        # This would typically check if the order exists and user was part of it
        # For now, we'll assume validation is done at API level
        pass

    async def _get_existing_review(self, db: AsyncSession, order_id: str, reviewer_id: str) -> Optional[Review]:
        """Check if review already exists."""
        result = await db.execute(
            select(Review).where(
                and_(
                    Review.order_id == uuid.UUID(order_id),
                    Review.reviewer_id == uuid.UUID(reviewer_id)
                )
            )
        )
        return result.scalar_one_or_none()

    async def _get_order_details(self, order_id: str) -> Dict[str, Any]:
        """Get order details from order service."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.settings.ORDER_SERVICE_URL}/orders/{order_id}")
            if response.status_code == 200:
                return response.json()
            else:
                raise ValueError("Order not found")

    def _determine_reviewee(self, order_details: Dict[str, Any], reviewer_id: str, reviewer_role: UserRole) -> str:
        """Determine who is being reviewed based on order details and reviewer role."""
        if reviewer_role == UserRole.HOSPITAL:
            return order_details.get("vendor_id")
        elif reviewer_role == UserRole.VENDOR:
            return order_details.get("hospital_id")
        else:
            raise ValueError("Invalid reviewer role")

    def _determine_review_type(self, reviewer_role: UserRole) -> ReviewType:
        """Determine review type based on reviewer role."""
        if reviewer_role == UserRole.HOSPITAL:
            return ReviewType.HOSPITAL_TO_VENDOR
        elif reviewer_role == UserRole.VENDOR:
            return ReviewType.VENDOR_TO_HOSPITAL
        else:
            raise ValueError("Invalid reviewer role")

    def _apply_filters(self, query, filters: ReviewFilters):
        """Apply filters to review query."""
        if filters.rating:
            query = query.where(Review.rating == filters.rating)
        if filters.review_type:
            query = query.where(Review.review_type == filters.review_type)
        if filters.status:
            query = query.where(Review.status == filters.status)
        if filters.is_verified is not None:
            query = query.where(Review.is_verified == filters.is_verified)
        if filters.start_date:
            query = query.where(Review.created_at >= filters.start_date)
        if filters.end_date:
            query = query.where(Review.created_at <= filters.end_date)
        return query

    async def _update_review_summary(self, db: AsyncSession, user_id: str, rating: int):
        """Update or create review summary for a user."""
        result = await db.execute(
            select(ReviewSummary).where(ReviewSummary.user_id == uuid.UUID(user_id))
        )
        summary = result.scalar_one_or_none()

        if not summary:
            # Create new summary
            summary = ReviewSummary(
                user_id=uuid.UUID(user_id),
                user_role=UserRole.VENDOR,  # This should be determined from user service
                total_reviews=1,
                average_rating=float(rating)
            )
            # Set rating counts
            setattr(summary, f"rating_{rating}_count", 1)
            db.add(summary)
        else:
            # Update existing summary
            old_total = summary.total_reviews
            old_average = summary.average_rating

            # Update counts
            summary.total_reviews += 1
            current_count = getattr(summary, f"rating_{rating}_count", 0)
            setattr(summary, f"rating_{rating}_count", current_count + 1)

            # Recalculate average
            total_rating_points = (old_average * old_total) + rating
            summary.average_rating = total_rating_points / summary.total_reviews

        summary.last_review_at = datetime.utcnow()
        summary.updated_at = datetime.utcnow()

        await db.commit()

    async def _update_review_summary_on_edit(
        self,
        db: AsyncSession,
        user_id: str,
        old_rating: int,
        new_rating: int
    ):
        """Update review summary when a review is edited."""
        result = await db.execute(
            select(ReviewSummary).where(ReviewSummary.user_id == uuid.UUID(user_id))
        )
        summary = result.scalar_one_or_none()

        if summary:
            # Decrease old rating count
            old_count = getattr(summary, f"rating_{old_rating}_count", 0)
            setattr(summary, f"rating_{old_rating}_count", max(0, old_count - 1))

            # Increase new rating count
            new_count = getattr(summary, f"rating_{new_rating}_count", 0)
            setattr(summary, f"rating_{new_rating}_count", new_count + 1)

            # Recalculate average
            total_rating_points = (summary.average_rating * summary.total_reviews) - old_rating + new_rating
            summary.average_rating = total_rating_points / summary.total_reviews
            summary.updated_at = datetime.utcnow()

            await db.commit()

    async def _update_helpfulness_counts(
        self,
        db: AsyncSession,
        review_id: str,
        is_helpful: bool,
        old_vote: Optional[bool]
    ):
        """Update helpfulness counts on a review."""
        review = await self.get_review(db, review_id)
        if not review:
            return

        # Adjust counts based on vote change
        if old_vote is None:
            # New vote
            if is_helpful:
                review.helpful_count += 1
            else:
                review.not_helpful_count += 1
        elif old_vote != is_helpful:
            # Vote changed
            if is_helpful:
                review.helpful_count += 1
                review.not_helpful_count = max(0, review.not_helpful_count - 1)
            else:
                review.not_helpful_count += 1
                review.helpful_count = max(0, review.helpful_count - 1)

        await db.commit()
