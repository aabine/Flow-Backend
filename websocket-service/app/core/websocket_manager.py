from fastapi import WebSocket
from typing import Dict, List, Optional, Set
import json
import asyncio
from datetime import datetime
import redis.asyncio as redis
from geopy.distance import geodesic
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared.models import UserRole
from .config import settings


class ConnectionInfo:
    def __init__(self, websocket: WebSocket, user_role: str, location: Optional[dict] = None):
        self.websocket = websocket
        self.user_role = user_role
        self.location = location
        self.subscribed_events: Set[str] = set()
        self.connected_at = datetime.utcnow()
        self.last_ping = datetime.utcnow()


class WebSocketManager:
    def __init__(self):
        # Active connections: user_id -> ConnectionInfo
        self.active_connections: Dict[str, ConnectionInfo] = {}
        
        # Emergency channels: area_id -> Set[user_id]
        self.emergency_channels: Dict[str, Set[str]] = {}
        
        # Event subscriptions: event_type -> Set[user_id]
        self.event_subscriptions: Dict[str, Set[str]] = {}
        
        # Redis client for pub/sub
        self.redis_client = None
        
        # Initialize Redis connection
        asyncio.create_task(self._init_redis())
    
    async def _init_redis(self):
        """Initialize Redis connection for pub/sub."""
        try:
            self.redis_client = redis.from_url(settings.REDIS_URL)
            await self.redis_client.ping()
            print("Redis connection established for WebSocket service")
        except Exception as e:
            print(f"Failed to connect to Redis: {e}")
    
    async def connect(self, user_id: str, websocket: WebSocket, user_role: str):
        """Connect a user to WebSocket."""
        connection_info = ConnectionInfo(websocket, user_role)
        self.active_connections[user_id] = connection_info
        
        # Auto-subscribe to relevant events based on role
        await self._auto_subscribe_by_role(user_id, user_role)
        
        print(f"User {user_id} ({user_role}) connected via WebSocket")
    
    async def disconnect(self, user_id: str):
        """Disconnect a user from WebSocket."""
        if user_id in self.active_connections:
            # Remove from event subscriptions
            for event_type, subscribers in self.event_subscriptions.items():
                subscribers.discard(user_id)
            
            # Remove from emergency channels
            for area_id, users in self.emergency_channels.items():
                users.discard(user_id)
            
            # Remove connection
            del self.active_connections[user_id]
            
            print(f"User {user_id} disconnected from WebSocket")
    
    async def send_personal_message(self, user_id: str, message: dict):
        """Send message to a specific user."""
        if user_id in self.active_connections:
            connection = self.active_connections[user_id]
            try:
                await connection.websocket.send_text(json.dumps(message))
                return True
            except Exception as e:
                print(f"Failed to send message to {user_id}: {e}")
                await self.disconnect(user_id)
                return False
        return False
    
    async def broadcast_to_role(self, role: UserRole, message: dict):
        """Broadcast message to all users with specific role."""
        disconnected_users = []
        
        for user_id, connection in self.active_connections.items():
            if connection.user_role == role:
                try:
                    await connection.websocket.send_text(json.dumps(message))
                except Exception as e:
                    print(f"Failed to send message to {user_id}: {e}")
                    disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            await self.disconnect(user_id)
    
    async def broadcast_to_subscribers(self, event_type: str, message: dict):
        """Broadcast message to all users subscribed to an event type."""
        if event_type not in self.event_subscriptions:
            return
        
        subscribers = self.event_subscriptions[event_type].copy()
        disconnected_users = []
        
        for user_id in subscribers:
            if user_id in self.active_connections:
                try:
                    await self.active_connections[user_id].websocket.send_text(json.dumps(message))
                except Exception as e:
                    print(f"Failed to send message to {user_id}: {e}")
                    disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            await self.disconnect(user_id)
    
    async def broadcast_to_nearby_hospitals(self, location: dict, message: dict, radius_km: float = 50.0):
        """Broadcast message to hospitals within radius of location."""
        if not location or 'latitude' not in location or 'longitude' not in location:
            return
        
        target_location = (location['latitude'], location['longitude'])
        disconnected_users = []
        
        for user_id, connection in self.active_connections.items():
            if (connection.user_role == UserRole.HOSPITAL and 
                connection.location and 
                'latitude' in connection.location and 
                'longitude' in connection.location):
                
                user_location = (connection.location['latitude'], connection.location['longitude'])
                distance = geodesic(target_location, user_location).kilometers
                
                if distance <= radius_km:
                    try:
                        await connection.websocket.send_text(json.dumps(message))
                    except Exception as e:
                        print(f"Failed to send message to {user_id}: {e}")
                        disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            await self.disconnect(user_id)
    
    async def broadcast_to_nearby_vendors(self, location: dict, message: dict, radius_km: float = 50.0):
        """Broadcast message to vendors within radius of location."""
        if not location or 'latitude' not in location or 'longitude' not in location:
            return
        
        target_location = (location['latitude'], location['longitude'])
        disconnected_users = []
        
        for user_id, connection in self.active_connections.items():
            if (connection.user_role == UserRole.VENDOR and 
                connection.location and 
                'latitude' in connection.location and 
                'longitude' in connection.location):
                
                user_location = (connection.location['latitude'], connection.location['longitude'])
                distance = geodesic(target_location, user_location).kilometers
                
                if distance <= radius_km:
                    try:
                        await connection.websocket.send_text(json.dumps(message))
                    except Exception as e:
                        print(f"Failed to send message to {user_id}: {e}")
                        disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            await self.disconnect(user_id)
    
    async def subscribe_user_to_events(self, user_id: str, event_types: List[str]):
        """Subscribe user to specific event types."""
        if user_id not in self.active_connections:
            return
        
        connection = self.active_connections[user_id]
        
        for event_type in event_types:
            if event_type not in self.event_subscriptions:
                self.event_subscriptions[event_type] = set()
            
            self.event_subscriptions[event_type].add(user_id)
            connection.subscribed_events.add(event_type)
    
    async def unsubscribe_user_from_events(self, user_id: str, event_types: List[str]):
        """Unsubscribe user from specific event types."""
        if user_id not in self.active_connections:
            return
        
        connection = self.active_connections[user_id]
        
        for event_type in event_types:
            if event_type in self.event_subscriptions:
                self.event_subscriptions[event_type].discard(user_id)
            
            connection.subscribed_events.discard(event_type)
    
    async def update_user_location(self, user_id: str, latitude: float, longitude: float):
        """Update user's location for proximity-based notifications."""
        if user_id in self.active_connections:
            self.active_connections[user_id].location = {
                'latitude': latitude,
                'longitude': longitude,
                'updated_at': datetime.utcnow().isoformat()
            }
    
    async def join_emergency_channel(self, user_id: str, area_id: str, websocket: WebSocket):
        """Join emergency channel for specific area."""
        if area_id not in self.emergency_channels:
            self.emergency_channels[area_id] = set()
        
        self.emergency_channels[area_id].add(user_id)
        
        # Update connection info if user is already connected
        if user_id in self.active_connections:
            self.active_connections[user_id].websocket = websocket
    
    async def leave_emergency_channel(self, user_id: str, area_id: str):
        """Leave emergency channel."""
        if area_id in self.emergency_channels:
            self.emergency_channels[area_id].discard(user_id)
            
            # Clean up empty channels
            if not self.emergency_channels[area_id]:
                del self.emergency_channels[area_id]
    
    async def broadcast_emergency_alert(self, area_id: str, message: dict):
        """Broadcast emergency alert to all users in area channel."""
        if area_id not in self.emergency_channels:
            return
        
        users_in_channel = self.emergency_channels[area_id].copy()
        disconnected_users = []
        
        for user_id in users_in_channel:
            if user_id in self.active_connections:
                try:
                    await self.active_connections[user_id].websocket.send_text(json.dumps(message))
                except Exception as e:
                    print(f"Failed to send emergency alert to {user_id}: {e}")
                    disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            await self.disconnect(user_id)
    
    async def _auto_subscribe_by_role(self, user_id: str, user_role: str):
        """Auto-subscribe users to relevant events based on their role."""
        role_subscriptions = {
            UserRole.HOSPITAL: [
                'inventory_update',
                'order_status_update',
                'delivery_update',
                'emergency_response',
                'vendor_availability'
            ],
            UserRole.VENDOR: [
                'order_placed',
                'emergency_alert',
                'payment_completed',
                'inventory_request',
                'delivery_assigned'
            ],
            UserRole.ADMIN: [
                'system_alert',
                'user_activity',
                'order_status_update',
                'payment_completed',
                'emergency_alert',
                'inventory_update'
            ]
        }
        
        if user_role in role_subscriptions:
            await self.subscribe_user_to_events(user_id, role_subscriptions[user_role])
    
    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        return len(self.active_connections)
    
    def get_connections_by_role(self) -> Dict[str, int]:
        """Get connection count by user role."""
        role_counts = {}
        for connection in self.active_connections.values():
            role = connection.user_role
            role_counts[role] = role_counts.get(role, 0) + 1
        return role_counts
    
    def get_emergency_channels_info(self) -> Dict[str, int]:
        """Get information about emergency channels."""
        return {area_id: len(users) for area_id, users in self.emergency_channels.items()}
    
    async def ping_all_connections(self):
        """Send ping to all connections to check if they're alive."""
        disconnected_users = []
        
        ping_message = {
            "type": "ping",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        for user_id, connection in self.active_connections.items():
            try:
                await connection.websocket.send_text(json.dumps(ping_message))
                connection.last_ping = datetime.utcnow()
            except Exception as e:
                print(f"Ping failed for {user_id}: {e}")
                disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            await self.disconnect(user_id)
    
    async def cleanup_stale_connections(self, max_idle_minutes: int = 30):
        """Clean up connections that haven't responded to ping in a while."""
        current_time = datetime.utcnow()
        stale_users = []
        
        for user_id, connection in self.active_connections.items():
            idle_time = (current_time - connection.last_ping).total_seconds() / 60
            if idle_time > max_idle_minutes:
                stale_users.append(user_id)
        
        for user_id in stale_users:
            await self.disconnect(user_id)
            print(f"Cleaned up stale connection for user {user_id}")
    
    async def broadcast_system_message(self, message: dict, exclude_roles: Optional[List[str]] = None):
        """Broadcast system message to all connected users."""
        exclude_roles = exclude_roles or []
        disconnected_users = []
        
        for user_id, connection in self.active_connections.items():
            if connection.user_role not in exclude_roles:
                try:
                    await connection.websocket.send_text(json.dumps(message))
                except Exception as e:
                    print(f"Failed to send system message to {user_id}: {e}")
                    disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            await self.disconnect(user_id)
