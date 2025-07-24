"""
Secure database configuration and utilities for the Oxygen Supply Platform.
Implements encrypted connections, query parameterization, audit logging, and security best practices.
"""

import os
import ssl
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.engine import Engine
from datetime import datetime
import json
import hashlib
import secrets

from .encryption import encryption_manager, data_masking

logger = logging.getLogger(__name__)


class SecureDatabaseConfig:
    """Secure database configuration with encryption and security features."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.environment = os.getenv("ENVIRONMENT", "development")
        
        # Database connection parameters
        self.db_host = os.getenv("DB_HOST", "localhost")
        self.db_port = os.getenv("DB_PORT", "5432")
        self.db_name = os.getenv("DB_NAME", f"{service_name}_db")
        self.db_user = os.getenv("DB_USER", f"{service_name}_user")
        self.db_password = os.getenv("DB_PASSWORD", "")
        
        # SSL Configuration
        self.ssl_mode = os.getenv("DB_SSL_MODE", "require" if self.environment == "production" else "prefer")
        self.ssl_cert_path = os.getenv("DB_SSL_CERT_PATH")
        self.ssl_key_path = os.getenv("DB_SSL_KEY_PATH")
        self.ssl_ca_path = os.getenv("DB_SSL_CA_PATH")
        
        # Connection pool settings
        self.pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
        self.max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
        self.pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
        self.pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # 1 hour
        
        # Security settings
        self.enable_audit_logging = os.getenv("DB_AUDIT_LOGGING", "true").lower() == "true"
        self.enable_query_logging = os.getenv("DB_QUERY_LOGGING", "false").lower() == "true"
        self.enable_slow_query_logging = os.getenv("DB_SLOW_QUERY_LOGGING", "true").lower() == "true"
        self.slow_query_threshold = float(os.getenv("DB_SLOW_QUERY_THRESHOLD", "1.0"))  # seconds
    
    def get_database_url(self, async_driver: bool = True) -> str:
        """Generate secure database URL with SSL configuration."""
        
        # Choose driver
        if async_driver:
            driver = "postgresql+asyncpg"
        else:
            driver = "postgresql+psycopg2"
        
        # Build base URL
        url = f"{driver}://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        
        # Add SSL parameters
        ssl_params = []
        
        if self.ssl_mode:
            ssl_params.append(f"sslmode={self.ssl_mode}")
        
        if self.ssl_cert_path:
            ssl_params.append(f"sslcert={self.ssl_cert_path}")
        
        if self.ssl_key_path:
            ssl_params.append(f"sslkey={self.ssl_key_path}")
        
        if self.ssl_ca_path:
            ssl_params.append(f"sslrootcert={self.ssl_ca_path}")
        
        # Add connection parameters
        connection_params = [
            "connect_timeout=10",
            "command_timeout=30",
            "server_settings=application_name=" + self.service_name
        ]
        
        all_params = ssl_params + connection_params
        
        if all_params:
            url += "?" + "&".join(all_params)
        
        return url
    
    def get_engine_kwargs(self) -> Dict[str, Any]:
        """Get engine configuration with security settings."""
        
        kwargs = {
            "poolclass": QueuePool,
            "pool_size": self.pool_size,
            "max_overflow": self.max_overflow,
            "pool_timeout": self.pool_timeout,
            "pool_recycle": self.pool_recycle,
            "pool_pre_ping": True,  # Validate connections before use
            "echo": self.enable_query_logging,
            "echo_pool": False,  # Don't log pool events in production
        }
        
        # Add SSL context for synchronous connections
        if not self.get_database_url().startswith("postgresql+asyncpg"):
            ssl_context = self._create_ssl_context()
            if ssl_context:
                kwargs["connect_args"] = {"sslcontext": ssl_context}
        
        return kwargs
    
    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Create SSL context for database connections."""
        
        if self.ssl_mode in ["disable", "allow"]:
            return None
        
        try:
            context = ssl.create_default_context()
            
            # Configure SSL verification
            if self.ssl_mode == "require":
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            elif self.ssl_mode in ["verify-ca", "verify-full"]:
                context.verify_mode = ssl.CERT_REQUIRED
                if self.ssl_ca_path:
                    context.load_verify_locations(self.ssl_ca_path)
            
            # Load client certificate if provided
            if self.ssl_cert_path and self.ssl_key_path:
                context.load_cert_chain(self.ssl_cert_path, self.ssl_key_path)
            
            return context
            
        except Exception as e:
            logger.error(f"Failed to create SSL context: {str(e)}")
            return None


class DatabaseAuditor:
    """Database audit logging for security monitoring."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.audit_logger = logging.getLogger(f"{service_name}.audit")
        
        # Configure audit logger
        if not self.audit_logger.handlers:
            handler = logging.FileHandler(f"/var/log/{service_name}/audit.log")
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.audit_logger.addHandler(handler)
            self.audit_logger.setLevel(logging.INFO)
    
    def log_query(
        self,
        query: str,
        parameters: Dict[str, Any] = None,
        user_id: str = None,
        execution_time: float = None,
        row_count: int = None
    ):
        """Log database query for audit purposes."""
        
        # Mask sensitive data in query and parameters
        masked_query = self._mask_sensitive_query(query)
        masked_params = data_masking.mask_sensitive_dict(parameters or {})
        
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": self.service_name,
            "user_id": user_id,
            "query": masked_query,
            "parameters": masked_params,
            "execution_time_ms": round(execution_time * 1000, 2) if execution_time else None,
            "row_count": row_count,
            "query_hash": hashlib.sha256(query.encode()).hexdigest()[:16]
        }
        
        self.audit_logger.info(json.dumps(audit_entry))
    
    def log_connection_event(self, event_type: str, details: Dict[str, Any]):
        """Log database connection events."""
        
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": self.service_name,
            "event_type": f"db_connection_{event_type}",
            "details": details
        }
        
        self.audit_logger.info(json.dumps(audit_entry))
    
    def log_security_event(self, event_type: str, details: Dict[str, Any]):
        """Log database security events."""
        
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": self.service_name,
            "event_type": f"db_security_{event_type}",
            "details": details,
            "severity": "HIGH"
        }
        
        self.audit_logger.warning(json.dumps(audit_entry))
    
    def _mask_sensitive_query(self, query: str) -> str:
        """Mask sensitive data in SQL queries."""
        
        # List of sensitive patterns to mask
        sensitive_patterns = [
            (r"password\s*=\s*'[^']*'", "password='***'"),
            (r"password\s*=\s*\"[^\"]*\"", "password=\"***\""),
            (r"token\s*=\s*'[^']*'", "token='***'"),
            (r"secret\s*=\s*'[^']*'", "secret='***'"),
            (r"key\s*=\s*'[^']*'", "key='***'"),
        ]
        
        masked_query = query
        for pattern, replacement in sensitive_patterns:
            import re
            masked_query = re.sub(pattern, replacement, masked_query, flags=re.IGNORECASE)
        
        return masked_query


class SecureQueryBuilder:
    """Secure query builder with parameterization and validation."""
    
    @staticmethod
    def build_select_query(
        table: str,
        columns: List[str] = None,
        where_conditions: Dict[str, Any] = None,
        order_by: str = None,
        limit: int = None,
        offset: int = None
    ) -> tuple:
        """Build a secure SELECT query with parameterization."""
        
        # Validate table name
        if not SecureQueryBuilder._is_valid_identifier(table):
            raise ValueError(f"Invalid table name: {table}")
        
        # Build column list
        if columns:
            # Validate column names
            for col in columns:
                if not SecureQueryBuilder._is_valid_identifier(col):
                    raise ValueError(f"Invalid column name: {col}")
            column_list = ", ".join(columns)
        else:
            column_list = "*"
        
        # Start building query
        query = f"SELECT {column_list} FROM {table}"
        params = {}
        
        # Add WHERE conditions
        if where_conditions:
            where_clauses = []
            for i, (column, value) in enumerate(where_conditions.items()):
                if not SecureQueryBuilder._is_valid_identifier(column):
                    raise ValueError(f"Invalid column name in WHERE: {column}")
                
                param_name = f"param_{i}"
                where_clauses.append(f"{column} = :{param_name}")
                params[param_name] = value
            
            query += " WHERE " + " AND ".join(where_clauses)
        
        # Add ORDER BY
        if order_by:
            if not SecureQueryBuilder._is_valid_identifier(order_by.split()[0]):
                raise ValueError(f"Invalid ORDER BY column: {order_by}")
            query += f" ORDER BY {order_by}"
        
        # Add LIMIT and OFFSET
        if limit:
            query += f" LIMIT {int(limit)}"
        
        if offset:
            query += f" OFFSET {int(offset)}"
        
        return query, params
    
    @staticmethod
    def build_insert_query(
        table: str,
        data: Dict[str, Any],
        returning: List[str] = None
    ) -> tuple:
        """Build a secure INSERT query with parameterization."""
        
        # Validate table name
        if not SecureQueryBuilder._is_valid_identifier(table):
            raise ValueError(f"Invalid table name: {table}")
        
        if not data:
            raise ValueError("No data provided for INSERT")
        
        # Validate column names
        for column in data.keys():
            if not SecureQueryBuilder._is_valid_identifier(column):
                raise ValueError(f"Invalid column name: {column}")
        
        columns = list(data.keys())
        placeholders = [f":{col}" for col in columns]
        
        query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        
        # Add RETURNING clause
        if returning:
            for col in returning:
                if not SecureQueryBuilder._is_valid_identifier(col):
                    raise ValueError(f"Invalid RETURNING column: {col}")
            query += f" RETURNING {', '.join(returning)}"
        
        return query, data
    
    @staticmethod
    def _is_valid_identifier(identifier: str) -> bool:
        """Validate SQL identifier to prevent injection."""
        
        if not identifier:
            return False
        
        # Check for basic SQL injection patterns
        dangerous_patterns = [
            ';', '--', '/*', '*/', 'xp_', 'sp_', 'exec', 'execute',
            'union', 'select', 'insert', 'update', 'delete', 'drop',
            'create', 'alter', 'truncate'
        ]
        
        identifier_lower = identifier.lower()
        for pattern in dangerous_patterns:
            if pattern in identifier_lower:
                return False
        
        # Check if it's a valid identifier (alphanumeric + underscore, starts with letter)
        import re
        return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', identifier))


def setup_database_security_events(engine: Engine, auditor: DatabaseAuditor):
    """Set up database security event listeners."""
    
    @event.listens_for(engine, "connect")
    def on_connect(dbapi_connection, connection_record):
        """Handle new database connections."""
        auditor.log_connection_event("established", {
            "connection_id": id(dbapi_connection),
            "pid": os.getpid()
        })
    
    @event.listens_for(engine, "checkout")
    def on_checkout(dbapi_connection, connection_record, connection_proxy):
        """Handle connection checkout from pool."""
        auditor.log_connection_event("checkout", {
            "connection_id": id(dbapi_connection),
            "pool_size": engine.pool.size(),
            "checked_out": engine.pool.checkedout()
        })
    
    @event.listens_for(engine, "checkin")
    def on_checkin(dbapi_connection, connection_record):
        """Handle connection checkin to pool."""
        auditor.log_connection_event("checkin", {
            "connection_id": id(dbapi_connection),
            "pool_size": engine.pool.size(),
            "checked_out": engine.pool.checkedout()
        })


# Global instances for easy import
def create_secure_engine(service_name: str, async_engine: bool = True):
    """Create a secure database engine with all security features enabled."""
    
    config = SecureDatabaseConfig(service_name)
    auditor = DatabaseAuditor(service_name)
    
    database_url = config.get_database_url(async_driver=async_engine)
    engine_kwargs = config.get_engine_kwargs()
    
    if async_engine:
        engine = create_async_engine(database_url, **engine_kwargs)
    else:
        engine = create_engine(database_url, **engine_kwargs)
        setup_database_security_events(engine, auditor)
    
    logger.info(f"Created secure database engine for {service_name}")
    
    return engine, auditor
