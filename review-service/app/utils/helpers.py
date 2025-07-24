from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import httpx
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import get_settings

settings = get_settings()


async def get_user_details(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user details from user service."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.USER_SERVICE_URL}/users/{user_id}")
            if response.status_code == 200:
                return response.json()
            return None
    except Exception as e:
        print(f"Error fetching user details: {e}")
        return None


async def get_order_details(order_id: str) -> Optional[Dict[str, Any]]:
    """Get order details from order service."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.ORDER_SERVICE_URL}/orders/{order_id}")
            if response.status_code == 200:
                return response.json()
            return None
    except Exception as e:
        print(f"Error fetching order details: {e}")
        return None


async def send_notification(notification_data: Dict[str, Any]) -> bool:
    """Send notification via notification service."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.NOTIFICATION_SERVICE_URL}/notifications/",
                json=notification_data
            )
            return response.status_code == 200
    except Exception as e:
        print(f"Error sending notification: {e}")
        return False


def calculate_rating_distribution(ratings: Dict[str, int]) -> Dict[str, float]:
    """Calculate rating distribution percentages."""
    total = sum(ratings.values())
    if total == 0:
        return {str(i): 0.0 for i in range(1, 6)}
    
    return {
        rating: (count / total) * 100
        for rating, count in ratings.items()
    }


def is_within_edit_window(created_at: datetime, window_hours: int = 24) -> bool:
    """Check if review is within edit window."""
    edit_deadline = created_at + timedelta(hours=window_hours)
    return datetime.utcnow() <= edit_deadline


def format_review_for_response(review, include_personal_info: bool = True) -> Dict[str, Any]:
    """Format review data for API response."""
    data = {
        "id": str(review.id),
        "order_id": str(review.order_id),
        "rating": review.rating,
        "comment": review.comment if not review.is_anonymous or include_personal_info else None,
        "review_type": review.review_type.value,
        "status": review.status.value,
        "is_verified": review.is_verified,
        "is_anonymous": review.is_anonymous,
        "created_at": review.created_at.isoformat(),
        "updated_at": review.updated_at.isoformat() if review.updated_at else None,
        "helpful_count": review.helpful_count,
        "not_helpful_count": review.not_helpful_count
    }
    
    if include_personal_info:
        data.update({
            "reviewer_id": str(review.reviewer_id),
            "reviewee_id": str(review.reviewee_id),
            "response": review.response,
            "response_at": review.response_at.isoformat() if review.response_at else None
        })
    
    return data


def validate_rating(rating: int) -> bool:
    """Validate rating value."""
    return 1 <= rating <= 5


def sanitize_comment(comment: str) -> str:
    """Basic comment sanitization."""
    if not comment:
        return ""
    
    # Remove excessive whitespace
    comment = " ".join(comment.split())
    
    # Truncate if too long
    max_length = settings.MAX_REVIEW_LENGTH
    if len(comment) > max_length:
        comment = comment[:max_length].rsplit(' ', 1)[0] + "..."
    
    return comment


def generate_review_summary_stats(reviews) -> Dict[str, Any]:
    """Generate summary statistics for reviews."""
    if not reviews:
        return {
            "total_reviews": 0,
            "average_rating": 0.0,
            "rating_distribution": {str(i): 0 for i in range(1, 6)},
            "recent_reviews_count": 0,
            "verified_reviews_percentage": 0.0
        }
    
    total_reviews = len(reviews)
    total_rating = sum(review.rating for review in reviews)
    average_rating = total_rating / total_reviews if total_reviews > 0 else 0.0
    
    # Rating distribution
    rating_counts = {str(i): 0 for i in range(1, 6)}
    verified_count = 0
    recent_count = 0
    
    recent_threshold = datetime.utcnow() - timedelta(days=30)
    
    for review in reviews:
        rating_counts[str(review.rating)] += 1
        if review.is_verified:
            verified_count += 1
        if review.created_at >= recent_threshold:
            recent_count += 1
    
    verified_percentage = (verified_count / total_reviews) * 100 if total_reviews > 0 else 0.0
    
    return {
        "total_reviews": total_reviews,
        "average_rating": round(average_rating, 2),
        "rating_distribution": rating_counts,
        "recent_reviews_count": recent_count,
        "verified_reviews_percentage": round(verified_percentage, 2)
    }
