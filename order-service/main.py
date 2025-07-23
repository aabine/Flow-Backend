from fastapi import FastAPI, HTTPException, Depends, status, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional, List
import os
import sys

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.database import get_db
from app.models.order import Order, OrderItem
from app.schemas.order import OrderCreate, OrderResponse, OrderUpdate, OrderListResponse
from app.services.order_service import OrderService
from app.services.event_service import EventService
from shared.models import OrderStatus, APIResponse, UserRole

app = FastAPI(
    title="Order Service",
    description="Order management and lifecycle service",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

order_service = OrderService()
event_service = EventService()


def get_current_user(
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None)
) -> dict:
    """Get current user from headers (set by API Gateway)."""
    if not x_user_id or not x_user_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User authentication required"
        )
    return {"user_id": x_user_id, "role": x_user_role}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Order Service",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/orders", response_model=APIResponse)
async def create_order(
    order_data: OrderCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new order."""
    try:
        # Only hospitals can create orders
        if current_user["role"] != UserRole.HOSPITAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only hospitals can create orders"
            )
        
        # Create order
        order = await order_service.create_order(db, current_user["user_id"], order_data)
        
        # Emit order created event
        await event_service.emit_order_created(order)
        
        # If emergency order, emit emergency event
        if order_data.is_emergency:
            await event_service.emit_emergency_order(order)
        
        return APIResponse(
            success=True,
            message="Order created successfully",
            data={
                "order_id": str(order.id),
                "reference": order.reference,
                "status": order.status,
                "is_emergency": order.is_emergency
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create order: {str(e)}"
        )


@app.get("/orders", response_model=OrderListResponse)
async def get_orders(
    page: int = 1,
    size: int = 20,
    status_filter: Optional[OrderStatus] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get orders for current user."""
    try:
        orders, total = await order_service.get_user_orders(
            db, current_user["user_id"], current_user["role"], page, size, status_filter
        )
        
        return OrderListResponse(
            items=[OrderResponse.from_orm(order) for order in orders],
            total=total,
            page=page,
            size=size,
            pages=(total + size - 1) // size
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get orders: {str(e)}"
        )


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get order by ID."""
    try:
        order = await order_service.get_order_by_id(db, order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        # Check access permissions
        if not await order_service.can_access_order(order, current_user["user_id"], current_user["role"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return OrderResponse.from_orm(order)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get order: {str(e)}"
        )


@app.put("/orders/{order_id}", response_model=APIResponse)
async def update_order(
    order_id: str,
    order_update: OrderUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update order status."""
    try:
        order = await order_service.get_order_by_id(db, order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        # Check permissions for status updates
        if not await order_service.can_update_order(order, current_user["user_id"], current_user["role"], order_update):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied for this update"
            )
        
        # Update order
        updated_order = await order_service.update_order(db, order_id, order_update)
        
        # Emit status change event
        if order_update.status:
            await event_service.emit_order_status_changed(updated_order, order_update.status)
        
        return APIResponse(
            success=True,
            message="Order updated successfully",
            data={
                "order_id": str(updated_order.id),
                "status": updated_order.status
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update order: {str(e)}"
        )


@app.post("/orders/{order_id}/accept", response_model=APIResponse)
async def accept_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Accept order (vendor only)."""
    try:
        if current_user["role"] != UserRole.VENDOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only vendors can accept orders"
            )
        
        order = await order_service.accept_order(db, order_id, current_user["user_id"])
        
        # Emit order accepted event
        await event_service.emit_order_accepted(order)
        
        return APIResponse(
            success=True,
            message="Order accepted successfully",
            data={"order_id": str(order.id)}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to accept order: {str(e)}"
        )


@app.post("/orders/{order_id}/cancel", response_model=APIResponse)
async def cancel_order(
    order_id: str,
    reason: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel order."""
    try:
        order = await order_service.get_order_by_id(db, order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        # Check if user can cancel this order
        if not await order_service.can_cancel_order(order, current_user["user_id"], current_user["role"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot cancel this order"
            )
        
        cancelled_order = await order_service.cancel_order(db, order_id, reason)
        
        # Emit order cancelled event
        await event_service.emit_order_cancelled(cancelled_order, reason)
        
        return APIResponse(
            success=True,
            message="Order cancelled successfully",
            data={"order_id": str(cancelled_order.id)}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel order: {str(e)}"
        )


@app.get("/orders/{order_id}/tracking")
async def get_order_tracking(
    order_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get order tracking information."""
    try:
        order = await order_service.get_order_by_id(db, order_id)
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        # Check access permissions
        if not await order_service.can_access_order(order, current_user["user_id"], current_user["role"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        tracking_info = await order_service.get_order_tracking(db, order_id)
        
        return {
            "order_id": order_id,
            "status": order.status,
            "tracking": tracking_info,
            "estimated_delivery": order.estimated_delivery_time,
            "last_updated": order.updated_at
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get tracking info: {str(e)}"
        )


@app.get("/emergency-orders")
async def get_emergency_orders(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get emergency orders (vendor and admin only)."""
    try:
        if current_user["role"] not in [UserRole.VENDOR, UserRole.ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        emergency_orders = await order_service.get_emergency_orders(db, current_user["user_id"], current_user["role"])
        
        return {
            "emergency_orders": [OrderResponse.from_orm(order) for order in emergency_orders],
            "count": len(emergency_orders)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get emergency orders: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
