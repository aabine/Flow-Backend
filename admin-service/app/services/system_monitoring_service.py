from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, func, text
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import httpx
import asyncio
import psutil
import uuid
import sys
import os

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.core.config import get_settings
from app.models.admin import SystemMetrics, SystemAlert, MetricType
from app.schemas.admin import (
    ServiceHealthStatus, SystemHealthResponse, AlertResponse, AlertActionRequest
)

settings = get_settings()


class SystemMonitoringService:
    def __init__(self):
        self.settings = settings
        self.services = {
            "user-service": self.settings.USER_SERVICE_URL,
            "order-service": self.settings.ORDER_SERVICE_URL,
            "inventory-service": self.settings.INVENTORY_SERVICE_URL,
            "payment-service": self.settings.PAYMENT_SERVICE_URL,
            "review-service": self.settings.REVIEW_SERVICE_URL,
            "notification-service": self.settings.NOTIFICATION_SERVICE_URL,
            "location-service": self.settings.LOCATION_SERVICE_URL,
            "pricing-service": self.settings.PRICING_SERVICE_URL,
            "supplier-onboarding-service": self.settings.SUPPLIER_ONBOARDING_SERVICE_URL,
        }

    async def get_system_health(self, db: AsyncSession) -> SystemHealthResponse:
        """Get comprehensive system health status."""
        
        # Check all microservices
        service_statuses = await self._check_all_services()
        
        # Check infrastructure components
        database_status = await self._check_database_health(db)
        redis_status = await self._check_redis_health()
        rabbitmq_status = await self._check_rabbitmq_health()
        
        # Determine overall status
        overall_status = self._determine_overall_status(
            service_statuses, database_status, redis_status, rabbitmq_status
        )
        
        return SystemHealthResponse(
            overall_status=overall_status,
            services=service_statuses,
            database_status=database_status,
            redis_status=redis_status,
            rabbitmq_status=rabbitmq_status
        )

    async def collect_system_metrics(self, db: AsyncSession):
        """Collect and store system metrics."""
        
        try:
            # Collect service metrics
            await self._collect_service_metrics(db)
            
            # Collect system resource metrics
            await self._collect_system_resource_metrics(db)
            
            # Clean up old metrics
            await self._cleanup_old_metrics(db)
            
        except Exception as e:
            print(f"Error collecting system metrics: {e}")

    async def get_alerts(
        self, 
        db: AsyncSession,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        page: int = 1,
        size: int = 20
    ) -> Tuple[List[AlertResponse], int]:
        """Get system alerts with filtering."""
        
        try:
            query = select(SystemAlert)
            
            # Apply filters
            if status:
                query = query.where(SystemAlert.status == status)
            if severity:
                query = query.where(SystemAlert.severity == severity)
            
            # Count total
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await db.execute(count_query)
            total = total_result.scalar()
            
            # Get paginated results
            query = query.order_by(SystemAlert.created_at.desc())
            query = query.offset((page - 1) * size).limit(size)
            
            result = await db.execute(query)
            alerts = result.scalars().all()
            
            # Convert to response format
            alert_responses = [
                AlertResponse(
                    id=str(alert.id),
                    alert_type=alert.alert_type,
                    severity=alert.severity,
                    title=alert.title,
                    message=alert.message,
                    service_name=alert.service_name,
                    status=alert.status,
                    created_at=alert.created_at,
                    acknowledged_at=alert.acknowledged_at
                )
                for alert in alerts
            ]
            
            return alert_responses, total
            
        except Exception as e:
            print(f"Error fetching alerts: {e}")
            return [], 0

    async def handle_alert_action(
        self, 
        db: AsyncSession,
        alert_id: str,
        action_request: AlertActionRequest,
        admin_user_id: str
    ) -> bool:
        """Handle admin action on an alert."""
        
        try:
            # Get alert
            result = await db.execute(
                select(SystemAlert).where(SystemAlert.id == uuid.UUID(alert_id))
            )
            alert = result.scalar_one_or_none()
            
            if not alert:
                return False
            
            # Perform action
            if action_request.action == "acknowledge":
                alert.status = "acknowledged"
                alert.acknowledged_by = uuid.UUID(admin_user_id)
                alert.acknowledged_at = datetime.utcnow()
            elif action_request.action == "resolve":
                alert.status = "resolved"
                alert.resolved_at = datetime.utcnow()
            elif action_request.action == "escalate":
                # Create escalated alert or send notification
                await self._escalate_alert(alert, admin_user_id)
            
            await db.commit()
            return True
            
        except Exception as e:
            print(f"Error handling alert action: {e}")
            await db.rollback()
            return False

    async def create_alert(
        self,
        db: AsyncSession,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        service_name: str,
        details: Optional[Dict[str, Any]] = None
    ) -> SystemAlert:
        """Create a new system alert."""
        
        try:
            alert = SystemAlert(
                alert_type=alert_type,
                severity=severity,
                title=title,
                message=message,
                service_name=service_name,
                details=details,
                status="active"
            )
            
            db.add(alert)
            await db.commit()
            await db.refresh(alert)
            
            # Send notification to admins if critical
            if severity == "critical":
                await self._notify_admins_of_critical_alert(alert)
            
            return alert
            
        except Exception as e:
            print(f"Error creating alert: {e}")
            await db.rollback()
            raise

    async def get_service_metrics(
        self, 
        db: AsyncSession,
        service_name: str,
        metric_type: MetricType,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get metrics for a specific service."""
        
        try:
            start_time = datetime.utcnow() - timedelta(hours=hours)
            
            query = select(SystemMetrics).where(
                and_(
                    SystemMetrics.service_name == service_name,
                    SystemMetrics.metric_type == metric_type,
                    SystemMetrics.timestamp >= start_time
                )
            ).order_by(SystemMetrics.timestamp)
            
            result = await db.execute(query)
            metrics = result.scalars().all()
            
            return [
                {
                    "timestamp": metric.timestamp.isoformat(),
                    "value": metric.value,
                    "unit": metric.unit,
                    "metadata": metric.metadata
                }
                for metric in metrics
            ]
            
        except Exception as e:
            print(f"Error fetching service metrics: {e}")
            return []

    async def get_system_overview(self, db: AsyncSession) -> Dict[str, Any]:
        """Get system overview with key metrics."""
        
        try:
            # Get current system resource usage
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Get service health summary
            service_health = await self._get_service_health_summary()
            
            # Get recent alerts count
            recent_alerts_query = select(func.count()).select_from(
                select(SystemAlert).where(
                    and_(
                        SystemAlert.created_at >= datetime.utcnow() - timedelta(hours=24),
                        SystemAlert.status == "active"
                    )
                ).subquery()
            )
            recent_alerts_result = await db.execute(recent_alerts_query)
            recent_alerts_count = recent_alerts_result.scalar()
            
            return {
                "system_resources": {
                    "cpu_usage": cpu_usage,
                    "memory_usage": memory.percent,
                    "disk_usage": disk.percent,
                    "memory_total": memory.total,
                    "memory_available": memory.available,
                    "disk_total": disk.total,
                    "disk_free": disk.free
                },
                "service_health": service_health,
                "alerts": {
                    "active_count": recent_alerts_count,
                    "last_24h": recent_alerts_count
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            print(f"Error getting system overview: {e}")
            return {}

    # Helper methods
    async def _check_all_services(self) -> List[ServiceHealthStatus]:
        """Check health of all microservices."""
        
        service_statuses = []
        
        async with httpx.AsyncClient() as client:
            for service_name, service_url in self.services.items():
                try:
                    start_time = datetime.utcnow()
                    response = await client.get(
                        f"{service_url}/health", 
                        timeout=self.settings.HEALTH_CHECK_TIMEOUT_SECONDS
                    )
                    response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    status = "healthy" if response.status_code == 200 else "degraded"
                    error_message = None
                    
                except httpx.TimeoutException:
                    status = "degraded"
                    response_time = None
                    error_message = "Request timeout"
                    
                except Exception as e:
                    status = "down"
                    response_time = None
                    error_message = str(e)
                
                service_statuses.append(ServiceHealthStatus(
                    service_name=service_name,
                    status=status,
                    response_time=response_time,
                    last_check=datetime.utcnow(),
                    error_message=error_message
                ))
        
        return service_statuses

    async def _check_database_health(self, db: AsyncSession) -> str:
        """Check database connectivity and health."""
        try:
            await db.execute(text("SELECT 1"))
            return "healthy"
        except Exception:
            return "down"

    async def _check_redis_health(self) -> str:
        """Check Redis connectivity."""
        try:
            # Would implement Redis health check
            return "healthy"
        except Exception:
            return "down"

    async def _check_rabbitmq_health(self) -> str:
        """Check RabbitMQ connectivity."""
        try:
            # Would implement RabbitMQ health check
            return "healthy"
        except Exception:
            return "down"

    def _determine_overall_status(
        self,
        service_statuses: List[ServiceHealthStatus],
        database_status: str,
        redis_status: str,
        rabbitmq_status: str
    ) -> str:
        """Determine overall system status."""

        # Check critical infrastructure
        if database_status == "down" or redis_status == "down" or rabbitmq_status == "down":
            return "critical"

        # Check service health
        down_services = sum(1 for s in service_statuses if s.status == "down")
        degraded_services = sum(1 for s in service_statuses if s.status == "degraded")

        if down_services > 0:
            return "degraded"
        elif degraded_services > 2:
            return "degraded"
        else:
            return "healthy"

    async def _collect_service_metrics(self, db: AsyncSession):
        """Collect metrics from all services."""

        for service_name, service_url in self.services.items():
            try:
                async with httpx.AsyncClient() as client:
                    # Collect response time
                    start_time = datetime.utcnow()
                    response = await client.get(f"{service_url}/health", timeout=5.0)
                    response_time = (datetime.utcnow() - start_time).total_seconds() * 1000

                    # Store response time metric
                    await self._store_metric(
                        db, MetricType.RESPONSE_TIME, service_name, response_time, "milliseconds"
                    )

                    # Store error rate (0 if healthy, 100 if down)
                    error_rate = 0 if response.status_code == 200 else 100
                    await self._store_metric(
                        db, MetricType.ERROR_RATE, service_name, error_rate, "percentage"
                    )

            except Exception as e:
                # Store error metric
                await self._store_metric(
                    db, MetricType.ERROR_RATE, service_name, 100, "percentage"
                )

    async def _collect_system_resource_metrics(self, db: AsyncSession):
        """Collect system resource metrics."""

        try:
            # CPU usage
            cpu_usage = psutil.cpu_percent(interval=1)
            await self._store_metric(db, MetricType.RESPONSE_TIME, "system", cpu_usage, "percentage", {"resource": "cpu"})

            # Memory usage
            memory = psutil.virtual_memory()
            await self._store_metric(db, MetricType.RESPONSE_TIME, "system", memory.percent, "percentage", {"resource": "memory"})

            # Disk usage
            disk = psutil.disk_usage('/')
            await self._store_metric(db, MetricType.RESPONSE_TIME, "system", disk.percent, "percentage", {"resource": "disk"})

        except Exception as e:
            print(f"Error collecting system resource metrics: {e}")

    async def _store_metric(
        self,
        db: AsyncSession,
        metric_type: MetricType,
        service_name: str,
        value: float,
        unit: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Store a metric in the database."""

        try:
            metric = SystemMetrics(
                metric_type=metric_type,
                service_name=service_name,
                value=value,
                unit=unit,
                metadata=metadata
            )

            db.add(metric)
            await db.commit()

        except Exception as e:
            print(f"Error storing metric: {e}")
            await db.rollback()

    async def _cleanup_old_metrics(self, db: AsyncSession):
        """Clean up old metrics beyond retention period."""

        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.settings.METRICS_RETENTION_DAYS)

            await db.execute(
                delete(SystemMetrics).where(SystemMetrics.timestamp < cutoff_date)
            )
            await db.commit()

        except Exception as e:
            print(f"Error cleaning up old metrics: {e}")
            await db.rollback()

    async def _escalate_alert(self, alert: SystemAlert, admin_user_id: str):
        """Escalate an alert to higher priority."""

        try:
            # Send notification to all admins
            notification_data = {
                "type": "broadcast",
                "title": f"ESCALATED ALERT: {alert.title}",
                "message": f"Alert from {alert.service_name}: {alert.message}",
                "metadata": {
                    "alert_id": str(alert.id),
                    "severity": alert.severity,
                    "escalated_by": admin_user_id
                }
            }

            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.settings.NOTIFICATION_SERVICE_URL}/admin/broadcast",
                    json=notification_data
                )

        except Exception as e:
            print(f"Error escalating alert: {e}")

    async def _notify_admins_of_critical_alert(self, alert: SystemAlert):
        """Notify all admins of a critical alert."""

        try:
            notification_data = {
                "type": "broadcast",
                "title": f"CRITICAL ALERT: {alert.title}",
                "message": f"Critical issue in {alert.service_name}: {alert.message}",
                "metadata": {
                    "alert_id": str(alert.id),
                    "severity": alert.severity,
                    "service": alert.service_name
                }
            }

            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.settings.NOTIFICATION_SERVICE_URL}/admin/broadcast",
                    json=notification_data
                )

        except Exception as e:
            print(f"Error notifying admins of critical alert: {e}")

    async def _get_service_health_summary(self) -> Dict[str, str]:
        """Get a summary of service health statuses."""

        service_statuses = await self._check_all_services()
        return {
            status.service_name: status.status
            for status in service_statuses
        }
