import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from geopy.distance import geodesic
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.emergency_config import (
    emergency_manager, EmergencyLevel, ESCALATION_RULES, 
    PRIORITY_RESPONSE_TIMES, NOTIFICATION_RADIUS_KM
)
from shared.models import UserRole


class LocationNotificationService:
    def __init__(self, websocket_manager):
        self.websocket_manager = websocket_manager
        self.active_alerts = {}
        self.escalation_tasks = {}
    
    async def send_location_based_alert(
        self, 
        alert_type: str,
        center_latitude: float,
        center_longitude: float,
        message: dict,
        radius_km: Optional[float] = None,
        target_roles: Optional[List[str]] = None,
        emergency_level: EmergencyLevel = EmergencyLevel.MEDIUM
    ):
        """Send location-based alert to users within radius."""
        
        # Get configuration for this alert type
        if radius_km is None:
            radius_km = emergency_manager.get_notification_radius(alert_type, emergency_level)
        
        if target_roles is None:
            target_roles = emergency_manager.get_target_roles_for_alert(alert_type)
        
        # Find users within radius
        target_users = await self._find_users_in_radius(
            center_latitude, center_longitude, radius_km, target_roles
        )
        
        # Send alerts to target users
        alert_id = f"{alert_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        sent_count = 0
        for user_id, user_info in target_users.items():
            enhanced_message = {
                **message,
                "alert_id": alert_id,
                "alert_type": alert_type,
                "emergency_level": emergency_level,
                "distance_km": user_info["distance_km"],
                "priority": emergency_level,
                "location": {
                    "latitude": center_latitude,
                    "longitude": center_longitude
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            success = await self.websocket_manager.send_personal_message(user_id, enhanced_message)
            if success:
                sent_count += 1
        
        # Store alert for potential escalation
        self.active_alerts[alert_id] = {
            "alert_type": alert_type,
            "center_latitude": center_latitude,
            "center_longitude": center_longitude,
            "radius_km": radius_km,
            "target_roles": target_roles,
            "emergency_level": emergency_level,
            "created_at": datetime.utcnow(),
            "sent_count": sent_count,
            "escalation_count": 0,
            "message": message
        }
        
        # Schedule escalation if needed
        if emergency_level in [EmergencyLevel.HIGH, EmergencyLevel.CRITICAL]:
            await self._schedule_escalation(alert_id)
        
        return {
            "alert_id": alert_id,
            "sent_count": sent_count,
            "radius_km": radius_km,
            "target_users": len(target_users)
        }
    
    async def send_emergency_zone_alert(
        self,
        zone_id: str,
        alert_type: str,
        message: dict,
        emergency_level: EmergencyLevel = EmergencyLevel.HIGH
    ):
        """Send alert to all users in an emergency zone."""
        
        zone_config = emergency_manager.zones.get(zone_id)
        if not zone_config:
            raise ValueError(f"Emergency zone {zone_id} not found")
        
        # Create emergency channel
        channel_id = emergency_manager.create_emergency_channel_id(zone_id, alert_type)
        
        # Send location-based alert
        result = await self.send_location_based_alert(
            alert_type=alert_type,
            center_latitude=zone_config.center_latitude,
            center_longitude=zone_config.center_longitude,
            message=message,
            radius_km=zone_config.radius_km,
            emergency_level=emergency_level
        )
        
        # If insufficient response, try backup zones
        if result["sent_count"] < zone_config.required_vendor_count:
            backup_zones = emergency_manager.get_backup_zones(zone_id)
            
            for backup_zone in backup_zones:
                backup_result = await self.send_location_based_alert(
                    alert_type=f"{alert_type}_backup",
                    center_latitude=backup_zone.center_latitude,
                    center_longitude=backup_zone.center_longitude,
                    message={
                        **message,
                        "backup_zone": True,
                        "primary_zone": zone_id
                    },
                    radius_km=backup_zone.radius_km,
                    emergency_level=emergency_level
                )
                
                result["sent_count"] += backup_result["sent_count"]
        
        return {
            **result,
            "zone_id": zone_id,
            "channel_id": channel_id,
            "backup_zones_activated": result["sent_count"] >= zone_config.required_vendor_count
        }
    
    async def send_proximity_alert(
        self,
        user_id: str,
        alert_type: str,
        message: dict,
        radius_km: float = 25.0,
        target_roles: Optional[List[str]] = None
    ):
        """Send alert to users near a specific user."""
        
        # Get user's current location
        user_location = await self._get_user_location(user_id)
        if not user_location:
            raise ValueError(f"Location not available for user {user_id}")
        
        return await self.send_location_based_alert(
            alert_type=alert_type,
            center_latitude=user_location["latitude"],
            center_longitude=user_location["longitude"],
            message=message,
            radius_km=radius_km,
            target_roles=target_roles
        )
    
    async def escalate_alert(self, alert_id: str):
        """Escalate an existing alert to wider radius."""
        
        if alert_id not in self.active_alerts:
            return False
        
        alert = self.active_alerts[alert_id]
        escalation_rules = ESCALATION_RULES.get(alert["emergency_level"])
        
        if not escalation_rules or alert["escalation_count"] >= escalation_rules["max_escalations"]:
            return False
        
        # Increase radius for escalation
        new_radius = min(
            alert["radius_km"] * 1.5,
            escalation_rules["escalation_radius_km"]
        )
        
        # Send escalated alert
        escalated_message = {
            **alert["message"],
            "escalated": True,
            "escalation_level": alert["escalation_count"] + 1,
            "original_alert_id": alert_id
        }
        
        result = await self.send_location_based_alert(
            alert_type=f"{alert['alert_type']}_escalated",
            center_latitude=alert["center_latitude"],
            center_longitude=alert["center_longitude"],
            message=escalated_message,
            radius_km=new_radius,
            target_roles=alert["target_roles"],
            emergency_level=alert["emergency_level"]
        )
        
        # Update alert record
        alert["escalation_count"] += 1
        alert["radius_km"] = new_radius
        alert["sent_count"] += result["sent_count"]
        
        # Schedule next escalation if needed
        if alert["escalation_count"] < escalation_rules["max_escalations"]:
            await self._schedule_escalation(alert_id)
        
        return True
    
    async def send_vendor_availability_alert(
        self,
        vendor_id: str,
        availability_status: str,
        radius_km: float = 30.0
    ):
        """Send vendor availability alert to nearby hospitals."""
        
        vendor_location = await self._get_user_location(vendor_id)
        if not vendor_location:
            return False
        
        message = {
            "type": "vendor_availability",
            "vendor_id": vendor_id,
            "status": availability_status,
            "location": vendor_location
        }
        
        return await self.send_location_based_alert(
            alert_type="vendor_availability",
            center_latitude=vendor_location["latitude"],
            center_longitude=vendor_location["longitude"],
            message=message,
            radius_km=radius_km,
            target_roles=[UserRole.HOSPITAL],
            emergency_level=EmergencyLevel.LOW
        )
    
    async def send_inventory_alert(
        self,
        vendor_id: str,
        inventory_data: dict,
        alert_level: EmergencyLevel = EmergencyLevel.MEDIUM
    ):
        """Send inventory-related alert to nearby hospitals."""
        
        vendor_location = await self._get_user_location(vendor_id)
        if not vendor_location:
            return False
        
        alert_type = "inventory_low" if alert_level == EmergencyLevel.MEDIUM else "inventory_critical"
        
        message = {
            "type": alert_type,
            "vendor_id": vendor_id,
            "inventory": inventory_data,
            "location": vendor_location
        }
        
        return await self.send_location_based_alert(
            alert_type=alert_type,
            center_latitude=vendor_location["latitude"],
            center_longitude=vendor_location["longitude"],
            message=message,
            target_roles=[UserRole.HOSPITAL, UserRole.ADMIN],
            emergency_level=alert_level
        )
    
    async def send_delivery_tracking_update(
        self,
        order_id: str,
        delivery_location: dict,
        hospital_id: str,
        vendor_id: str,
        eta_minutes: int
    ):
        """Send delivery tracking update to relevant parties."""
        
        message = {
            "type": "delivery_tracking",
            "order_id": order_id,
            "current_location": delivery_location,
            "eta_minutes": eta_minutes,
            "hospital_id": hospital_id,
            "vendor_id": vendor_id
        }
        
        # Send to hospital and vendor
        await self.websocket_manager.send_personal_message(hospital_id, message)
        await self.websocket_manager.send_personal_message(vendor_id, message)
        
        # Send to nearby users for awareness (optional)
        await self.send_location_based_alert(
            alert_type="delivery_in_area",
            center_latitude=delivery_location["latitude"],
            center_longitude=delivery_location["longitude"],
            message=message,
            radius_km=5.0,
            target_roles=[UserRole.VENDOR],
            emergency_level=EmergencyLevel.LOW
        )
    
    async def _find_users_in_radius(
        self,
        center_lat: float,
        center_lon: float,
        radius_km: float,
        target_roles: List[str]
    ) -> Dict[str, dict]:
        """Find users within radius of center point."""
        
        target_users = {}
        center_point = (center_lat, center_lon)
        
        for user_id, connection in self.websocket_manager.active_connections.items():
            # Check if user role matches target roles
            if connection.user_role not in target_roles:
                continue
            
            # Check if user has location data
            if not connection.location:
                continue
            
            user_location = connection.location
            if 'latitude' not in user_location or 'longitude' not in user_location:
                continue
            
            # Calculate distance
            user_point = (user_location['latitude'], user_location['longitude'])
            distance = geodesic(center_point, user_point).kilometers
            
            if distance <= radius_km:
                target_users[user_id] = {
                    "distance_km": round(distance, 2),
                    "location": user_location,
                    "role": connection.user_role
                }
        
        return target_users
    
    async def _get_user_location(self, user_id: str) -> Optional[dict]:
        """Get user's current location."""
        
        if user_id in self.websocket_manager.active_connections:
            connection = self.websocket_manager.active_connections[user_id]
            return connection.location
        
        return None
    
    async def _schedule_escalation(self, alert_id: str):
        """Schedule alert escalation."""
        
        if alert_id not in self.active_alerts:
            return
        
        alert = self.active_alerts[alert_id]
        escalation_rules = ESCALATION_RULES.get(alert["emergency_level"])
        
        if not escalation_rules:
            return
        
        escalation_delay = escalation_rules["escalation_time_minutes"] * 60  # Convert to seconds
        
        # Cancel existing escalation task if any
        if alert_id in self.escalation_tasks:
            self.escalation_tasks[alert_id].cancel()
        
        # Schedule new escalation
        async def escalate_after_delay():
            await asyncio.sleep(escalation_delay)
            await self.escalate_alert(alert_id)
        
        self.escalation_tasks[alert_id] = asyncio.create_task(escalate_after_delay())
    
    async def cleanup_expired_alerts(self, max_age_hours: int = 24):
        """Clean up expired alerts."""
        
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        expired_alerts = []
        
        for alert_id, alert in self.active_alerts.items():
            if alert["created_at"] < cutoff_time:
                expired_alerts.append(alert_id)
        
        for alert_id in expired_alerts:
            # Cancel escalation task if exists
            if alert_id in self.escalation_tasks:
                self.escalation_tasks[alert_id].cancel()
                del self.escalation_tasks[alert_id]
            
            # Remove alert
            del self.active_alerts[alert_id]
        
        return len(expired_alerts)
    
    def get_active_alerts_summary(self) -> dict:
        """Get summary of active alerts."""
        
        summary = {
            "total_alerts": len(self.active_alerts),
            "by_level": {},
            "by_type": {},
            "escalated_alerts": 0
        }
        
        for alert in self.active_alerts.values():
            # Count by level
            level = alert["emergency_level"]
            summary["by_level"][level] = summary["by_level"].get(level, 0) + 1
            
            # Count by type
            alert_type = alert["alert_type"]
            summary["by_type"][alert_type] = summary["by_type"].get(alert_type, 0) + 1
            
            # Count escalated alerts
            if alert["escalation_count"] > 0:
                summary["escalated_alerts"] += 1
        
        return summary
