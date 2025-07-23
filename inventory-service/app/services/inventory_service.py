from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.inventory import Inventory, CylinderStock, StockMovement, StockReservation
from app.schemas.inventory import (
    InventoryCreate, InventoryUpdate, StockCreate, StockUpdate,
    StockMovementCreate, InventorySearchResult
)
from shared.models import CylinderSize, UserRole


class InventoryService:
    """Service for managing inventory operations."""
    
    async def create_inventory_location(
        self, 
        db: AsyncSession, 
        inventory_data: InventoryCreate, 
        vendor_id: str
    ) -> Inventory:
        """Create a new inventory location for a vendor."""
        inventory = Inventory(
            vendor_id=vendor_id,
            location_name=inventory_data.location_name,
            address=inventory_data.address,
            city=inventory_data.city,
            state=inventory_data.state,
            country=inventory_data.country,
            latitude=inventory_data.latitude,
            longitude=inventory_data.longitude
        )
        
        db.add(inventory)
        await db.commit()
        await db.refresh(inventory)
        
        # Initialize stock for all cylinder sizes
        for cylinder_size in CylinderSize:
            stock = CylinderStock(
                inventory_id=inventory.id,
                cylinder_size=cylinder_size,
                total_quantity=0,
                available_quantity=0,
                reserved_quantity=0
            )
            db.add(stock)
        
        await db.commit()
        return inventory
    
    async def get_vendor_inventory(
        self, 
        db: AsyncSession, 
        vendor_id: str
    ) -> List[Inventory]:
        """Get all inventory locations for a vendor."""
        result = await db.execute(
            select(Inventory)
            .options(selectinload(Inventory.stock))
            .where(and_(Inventory.vendor_id == vendor_id, Inventory.is_active == True))
        )
        return result.scalars().all()
    
    async def update_stock(
        self,
        db: AsyncSession,
        inventory_id: str,
        cylinder_size: CylinderSize,
        quantity_change: int,
        notes: Optional[str],
        user_id: str,
        order_id: Optional[str] = None
    ) -> CylinderStock:
        """Update stock levels for a specific cylinder size."""
        # Get the stock record
        result = await db.execute(
            select(CylinderStock)
            .where(and_(
                CylinderStock.inventory_id == inventory_id,
                CylinderStock.cylinder_size == cylinder_size
            ))
        )
        stock = result.scalar_one_or_none()
        
        if not stock:
            # Create new stock record if it doesn't exist
            stock = CylinderStock(
                inventory_id=inventory_id,
                cylinder_size=cylinder_size,
                total_quantity=max(0, quantity_change),
                available_quantity=max(0, quantity_change),
                reserved_quantity=0
            )
            db.add(stock)
        else:
            # Update existing stock
            previous_total = stock.total_quantity
            previous_available = stock.available_quantity
            
            stock.total_quantity = max(0, stock.total_quantity + quantity_change)
            stock.available_quantity = max(0, stock.available_quantity + quantity_change)
            
            # Create stock movement record
            movement = StockMovement(
                inventory_id=inventory_id,
                stock_id=stock.id,
                cylinder_size=cylinder_size,
                movement_type="in" if quantity_change > 0 else "out",
                quantity=abs(quantity_change),
                previous_quantity=previous_total,
                new_quantity=stock.total_quantity,
                order_id=order_id,
                notes=notes,
                created_by=user_id
            )
            db.add(movement)
        
        await db.commit()
        await db.refresh(stock)
        return stock
    
    async def get_inventory_stock(
        self,
        db: AsyncSession,
        inventory_id: str
    ) -> List[CylinderStock]:
        """Get all stock levels for an inventory location."""
        result = await db.execute(
            select(CylinderStock)
            .where(CylinderStock.inventory_id == inventory_id)
        )
        return result.scalars().all()
    
    async def search_available_inventory(
        self,
        db: AsyncSession,
        cylinder_size: CylinderSize,
        quantity: int,
        latitude: float,
        longitude: float,
        max_distance_km: float = 50.0
    ) -> List[InventorySearchResult]:
        """Search for available inventory near a location."""
        # Calculate distance using Haversine formula (simplified)
        # Note: This is a basic implementation. In production, use PostGIS or similar
        distance_formula = func.sqrt(
            func.pow(69.1 * (Inventory.latitude - latitude), 2) +
            func.pow(69.1 * (longitude - Inventory.longitude) * 
                    func.cos(Inventory.latitude / 57.3), 2)
        )
        
        result = await db.execute(
            select(
                Inventory,
                CylinderStock,
                distance_formula.label('distance_km')
            )
            .join(CylinderStock, Inventory.id == CylinderStock.inventory_id)
            .where(and_(
                Inventory.is_active == True,
                CylinderStock.cylinder_size == cylinder_size,
                CylinderStock.available_quantity >= quantity,
                distance_formula <= max_distance_km
            ))
            .order_by(distance_formula)
        )
        
        search_results = []
        for inventory, stock, distance in result:
            search_results.append(InventorySearchResult(
                inventory_id=inventory.id,
                vendor_id=inventory.vendor_id,
                location_name=inventory.location_name,
                address=inventory.address,
                city=inventory.city,
                state=inventory.state,
                latitude=inventory.latitude,
                longitude=inventory.longitude,
                distance_km=round(distance, 2),
                available_quantity=stock.available_quantity
            ))
        
        return search_results
    
    async def reserve_stock(
        self,
        db: AsyncSession,
        inventory_id: str,
        cylinder_size: CylinderSize,
        quantity: int,
        order_id: str,
        user_id: str
    ) -> bool:
        """Reserve stock for an order."""
        # Get the stock record
        result = await db.execute(
            select(CylinderStock)
            .where(and_(
                CylinderStock.inventory_id == inventory_id,
                CylinderStock.cylinder_size == cylinder_size
            ))
        )
        stock = result.scalar_one_or_none()
        
        if not stock or stock.available_quantity < quantity:
            return False
        
        # Update stock quantities
        stock.available_quantity -= quantity
        stock.reserved_quantity += quantity
        
        # Create reservation record
        reservation = StockReservation(
            inventory_id=inventory_id,
            stock_id=stock.id,
            order_id=order_id,
            cylinder_size=cylinder_size,
            quantity=quantity,
            reserved_by=user_id,
            expires_at=datetime.utcnow() + timedelta(hours=24)  # 24-hour expiry
        )
        db.add(reservation)
        
        # Create stock movement record
        movement = StockMovement(
            inventory_id=inventory_id,
            stock_id=stock.id,
            cylinder_size=cylinder_size,
            movement_type="reserved",
            quantity=quantity,
            previous_quantity=stock.available_quantity + quantity,
            new_quantity=stock.available_quantity,
            order_id=order_id,
            notes=f"Reserved for order {order_id}",
            created_by=user_id
        )
        db.add(movement)
        
        await db.commit()
        return True
    
    async def release_reservation(
        self,
        db: AsyncSession,
        inventory_id: str,
        order_id: str,
        user_id: str
    ) -> bool:
        """Release stock reservation."""
        # Get the reservation
        result = await db.execute(
            select(StockReservation)
            .where(and_(
                StockReservation.inventory_id == inventory_id,
                StockReservation.order_id == order_id,
                StockReservation.is_active == True
            ))
        )
        reservation = result.scalar_one_or_none()
        
        if not reservation:
            return False
        
        # Get the stock record
        result = await db.execute(
            select(CylinderStock)
            .where(CylinderStock.id == reservation.stock_id)
        )
        stock = result.scalar_one_or_none()
        
        if stock:
            # Update stock quantities
            stock.available_quantity += reservation.quantity
            stock.reserved_quantity -= reservation.quantity
            
            # Create stock movement record
            movement = StockMovement(
                inventory_id=inventory_id,
                stock_id=stock.id,
                cylinder_size=reservation.cylinder_size,
                movement_type="released",
                quantity=reservation.quantity,
                previous_quantity=stock.available_quantity - reservation.quantity,
                new_quantity=stock.available_quantity,
                order_id=order_id,
                notes=f"Released reservation for order {order_id}",
                created_by=user_id
            )
            db.add(movement)
        
        # Deactivate reservation
        reservation.is_active = False
        
        await db.commit()
        return True
    
    async def get_stock_movements(
        self,
        db: AsyncSession,
        inventory_id: str,
        page: int = 1,
        size: int = 20
    ) -> tuple[List[StockMovement], int]:
        """Get stock movement history with pagination."""
        offset = (page - 1) * size
        
        # Get total count
        count_result = await db.execute(
            select(func.count(StockMovement.id))
            .where(StockMovement.inventory_id == inventory_id)
        )
        total = count_result.scalar()
        
        # Get movements
        result = await db.execute(
            select(StockMovement)
            .where(StockMovement.inventory_id == inventory_id)
            .order_by(StockMovement.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        movements = result.scalars().all()
        
        return movements, total
    
    async def get_low_stock_alerts(
        self,
        db: AsyncSession,
        vendor_id: str
    ) -> List[Dict[str, Any]]:
        """Get low stock alerts for a vendor."""
        result = await db.execute(
            select(Inventory, CylinderStock)
            .join(CylinderStock, Inventory.id == CylinderStock.inventory_id)
            .where(and_(
                Inventory.vendor_id == vendor_id,
                Inventory.is_active == True,
                CylinderStock.available_quantity <= CylinderStock.minimum_threshold
            ))
        )
        
        alerts = []
        for inventory, stock in result:
            alerts.append({
                "inventory_id": inventory.id,
                "location_name": inventory.location_name,
                "cylinder_size": stock.cylinder_size.value,
                "current_quantity": stock.available_quantity,
                "minimum_threshold": stock.minimum_threshold,
                "shortage": stock.minimum_threshold - stock.available_quantity
            })
        
        return alerts
    
    async def check_vendor_availability(
        self,
        db: AsyncSession,
        vendor_id: str
    ) -> Dict[str, Any]:
        """Check if vendor has available inventory."""
        result = await db.execute(
            select(
                CylinderStock.cylinder_size,
                func.sum(CylinderStock.available_quantity).label('total_available')
            )
            .join(Inventory, CylinderStock.inventory_id == Inventory.id)
            .where(and_(
                Inventory.vendor_id == vendor_id,
                Inventory.is_active == True
            ))
            .group_by(CylinderStock.cylinder_size)
        )
        
        availability = {}
        for cylinder_size, total_available in result:
            availability[cylinder_size.value] = total_available or 0
        
        return {
            "vendor_id": vendor_id,
            "has_inventory": any(qty > 0 for qty in availability.values()),
            "availability": availability
        }
