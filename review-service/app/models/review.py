from sqlalchemy import Column, String, Boolean, DateTime, Text, Enum, Integer, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import sys
import os
from enum import Enum as PyEnum

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.database import Base
from shared.models import UserRole


class ReviewStatus(str, PyEnum):
    ACTIVE = "active"
    HIDDEN = "hidden"
    FLAGGED = "flagged"
    DELETED = "deleted"


class ReviewType(str, PyEnum):
    HOSPITAL_TO_VENDOR = "hospital_to_vendor"
    VENDOR_TO_HOSPITAL = "vendor_to_hospital"


class Review(Base):
    __tablename__ = "reviews"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    order_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    reviewer_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    reviewee_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Review content
    rating = Column(Integer, nullable=False)  # 1-5 stars
    comment = Column(Text, nullable=True)
    review_type = Column(Enum(ReviewType), nullable=False)
    
    # Review metadata
    status = Column(Enum(ReviewStatus), default=ReviewStatus.ACTIVE, index=True)
    is_verified = Column(Boolean, default=False)
    is_anonymous = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Moderation
    flagged_at = Column(DateTime(timezone=True), nullable=True)
    flagged_by = Column(UUID(as_uuid=True), nullable=True)
    flag_reason = Column(String, nullable=True)
    
    # Response from reviewee
    response = Column(Text, nullable=True)
    response_at = Column(DateTime(timezone=True), nullable=True)
    
    # Helpful votes
    helpful_count = Column(Integer, default=0)
    not_helpful_count = Column(Integer, default=0)
    
    __table_args__ = (
        Index('idx_review_order_reviewer', 'order_id', 'reviewer_id'),
        Index('idx_review_reviewee_rating', 'reviewee_id', 'rating'),
        Index('idx_review_created_status', 'created_at', 'status'),
    )


class ReviewSummary(Base):
    __tablename__ = "review_summaries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    user_role = Column(Enum(UserRole), nullable=False)
    
    # Rating statistics
    total_reviews = Column(Integer, default=0)
    average_rating = Column(Float, default=0.0)
    rating_1_count = Column(Integer, default=0)
    rating_2_count = Column(Integer, default=0)
    rating_3_count = Column(Integer, default=0)
    rating_4_count = Column(Integer, default=0)
    rating_5_count = Column(Integer, default=0)
    
    # Review counts by type
    reviews_as_vendor = Column(Integer, default=0)
    reviews_as_hospital = Column(Integer, default=0)
    
    # Quality metrics
    verified_reviews_count = Column(Integer, default=0)
    flagged_reviews_count = Column(Integer, default=0)
    
    # Timestamps
    last_review_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ReviewReport(Base):
    __tablename__ = "review_reports"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    review_id = Column(UUID(as_uuid=True), ForeignKey('reviews.id'), nullable=False, index=True)
    reporter_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Report details
    reason = Column(String, nullable=False)  # spam, inappropriate, fake, etc.
    description = Column(Text, nullable=True)
    
    # Report status
    status = Column(String, default="pending")  # pending, reviewed, resolved, dismissed
    admin_notes = Column(Text, nullable=True)
    resolved_by = Column(UUID(as_uuid=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship
    review = relationship("Review", backref="reports")


class ReviewHelpfulness(Base):
    __tablename__ = "review_helpfulness"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    review_id = Column(UUID(as_uuid=True), ForeignKey('reviews.id'), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Vote
    is_helpful = Column(Boolean, nullable=False)  # True for helpful, False for not helpful
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship
    review = relationship("Review", backref="helpfulness_votes")
    
    __table_args__ = (
        Index('idx_review_helpfulness_unique', 'review_id', 'user_id', unique=True),
    )
