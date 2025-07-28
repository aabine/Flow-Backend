from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import selectinload, joinedload
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import logging
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.models.cylinder import (
    Cylinder, CylinderMaintenance, CylinderQualityCheck, CylinderLifecycleEvent,
    CylinderUsageLog, CylinderBatch, CylinderBatchItem,
    CylinderLifecycleState, CylinderCondition, MaintenanceType, QualityCheckStatus
)
from app.models.inventory import Inventory
from app.schemas.cylinder import (
    CylinderCreate, CylinderUpdate, CylinderSearchFilters, CylinderSearchRequest,
    CylinderMaintenanceCreate, CylinderMaintenanceUpdate,
    CylinderQualityCheckCreate, CylinderQualityCheckUpdate,
    CylinderLifecycleEventCreate, CylinderUsageLogCreate, CylinderUsageLogUpdate,
    CylinderAllocationRequest, CylinderAllocationOption, CylinderAllocationResponse,
    CylinderBatchCreate, CylinderBatchUpdate
)
from shared.models import CylinderSize, UserRole
from app.services.event_service import event_service

logger = logging.getLogger(__name__)


class CylinderService:
    """Service for managing individual cylinders and their lifecycle."""

    async def create_cylinder(
        self, 
        db: AsyncSession, 
        cylinder_data: CylinderCreate, 
        vendor_id: str
    ) -> Cylinder:
        """Create a new cylinder and register it in the system."""
        try:
            # Verify inventory location exists and belongs to vendor
            inventory_result = await db.execute(
                select(Inventory).where(
                    and_(
                        Inventory.id == cylinder_data.inventory_location_id,
                        Inventory.vendor_id == vendor_id
                    )
                )
            )
            inventory = inventory_result.scalar_one_or_none()
            if not inventory:
                raise ValueError("Invalid inventory location or access denied")

            # Check for duplicate serial number
            existing_result = await db.execute(
                select(Cylinder).where(Cylinder.serial_number == cylinder_data.serial_number)
            )
            if existing_result.scalar_one_or_none():
                raise ValueError(f"Cylinder with serial number {cylinder_data.serial_number} already exists")

            # Create cylinder
            cylinder = Cylinder(
                serial_number=cylinder_data.serial_number,
                manufacturer_serial=cylinder_data.manufacturer_serial,
                vendor_id=vendor_id,
                inventory_location_id=cylinder_data.inventory_location_id,
                cylinder_size=cylinder_data.cylinder_size,
                capacity_liters=cylinder_data.capacity_liters,
                working_pressure_bar=cylinder_data.working_pressure_bar,
                test_pressure_bar=cylinder_data.test_pressure_bar,
                tare_weight_kg=cylinder_data.tare_weight_kg,
                manufacturer=cylinder_data.manufacturer,
                manufacture_date=cylinder_data.manufacture_date,
                material=cylinder_data.material,
                valve_type=cylinder_data.valve_type,
                thread_type=cylinder_data.thread_type,
                gas_type=cylinder_data.gas_type,
                purity_percentage=cylinder_data.purity_percentage,
                certification_number=cylinder_data.certification_number,
                regulatory_compliance=cylinder_data.regulatory_compliance,
                notes=cylinder_data.notes
            )

            db.add(cylinder)
            await db.commit()
            await db.refresh(cylinder)

            # Create initial lifecycle event
            await self._create_lifecycle_event(
                db, cylinder.id, "cylinder_registered", CylinderLifecycleState.NEW,
                vendor_id=vendor_id, notes="Cylinder registered in system"
            )

            # Publish event
            await event_service.publish_event(
                "cylinder_registered",
                {
                    "cylinder_id": str(cylinder.id),
                    "vendor_id": vendor_id,
                    "serial_number": cylinder.serial_number,
                    "cylinder_size": cylinder.cylinder_size.value,
                    "inventory_location_id": cylinder_data.inventory_location_id
                }
            )

            logger.info(f"Created cylinder {cylinder.id} with serial {cylinder.serial_number}")
            return cylinder

        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating cylinder: {e}")
            raise

    async def get_cylinder(self, db: AsyncSession, cylinder_id: str, vendor_id: str) -> Optional[Cylinder]:
        """Get cylinder by ID with vendor access control."""
        result = await db.execute(
            select(Cylinder)
            .options(
                selectinload(Cylinder.maintenance_records),
                selectinload(Cylinder.quality_checks),
                selectinload(Cylinder.lifecycle_events),
                selectinload(Cylinder.usage_logs)
            )
            .where(
                and_(
                    Cylinder.id == cylinder_id,
                    Cylinder.vendor_id == vendor_id
                )
            )
        )
        return result.scalar_one_or_none()

    async def update_cylinder(
        self, 
        db: AsyncSession, 
        cylinder_id: str, 
        cylinder_data: CylinderUpdate, 
        vendor_id: str,
        user_id: str
    ) -> Optional[Cylinder]:
        """Update cylinder information."""
        try:
            cylinder = await self.get_cylinder(db, cylinder_id, vendor_id)
            if not cylinder:
                return None

            # Track state changes for lifecycle events
            previous_state = cylinder.lifecycle_state
            previous_location = cylinder.inventory_location_id

            # Update fields
            update_data = cylinder_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(cylinder, field, value)

            await db.commit()
            await db.refresh(cylinder)

            # Create lifecycle event if state changed
            if cylinder_data.lifecycle_state and cylinder_data.lifecycle_state != previous_state:
                await self._create_lifecycle_event(
                    db, cylinder.id, "state_changed", cylinder.lifecycle_state,
                    previous_state=previous_state,
                    vendor_id=vendor_id,
                    triggered_by=user_id,
                    notes=f"State changed from {previous_state.value} to {cylinder.lifecycle_state.value}"
                )

            # Create location change event if location changed
            if (cylinder_data.inventory_location_id and 
                cylinder_data.inventory_location_id != previous_location):
                await self._create_lifecycle_event(
                    db, cylinder.id, "location_changed", cylinder.lifecycle_state,
                    previous_location_id=previous_location,
                    new_location_id=cylinder.inventory_location_id,
                    vendor_id=vendor_id,
                    triggered_by=user_id,
                    notes="Cylinder location updated"
                )

            logger.info(f"Updated cylinder {cylinder.id}")
            return cylinder

        except Exception as e:
            await db.rollback()
            logger.error(f"Error updating cylinder {cylinder_id}: {e}")
            raise

    async def search_cylinders(
        self, 
        db: AsyncSession, 
        search_request: CylinderSearchRequest,
        vendor_id: str
    ) -> Tuple[List[Cylinder], int]:
        """Search cylinders with filters and pagination."""
        try:
            filters = search_request.filters
            
            # Base query with vendor filter
            query = select(Cylinder).where(Cylinder.vendor_id == vendor_id)
            count_query = select(func.count(Cylinder.id)).where(Cylinder.vendor_id == vendor_id)

            # Apply filters
            conditions = []
            
            if filters.inventory_location_id:
                conditions.append(Cylinder.inventory_location_id == filters.inventory_location_id)
            
            if filters.cylinder_size:
                conditions.append(Cylinder.cylinder_size == filters.cylinder_size)
            
            if filters.lifecycle_state:
                conditions.append(Cylinder.lifecycle_state == filters.lifecycle_state)
            
            if filters.condition:
                conditions.append(Cylinder.condition == filters.condition)
            
            if filters.is_available is not None:
                conditions.append(Cylinder.is_available == filters.is_available)
            
            if filters.requires_maintenance is not None:
                conditions.append(Cylinder.requires_maintenance == filters.requires_maintenance)
            
            if filters.is_emergency_ready is not None:
                conditions.append(Cylinder.is_emergency_ready == filters.is_emergency_ready)
            
            if filters.current_hospital_id:
                conditions.append(Cylinder.current_hospital_id == filters.current_hospital_id)
            
            if filters.manufacturer:
                conditions.append(Cylinder.manufacturer.ilike(f"%{filters.manufacturer}%"))
            
            if filters.gas_type:
                conditions.append(Cylinder.gas_type == filters.gas_type)
            
            if filters.min_pressure is not None:
                conditions.append(Cylinder.current_pressure_bar >= filters.min_pressure)
            
            if filters.max_pressure is not None:
                conditions.append(Cylinder.current_pressure_bar <= filters.max_pressure)
            
            if filters.min_fill_percentage is not None:
                conditions.append(Cylinder.fill_level_percentage >= filters.min_fill_percentage)
            
            if filters.max_fill_percentage is not None:
                conditions.append(Cylinder.fill_level_percentage <= filters.max_fill_percentage)
            
            if filters.inspection_due_before:
                conditions.append(Cylinder.next_inspection_due <= filters.inspection_due_before)
            
            if filters.pressure_test_due_before:
                conditions.append(Cylinder.next_pressure_test_due <= filters.pressure_test_due_before)
            
            if filters.created_after:
                conditions.append(Cylinder.created_at >= filters.created_after)
            
            if filters.created_before:
                conditions.append(Cylinder.created_at <= filters.created_before)

            # Apply conditions
            if conditions:
                query = query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))

            # Get total count
            count_result = await db.execute(count_query)
            total = count_result.scalar()

            # Apply sorting
            sort_column = getattr(Cylinder, search_request.sort_by, Cylinder.created_at)
            if search_request.sort_order == "desc":
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())

            # Apply pagination
            offset = (search_request.page - 1) * search_request.page_size
            query = query.offset(offset).limit(search_request.page_size)

            # Include related data if requested
            if search_request.include_maintenance_history:
                query = query.options(selectinload(Cylinder.maintenance_records))
            
            if search_request.include_quality_checks:
                query = query.options(selectinload(Cylinder.quality_checks))
            
            if search_request.include_usage_logs:
                query = query.options(selectinload(Cylinder.usage_logs))

            # Execute query
            result = await db.execute(query)
            cylinders = result.scalars().all()

            return cylinders, total

        except Exception as e:
            logger.error(f"Error searching cylinders: {e}")
            raise

    async def allocate_cylinders(
        self,
        db: AsyncSession,
        allocation_request: CylinderAllocationRequest
    ) -> CylinderAllocationResponse:
        """Allocate cylinders for an order using intelligent algorithms."""
        try:
            # Find available cylinders matching criteria
            query = select(Cylinder).options(
                joinedload(Cylinder.inventory_location)
            ).where(
                and_(
                    Cylinder.cylinder_size == allocation_request.cylinder_size,
                    Cylinder.lifecycle_state == CylinderLifecycleState.ACTIVE,
                    Cylinder.is_available == True,
                    Cylinder.is_emergency_ready == True if allocation_request.is_emergency else True,
                    Cylinder.fill_level_percentage >= allocation_request.min_fill_percentage,
                    Cylinder.current_order_id.is_(None)
                )
            )

            # Add vendor filter if specified
            if allocation_request.preferred_vendor_id:
                query = query.where(Cylinder.vendor_id == allocation_request.preferred_vendor_id)

            # Add quality requirements filter
            if allocation_request.quality_requirements:
                # Filter based on recent quality checks
                subquery = select(CylinderQualityCheck.cylinder_id).where(
                    and_(
                        CylinderQualityCheck.overall_status == QualityCheckStatus.PASSED,
                        CylinderQualityCheck.check_date >= datetime.utcnow() - timedelta(days=30)
                    )
                )
                query = query.where(Cylinder.id.in_(subquery))

            result = await db.execute(query)
            available_cylinders = result.scalars().all()

            # Group cylinders by vendor and location
            vendor_groups = {}
            for cylinder in available_cylinders:
                vendor_id = str(cylinder.vendor_id)
                location_id = str(cylinder.inventory_location_id)

                if vendor_id not in vendor_groups:
                    vendor_groups[vendor_id] = {}

                if location_id not in vendor_groups[vendor_id]:
                    vendor_groups[vendor_id][location_id] = {
                        'cylinders': [],
                        'location': cylinder.inventory_location
                    }

                vendor_groups[vendor_id][location_id]['cylinders'].append(cylinder)

            # Calculate allocation options
            allocation_options = []

            for vendor_id, locations in vendor_groups.items():
                for location_id, location_data in locations.items():
                    cylinders = location_data['cylinders']
                    location = location_data['location']

                    # Check if we have enough cylinders at this location
                    if len(cylinders) >= allocation_request.quantity:
                        # Calculate distance
                        distance = self._calculate_distance(
                            float(location.latitude), float(location.longitude),
                            float(allocation_request.delivery_latitude),
                            float(allocation_request.delivery_longitude)
                        )

                        # Skip if outside max distance
                        if distance > allocation_request.max_distance_km:
                            continue

                        # Select best cylinders (highest fill level, newest)
                        selected_cylinders = sorted(
                            cylinders,
                            key=lambda c: (c.fill_level_percentage, c.created_at),
                            reverse=True
                        )[:allocation_request.quantity]

                        # Calculate estimated delivery time and cost
                        delivery_time = self._estimate_delivery_time(distance, allocation_request.is_emergency)
                        cost = self._calculate_allocation_cost(selected_cylinders, distance, allocation_request.is_emergency)

                        allocation_option = CylinderAllocationOption(
                            vendor_id=vendor_id,
                            vendor_name=f"Vendor {vendor_id}",  # TODO: Get actual vendor name
                            inventory_location_id=location_id,
                            location_name=location.location_name,
                            distance_km=distance,
                            available_cylinders=[str(c.id) for c in selected_cylinders],
                            estimated_delivery_time=delivery_time,
                            total_cost=cost,
                            currency="NGN"
                        )
                        allocation_options.append(allocation_option)

            # Sort options by distance and cost
            allocation_options.sort(key=lambda x: (x.distance_km, x.total_cost))

            # Select recommended option (closest with lowest cost)
            recommended_option = allocation_options[0] if allocation_options else None

            return CylinderAllocationResponse(
                order_id=allocation_request.order_id,
                allocation_options=allocation_options,
                recommended_option=recommended_option,
                total_options_found=len(allocation_options),
                search_criteria=allocation_request
            )

        except Exception as e:
            logger.error(f"Error allocating cylinders: {e}")
            raise

    async def reserve_cylinders(
        self,
        db: AsyncSession,
        cylinder_ids: List[str],
        order_id: str,
        vendor_id: str,
        user_id: str
    ) -> List[Cylinder]:
        """Reserve cylinders for an order."""
        try:
            # Get cylinders and verify they're available
            result = await db.execute(
                select(Cylinder).where(
                    and_(
                        Cylinder.id.in_(cylinder_ids),
                        Cylinder.vendor_id == vendor_id,
                        Cylinder.is_available == True,
                        Cylinder.current_order_id.is_(None)
                    )
                )
            )
            cylinders = result.scalars().all()

            if len(cylinders) != len(cylinder_ids):
                raise ValueError("Some cylinders are not available for reservation")

            # Reserve cylinders
            reserved_cylinders = []
            for cylinder in cylinders:
                cylinder.is_available = False
                cylinder.current_order_id = order_id
                cylinder.lifecycle_state = CylinderLifecycleState.IN_USE

                # Create lifecycle event
                await self._create_lifecycle_event(
                    db, cylinder.id, "reserved", CylinderLifecycleState.IN_USE,
                    previous_state=CylinderLifecycleState.ACTIVE,
                    order_id=order_id,
                    vendor_id=vendor_id,
                    triggered_by=user_id,
                    notes=f"Reserved for order {order_id}"
                )

                reserved_cylinders.append(cylinder)

            await db.commit()

            # Publish event
            await event_service.publish_event(
                "cylinders_reserved",
                {
                    "order_id": order_id,
                    "cylinder_ids": cylinder_ids,
                    "vendor_id": vendor_id,
                    "reserved_by": user_id
                }
            )

            logger.info(f"Reserved {len(reserved_cylinders)} cylinders for order {order_id}")
            return reserved_cylinders

        except Exception as e:
            await db.rollback()
            logger.error(f"Error reserving cylinders: {e}")
            raise

    async def release_cylinders(
        self,
        db: AsyncSession,
        cylinder_ids: List[str],
        vendor_id: str,
        user_id: str,
        reason: str = "Order cancelled"
    ) -> List[Cylinder]:
        """Release reserved cylinders back to available pool."""
        try:
            # Get reserved cylinders
            result = await db.execute(
                select(Cylinder).where(
                    and_(
                        Cylinder.id.in_(cylinder_ids),
                        Cylinder.vendor_id == vendor_id,
                        Cylinder.is_available == False
                    )
                )
            )
            cylinders = result.scalars().all()

            # Release cylinders
            released_cylinders = []
            for cylinder in cylinders:
                order_id = cylinder.current_order_id
                cylinder.is_available = True
                cylinder.current_order_id = None
                cylinder.lifecycle_state = CylinderLifecycleState.ACTIVE

                # Create lifecycle event
                await self._create_lifecycle_event(
                    db, cylinder.id, "released", CylinderLifecycleState.ACTIVE,
                    previous_state=CylinderLifecycleState.IN_USE,
                    order_id=order_id,
                    vendor_id=vendor_id,
                    triggered_by=user_id,
                    notes=f"Released: {reason}"
                )

                released_cylinders.append(cylinder)

            await db.commit()

            # Publish event
            await event_service.publish_event(
                "cylinders_released",
                {
                    "cylinder_ids": cylinder_ids,
                    "vendor_id": vendor_id,
                    "released_by": user_id,
                    "reason": reason
                }
            )

            logger.info(f"Released {len(released_cylinders)} cylinders")
            return released_cylinders

        except Exception as e:
            await db.rollback()
            logger.error(f"Error releasing cylinders: {e}")
            raise

    # Maintenance Management Methods
    async def schedule_maintenance(
        self,
        db: AsyncSession,
        maintenance_data: CylinderMaintenanceCreate,
        vendor_id: str,
        user_id: str
    ) -> CylinderMaintenance:
        """Schedule maintenance for a cylinder."""
        try:
            # Verify cylinder belongs to vendor
            cylinder = await self.get_cylinder(db, maintenance_data.cylinder_id, vendor_id)
            if not cylinder:
                raise ValueError("Cylinder not found or access denied")

            # Create maintenance record
            maintenance = CylinderMaintenance(
                cylinder_id=maintenance_data.cylinder_id,
                maintenance_type=maintenance_data.maintenance_type,
                scheduled_date=maintenance_data.scheduled_date,
                work_description=maintenance_data.work_description,
                technician_id=maintenance_data.technician_id,
                vendor_id=vendor_id,
                pre_maintenance_condition=cylinder.condition,
                post_maintenance_condition=cylinder.condition,
                is_emergency=maintenance_data.is_emergency
            )

            db.add(maintenance)

            # Update cylinder status if emergency maintenance
            if maintenance_data.is_emergency:
                cylinder.requires_maintenance = True
                cylinder.is_available = False
                cylinder.lifecycle_state = CylinderLifecycleState.MAINTENANCE

            await db.commit()
            await db.refresh(maintenance)

            # Create lifecycle event
            await self._create_lifecycle_event(
                db, cylinder.id, "maintenance_scheduled", cylinder.lifecycle_state,
                vendor_id=vendor_id,
                triggered_by=user_id,
                notes=f"Maintenance scheduled: {maintenance_data.maintenance_type.value}"
            )

            logger.info(f"Scheduled maintenance {maintenance.id} for cylinder {cylinder.id}")
            return maintenance

        except Exception as e:
            await db.rollback()
            logger.error(f"Error scheduling maintenance: {e}")
            raise

    async def complete_maintenance(
        self,
        db: AsyncSession,
        maintenance_id: str,
        maintenance_data: CylinderMaintenanceUpdate,
        vendor_id: str,
        user_id: str
    ) -> Optional[CylinderMaintenance]:
        """Complete maintenance and update cylinder status."""
        try:
            # Get maintenance record
            result = await db.execute(
                select(CylinderMaintenance)
                .options(selectinload(CylinderMaintenance.cylinder))
                .where(
                    and_(
                        CylinderMaintenance.id == maintenance_id,
                        CylinderMaintenance.vendor_id == vendor_id
                    )
                )
            )
            maintenance = result.scalar_one_or_none()
            if not maintenance:
                return None

            # Update maintenance record
            update_data = maintenance_data.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(maintenance, field, value)

            maintenance.is_completed = True
            maintenance.completed_date = datetime.utcnow()

            # Update cylinder based on maintenance results
            cylinder = maintenance.cylinder
            if maintenance_data.post_maintenance_condition:
                cylinder.condition = maintenance_data.post_maintenance_condition

            # Update maintenance flags
            cylinder.requires_maintenance = False
            cylinder.last_inspection_date = datetime.utcnow()

            # Calculate next maintenance due date
            if maintenance.maintenance_type == MaintenanceType.ROUTINE_INSPECTION:
                cylinder.next_inspection_due = datetime.utcnow() + timedelta(days=365)
            elif maintenance.maintenance_type == MaintenanceType.PRESSURE_TEST:
                cylinder.next_pressure_test_due = datetime.utcnow() + timedelta(days=1825)  # 5 years
                cylinder.last_pressure_test_date = datetime.utcnow()

            # Update availability based on condition
            if cylinder.condition in [CylinderCondition.EXCELLENT, CylinderCondition.GOOD]:
                cylinder.is_available = True
                cylinder.is_emergency_ready = True
                cylinder.lifecycle_state = CylinderLifecycleState.ACTIVE
            elif cylinder.condition == CylinderCondition.FAIR:
                cylinder.is_available = True
                cylinder.is_emergency_ready = False
                cylinder.lifecycle_state = CylinderLifecycleState.ACTIVE
            else:
                cylinder.is_available = False
                cylinder.is_emergency_ready = False
                cylinder.lifecycle_state = CylinderLifecycleState.QUARANTINE

            await db.commit()
            await db.refresh(maintenance)

            # Create lifecycle event
            await self._create_lifecycle_event(
                db, cylinder.id, "maintenance_completed", cylinder.lifecycle_state,
                vendor_id=vendor_id,
                triggered_by=user_id,
                notes=f"Maintenance completed: {maintenance.maintenance_type.value}"
            )

            logger.info(f"Completed maintenance {maintenance.id} for cylinder {cylinder.id}")
            return maintenance

        except Exception as e:
            await db.rollback()
            logger.error(f"Error completing maintenance: {e}")
            raise

    # Quality Control Methods
    async def create_quality_check(
        self,
        db: AsyncSession,
        quality_data: CylinderQualityCheckCreate,
        vendor_id: str,
        user_id: str
    ) -> CylinderQualityCheck:
        """Create a quality control check for a cylinder."""
        try:
            # Verify cylinder belongs to vendor
            cylinder = await self.get_cylinder(db, quality_data.cylinder_id, vendor_id)
            if not cylinder:
                raise ValueError("Cylinder not found or access denied")

            # Create quality check
            quality_check = CylinderQualityCheck(
                cylinder_id=quality_data.cylinder_id,
                check_type=quality_data.check_type,
                check_date=datetime.utcnow(),
                inspector_id=quality_data.inspector_id,
                vendor_id=vendor_id,
                parameters_checked=quality_data.parameters_checked,
                measurements=quality_data.measurements,
                acceptable_ranges=quality_data.acceptable_ranges,
                overall_status=QualityCheckStatus.PENDING,
                regulatory_standards=quality_data.regulatory_standards
            )

            db.add(quality_check)
            await db.commit()
            await db.refresh(quality_check)

            # Auto-evaluate check results
            await self._evaluate_quality_check(db, quality_check)

            logger.info(f"Created quality check {quality_check.id} for cylinder {cylinder.id}")
            return quality_check

        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating quality check: {e}")
            raise

    # Helper Methods
    async def _create_lifecycle_event(
        self,
        db: AsyncSession,
        cylinder_id: str,
        event_type: str,
        new_state: CylinderLifecycleState,
        previous_state: Optional[CylinderLifecycleState] = None,
        previous_location_id: Optional[str] = None,
        new_location_id: Optional[str] = None,
        order_id: Optional[str] = None,
        hospital_id: Optional[str] = None,
        vendor_id: Optional[str] = None,
        triggered_by: Optional[str] = None,
        notes: Optional[str] = None,
        latitude: Optional[Decimal] = None,
        longitude: Optional[Decimal] = None
    ) -> CylinderLifecycleEvent:
        """Create a lifecycle event for tracking cylinder state changes."""
        event = CylinderLifecycleEvent(
            cylinder_id=cylinder_id,
            event_type=event_type,
            event_date=datetime.utcnow(),
            triggered_by=triggered_by,
            previous_state=previous_state,
            new_state=new_state,
            previous_location_id=previous_location_id,
            new_location_id=new_location_id,
            order_id=order_id,
            hospital_id=hospital_id,
            vendor_id=vendor_id,
            notes=notes,
            latitude=latitude,
            longitude=longitude
        )

        db.add(event)
        return event

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> Decimal:
        """Calculate distance between two points using Haversine formula."""
        from math import radians, cos, sin, asin, sqrt

        # Convert to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        r = 6371  # Radius of earth in kilometers

        return Decimal(str(c * r))

    def _estimate_delivery_time(self, distance_km: Decimal, is_emergency: bool) -> int:
        """Estimate delivery time in minutes based on distance and urgency."""
        base_time = float(distance_km) * 2  # 2 minutes per km
        if is_emergency:
            return max(30, int(base_time * 0.7))  # 30% faster for emergency
        return max(60, int(base_time))

    def _calculate_allocation_cost(self, cylinders: List[Cylinder], distance_km: Decimal, is_emergency: bool) -> Decimal:
        """Calculate total cost for cylinder allocation."""
        base_cost = Decimal("100.0") * len(cylinders)  # Base cost per cylinder
        delivery_cost = distance_km * Decimal("5.0")  # 5 NGN per km

        if is_emergency:
            emergency_surcharge = base_cost * Decimal("0.5")  # 50% surcharge
            return base_cost + delivery_cost + emergency_surcharge

        return base_cost + delivery_cost

    async def _evaluate_quality_check(self, db: AsyncSession, quality_check: CylinderQualityCheck):
        """Auto-evaluate quality check results."""
        passed_checks = []
        failed_checks = []

        # Compare measurements against acceptable ranges
        for param, measurement in quality_check.measurements.items():
            if param in quality_check.acceptable_ranges:
                range_data = quality_check.acceptable_ranges[param]
                min_val = range_data.get('min')
                max_val = range_data.get('max')

                if min_val is not None and measurement < min_val:
                    failed_checks.append(f"{param}: {measurement} < {min_val}")
                elif max_val is not None and measurement > max_val:
                    failed_checks.append(f"{param}: {measurement} > {max_val}")
                else:
                    passed_checks.append(param)

        # Update quality check results
        quality_check.passed_checks = passed_checks
        quality_check.failed_checks = failed_checks

        if failed_checks:
            quality_check.overall_status = QualityCheckStatus.FAILED
            quality_check.follow_up_required = True
            quality_check.follow_up_date = datetime.utcnow() + timedelta(days=7)
        else:
            quality_check.overall_status = QualityCheckStatus.PASSED

        await db.commit()
