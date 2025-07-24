from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
from enum import Enum
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import UserRole
from app.models.review import ReviewStatus, ReviewType


# Base schemas
class ReviewBase(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")
    comment: Optional[str] = Field(None, max_length=1000, description="Review comment")
    is_anonymous: bool = Field(False, description="Whether the review should be anonymous")


# Request schemas
class ReviewCreate(ReviewBase):
    order_id: str = Field(..., description="Order ID this review is for")
    
    @validator('comment')
    def validate_comment(cls, v):
        if v and len(v.strip()) == 0:
            return None
        return v


class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)
    is_anonymous: Optional[bool] = None
    
    @validator('comment')
    def validate_comment(cls, v):
        if v and len(v.strip()) == 0:
            return None
        return v


class ReviewResponse(BaseModel):
    order_id: str = Field(..., description="Order ID this review is for")
    response: str = Field(..., max_length=500, description="Response to the review")


class ReviewReport(BaseModel):
    reason: str = Field(..., description="Reason for reporting")
    description: Optional[str] = Field(None, max_length=500, description="Additional details")


class ReviewHelpfulnessVote(BaseModel):
    is_helpful: bool = Field(..., description="True if helpful, False if not helpful")


# Response schemas
class ReviewResponseModel(ReviewBase):
    id: str
    order_id: str
    reviewer_id: str
    reviewee_id: str
    review_type: ReviewType
    status: ReviewStatus
    is_verified: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Optional fields
    response: Optional[str] = None
    response_at: Optional[datetime] = None
    helpful_count: int = 0
    not_helpful_count: int = 0
    
    # Reviewer/Reviewee info (populated from external services)
    reviewer_name: Optional[str] = None
    reviewee_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class ReviewSummaryResponse(BaseModel):
    user_id: str
    user_role: UserRole
    total_reviews: int
    average_rating: float
    rating_distribution: dict = Field(description="Distribution of ratings 1-5")
    reviews_as_vendor: int
    reviews_as_hospital: int
    verified_reviews_count: int
    last_review_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ReviewReportResponse(BaseModel):
    id: str
    review_id: str
    reporter_id: str
    reason: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class ReviewStatsResponse(BaseModel):
    total_reviews: int
    average_rating: float
    rating_distribution: dict
    recent_reviews_count: int
    verified_reviews_percentage: float


# Pagination and filtering
class ReviewFilters(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    review_type: Optional[ReviewType] = None
    status: Optional[ReviewStatus] = None
    is_verified: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class PaginatedReviewResponse(BaseModel):
    items: List[ReviewResponseModel]
    total: int
    page: int
    size: int
    pages: int


# Admin schemas
class AdminReviewUpdate(BaseModel):
    status: Optional[ReviewStatus] = None
    flag_reason: Optional[str] = None
    admin_notes: Optional[str] = None


class ReviewModerationAction(BaseModel):
    action: str = Field(..., description="Action to take: approve, flag, hide, delete")
    reason: Optional[str] = Field(None, description="Reason for the action")
    admin_notes: Optional[str] = Field(None, description="Admin notes")


# Bulk operations
class BulkReviewAction(BaseModel):
    review_ids: List[str] = Field(..., description="List of review IDs")
    action: str = Field(..., description="Action to perform")
    reason: Optional[str] = None
