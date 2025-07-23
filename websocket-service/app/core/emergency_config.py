from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import json


class EmergencyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationRadius(str, Enum):
    IMMEDIATE = "immediate"  # 5km
    LOCAL = "local"          # 15km
    REGIONAL = "regional"    # 50km
    CITYWIDE = "citywide"    # 100km


@dataclass
class EmergencyZoneConfig:
    zone_id: str
    name: str
    center_latitude: float
    center_longitude: float
    radius_km: float
    priority_level: EmergencyLevel
    auto_escalation: bool = True
    max_response_time_minutes: int = 30
    required_vendor_count: int = 3
    backup_zones: List[str] = None


@dataclass
class LocationBasedAlert:
    alert_type: str
    radius_km: float
    target_roles: List[str]
    priority: EmergencyLevel
    auto_broadcast: bool = True
    escalation_time_minutes: int = 15


# Nigeria Major Cities Emergency Zones Configuration
NIGERIA_EMERGENCY_ZONES = {
    "lagos_mainland": EmergencyZoneConfig(
        zone_id="lagos_mainland",
        name="Lagos Mainland Emergency Zone",
        center_latitude=6.5244,
        center_longitude=3.3792,
        radius_km=25.0,
        priority_level=EmergencyLevel.HIGH,
        required_vendor_count=5,
        backup_zones=["lagos_island", "ikeja"]
    ),
    "lagos_island": EmergencyZoneConfig(
        zone_id="lagos_island",
        name="Lagos Island Emergency Zone",
        center_latitude=6.4541,
        center_longitude=3.3947,
        radius_km=15.0,
        priority_level=EmergencyLevel.CRITICAL,
        required_vendor_count=3,
        backup_zones=["lagos_mainland", "victoria_island"]
    ),
    "ikeja": EmergencyZoneConfig(
        zone_id="ikeja",
        name="Ikeja Emergency Zone",
        center_latitude=6.6018,
        center_longitude=3.3515,
        radius_km=20.0,
        priority_level=EmergencyLevel.HIGH,
        required_vendor_count=4,
        backup_zones=["lagos_mainland"]
    ),
    "abuja_central": EmergencyZoneConfig(
        zone_id="abuja_central",
        name="Abuja Central Emergency Zone",
        center_latitude=9.0765,
        center_longitude=7.3986,
        radius_km=30.0,
        priority_level=EmergencyLevel.HIGH,
        required_vendor_count=4,
        backup_zones=["abuja_gwagwalada"]
    ),
    "kano_central": EmergencyZoneConfig(
        zone_id="kano_central",
        name="Kano Central Emergency Zone",
        center_latitude=12.0022,
        center_longitude=8.5920,
        radius_km=25.0,
        priority_level=EmergencyLevel.MEDIUM,
        required_vendor_count=3,
        backup_zones=["kano_nassarawa"]
    ),
    "port_harcourt": EmergencyZoneConfig(
        zone_id="port_harcourt",
        name="Port Harcourt Emergency Zone",
        center_latitude=4.8156,
        center_longitude=7.0498,
        radius_km=20.0,
        priority_level=EmergencyLevel.HIGH,
        required_vendor_count=3,
        backup_zones=["rivers_state"]
    ),
    "ibadan_central": EmergencyZoneConfig(
        zone_id="ibadan_central",
        name="Ibadan Central Emergency Zone",
        center_latitude=7.3775,
        center_longitude=3.9470,
        radius_km=25.0,
        priority_level=EmergencyLevel.MEDIUM,
        required_vendor_count=3,
        backup_zones=["oyo_state"]
    )
}

# Location-based notification configurations
LOCATION_ALERTS = {
    "inventory_low": LocationBasedAlert(
        alert_type="inventory_low",
        radius_km=30.0,
        target_roles=["hospital", "admin"],
        priority=EmergencyLevel.MEDIUM,
        escalation_time_minutes=60
    ),
    "inventory_critical": LocationBasedAlert(
        alert_type="inventory_critical",
        radius_km=50.0,
        target_roles=["hospital", "vendor", "admin"],
        priority=EmergencyLevel.HIGH,
        escalation_time_minutes=30
    ),
    "emergency_order": LocationBasedAlert(
        alert_type="emergency_order",
        radius_km=25.0,
        target_roles=["vendor"],
        priority=EmergencyLevel.CRITICAL,
        escalation_time_minutes=10
    ),
    "vendor_offline": LocationBasedAlert(
        alert_type="vendor_offline",
        radius_km=40.0,
        target_roles=["hospital", "admin"],
        priority=EmergencyLevel.MEDIUM,
        escalation_time_minutes=45
    ),
    "delivery_delayed": LocationBasedAlert(
        alert_type="delivery_delayed",
        radius_km=15.0,
        target_roles=["hospital", "vendor", "admin"],
        priority=EmergencyLevel.MEDIUM,
        escalation_time_minutes=30
    ),
    "system_outage": LocationBasedAlert(
        alert_type="system_outage",
        radius_km=100.0,
        target_roles=["hospital", "vendor", "admin"],
        priority=EmergencyLevel.HIGH,
        escalation_time_minutes=15
    )
}

# Notification radius mappings
NOTIFICATION_RADIUS_KM = {
    NotificationRadius.IMMEDIATE: 5.0,
    NotificationRadius.LOCAL: 15.0,
    NotificationRadius.REGIONAL: 50.0,
    NotificationRadius.CITYWIDE: 100.0
}

# Emergency escalation rules
ESCALATION_RULES = {
    EmergencyLevel.LOW: {
        "initial_radius_km": 15.0,
        "escalation_radius_km": 30.0,
        "escalation_time_minutes": 60,
        "max_escalations": 2
    },
    EmergencyLevel.MEDIUM: {
        "initial_radius_km": 25.0,
        "escalation_radius_km": 50.0,
        "escalation_time_minutes": 30,
        "max_escalations": 3
    },
    EmergencyLevel.HIGH: {
        "initial_radius_km": 35.0,
        "escalation_radius_km": 75.0,
        "escalation_time_minutes": 15,
        "max_escalations": 4
    },
    EmergencyLevel.CRITICAL: {
        "initial_radius_km": 50.0,
        "escalation_radius_km": 100.0,
        "escalation_time_minutes": 5,
        "max_escalations": 5
    }
}

# Priority response times (in minutes)
PRIORITY_RESPONSE_TIMES = {
    EmergencyLevel.LOW: 120,      # 2 hours
    EmergencyLevel.MEDIUM: 60,    # 1 hour
    EmergencyLevel.HIGH: 30,      # 30 minutes
    EmergencyLevel.CRITICAL: 15   # 15 minutes
}


class EmergencyChannelManager:
    def __init__(self):
        self.zones = NIGERIA_EMERGENCY_ZONES
        self.alerts = LOCATION_ALERTS
        self.active_emergencies = {}
    
    def get_zone_by_location(self, latitude: float, longitude: float) -> Optional[EmergencyZoneConfig]:
        """Find the emergency zone for a given location."""
        from geopy.distance import geodesic
        
        for zone in self.zones.values():
            zone_center = (zone.center_latitude, zone.center_longitude)
            location = (latitude, longitude)
            distance = geodesic(zone_center, location).kilometers
            
            if distance <= zone.radius_km:
                return zone
        
        return None
    
    def get_notification_radius(self, alert_type: str, emergency_level: EmergencyLevel) -> float:
        """Get notification radius for alert type and emergency level."""
        if alert_type in self.alerts:
            base_radius = self.alerts[alert_type].radius_km
        else:
            base_radius = 25.0  # Default radius
        
        # Adjust radius based on emergency level
        multiplier = {
            EmergencyLevel.LOW: 0.8,
            EmergencyLevel.MEDIUM: 1.0,
            EmergencyLevel.HIGH: 1.5,
            EmergencyLevel.CRITICAL: 2.0
        }.get(emergency_level, 1.0)
        
        return base_radius * multiplier
    
    def should_escalate(self, emergency_id: str, elapsed_minutes: int) -> bool:
        """Check if emergency should be escalated."""
        if emergency_id not in self.active_emergencies:
            return False
        
        emergency = self.active_emergencies[emergency_id]
        escalation_rules = ESCALATION_RULES.get(emergency.get("level", EmergencyLevel.MEDIUM))
        
        return elapsed_minutes >= escalation_rules["escalation_time_minutes"]
    
    def get_backup_zones(self, primary_zone_id: str) -> List[EmergencyZoneConfig]:
        """Get backup zones for a primary zone."""
        if primary_zone_id not in self.zones:
            return []
        
        primary_zone = self.zones[primary_zone_id]
        backup_zones = []
        
        if primary_zone.backup_zones:
            for backup_id in primary_zone.backup_zones:
                if backup_id in self.zones:
                    backup_zones.append(self.zones[backup_id])
        
        return backup_zones
    
    def create_emergency_channel_id(self, zone_id: str, emergency_type: str) -> str:
        """Create unique emergency channel ID."""
        import uuid
        from datetime import datetime
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        
        return f"emergency_{zone_id}_{emergency_type}_{timestamp}_{unique_id}"
    
    def get_target_roles_for_alert(self, alert_type: str) -> List[str]:
        """Get target user roles for specific alert type."""
        if alert_type in self.alerts:
            return self.alerts[alert_type].target_roles
        
        # Default roles for unknown alert types
        return ["admin"]


# Global emergency channel manager instance
emergency_manager = EmergencyChannelManager()
