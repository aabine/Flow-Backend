from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional, Set
import json
import asyncio
import redis.asyncio as redis
from datetime import datetime
import uuid
import os
import sys

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings

settings = get_settings()
from app.core.websocket_manager import WebSocketManager
from app.core.db_init import init_websocket_database
from app.services.auth_service import AuthService
from app.services.event_service import EventService
from app.services.location_notification_service import LocationNotificationService
from app.core.emergency_config import emergency_manager, EmergencyLevel
from shared.models import UserRole, EventType
from shared.exceptions import AuthException
import logging

logger = logging.getLogger(__name__)

app = FastAPI(
    title="WebSocket Service",
    description="Real-time WebSocket communication service for critical platform updates",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database initialization flag
_db_initialized = False

@app.on_event("startup")
async def startup_event():
    """Initialize database and services on startup."""
    global _db_initialized
    if not _db_initialized:
        logger.info("🚀 Starting WebSocket Service...")
        success = await init_websocket_database()
        if success:
            logger.info("✅ WebSocket Service database initialization completed")
            _db_initialized = True
        else:
            logger.error("❌ WebSocket Service database initialization failed")
            # Don't exit - let the service start but log the error
    else:
        logger.info("ℹ️ Database already initialized")

# Initialize services
auth_service = AuthService()
websocket_manager = WebSocketManager()
event_service = EventService(websocket_manager)
location_notification_service = LocationNotificationService(websocket_manager)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        user = await auth_service.verify_token(token)
        if user is None:
            raise credentials_exception
        return user
    except AuthException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "WebSocket Service",
        "version": "1.0.0",
        "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
        "active_connections": websocket_manager.get_connection_count()
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
        "active_connections": websocket_manager.get_connection_count()
    }


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, token: Optional[str] = None):
    """Main WebSocket endpoint for real-time communication."""
    try:
        # Authenticate user
        if token:
            user_data = await auth_service.verify_token(token)
            if not user_data or user_data.get("user_id") != user_id:
                await websocket.close(code=4001, reason="Authentication failed")
                return
        else:
            await websocket.close(code=4001, reason="Token required")
            return
        
        # Accept connection
        await websocket.accept()
        
        # Add to connection manager
        await websocket_manager.connect(user_id, websocket, user_data.get("role"))
        
        try:
            # Send welcome message
            await websocket_manager.send_personal_message(user_id, {
                "type": "connection_established",
                "message": "WebSocket connection established",
                "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
                "user_id": user_id
            })
            
            # Listen for messages
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle different message types
                await handle_websocket_message(user_id, message)
                
        except WebSocketDisconnect:
            await websocket_manager.disconnect(user_id)
            
    except Exception as e:
        print(f"WebSocket error for user {user_id}: {str(e)}")
        await websocket_manager.disconnect(user_id)


async def handle_websocket_message(user_id: str, message: dict):
    """Handle incoming WebSocket messages."""
    message_type = message.get("type")
    
    if message_type == "ping":
        await websocket_manager.send_personal_message(user_id, {
            "type": "pong",
            "timestamp": datetime.now(datetime.timezone.utc).isoformat()
        })
    
    elif message_type == "subscribe":
        # Subscribe to specific event types
        event_types = message.get("events", [])
        await websocket_manager.subscribe_user_to_events(user_id, event_types)
        
        await websocket_manager.send_personal_message(user_id, {
            "type": "subscription_confirmed",
            "events": event_types,
            "timestamp": datetime.now(datetime.timezone.utc).isoformat()
        })
    
    elif message_type == "unsubscribe":
        # Unsubscribe from specific event types
        event_types = message.get("events", [])
        await websocket_manager.unsubscribe_user_from_events(user_id, event_types)
        
        await websocket_manager.send_personal_message(user_id, {
            "type": "unsubscription_confirmed",
            "events": event_types,
            "timestamp": datetime.now(datetime.timezone.utc).isoformat()
        })
    
    elif message_type == "location_update":
        # Update user location for proximity-based notifications
        latitude = message.get("latitude")
        longitude = message.get("longitude")
        
        if latitude and longitude:
            await websocket_manager.update_user_location(user_id, latitude, longitude)
            
            await websocket_manager.send_personal_message(user_id, {
                "type": "location_updated",
                "timestamp": datetime.now(datetime.timezone.utc).isoformat()
            })


@app.websocket("/ws/emergency/{area_id}")
async def emergency_websocket(websocket: WebSocket, area_id: str, token: Optional[str] = None):
    """Emergency WebSocket channel for critical alerts in specific areas."""
    try:
        # Authenticate user
        if token:
            user_data = await auth_service.verify_token(token)
            if not user_data:
                await websocket.close(code=4001, reason="Authentication failed")
                return
        else:
            await websocket.close(code=4001, reason="Token required")
            return
        
        await websocket.accept()
        user_id = user_data.get("user_id")
        
        # Add to emergency channel
        await websocket_manager.join_emergency_channel(user_id, area_id, websocket)
        
        try:
            await websocket_manager.send_personal_message(user_id, {
                "type": "emergency_channel_joined",
                "area_id": area_id,
                "timestamp": datetime.now(datetime.timezone.utc).isoformat()
            })
            
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle emergency messages
                if message.get("type") == "emergency_alert":
                    # Only hospitals and admins can send emergency alerts
                    if user_data.get("role") in [UserRole.HOSPITAL, UserRole.ADMIN]:
                        await websocket_manager.broadcast_emergency_alert(area_id, {
                            "type": "emergency_alert",
                            "title": message.get("title"),
                            "message": message.get("message"),
                            "severity": message.get("severity", "high"),
                            "location": message.get("location"),
                            "sender_id": user_id,
                            "timestamp": datetime.now(datetime.timezone.utc).isoformat()
                        })
                
        except WebSocketDisconnect:
            await websocket_manager.leave_emergency_channel(user_id, area_id)
            
    except Exception as e:
        print(f"Emergency WebSocket error for user {user_id} in area {area_id}: {str(e)}")
        await websocket_manager.leave_emergency_channel(user_id, area_id)


@app.post("/broadcast/inventory-update")
async def broadcast_inventory_update(
    vendor_id: str,
    inventory_id: str,
    cylinder_size: str,
    available_quantity: int,
    location: dict
):
    """Broadcast inventory update to relevant users."""
    try:
        message = {
            "type": "inventory_update",
            "vendor_id": vendor_id,
            "inventory_id": inventory_id,
            "cylinder_size": cylinder_size,
            "available_quantity": available_quantity,
            "location": location,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Broadcast to hospitals in the area
        await websocket_manager.broadcast_to_nearby_hospitals(location, message, radius_km=50)
        
        # Send to vendor
        await websocket_manager.send_personal_message(vendor_id, message)
        
        return {"status": "broadcasted", "message_type": "inventory_update"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to broadcast inventory update: {str(e)}"
        )


@app.post("/broadcast/order-status")
async def broadcast_order_status(
    order_id: str,
    hospital_id: str,
    vendor_id: str,
    status: str,
    estimated_delivery: Optional[str] = None,
    tracking_info: Optional[dict] = None
):
    """Broadcast order status update to relevant parties."""
    try:
        message = {
            "type": "order_status_update",
            "order_id": order_id,
            "status": status,
            "estimated_delivery": estimated_delivery,
            "tracking_info": tracking_info,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to hospital
        await websocket_manager.send_personal_message(hospital_id, message)
        
        # Send to vendor if assigned
        if vendor_id:
            await websocket_manager.send_personal_message(vendor_id, message)
        
        return {"status": "broadcasted", "message_type": "order_status_update"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to broadcast order status: {str(e)}"
        )


@app.post("/broadcast/emergency-alert")
async def broadcast_emergency_alert(
    title: str,
    message: str,
    location: dict,
    radius_km: float = 50.0,
    severity: str = "high"
):
    """Broadcast emergency alert to vendors in area."""
    try:
        alert_message = {
            "type": "emergency_alert",
            "title": title,
            "message": message,
            "location": location,
            "severity": severity,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Broadcast to vendors in the area
        await websocket_manager.broadcast_to_nearby_vendors(location, alert_message, radius_km)
        
        return {"status": "broadcasted", "message_type": "emergency_alert"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to broadcast emergency alert: {str(e)}"
        )


@app.post("/broadcast/delivery-update")
async def broadcast_delivery_update(
    order_id: str,
    hospital_id: str,
    vendor_id: str,
    delivery_status: str,
    current_location: Optional[dict] = None,
    eta_minutes: Optional[int] = None
):
    """Broadcast delivery status update."""
    try:
        message = {
            "type": "delivery_update",
            "order_id": order_id,
            "delivery_status": delivery_status,
            "current_location": current_location,
            "eta_minutes": eta_minutes,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to hospital
        await websocket_manager.send_personal_message(hospital_id, message)
        
        # Send to vendor
        await websocket_manager.send_personal_message(vendor_id, message)
        
        return {"status": "broadcasted", "message_type": "delivery_update"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to broadcast delivery update: {str(e)}"
        )


@app.get("/connections")
async def get_active_connections():
    """Get active WebSocket connections (admin only)."""
    return {
        "total_connections": websocket_manager.get_connection_count(),
        "connections_by_role": websocket_manager.get_connections_by_role(),
        "emergency_channels": websocket_manager.get_emergency_channels_info()
    }


@app.post("/test-connection/{user_id}")
async def test_connection(user_id: str, message: dict):
    """Test WebSocket connection by sending a message."""
    try:
        await websocket_manager.send_personal_message(user_id, {
            "type": "test_message",
            "data": message,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return {"status": "message_sent", "user_id": user_id}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send test message: {str(e)}"
        )


@app.post("/broadcast/system")
async def broadcast_system_message(
    message: dict,
    current_user: dict = Depends(get_current_user)
):
    """Broadcast system message to all connected users."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    await websocket_manager.broadcast_to_all({
        "type": "system_message",
        "message": message["message"],
        "timestamp": datetime.utcnow().isoformat(),
        "priority": message.get("priority", "normal")
    })
    
    return {"status": "success", "message": "System message broadcasted"}


@app.post("/location-alert")
async def send_location_alert(
    alert_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Send location-based alert to users within radius."""
    if current_user["role"] not in ["admin", "vendor"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    required_fields = ["alert_type", "latitude", "longitude", "message"]
    if not all(field in alert_data for field in required_fields):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    try:
        result = await location_notification_service.send_location_based_alert(
            alert_type=alert_data["alert_type"],
            center_latitude=alert_data["latitude"],
            center_longitude=alert_data["longitude"],
            message=alert_data["message"],
            radius_km=alert_data.get("radius_km"),
            target_roles=alert_data.get("target_roles"),
            emergency_level=EmergencyLevel(alert_data.get("emergency_level", "medium"))
        )
        
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/emergency-zone-alert")
async def send_emergency_zone_alert(
    alert_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Send alert to emergency zone."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    required_fields = ["zone_id", "alert_type", "message"]
    if not all(field in alert_data for field in required_fields):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    try:
        result = await location_notification_service.send_emergency_zone_alert(
            zone_id=alert_data["zone_id"],
            alert_type=alert_data["alert_type"],
            message=alert_data["message"],
            emergency_level=EmergencyLevel(alert_data.get("emergency_level", "high"))
        )
        
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/proximity-alert")
async def send_proximity_alert(
    alert_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Send alert to users near a specific user."""
    required_fields = ["user_id", "alert_type", "message"]
    if not all(field in alert_data for field in required_fields):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    # Users can only send proximity alerts for themselves unless they're admin
    if current_user["user_id"] != alert_data["user_id"] and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Can only send proximity alerts for yourself")
    
    try:
        result = await location_notification_service.send_proximity_alert(
            user_id=alert_data["user_id"],
            alert_type=alert_data["alert_type"],
            message=alert_data["message"],
            radius_km=alert_data.get("radius_km", 25.0),
            target_roles=alert_data.get("target_roles")
        )
        
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/emergency-zones")
async def get_emergency_zones(
    current_user: dict = Depends(get_current_user)
):
    """Get list of emergency zones."""
    zones = []
    for zone_id, zone_config in emergency_manager.zones.items():
        zones.append({
            "zone_id": zone_id,
            "name": zone_config.name,
            "center_latitude": zone_config.center_latitude,
            "center_longitude": zone_config.center_longitude,
            "radius_km": zone_config.radius_km,
            "priority_level": zone_config.priority_level,
            "required_vendor_count": zone_config.required_vendor_count
        })
    
    return {"zones": zones}


@app.get("/active-alerts")
async def get_active_alerts(
    current_user: dict = Depends(get_current_user)
):
    """Get summary of active alerts."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    summary = location_notification_service.get_active_alerts_summary()
    return {"active_alerts": summary}


@app.post("/escalate-alert/{alert_id}")
async def escalate_alert(
    alert_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Manually escalate an alert."""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    success = await location_notification_service.escalate_alert(alert_id)
    
    if success:
        return {"status": "success", "message": "Alert escalated"}
    else:
        raise HTTPException(status_code=404, detail="Alert not found or cannot be escalated")





if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8012)
