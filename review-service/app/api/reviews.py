from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import get_db
from app.services.review_service import ReviewService
from app.services.event_service import event_service
from app.schemas.review import (
    ReviewCreate, ReviewUpdate, ReviewResponse, ReviewResponseModel,
    ReviewReport, ReviewHelpfulnessVote, ReviewFilters, PaginatedReviewResponse,
    ReviewSummaryResponse, ReviewReportResponse, AdminReviewUpdate,
    ReviewModerationAction, ReviewStatsResponse
)
from shared.models import APIResponse, UserRole

router = APIRouter()
review_service = ReviewService()


async def get_current_user(
    x_user_id: str = Header(..., alias="X-User-ID"),
    x_user_role: str = Header(..., alias="X-User-Role")
) -> dict:
    """Get current user from headers (set by API Gateway)."""
    return {
        "user_id": x_user_id,
        "role": UserRole(x_user_role)
    }


@router.post("/", response_model=APIResponse)
async def create_review(
    review_data: ReviewCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new review."""
    try:
        review = await review_service.create_review(
            db, review_data, current_user["user_id"], current_user["role"]
        )
        
        # Emit event
        await event_service.emit_review_created({
            "id": str(review.id),
            "order_id": str(review.order_id),
            "reviewer_id": str(review.reviewer_id),
            "reviewee_id": str(review.reviewee_id),
            "rating": review.rating,
            "review_type": review.review_type.value
        })
        
        return APIResponse(
            success=True,
            message="Review created successfully",
            data={"review_id": str(review.id)}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{review_id}", response_model=ReviewResponseModel)
async def get_review(
    review_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific review."""
    review = await review_service.get_review(db, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    return review


@router.put("/{review_id}", response_model=APIResponse)
async def update_review(
    review_id: str,
    review_data: ReviewUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a review (only by reviewer within edit window)."""
    try:
        review = await review_service.update_review(
            db, review_id, review_data, current_user["user_id"]
        )
        
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        # Emit event
        await event_service.emit_review_updated({
            "id": str(review.id),
            "order_id": str(review.order_id),
            "reviewer_id": str(review.reviewer_id),
            "reviewee_id": str(review.reviewee_id),
            "rating": review.rating
        })
        
        return APIResponse(
            success=True,
            message="Review updated successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{review_id}/respond", response_model=APIResponse)
async def respond_to_review(
    review_id: str,
    response_data: ReviewResponse,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Respond to a review (only by reviewee)."""
    try:
        review = await review_service.respond_to_review(
            db, review_id, response_data, current_user["user_id"]
        )
        
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        
        # Emit event
        await event_service.emit_review_responded({
            "id": str(review.id),
            "order_id": str(review.order_id),
            "reviewer_id": str(review.reviewer_id),
            "reviewee_id": str(review.reviewee_id)
        })
        
        return APIResponse(
            success=True,
            message="Response added successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{review_id}/vote", response_model=APIResponse)
async def vote_helpfulness(
    review_id: str,
    vote_data: ReviewHelpfulnessVote,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Vote on review helpfulness."""
    try:
        await review_service.vote_helpfulness(
            db, review_id, vote_data, current_user["user_id"]
        )
        
        return APIResponse(
            success=True,
            message="Vote recorded successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{review_id}/report", response_model=APIResponse)
async def report_review(
    review_id: str,
    report_data: ReviewReport,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Report a review for moderation."""
    try:
        report = await review_service.report_review(
            db, review_id, report_data, current_user["user_id"]
        )
        
        # Emit event
        await event_service.emit_review_reported(
            {"id": review_id},
            {
                "id": str(report.id),
                "reporter_id": str(report.reporter_id),
                "reason": report.reason
            }
        )
        
        return APIResponse(
            success=True,
            message="Review reported successfully",
            data={"report_id": str(report.id)}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/user/{user_id}", response_model=PaginatedReviewResponse)
async def get_user_reviews(
    user_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    rating: Optional[int] = Query(None, ge=1, le=5),
    review_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get reviews for a specific user (as reviewee)."""
    try:
        filters = ReviewFilters(rating=rating, review_type=review_type)
        reviews, total = await review_service.get_reviews_for_user(
            db, user_id, filters, page, size
        )

        pages = (total + size - 1) // size

        return PaginatedReviewResponse(
            items=[ReviewResponseModel.from_orm(review) for review in reviews],
            total=total,
            page=page,
            size=size,
            pages=pages
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/by-user/{user_id}", response_model=PaginatedReviewResponse)
async def get_reviews_by_user(
    user_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get reviews written by a specific user (as reviewer)."""
    try:
        reviews, total = await review_service.get_reviews_by_user(
            db, user_id, page, size
        )

        pages = (total + size - 1) // size

        return PaginatedReviewResponse(
            items=[ReviewResponseModel.from_orm(review) for review in reviews],
            total=total,
            page=page,
            size=size,
            pages=pages
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/summary/{user_id}", response_model=ReviewSummaryResponse)
async def get_review_summary(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get review summary for a user."""
    summary = await review_service.get_review_summary(db, user_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Review summary not found")

    # Format rating distribution
    rating_distribution = {
        "1": summary.rating_1_count,
        "2": summary.rating_2_count,
        "3": summary.rating_3_count,
        "4": summary.rating_4_count,
        "5": summary.rating_5_count
    }

    return ReviewSummaryResponse(
        user_id=str(summary.user_id),
        user_role=summary.user_role,
        total_reviews=summary.total_reviews,
        average_rating=summary.average_rating,
        rating_distribution=rating_distribution,
        reviews_as_vendor=summary.reviews_as_vendor,
        reviews_as_hospital=summary.reviews_as_hospital,
        verified_reviews_count=summary.verified_reviews_count,
        last_review_at=summary.last_review_at
    )


# Admin endpoints
@router.post("/{review_id}/moderate", response_model=APIResponse)
async def moderate_review(
    review_id: str,
    action_data: ReviewModerationAction,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Moderate a review (admin only)."""
    if current_user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        review = await review_service.moderate_review(
            db, review_id, action_data, current_user["user_id"]
        )

        if not review:
            raise HTTPException(status_code=404, detail="Review not found")

        # Emit event
        await event_service.emit_review_moderated(
            {
                "id": str(review.id),
                "status": review.status.value
            },
            action_data.action
        )

        return APIResponse(
            success=True,
            message=f"Review {action_data.action}ed successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
