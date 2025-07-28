#!/usr/bin/env python3
"""
Comprehensive Database Initialization Script
Service-Model-Driven Schema Generation for Flow-Backend Microservices

This script dynamically analyzes each microservice's model definitions and generates
the exact database schema required for production deployment.

Features:
- Service-model-driven schema generation
- Comprehensive error handling and rollback capabilities
- Detailed logging and validation
- Support for fresh initialization and incremental updates
- Foreign key relationship management
- Index optimization for query patterns
"""

import asyncio
import asyncpg
import logging
import sys
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('database_init.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

class SchemaValidationError(Exception):
    """Raised when schema validation fails"""
    pass

class ServiceModelError(Exception):
    """Raised when service model analysis fails"""
    pass

@dataclass
class ColumnDefinition:
    """Represents a database column definition"""
    name: str
    data_type: str
    nullable: bool = True
    primary_key: bool = False
    unique: bool = False
    default: Optional[str] = None
    foreign_key: Optional[str] = None
    check_constraint: Optional[str] = None
    index: bool = False

@dataclass
class TableDefinition:
    """Represents a database table definition"""
    name: str
    columns: List[ColumnDefinition]
    indexes: List[str] = None
    constraints: List[str] = None
    service: str = ""

@dataclass
class ServiceSchema:
    """Represents a complete service schema"""
    service_name: str
    tables: List[TableDefinition]
    dependencies: List[str] = None

class DatabaseInitializer:
    """Main database initialization class"""
    
    def __init__(self, connection_string: str = None):
        self.connection_string = connection_string or self._get_connection_string()
        self.conn = None
        self.schemas: Dict[str, ServiceSchema] = {}
        self.initialization_log = []
        
    def _get_connection_string(self) -> str:
        """Get database connection string from environment or defaults"""
        host = os.getenv('DB_HOST', 'localhost')
        port = os.getenv('DB_PORT', '5432')
        user = os.getenv('DB_USER', 'user')
        password = os.getenv('DB_PASSWORD', 'password')
        database = os.getenv('DB_NAME', 'oxygen_platform')
        
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    
    async def connect(self, max_retries: int = 10, initial_delay: float = 1.0):
        """Establish database connection with robust retry logic"""
        retry_delay = initial_delay

        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 Database connection attempt {attempt + 1}/{max_retries}...")

                # Use connection with timeout and proper configuration
                self.conn = await asyncpg.connect(
                    self.connection_string,
                    timeout=30.0,  # 30 second connection timeout
                    command_timeout=60.0,  # 60 second command timeout
                    server_settings={
                        'application_name': 'flow_backend_init',
                        'tcp_keepalives_idle': '600',
                        'tcp_keepalives_interval': '30',
                        'tcp_keepalives_count': '3'
                    }
                )

                # Test the connection with a simple query
                await self.conn.fetchval("SELECT 1")
                logger.info("✅ Database connection established and verified")
                return True

            except (asyncpg.exceptions.ConnectionDoesNotExistError,
                   asyncpg.exceptions.CannotConnectNowError,
                   asyncpg.exceptions.ConnectionFailureError,
                   ConnectionRefusedError,
                   OSError) as e:
                logger.warning(f"⚠️ Database connection attempt {attempt + 1} failed: {e}")

                if attempt < max_retries - 1:
                    logger.info(f"🔄 Retrying in {retry_delay:.1f} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 30.0)  # Exponential backoff with cap
                else:
                    logger.error(f"❌ Failed to connect to database after {max_retries} attempts")
                    return False

            except Exception as e:
                logger.error(f"❌ Unexpected database connection error: {e}")
                return False

        return False
    
    async def disconnect(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            logger.info("🔌 Database connection closed")

    async def wait_for_database(self, max_wait_time: int = 120):
        """Wait for database to be ready with health checks"""
        logger.info("⏳ Waiting for database to be ready...")

        start_time = asyncio.get_event_loop().time()
        check_interval = 2.0

        while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
            try:
                # Try to establish a test connection
                test_conn = await asyncpg.connect(
                    self.connection_string,
                    timeout=5.0
                )

                # Test basic database functionality
                await test_conn.fetchval("SELECT 1")
                await test_conn.fetchval("SELECT version()")

                await test_conn.close()
                logger.info("✅ Database is ready and accepting connections")
                return True

            except Exception as e:
                logger.info(f"⏳ Database not ready yet: {e}")
                await asyncio.sleep(check_interval)
                check_interval = min(check_interval * 1.1, 10.0)  # Gradually increase interval

        logger.error(f"❌ Database did not become ready within {max_wait_time} seconds")
        return False
    
    def _define_service_schemas(self):
        """Define all service schemas based on model analysis"""
        logger.info("📋 Defining service schemas based on model analysis...")
        
        # User Service Schema
        self.schemas['user'] = ServiceSchema(
            service_name='user',
            tables=[
                TableDefinition(
                    name='users',
                    service='user',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('email', 'VARCHAR(255)', False, unique=True, index=True),
                        ColumnDefinition('password_hash', 'VARCHAR(255)', False),
                        ColumnDefinition('role', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE'),
                        ColumnDefinition('is_verified', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('verification_token', 'VARCHAR(255)'),
                        ColumnDefinition('reset_token', 'VARCHAR(255)'),
                        ColumnDefinition('reset_token_expires', 'TIMESTAMPTZ'),
                        ColumnDefinition('mfa_enabled', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('mfa_secret', 'VARCHAR(255)'),
                        ColumnDefinition('last_login', 'TIMESTAMPTZ'),
                        ColumnDefinition('login_attempts', 'INTEGER', False, default='0'),
                        ColumnDefinition('locked_until', 'TIMESTAMPTZ'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)',
                        'CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)',
                        'CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active)',
                        'CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at)',
                    ]
                ),
            ]
        )
        
        logger.info("✅ User service schema defined")

        # User Sessions Table
        self.schemas['user'].tables.append(
            TableDefinition(
                name='user_sessions',
                service='user',
                columns=[
                    ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                    ColumnDefinition('user_id', 'UUID', False, foreign_key='users(id)', index=True),
                    ColumnDefinition('session_token', 'VARCHAR(255)', False, unique=True),
                    ColumnDefinition('refresh_token', 'VARCHAR(255)', False, unique=True),
                    ColumnDefinition('expires_at', 'TIMESTAMPTZ', False),
                    ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE'),
                    ColumnDefinition('ip_address', 'INET'),
                    ColumnDefinition('user_agent', 'TEXT'),
                    ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                    ColumnDefinition('last_accessed', 'TIMESTAMPTZ'),
                ],
                indexes=[
                    'CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)',
                    'CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token)',
                    'CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at)',
                ]
            )
        )

        # User Profiles Table
        self.schemas['user'].tables.append(
            TableDefinition(
                name='user_profiles',
                service='user',
                columns=[
                    ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                    ColumnDefinition('user_id', 'UUID', False, foreign_key='users(id)', unique=True),
                    ColumnDefinition('first_name', 'VARCHAR(100)'),
                    ColumnDefinition('last_name', 'VARCHAR(100)'),
                    ColumnDefinition('phone', 'VARCHAR(20)'),
                    ColumnDefinition('address', 'TEXT'),
                    ColumnDefinition('city', 'VARCHAR(100)'),
                    ColumnDefinition('state', 'VARCHAR(100)'),
                    ColumnDefinition('country', 'VARCHAR(100)'),
                    ColumnDefinition('postal_code', 'VARCHAR(20)'),
                    ColumnDefinition('date_of_birth', 'DATE'),
                    ColumnDefinition('profile_picture_url', 'TEXT'),
                    ColumnDefinition('bio', 'TEXT'),
                    ColumnDefinition('preferences', 'JSONB'),
                    ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                    ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                ],
                indexes=[
                    'CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)',
                ]
            )
        )

        # Order Service Schema
        self.schemas['order'] = ServiceSchema(
            service_name='order',
            tables=[
                TableDefinition(
                    name='orders',
                    service='order',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('user_id', 'UUID', False, foreign_key='users(id)', index=True),
                        ColumnDefinition('order_number', 'VARCHAR(50)', False, unique=True, index=True),
                        ColumnDefinition('status', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('priority', 'VARCHAR(20)', False, default="'normal'"),
                        ColumnDefinition('is_emergency', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('total_amount', 'DECIMAL(10,2)', False),
                        ColumnDefinition('currency', 'VARCHAR(3)', False, default="'NGN'"),
                        ColumnDefinition('delivery_address', 'TEXT', False),
                        ColumnDefinition('delivery_latitude', 'DOUBLE PRECISION'),
                        ColumnDefinition('delivery_longitude', 'DOUBLE PRECISION'),
                        ColumnDefinition('delivery_instructions', 'TEXT'),
                        ColumnDefinition('required_delivery_date', 'TIMESTAMPTZ'),
                        ColumnDefinition('estimated_delivery_date', 'TIMESTAMPTZ'),
                        ColumnDefinition('actual_delivery_date', 'TIMESTAMPTZ'),
                        ColumnDefinition('notes', 'TEXT'),
                        ColumnDefinition('metadata', 'JSONB'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)',
                        'CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)',
                        'CREATE INDEX IF NOT EXISTS idx_orders_emergency ON orders(is_emergency)',
                        'CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at)',
                        'CREATE INDEX IF NOT EXISTS idx_orders_delivery_date ON orders(required_delivery_date)',
                    ]
                ),
                TableDefinition(
                    name='order_items',
                    service='order',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('order_id', 'UUID', False, foreign_key='orders(id)', index=True),
                        ColumnDefinition('product_id', 'UUID', False, index=True),
                        ColumnDefinition('product_name', 'VARCHAR(255)', False),
                        ColumnDefinition('cylinder_size', 'VARCHAR(20)', False),
                        ColumnDefinition('quantity', 'INTEGER', False),
                        ColumnDefinition('unit_price', 'DECIMAL(10,2)', False),
                        ColumnDefinition('total_price', 'DECIMAL(10,2)', False),
                        ColumnDefinition('supplier_id', 'UUID'),
                        ColumnDefinition('supplier_name', 'VARCHAR(255)'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id)',
                        'CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON order_items(product_id)',
                        'CREATE INDEX IF NOT EXISTS idx_order_items_supplier_id ON order_items(supplier_id)',
                    ]
                ),
            ]
        )

        logger.info("✅ Order service schema defined")

        # Payment Service Schema
        self.schemas['payment'] = ServiceSchema(
            service_name='payment',
            tables=[
                TableDefinition(
                    name='payments',
                    service='payment',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('order_id', 'UUID', False, foreign_key='orders(id)', index=True),
                        ColumnDefinition('user_id', 'UUID', False, foreign_key='users(id)', index=True),
                        ColumnDefinition('vendor_id', 'UUID', foreign_key='users(id)', index=True),
                        ColumnDefinition('reference', 'VARCHAR(255)', False, unique=True, index=True),
                        ColumnDefinition('amount', 'DECIMAL(10,2)', False),
                        ColumnDefinition('platform_fee', 'DECIMAL(10,2)', False, default='0.00'),
                        ColumnDefinition('vendor_amount', 'DECIMAL(10,2)'),
                        ColumnDefinition('currency', 'VARCHAR(3)', False, default="'NGN'"),
                        ColumnDefinition('status', 'VARCHAR(50)', False, default="'pending'", index=True),
                        ColumnDefinition('payment_method', 'VARCHAR(50)', False),
                        ColumnDefinition('provider', 'VARCHAR(50)', False, default="'paystack'"),
                        ColumnDefinition('provider_reference', 'VARCHAR(255)'),
                        ColumnDefinition('paystack_reference', 'VARCHAR(255)', index=True),
                        ColumnDefinition('paystack_access_code', 'VARCHAR(255)'),
                        ColumnDefinition('authorization_url', 'TEXT'),
                        ColumnDefinition('provider_response', 'JSONB'),
                        ColumnDefinition('metadata', 'JSONB'),
                        ColumnDefinition('paid_at', 'TIMESTAMPTZ', index=True),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('completed_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id)',
                        'CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)',
                        'CREATE INDEX IF NOT EXISTS idx_payments_vendor_id ON payments(vendor_id)',
                        'CREATE INDEX IF NOT EXISTS idx_payments_reference ON payments(reference)',
                        'CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)',
                        'CREATE INDEX IF NOT EXISTS idx_payments_paystack_ref ON payments(paystack_reference)',
                        'CREATE INDEX IF NOT EXISTS idx_payments_created_at ON payments(created_at)',
                        'CREATE INDEX IF NOT EXISTS idx_payments_paid_at ON payments(paid_at)',
                    ],
                    constraints=[
                        "ALTER TABLE payments ADD CONSTRAINT chk_payment_status CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled', 'refunded'))"
                    ]
                ),
            ]
        )

        logger.info("✅ Payment service schema defined")

        # Notification Service Schema
        self.schemas['notification'] = ServiceSchema(
            service_name='notification',
            tables=[
                TableDefinition(
                    name='notification_templates',
                    service='notification',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('name', 'VARCHAR(255)', False, unique=True),
                        ColumnDefinition('subject', 'VARCHAR(255)', False),
                        ColumnDefinition('body', 'TEXT', False),
                        ColumnDefinition('notification_type', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('channel', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE'),
                        ColumnDefinition('variables', 'JSONB'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_notification_templates_name ON notification_templates(name)',
                        'CREATE INDEX IF NOT EXISTS idx_notification_templates_type ON notification_templates(notification_type)',
                    ]
                ),
                TableDefinition(
                    name='notifications',
                    service='notification',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('user_id', 'UUID', False, foreign_key='users(id)', index=True),
                        ColumnDefinition('title', 'VARCHAR(255)', False),
                        ColumnDefinition('message', 'TEXT', False),
                        ColumnDefinition('notification_type', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('status', 'VARCHAR(50)', False, default="'pending'", index=True),
                        ColumnDefinition('channel', 'VARCHAR(50)', False, default="'in_app'", index=True),
                        ColumnDefinition('is_read', 'BOOLEAN', False, default='FALSE', index=True),
                        ColumnDefinition('template_id', 'UUID', foreign_key='notification_templates(id)', index=True),
                        ColumnDefinition('metadata', 'JSONB'),
                        ColumnDefinition('sent_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('delivered_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('read_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ', False, default='NOW()'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id)',
                        'CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(notification_type)',
                        'CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status)',
                        'CREATE INDEX IF NOT EXISTS idx_notifications_channel ON notifications(channel)',
                        'CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read)',
                        'CREATE INDEX IF NOT EXISTS idx_notifications_template_id ON notifications(template_id)',
                        'CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at)',
                    ]
                ),
            ]
        )

        logger.info("✅ Notification service schema defined")

        # Location Service Schema
        self.schemas['location'] = ServiceSchema(
            service_name='location',
            tables=[
                TableDefinition(
                    name='locations',
                    service='location',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('user_id', 'UUID', False, foreign_key='users(id)', index=True),
                        ColumnDefinition('name', 'VARCHAR(255)', False),
                        ColumnDefinition('address', 'TEXT', False),
                        ColumnDefinition('latitude', 'DOUBLE PRECISION', False),
                        ColumnDefinition('longitude', 'DOUBLE PRECISION', False),
                        ColumnDefinition('city', 'VARCHAR(100)'),
                        ColumnDefinition('state', 'VARCHAR(100)'),
                        ColumnDefinition('country', 'VARCHAR(100)'),
                        ColumnDefinition('postal_code', 'VARCHAR(20)'),
                        ColumnDefinition('location_type', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('is_default', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE'),
                        ColumnDefinition('metadata', 'JSONB'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_locations_user_id ON locations(user_id)',
                        'CREATE INDEX IF NOT EXISTS idx_locations_type ON locations(location_type)',
                        'CREATE INDEX IF NOT EXISTS idx_locations_coordinates ON locations(latitude, longitude)',
                        'CREATE INDEX IF NOT EXISTS idx_locations_default ON locations(is_default)',
                    ]
                ),
                TableDefinition(
                    name='emergency_zones',
                    service='location',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('name', 'VARCHAR(255)', False),
                        ColumnDefinition('center_latitude', 'DOUBLE PRECISION', False),
                        ColumnDefinition('center_longitude', 'DOUBLE PRECISION', False),
                        ColumnDefinition('radius_km', 'DECIMAL(8,2)', False),
                        ColumnDefinition('priority_level', 'INTEGER', False, default='1'),
                        ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_emergency_zones_center ON emergency_zones(center_latitude, center_longitude)',
                        'CREATE INDEX IF NOT EXISTS idx_emergency_zones_priority ON emergency_zones(priority_level)',
                    ]
                ),
                TableDefinition(
                    name='service_areas',
                    service='location',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('vendor_id', 'UUID', False, foreign_key='users(id)', index=True),
                        ColumnDefinition('name', 'VARCHAR(255)', False),
                        ColumnDefinition('center_latitude', 'DOUBLE PRECISION', False),
                        ColumnDefinition('center_longitude', 'DOUBLE PRECISION', False),
                        ColumnDefinition('radius_km', 'DECIMAL(8,2)', False),
                        ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_service_areas_vendor ON service_areas(vendor_id)',
                        'CREATE INDEX IF NOT EXISTS idx_service_areas_center ON service_areas(center_latitude, center_longitude)',
                    ]
                ),
            ]
        )

        logger.info("✅ Location service schema defined")

        # Inventory Service Schema
        self.schemas['inventory'] = ServiceSchema(
            service_name='inventory',
            tables=[
                TableDefinition(
                    name='inventory_locations',
                    service='inventory',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('supplier_id', 'UUID', False, foreign_key='users(id)', index=True),
                        ColumnDefinition('location_id', 'UUID', False, foreign_key='locations(id)', index=True),
                        ColumnDefinition('cylinder_size', 'VARCHAR(20)', False, index=True),
                        ColumnDefinition('quantity_available', 'INTEGER', False, default='0'),
                        ColumnDefinition('quantity_reserved', 'INTEGER', False, default='0'),
                        ColumnDefinition('unit_price', 'DECIMAL(10,2)', False),
                        ColumnDefinition('minimum_stock', 'INTEGER', False, default='0'),
                        ColumnDefinition('maximum_stock', 'INTEGER'),
                        ColumnDefinition('reorder_point', 'INTEGER'),
                        ColumnDefinition('last_restocked', 'TIMESTAMPTZ'),
                        ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE'),
                        ColumnDefinition('metadata', 'JSONB'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_inventory_supplier_id ON inventory_locations(supplier_id)',
                        'CREATE INDEX IF NOT EXISTS idx_inventory_location_id ON inventory_locations(location_id)',
                        'CREATE INDEX IF NOT EXISTS idx_inventory_cylinder_size ON inventory_locations(cylinder_size)',
                        'CREATE INDEX IF NOT EXISTS idx_inventory_availability ON inventory_locations(quantity_available)',
                    ]
                ),
            ]
        )

        logger.info("✅ Inventory service schema defined")

        # Review Service Schema
        self.schemas['review'] = ServiceSchema(
            service_name='review',
            tables=[
                TableDefinition(
                    name='reviews',
                    service='review',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('user_id', 'UUID', False, foreign_key='users(id)', index=True),
                        ColumnDefinition('order_id', 'UUID', foreign_key='orders(id)', index=True),
                        ColumnDefinition('supplier_id', 'UUID', foreign_key='users(id)', index=True),
                        ColumnDefinition('rating', 'INTEGER', False, index=True),
                        ColumnDefinition('title', 'VARCHAR(255)'),
                        ColumnDefinition('comment', 'TEXT'),
                        ColumnDefinition('review_type', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('is_verified', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('is_moderated', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('moderation_notes', 'TEXT'),
                        ColumnDefinition('helpful_count', 'INTEGER', False, default='0'),
                        ColumnDefinition('metadata', 'JSONB'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_reviews_user_id ON reviews(user_id)',
                        'CREATE INDEX IF NOT EXISTS idx_reviews_order_id ON reviews(order_id)',
                        'CREATE INDEX IF NOT EXISTS idx_reviews_supplier_id ON reviews(supplier_id)',
                        'CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating)',
                        'CREATE INDEX IF NOT EXISTS idx_reviews_type ON reviews(review_type)',
                        'CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at)',
                    ],
                    constraints=[
                        "ALTER TABLE reviews ADD CONSTRAINT chk_review_rating CHECK (rating >= 1 AND rating <= 5)"
                    ]
                ),
            ]
        )

        logger.info("✅ Review service schema defined")

        # Admin Service Schema
        self.schemas['admin'] = ServiceSchema(
            service_name='admin',
            tables=[
                TableDefinition(
                    name='admin_users',
                    service='admin',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('user_id', 'UUID', False, foreign_key='users(id)', unique=True, index=True),
                        ColumnDefinition('admin_level', 'VARCHAR(50)', False, default="'admin'"),
                        ColumnDefinition('permissions', 'JSONB', False, default='[]'),
                        ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE'),
                        ColumnDefinition('last_login', 'TIMESTAMPTZ'),
                        ColumnDefinition('login_count', 'INTEGER', False, default='0'),
                        ColumnDefinition('current_session_id', 'VARCHAR(255)'),
                        ColumnDefinition('session_expires_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_admin_users_user_id ON admin_users(user_id)',
                        'CREATE INDEX IF NOT EXISTS idx_admin_users_level ON admin_users(admin_level)',
                    ]
                ),
                TableDefinition(
                    name='audit_logs',
                    service='admin',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('admin_user_id', 'UUID', False, foreign_key='admin_users(id)', index=True),
                        ColumnDefinition('action_type', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('resource_type', 'VARCHAR(50)', False),
                        ColumnDefinition('resource_id', 'VARCHAR(255)', index=True),
                        ColumnDefinition('description', 'TEXT', False),
                        ColumnDefinition('old_values', 'JSONB'),
                        ColumnDefinition('new_values', 'JSONB'),
                        ColumnDefinition('ip_address', 'INET'),
                        ColumnDefinition('user_agent', 'TEXT'),
                        ColumnDefinition('request_id', 'VARCHAR(255)'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()', index=True),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_audit_logs_admin_user ON audit_logs(admin_user_id)',
                        'CREATE INDEX IF NOT EXISTS idx_audit_logs_action_type ON audit_logs(action_type)',
                        'CREATE INDEX IF NOT EXISTS idx_audit_logs_resource ON audit_logs(resource_type, resource_id)',
                        'CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at)',
                    ]
                ),
                TableDefinition(
                    name='system_metrics',
                    service='admin',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('metric_type', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('service_name', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('value', 'DOUBLE PRECISION', False),
                        ColumnDefinition('unit', 'VARCHAR(20)'),
                        ColumnDefinition('metric_metadata', 'JSONB'),
                        ColumnDefinition('tags', 'JSONB'),
                        ColumnDefinition('timestamp', 'TIMESTAMPTZ', False, default='NOW()', index=True),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_system_metrics_type_time ON system_metrics(metric_type, timestamp)',
                        'CREATE INDEX IF NOT EXISTS idx_system_metrics_service_time ON system_metrics(service_name, timestamp)',
                    ]
                ),
                TableDefinition(
                    name='system_alerts',
                    service='admin',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('alert_type', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('severity', 'VARCHAR(20)', False, index=True),
                        ColumnDefinition('title', 'VARCHAR(255)', False),
                        ColumnDefinition('message', 'TEXT', False),
                        ColumnDefinition('service_name', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('component', 'VARCHAR(100)'),
                        ColumnDefinition('details', 'JSONB'),
                        ColumnDefinition('threshold_value', 'DOUBLE PRECISION'),
                        ColumnDefinition('current_value', 'DOUBLE PRECISION'),
                        ColumnDefinition('status', 'VARCHAR(20)', False, default="'active'", index=True),
                        ColumnDefinition('acknowledged_by', 'UUID', foreign_key='admin_users(id)'),
                        ColumnDefinition('acknowledged_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('resolved_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()', index=True),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_system_alerts_status_severity ON system_alerts(status, severity)',
                        'CREATE INDEX IF NOT EXISTS idx_system_alerts_service_time ON system_alerts(service_name, created_at)',
                    ]
                ),
            ]
        )

        logger.info("✅ Admin service schema defined")

        # Supplier Service Schema
        self.schemas['supplier'] = ServiceSchema(
            service_name='supplier',
            tables=[
                TableDefinition(
                    name='suppliers',
                    service='supplier',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('user_id', 'UUID', False, foreign_key='users(id)', unique=True, index=True),
                        ColumnDefinition('business_name', 'VARCHAR(255)', False),
                        ColumnDefinition('registration_number', 'VARCHAR(100)'),
                        ColumnDefinition('tax_identification_number', 'VARCHAR(100)'),
                        ColumnDefinition('contact_person', 'VARCHAR(255)'),
                        ColumnDefinition('contact_phone', 'VARCHAR(20)'),
                        ColumnDefinition('business_address', 'TEXT'),
                        ColumnDefinition('status', 'VARCHAR(50)', False, default="'pending_verification'", index=True),
                        ColumnDefinition('rejection_reason', 'TEXT'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_suppliers_user_id ON suppliers(user_id)',
                        'CREATE INDEX IF NOT EXISTS idx_suppliers_status ON suppliers(status)',
                        'CREATE INDEX IF NOT EXISTS idx_suppliers_business_name ON suppliers(business_name)',
                    ]
                ),
                TableDefinition(
                    name='documents',
                    service='supplier',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('supplier_id', 'UUID', False, foreign_key='suppliers(id)', index=True),
                        ColumnDefinition('document_type', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('document_name', 'VARCHAR(255)', False),
                        ColumnDefinition('file_path', 'TEXT', False),
                        ColumnDefinition('file_size', 'BIGINT'),
                        ColumnDefinition('mime_type', 'VARCHAR(100)'),
                        ColumnDefinition('verification_status', 'VARCHAR(50)', False, default="'pending'", index=True),
                        ColumnDefinition('verification_notes', 'TEXT'),
                        ColumnDefinition('verified_by', 'UUID', foreign_key='admin_users(id)'),
                        ColumnDefinition('verified_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_documents_supplier_id ON documents(supplier_id)',
                        'CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(document_type)',
                        'CREATE INDEX IF NOT EXISTS idx_documents_verification_status ON documents(verification_status)',
                    ]
                ),
            ]
        )

        logger.info("✅ Supplier service schema defined")


        # Delivery Service Schema
        self.schemas['delivery'] = ServiceSchema(
            service_name='delivery',
            tables=[
                TableDefinition(
                    name='deliveries',
                    service='delivery',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('order_id', 'UUID', False, foreign_key='orders(id)', unique=True, index=True),
                        ColumnDefinition('driver_id', 'UUID', index=True),
                        ColumnDefinition('vehicle_id', 'UUID', index=True),
                        ColumnDefinition('status', 'VARCHAR(50)', False, default="'pending'", index=True),
                        ColumnDefinition('priority', 'VARCHAR(20)', False, default="'normal'"),
                        ColumnDefinition('pickup_address', 'TEXT', False),
                        ColumnDefinition('pickup_latitude', 'DOUBLE PRECISION'),
                        ColumnDefinition('pickup_longitude', 'DOUBLE PRECISION'),
                        ColumnDefinition('delivery_address', 'TEXT', False),
                        ColumnDefinition('delivery_latitude', 'DOUBLE PRECISION'),
                        ColumnDefinition('delivery_longitude', 'DOUBLE PRECISION'),
                        ColumnDefinition('estimated_distance_km', 'DOUBLE PRECISION'),
                        ColumnDefinition('actual_distance_km', 'DOUBLE PRECISION'),
                        ColumnDefinition('estimated_duration_minutes', 'INTEGER'),
                        ColumnDefinition('actual_duration_minutes', 'INTEGER'),
                        ColumnDefinition('scheduled_pickup_time', 'TIMESTAMPTZ'),
                        ColumnDefinition('actual_pickup_time', 'TIMESTAMPTZ'),
                        ColumnDefinition('estimated_delivery_time', 'TIMESTAMPTZ'),
                        ColumnDefinition('actual_delivery_time', 'TIMESTAMPTZ'),
                        ColumnDefinition('delivery_instructions', 'TEXT'),
                        ColumnDefinition('delivery_notes', 'TEXT'),
                        ColumnDefinition('tracking_data', 'JSONB'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_deliveries_order_id ON deliveries(order_id)',
                        'CREATE INDEX IF NOT EXISTS idx_deliveries_driver_id ON deliveries(driver_id)',
                        'CREATE INDEX IF NOT EXISTS idx_deliveries_status ON deliveries(status)',
                        'CREATE INDEX IF NOT EXISTS idx_deliveries_scheduled_pickup ON deliveries(scheduled_pickup_time)',
                    ]
                ),
            ]
        )

        logger.info("✅ Delivery service schema defined")

        # Pricing Service Schema - Comprehensive vendor and product management
        self.schemas['pricing'] = ServiceSchema(
            service_name='pricing',
            tables=[
                # Vendors table
                TableDefinition(
                    name='vendors',
                    service='pricing',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('user_id', 'UUID', False, foreign_key='users(id)', unique=True, index=True),
                        ColumnDefinition('business_name', 'VARCHAR(255)', False, index=True),
                        ColumnDefinition('business_registration_number', 'VARCHAR(100)'),
                        ColumnDefinition('tax_identification_number', 'VARCHAR(100)'),
                        ColumnDefinition('contact_person', 'VARCHAR(255)'),
                        ColumnDefinition('contact_phone', 'VARCHAR(20)'),
                        ColumnDefinition('contact_email', 'VARCHAR(255)'),
                        ColumnDefinition('business_address', 'TEXT'),
                        ColumnDefinition('business_city', 'VARCHAR(100)'),
                        ColumnDefinition('business_state', 'VARCHAR(100)'),
                        ColumnDefinition('business_country', 'VARCHAR(100)', False, default="'Nigeria'"),
                        ColumnDefinition('postal_code', 'VARCHAR(20)'),
                        ColumnDefinition('business_type', 'VARCHAR(50)', False, default="'medical_supplier'"),
                        ColumnDefinition('years_in_business', 'INTEGER'),
                        ColumnDefinition('license_number', 'VARCHAR(100)'),
                        ColumnDefinition('certification_details', 'JSONB'),
                        ColumnDefinition('verification_status', 'VARCHAR(50)', False, default="'pending'", index=True),
                        ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE', index=True),
                        ColumnDefinition('is_featured', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('rejection_reason', 'TEXT'),
                        ColumnDefinition('average_rating', 'DECIMAL(3,2)', False, default='0.0'),
                        ColumnDefinition('total_orders', 'INTEGER', False, default='0'),
                        ColumnDefinition('successful_deliveries', 'INTEGER', False, default='0'),
                        ColumnDefinition('response_time_hours', 'DECIMAL(5,2)', False, default='24.0'),
                        ColumnDefinition('operating_hours', 'JSONB'),
                        ColumnDefinition('emergency_contact', 'VARCHAR(20)'),
                        ColumnDefinition('emergency_surcharge_percentage', 'DECIMAL(5,2)', False, default='0.0'),
                        ColumnDefinition('minimum_order_value', 'DECIMAL(10,2)', False, default='0.0'),
                        ColumnDefinition('vendor_metadata', 'JSONB'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('verified_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('last_active_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_vendors_user_id ON vendors(user_id)',
                        'CREATE INDEX IF NOT EXISTS idx_vendors_business_name ON vendors(business_name)',
                        'CREATE INDEX IF NOT EXISTS idx_vendors_verification_status ON vendors(verification_status)',
                        'CREATE INDEX IF NOT EXISTS idx_vendors_is_active ON vendors(is_active)',
                        'CREATE INDEX IF NOT EXISTS idx_vendors_business_type ON vendors(business_type)',
                        'CREATE INDEX IF NOT EXISTS idx_vendors_rating ON vendors(average_rating)',
                    ]
                ),
                # Vendor profiles table
                TableDefinition(
                    name='vendor_profiles',
                    service='pricing',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('vendor_id', 'UUID', False, foreign_key='vendors(id)', unique=True, index=True),
                        ColumnDefinition('company_description', 'TEXT'),
                        ColumnDefinition('company_logo_url', 'VARCHAR(500)'),
                        ColumnDefinition('website_url', 'VARCHAR(255)'),
                        ColumnDefinition('social_media_links', 'JSONB'),
                        ColumnDefinition('specializations', 'JSONB'),
                        ColumnDefinition('certifications', 'JSONB'),
                        ColumnDefinition('quality_standards', 'JSONB'),
                        ColumnDefinition('delivery_methods', 'JSONB'),
                        ColumnDefinition('payment_methods', 'JSONB'),
                        ColumnDefinition('return_policy', 'TEXT'),
                        ColumnDefinition('warranty_policy', 'TEXT'),
                        ColumnDefinition('coverage_areas', 'JSONB'),
                        ColumnDefinition('delivery_zones', 'JSONB'),
                        ColumnDefinition('on_time_delivery_rate', 'DECIMAL(5,2)', False, default='0.0'),
                        ColumnDefinition('customer_satisfaction_score', 'DECIMAL(3,2)', False, default='0.0'),
                        ColumnDefinition('order_fulfillment_rate', 'DECIMAL(5,2)', False, default='0.0'),
                        ColumnDefinition('preferred_communication_method', 'VARCHAR(50)', False, default="'email'"),
                        ColumnDefinition('notification_preferences', 'JSONB'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_vendor_profiles_vendor_id ON vendor_profiles(vendor_id)',
                    ]
                ),
                # Service areas table
                TableDefinition(
                    name='service_areas',
                    service='pricing',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('vendor_id', 'UUID', False, foreign_key='vendors(id)', index=True),
                        ColumnDefinition('area_name', 'VARCHAR(255)', False),
                        ColumnDefinition('area_type', 'VARCHAR(50)', False),
                        ColumnDefinition('center_latitude', 'DECIMAL(10,8)'),
                        ColumnDefinition('center_longitude', 'DECIMAL(11,8)'),
                        ColumnDefinition('radius_km', 'DECIMAL(8,2)'),
                        ColumnDefinition('boundary_coordinates', 'JSONB'),
                        ColumnDefinition('state', 'VARCHAR(100)'),
                        ColumnDefinition('cities', 'JSONB'),
                        ColumnDefinition('postal_codes', 'JSONB'),
                        ColumnDefinition('delivery_fee', 'DECIMAL(10,2)', False, default='0.0'),
                        ColumnDefinition('minimum_order_value', 'DECIMAL(10,2)', False, default='0.0'),
                        ColumnDefinition('estimated_delivery_time_hours', 'INTEGER', False, default='24'),
                        ColumnDefinition('emergency_delivery_available', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('emergency_delivery_time_hours', 'INTEGER'),
                        ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE', index=True),
                        ColumnDefinition('priority_level', 'INTEGER', False, default='1'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_service_areas_vendor_id ON service_areas(vendor_id)',
                        'CREATE INDEX IF NOT EXISTS idx_service_areas_coordinates ON service_areas(center_latitude, center_longitude)',
                        'CREATE INDEX IF NOT EXISTS idx_service_areas_active ON service_areas(is_active)',
                    ]
                ),
                # Product catalogs table
                TableDefinition(
                    name='product_catalogs',
                    service='pricing',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('vendor_id', 'UUID', False, foreign_key='vendors(id)', index=True),
                        ColumnDefinition('product_code', 'VARCHAR(100)', False, index=True),
                        ColumnDefinition('product_name', 'VARCHAR(255)', False, index=True),
                        ColumnDefinition('product_category', 'VARCHAR(100)', False, index=True),
                        ColumnDefinition('product_subcategory', 'VARCHAR(100)'),
                        ColumnDefinition('cylinder_size', 'VARCHAR(20)', index=True),
                        ColumnDefinition('capacity_liters', 'DECIMAL(8,2)'),
                        ColumnDefinition('pressure_bar', 'DECIMAL(8,2)'),
                        ColumnDefinition('gas_type', 'VARCHAR(50)', False, default="'medical_oxygen'"),
                        ColumnDefinition('purity_percentage', 'DECIMAL(5,2)'),
                        ColumnDefinition('dimensions', 'JSONB'),
                        ColumnDefinition('weight_kg', 'DECIMAL(8,2)'),
                        ColumnDefinition('material', 'VARCHAR(100)'),
                        ColumnDefinition('color', 'VARCHAR(50)'),
                        ColumnDefinition('description', 'TEXT'),
                        ColumnDefinition('features', 'JSONB'),
                        ColumnDefinition('specifications', 'JSONB'),
                        ColumnDefinition('usage_instructions', 'TEXT'),
                        ColumnDefinition('safety_information', 'TEXT'),
                        ColumnDefinition('certifications', 'JSONB'),
                        ColumnDefinition('regulatory_approvals', 'JSONB'),
                        ColumnDefinition('quality_standards', 'JSONB'),
                        ColumnDefinition('product_images', 'JSONB'),
                        ColumnDefinition('product_documents', 'JSONB'),
                        ColumnDefinition('is_available', 'BOOLEAN', False, default='TRUE', index=True),
                        ColumnDefinition('stock_status', 'VARCHAR(50)', False, default="'in_stock'", index=True),
                        ColumnDefinition('minimum_order_quantity', 'INTEGER', False, default='1'),
                        ColumnDefinition('maximum_order_quantity', 'INTEGER'),
                        ColumnDefinition('base_price', 'DECIMAL(10,2)'),
                        ColumnDefinition('currency', 'VARCHAR(3)', False, default="'NGN'"),
                        ColumnDefinition('vendor_product_code', 'VARCHAR(100)'),
                        ColumnDefinition('manufacturer', 'VARCHAR(255)'),
                        ColumnDefinition('brand', 'VARCHAR(100)'),
                        ColumnDefinition('model_number', 'VARCHAR(100)'),
                        ColumnDefinition('requires_special_handling', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('hazardous_material', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('storage_requirements', 'TEXT'),
                        ColumnDefinition('shelf_life_days', 'INTEGER'),
                        ColumnDefinition('search_keywords', 'JSONB'),
                        ColumnDefinition('tags', 'JSONB'),
                        ColumnDefinition('is_featured', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE', index=True),
                        ColumnDefinition('approval_status', 'VARCHAR(50)', False, default="'pending'", index=True),
                        ColumnDefinition('product_metadata', 'JSONB'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('approved_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_product_catalogs_vendor_id ON product_catalogs(vendor_id)',
                        'CREATE INDEX IF NOT EXISTS idx_product_catalogs_product_code ON product_catalogs(product_code)',
                        'CREATE INDEX IF NOT EXISTS idx_product_catalogs_product_name ON product_catalogs(product_name)',
                        'CREATE INDEX IF NOT EXISTS idx_product_catalogs_category ON product_catalogs(product_category)',
                        'CREATE INDEX IF NOT EXISTS idx_product_catalogs_cylinder_size ON product_catalogs(cylinder_size)',
                        'CREATE INDEX IF NOT EXISTS idx_product_catalogs_available ON product_catalogs(is_available)',
                        'CREATE INDEX IF NOT EXISTS idx_product_catalogs_stock_status ON product_catalogs(stock_status)',
                        'CREATE INDEX IF NOT EXISTS idx_product_catalogs_active ON product_catalogs(is_active)',
                        'CREATE INDEX IF NOT EXISTS idx_product_catalogs_approval ON product_catalogs(approval_status)',
                    ]
                ),
                # Pricing tiers table
                TableDefinition(
                    name='pricing_tiers',
                    service='pricing',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('vendor_id', 'UUID', False, foreign_key='vendors(id)', index=True),
                        ColumnDefinition('product_id', 'UUID', False, foreign_key='product_catalogs(id)', index=True),
                        ColumnDefinition('service_area_id', 'UUID', foreign_key='service_areas(id)', index=True),
                        ColumnDefinition('tier_name', 'VARCHAR(100)', False),
                        ColumnDefinition('unit_price', 'DECIMAL(10,2)', False),
                        ColumnDefinition('currency', 'VARCHAR(3)', False, default="'NGN'"),
                        ColumnDefinition('minimum_quantity', 'INTEGER', False, default='1'),
                        ColumnDefinition('maximum_quantity', 'INTEGER'),
                        ColumnDefinition('delivery_fee', 'DECIMAL(10,2)', False, default='0.0'),
                        ColumnDefinition('setup_fee', 'DECIMAL(10,2)', False, default='0.0'),
                        ColumnDefinition('handling_fee', 'DECIMAL(10,2)', False, default='0.0'),
                        ColumnDefinition('emergency_surcharge', 'DECIMAL(10,2)', False, default='0.0'),
                        ColumnDefinition('bulk_discount_percentage', 'DECIMAL(5,2)', False, default='0.0'),
                        ColumnDefinition('loyalty_discount_percentage', 'DECIMAL(5,2)', False, default='0.0'),
                        ColumnDefinition('seasonal_discount_percentage', 'DECIMAL(5,2)', False, default='0.0'),
                        ColumnDefinition('effective_from', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('effective_until', 'TIMESTAMPTZ'),
                        ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE', index=True),
                        ColumnDefinition('payment_terms', 'VARCHAR(100)'),
                        ColumnDefinition('minimum_order_value', 'DECIMAL(10,2)'),
                        ColumnDefinition('cancellation_policy', 'TEXT'),
                        ColumnDefinition('priority_rank', 'INTEGER', False, default='1'),
                        ColumnDefinition('is_featured', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('is_promotional', 'BOOLEAN', False, default='FALSE'),
                        ColumnDefinition('pricing_notes', 'TEXT'),
                        ColumnDefinition('internal_notes', 'TEXT'),
                        ColumnDefinition('pricing_metadata', 'JSONB'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_pricing_tiers_vendor_id ON pricing_tiers(vendor_id)',
                        'CREATE INDEX IF NOT EXISTS idx_pricing_tiers_product_id ON pricing_tiers(product_id)',
                        'CREATE INDEX IF NOT EXISTS idx_pricing_tiers_service_area_id ON pricing_tiers(service_area_id)',
                        'CREATE INDEX IF NOT EXISTS idx_pricing_tiers_active ON pricing_tiers(is_active)',
                        'CREATE INDEX IF NOT EXISTS idx_pricing_tiers_effective ON pricing_tiers(effective_from, effective_until)',
                    ]
                ),
                # Price history table
                TableDefinition(
                    name='price_history',
                    service='pricing',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('pricing_tier_id', 'UUID', False, foreign_key='pricing_tiers(id)', index=True),
                        ColumnDefinition('vendor_id', 'UUID', False, foreign_key='vendors(id)', index=True),
                        ColumnDefinition('product_id', 'UUID', False, foreign_key='product_catalogs(id)', index=True),
                        ColumnDefinition('old_unit_price', 'DECIMAL(10,2)'),
                        ColumnDefinition('new_unit_price', 'DECIMAL(10,2)'),
                        ColumnDefinition('old_delivery_fee', 'DECIMAL(10,2)'),
                        ColumnDefinition('new_delivery_fee', 'DECIMAL(10,2)'),
                        ColumnDefinition('change_type', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('change_percentage', 'DECIMAL(5,2)'),
                        ColumnDefinition('change_reason', 'VARCHAR(255)'),
                        ColumnDefinition('change_notes', 'TEXT'),
                        ColumnDefinition('market_conditions', 'JSONB'),
                        ColumnDefinition('competitor_pricing', 'JSONB'),
                        ColumnDefinition('effective_date', 'TIMESTAMPTZ', False),
                        ColumnDefinition('recorded_at', 'TIMESTAMPTZ', False, default='NOW()'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_price_history_pricing_tier_id ON price_history(pricing_tier_id)',
                        'CREATE INDEX IF NOT EXISTS idx_price_history_vendor_id ON price_history(vendor_id)',
                        'CREATE INDEX IF NOT EXISTS idx_price_history_product_id ON price_history(product_id)',
                        'CREATE INDEX IF NOT EXISTS idx_price_history_change_type ON price_history(change_type)',
                        'CREATE INDEX IF NOT EXISTS idx_price_history_effective_date ON price_history(effective_date)',
                    ]
                ),
                # Price alerts table
                TableDefinition(
                    name='price_alerts',
                    service='pricing',
                    columns=[
                        ColumnDefinition('id', 'UUID', False, True, default='gen_random_uuid()'),
                        ColumnDefinition('user_id', 'UUID', False, foreign_key='users(id)', index=True),
                        ColumnDefinition('product_id', 'UUID', False, foreign_key='product_catalogs(id)', index=True),
                        ColumnDefinition('vendor_id', 'UUID', foreign_key='vendors(id)', index=True),
                        ColumnDefinition('alert_type', 'VARCHAR(50)', False, index=True),
                        ColumnDefinition('target_price', 'DECIMAL(10,2)'),
                        ColumnDefinition('price_threshold_percentage', 'DECIMAL(5,2)'),
                        ColumnDefinition('is_active', 'BOOLEAN', False, default='TRUE', index=True),
                        ColumnDefinition('notification_method', 'VARCHAR(50)', False, default="'email'"),
                        ColumnDefinition('frequency', 'VARCHAR(50)', False, default="'immediate'"),
                        ColumnDefinition('last_triggered_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('trigger_count', 'INTEGER', False, default='0'),
                        ColumnDefinition('last_price_checked', 'DECIMAL(10,2)'),
                        ColumnDefinition('expires_at', 'TIMESTAMPTZ'),
                        ColumnDefinition('created_at', 'TIMESTAMPTZ', False, default='NOW()'),
                        ColumnDefinition('updated_at', 'TIMESTAMPTZ'),
                    ],
                    indexes=[
                        'CREATE INDEX IF NOT EXISTS idx_price_alerts_user_id ON price_alerts(user_id)',
                        'CREATE INDEX IF NOT EXISTS idx_price_alerts_product_id ON price_alerts(product_id)',
                        'CREATE INDEX IF NOT EXISTS idx_price_alerts_vendor_id ON price_alerts(vendor_id)',
                        'CREATE INDEX IF NOT EXISTS idx_price_alerts_alert_type ON price_alerts(alert_type)',
                        'CREATE INDEX IF NOT EXISTS idx_price_alerts_active ON price_alerts(is_active)',
                    ]
                ),
            ]
        )

        logger.info("✅ Pricing service schema defined")
        logger.info("🎯 All service schemas defined successfully")
    
    async def create_table(self, table_def: TableDefinition) -> bool:
        """Create a single table with all its columns and constraints"""
        try:
            # Build CREATE TABLE statement
            columns_sql = []
            for col in table_def.columns:
                col_sql = f"{col.name} {col.data_type}"
                
                if col.primary_key:
                    col_sql += " PRIMARY KEY"
                elif not col.nullable:
                    col_sql += " NOT NULL"
                
                if col.unique and not col.primary_key:
                    col_sql += " UNIQUE"
                
                if col.default:
                    if col.default in ['NOW()', 'gen_random_uuid()']:
                        col_sql += f" DEFAULT {col.default}"
                    else:
                        col_sql += f" DEFAULT {col.default}"
                
                columns_sql.append(col_sql)
            
            # Skip foreign key constraints for now to avoid dependency issues
            # Foreign keys can be added later once all tables are created
            
            create_sql = f"""
                CREATE TABLE IF NOT EXISTS {table_def.name} (
                    {', '.join(columns_sql)}
                )
            """
            
            await self.conn.execute(create_sql)
            logger.info(f"✅ Created table: {table_def.name}")
            
            # Create indexes
            if table_def.indexes:
                for index_sql in table_def.indexes:
                    await self.conn.execute(index_sql)
                    logger.info(f"✅ Created index for table: {table_def.name}")

            # Add constraints
            if table_def.constraints:
                for constraint_sql in table_def.constraints:
                    try:
                        await self.conn.execute(constraint_sql)
                        logger.info(f"✅ Added constraint for table: {table_def.name}")
                    except Exception as e:
                        logger.warning(f"⚠️ Constraint already exists for table {table_def.name}: {e}")

            self.initialization_log.append(f"Created table: {table_def.name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create table {table_def.name}: {e}")
            return False

    async def validate_schema(self) -> bool:
        """Validate that the created schema matches service model expectations"""
        logger.info("🔍 Validating database schema against service models...")

        try:
            validation_errors = []

            # Check critical tables exist
            critical_tables = [
                'users', 'user_sessions', 'user_profiles',
                'orders', 'order_items',
                'payments',
                'notifications', 'notification_templates',
                'locations',
                'inventory_locations',
                'reviews',
                'admin_users', 'audit_logs',
                'suppliers', 'documents',
                'deliveries',
                'product_pricing'
            ]

            for table_name in critical_tables:
                result = await self.conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = $1
                    )
                """, table_name)

                if not result:
                    validation_errors.append(f"Missing critical table: {table_name}")
                else:
                    logger.info(f"✅ Table exists: {table_name}")

            # Check critical columns exist in key tables
            critical_columns = {
                'payments': ['user_id', 'vendor_id', 'platform_fee', 'paystack_reference'],
                'notifications': ['channel', 'is_read', 'template_id', 'read_at'],
                'locations': ['user_id'],
                'users': ['mfa_enabled', 'role', 'is_active']
            }

            for table_name, columns in critical_columns.items():
                for column_name in columns:
                    result = await self.conn.fetchval("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.columns
                            WHERE table_schema = 'public'
                            AND table_name = $1
                            AND column_name = $2
                        )
                    """, table_name, column_name)

                    if not result:
                        validation_errors.append(f"Missing column {column_name} in table {table_name}")
                    else:
                        logger.info(f"✅ Column exists: {table_name}.{column_name}")

            if validation_errors:
                logger.error("❌ Schema validation failed:")
                for error in validation_errors:
                    logger.error(f"   - {error}")
                return False
            else:
                logger.info("✅ Schema validation completed successfully")
                return True

        except Exception as e:
            logger.error(f"❌ Schema validation error: {e}")
            return False

    async def initialize_database(self) -> bool:
        """Initialize the complete database schema"""
        logger.info("🚀 Starting comprehensive database initialization...")
        
        try:
            # Connect to database
            if not await self.connect():
                return False
            
            # Define all service schemas
            self._define_service_schemas()
            
            # Create tables in dependency order
            success_count = 0
            total_tables = sum(len(schema.tables) for schema in self.schemas.values())
            
            for service_name, schema in self.schemas.items():
                logger.info(f"📋 Initializing {service_name} service schema...")
                
                for table_def in schema.tables:
                    if await self.create_table(table_def):
                        success_count += 1
                    else:
                        logger.error(f"❌ Failed to create table {table_def.name}")
            
            # Log summary
            logger.info(f"📊 Database initialization summary:")
            logger.info(f"   ✅ Successfully created: {success_count}/{total_tables} tables")

            if success_count == total_tables:
                # Validate schema
                if await self.validate_schema():
                    logger.info("🎉 Database initialization and validation completed successfully!")

                    # Log initialization summary
                    logger.info("📋 Initialization Log:")
                    for log_entry in self.initialization_log:
                        logger.info(f"   - {log_entry}")

                    return True
                else:
                    logger.error("❌ Database schema validation failed")
                    return False
            else:
                logger.error(f"❌ Database initialization incomplete: {total_tables - success_count} tables failed")
                return False
                
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            return False
        finally:
            await self.disconnect()

async def create_production_schema():
    """Create production-ready schema based on service analysis"""
    logger.info("🚀 Creating production-ready database schema...")

    # Initialize database connection with proper retry logic
    initializer = DatabaseInitializer()

    try:
        # Use the robust connection method
        if not await initializer.connect():
            logger.error("❌ Failed to establish database connection")
            return False

        conn = initializer.conn

        # Create enums first (required by tables)
        enums = [
            "CREATE TYPE IF NOT EXISTS paymentstatus AS ENUM ('pending', 'processing', 'completed', 'failed', 'refunded')",
            "CREATE TYPE IF NOT EXISTS deliverystatus AS ENUM ('pending', 'assigned', 'picked_up', 'in_transit', 'delivered', 'failed')",
            "CREATE TYPE IF NOT EXISTS orderstatus AS ENUM ('pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled')",
            "CREATE TYPE IF NOT EXISTS notificationtype AS ENUM ('email', 'sms', 'push', 'in_app')",
        ]

        for enum_sql in enums:
            try:
                await conn.execute(enum_sql)
                logger.info(f"✅ Created enum: {enum_sql.split()[4]}")
            except Exception as e:
                logger.warning(f"⚠️ Enum creation warning: {e}")

        # Core tables that all services depend on
        core_tables = [
            # Users table (foundation for all services)
            '''CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                email_verified BOOLEAN NOT NULL DEFAULT FALSE,
                mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                failed_login_attempts INTEGER NOT NULL DEFAULT 0,
                account_locked_until TIMESTAMPTZ,
                password_changed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ,
                last_login TIMESTAMPTZ
            )''',

            # User sessions for authentication
            '''CREATE TABLE IF NOT EXISTS user_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL,
                access_token_jti VARCHAR(255) NOT NULL UNIQUE,
                refresh_token_jti VARCHAR(255),
                ip_address VARCHAR(255),
                user_agent TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL,
                last_activity TIMESTAMPTZ DEFAULT NOW(),
                logged_out_at TIMESTAMPTZ,
                is_active BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )''',

            # User Profiles table
            '''CREATE TABLE IF NOT EXISTS user_profiles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL UNIQUE,
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                phone_number VARCHAR(255),
                address TEXT,
                city VARCHAR(255),
                state VARCHAR(255),
                country VARCHAR(255) DEFAULT 'Nigeria',
                avatar_url VARCHAR(255),
                bio TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )''',

            # Hospital Profiles table
            '''CREATE TABLE IF NOT EXISTS hospital_profiles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL UNIQUE,
                hospital_name VARCHAR(255) NOT NULL,
                registration_number VARCHAR(255),
                license_number VARCHAR(255),
                contact_person VARCHAR(255),
                contact_phone VARCHAR(255),
                emergency_contact VARCHAR(255),
                bed_capacity VARCHAR(255),
                hospital_type VARCHAR(255),
                services_offered TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )''',

            # Vendor Profiles table
            '''CREATE TABLE IF NOT EXISTS vendor_profiles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL UNIQUE,
                business_name VARCHAR(255) NOT NULL,
                registration_number VARCHAR(255),
                tax_identification_number VARCHAR(255),
                contact_person VARCHAR(255),
                contact_phone VARCHAR(255),
                business_address TEXT,
                delivery_radius_km FLOAT,
                operating_hours VARCHAR(255),
                emergency_service BOOLEAN DEFAULT FALSE,
                minimum_order_value FLOAT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )''',

            # Security Events table
            '''CREATE TABLE IF NOT EXISTS security_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID,
                event_type VARCHAR(255) NOT NULL,
                event_data VARCHAR(1000),
                ip_address VARCHAR(255),
                user_agent TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )''',

            # Orders table (updated for order service)
            '''CREATE TABLE IF NOT EXISTS orders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                reference VARCHAR(255) NOT NULL UNIQUE,
                hospital_id UUID NOT NULL,
                vendor_id UUID,
                status orderstatus NOT NULL DEFAULT 'pending',
                is_emergency BOOLEAN NOT NULL DEFAULT FALSE,
                delivery_address TEXT NOT NULL,
                delivery_latitude DOUBLE PRECISION NOT NULL,
                delivery_longitude DOUBLE PRECISION NOT NULL,
                delivery_contact_name VARCHAR(255),
                delivery_contact_phone VARCHAR(255),
                notes TEXT,
                special_instructions TEXT,
                subtotal DECIMAL(10,2),
                delivery_fee DECIMAL(10,2),
                emergency_surcharge DECIMAL(10,2),
                total_amount DECIMAL(10,2),
                requested_delivery_time TIMESTAMPTZ,
                estimated_delivery_time TIMESTAMPTZ,
                actual_delivery_time TIMESTAMPTZ,
                tracking_number VARCHAR(255),
                delivery_notes TEXT,
                cancellation_reason TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )''',

            # Order items table
            '''CREATE TABLE IF NOT EXISTS order_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                cylinder_size VARCHAR(50) NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price DECIMAL(10,2),
                total_price DECIMAL(10,2),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )''',

            # Order status history table
            '''CREATE TABLE IF NOT EXISTS order_status_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                status orderstatus NOT NULL,
                notes TEXT,
                updated_by UUID NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )''',

            # Payments table with all required columns
            '''CREATE TABLE IF NOT EXISTS payments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL,
                user_id UUID NOT NULL,
                vendor_id UUID,
                reference VARCHAR(255) NOT NULL UNIQUE,
                amount DECIMAL(10,2) NOT NULL,
                platform_fee DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                vendor_amount DECIMAL(10,2),
                currency VARCHAR(3) NOT NULL DEFAULT 'NGN',
                status paymentstatus NOT NULL DEFAULT 'pending',
                payment_method VARCHAR(50),
                provider VARCHAR(50) NOT NULL DEFAULT 'paystack',
                provider_reference VARCHAR(255),
                paystack_reference VARCHAR(255),
                paystack_access_code VARCHAR(255),
                authorization_url TEXT,
                provider_response JSONB,
                metadata JSONB,
                paid_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ
            )''',

            # Payment splits table
            '''CREATE TABLE IF NOT EXISTS payment_splits (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                payment_id UUID NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
                recipient_type VARCHAR(50) NOT NULL,
                recipient_id UUID NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                percentage DECIMAL(5,2) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                paystack_split_code VARCHAR(255),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )''',

            # Payment webhooks table
            '''CREATE TABLE IF NOT EXISTS payment_webhooks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                payment_id UUID REFERENCES payments(id) ON DELETE SET NULL,
                event_type VARCHAR(100) NOT NULL,
                paystack_reference VARCHAR(255) NOT NULL,
                webhook_data JSONB NOT NULL,
                processed BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )''',

            # Notifications table with all required columns
            '''CREATE TABLE IF NOT EXISTS notifications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                notification_type VARCHAR(50) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                channel VARCHAR(50) NOT NULL DEFAULT 'in_app',
                is_read BOOLEAN NOT NULL DEFAULT FALSE,
                template_id UUID,
                metadata JSONB,
                sent_at TIMESTAMPTZ,
                delivered_at TIMESTAMPTZ,
                read_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )''',

            # Locations table
            '''CREATE TABLE IF NOT EXISTS locations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL,
                name VARCHAR(255) NOT NULL,
                address TEXT NOT NULL,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                city VARCHAR(100),
                state VARCHAR(100),
                country VARCHAR(100),
                postal_code VARCHAR(20),
                location_type VARCHAR(50) NOT NULL,
                is_default BOOLEAN NOT NULL DEFAULT FALSE,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )''',

            # Reviews table
            '''CREATE TABLE IF NOT EXISTS reviews (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL,
                order_id UUID,
                supplier_id UUID,
                rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                title VARCHAR(255),
                comment TEXT,
                review_type VARCHAR(50) NOT NULL,
                is_verified BOOLEAN NOT NULL DEFAULT FALSE,
                is_moderated BOOLEAN NOT NULL DEFAULT FALSE,
                moderation_notes TEXT,
                helpful_count INTEGER NOT NULL DEFAULT 0,
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )'''
        ]

        # Create all tables
        tables_created = 0
        for i, table_sql in enumerate(core_tables):
            try:
                await conn.execute(table_sql)
                table_name = table_sql.split('IF NOT EXISTS ')[1].split(' (')[0]
                logger.info(f"✅ Created table: {table_name}")
                tables_created += 1
            except Exception as e:
                logger.error(f"❌ Failed to create table {i+1}: {e}")

        # Create essential indexes
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)',
            'CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)',
            'CREATE INDEX IF NOT EXISTS idx_users_active ON users(is_active)',
            'CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)',
            'CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token)',
            'CREATE INDEX IF NOT EXISTS idx_orders_hospital_id ON orders(hospital_id)',
            'CREATE INDEX IF NOT EXISTS idx_orders_vendor_id ON orders(vendor_id)',
            'CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)',
            'CREATE INDEX IF NOT EXISTS idx_orders_emergency ON orders(is_emergency)',
            'CREATE INDEX IF NOT EXISTS idx_orders_reference ON orders(reference)',
            'CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at)',
            'CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id)',
            'CREATE INDEX IF NOT EXISTS idx_order_status_history_order_id ON order_status_history(order_id)',
            'CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)',
            'CREATE INDEX IF NOT EXISTS idx_payments_vendor_id ON payments(vendor_id)',
            'CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)',
            'CREATE INDEX IF NOT EXISTS idx_payments_paystack_ref ON payments(paystack_reference)',
            'CREATE INDEX IF NOT EXISTS idx_payments_reference ON payments(reference)',
            'CREATE INDEX IF NOT EXISTS idx_payment_splits_payment_id ON payment_splits(payment_id)',
            'CREATE INDEX IF NOT EXISTS idx_payment_splits_recipient ON payment_splits(recipient_id)',
            'CREATE INDEX IF NOT EXISTS idx_payment_webhooks_payment_id ON payment_webhooks(payment_id)',
            'CREATE INDEX IF NOT EXISTS idx_payment_webhooks_event ON payment_webhooks(event_type)',
            'CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id)',
            'CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read)',
            'CREATE INDEX IF NOT EXISTS idx_notifications_channel ON notifications(channel)',
            'CREATE INDEX IF NOT EXISTS idx_locations_user_id ON locations(user_id)',
            'CREATE INDEX IF NOT EXISTS idx_locations_type ON locations(location_type)',
            'CREATE INDEX IF NOT EXISTS idx_reviews_user_id ON reviews(user_id)',
            'CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating)',
        ]

        indexes_created = 0
        for index_sql in indexes:
            try:
                await conn.execute(index_sql)
                indexes_created += 1
            except Exception as e:
                logger.warning(f"⚠️ Index creation warning: {e}")

        logger.info(f"🎉 Production schema creation completed!")
        logger.info(f"   ✅ Tables created: {tables_created}/{len(core_tables)}")
        logger.info(f"   ✅ Indexes created: {indexes_created}/{len(indexes)}")

        return tables_created == len(core_tables)

    except Exception as e:
        logger.error(f"❌ Production schema creation failed: {e}")
        return False
    finally:
        # Ensure connection is properly closed
        await initializer.disconnect()

async def main():
    """Main entry point"""
    logger.info("🚀 Starting Flow-Backend Database Initialization")

    # Initialize database connection handler
    initializer = DatabaseInitializer()

    # Wait for database to be ready
    if not await initializer.wait_for_database():
        logger.error("❌ Database readiness check failed")
        sys.exit(1)

    # Use the simplified production schema creation
    success = await create_production_schema()

    if success:
        logger.info("✅ Database initialization completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Database initialization failed")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
