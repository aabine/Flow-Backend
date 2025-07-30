"""
Circuit Breaker Pattern Implementation for Flow-Backend Services
Provides fault tolerance and prevents cascade failures in service-to-service communication
"""

import asyncio
import time
from typing import Callable, Any, Optional, Dict
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, requests fail fast
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5          # Number of failures to open circuit
    recovery_timeout: int = 60          # Seconds to wait before trying half-open
    success_threshold: int = 3          # Successes needed to close from half-open
    timeout: float = 30.0               # Request timeout in seconds
    expected_exception: type = Exception  # Exception type that counts as failure


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """Circuit breaker implementation with async support."""
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        # State management
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
        
        # Statistics
        self.total_requests = 0
        self.total_failures = 0
        self.total_successes = 0
        self.total_timeouts = 0
        self.total_circuit_open_rejections = 0
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            self.total_requests += 1
            
            # Check if circuit should transition states
            await self._check_state_transition()
            
            # If circuit is open, fail fast
            if self.state == CircuitState.OPEN:
                self.total_circuit_open_rejections += 1
                logger.warning(
                    f"Circuit breaker {self.name} is OPEN, rejecting request",
                    extra={
                        "circuit_breaker": self.name,
                        "state": self.state.value,
                        "failure_count": self.failure_count,
                        "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None
                    }
                )
                raise CircuitBreakerError(f"Circuit breaker {self.name} is OPEN")
        
        # Execute the function with timeout
        try:
            result = await asyncio.wait_for(
                self._execute_function(func, *args, **kwargs),
                timeout=self.config.timeout
            )
            
            # Record success
            await self._record_success()
            return result
            
        except asyncio.TimeoutError:
            await self._record_failure("timeout")
            self.total_timeouts += 1
            raise
        except self.config.expected_exception as e:
            await self._record_failure("exception", str(e))
            raise
        except Exception as e:
            # Unexpected exceptions don't count as circuit breaker failures
            logger.error(f"Unexpected error in circuit breaker {self.name}: {str(e)}")
            raise
    
    async def _execute_function(self, func: Callable, *args, **kwargs) -> Any:
        """Execute the function, handling both sync and async functions."""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            # Run sync function in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
    
    async def _check_state_transition(self):
        """Check if circuit breaker should transition states."""
        now = datetime.utcnow()
        
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if (self.last_failure_time and 
                now - self.last_failure_time >= timedelta(seconds=self.config.recovery_timeout)):
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info(
                    f"Circuit breaker {self.name} transitioning to HALF_OPEN",
                    extra={
                        "circuit_breaker": self.name,
                        "state": self.state.value,
                        "recovery_timeout": self.config.recovery_timeout
                    }
                )
        
        elif self.state == CircuitState.HALF_OPEN:
            # Check if enough successes to close circuit
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info(
                    f"Circuit breaker {self.name} transitioning to CLOSED",
                    extra={
                        "circuit_breaker": self.name,
                        "state": self.state.value,
                        "success_threshold": self.config.success_threshold
                    }
                )
    
    async def _record_success(self):
        """Record a successful operation."""
        async with self._lock:
            self.total_successes += 1
            self.last_success_time = datetime.utcnow()
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success
                self.failure_count = 0
    
    async def _record_failure(self, failure_type: str, error_message: str = None):
        """Record a failed operation."""
        async with self._lock:
            self.total_failures += 1
            self.failure_count += 1
            self.last_failure_time = datetime.utcnow()
            
            logger.warning(
                f"Circuit breaker {self.name} recorded failure",
                extra={
                    "circuit_breaker": self.name,
                    "failure_type": failure_type,
                    "failure_count": self.failure_count,
                    "error_message": error_message,
                    "state": self.state.value
                }
            )
            
            # Check if we should open the circuit
            if (self.state in [CircuitState.CLOSED, CircuitState.HALF_OPEN] and 
                self.failure_count >= self.config.failure_threshold):
                
                self.state = CircuitState.OPEN
                self.success_count = 0
                
                logger.error(
                    f"Circuit breaker {self.name} OPENED due to failures",
                    extra={
                        "circuit_breaker": self.name,
                        "state": self.state.value,
                        "failure_count": self.failure_count,
                        "failure_threshold": self.config.failure_threshold
                    }
                )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "success_threshold": self.config.success_threshold,
                "timeout": self.config.timeout
            },
            "statistics": {
                "total_requests": self.total_requests,
                "total_failures": self.total_failures,
                "total_successes": self.total_successes,
                "total_timeouts": self.total_timeouts,
                "total_circuit_open_rejections": self.total_circuit_open_rejections,
                "failure_rate": (self.total_failures / self.total_requests * 100) if self.total_requests > 0 else 0,
                "success_rate": (self.total_successes / self.total_requests * 100) if self.total_requests > 0 else 0
            }
        }
    
    async def reset(self):
        """Reset circuit breaker to closed state."""
        async with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
            
            logger.info(
                f"Circuit breaker {self.name} manually reset",
                extra={
                    "circuit_breaker": self.name,
                    "state": self.state.value
                }
            )


class CircuitBreakerManager:
    """Manages multiple circuit breakers."""
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.default_config = CircuitBreakerConfig()
    
    def get_circuit_breaker(self, name: str, config: CircuitBreakerConfig = None) -> CircuitBreaker:
        """Get or create a circuit breaker."""
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(
                name=name,
                config=config or self.default_config
            )
        return self.circuit_breakers[name]
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        return {name: cb.get_stats() for name, cb in self.circuit_breakers.items()}
    
    async def reset_all(self):
        """Reset all circuit breakers."""
        for circuit_breaker in self.circuit_breakers.values():
            await circuit_breaker.reset()


# Global circuit breaker manager
circuit_breaker_manager = CircuitBreakerManager()


def circuit_breaker(name: str, config: CircuitBreakerConfig = None):
    """Decorator for applying circuit breaker to functions."""
    def decorator(func: Callable):
        cb = circuit_breaker_manager.get_circuit_breaker(name, config)
        
        async def wrapper(*args, **kwargs):
            return await cb.call(func, *args, **kwargs)
        
        return wrapper
    return decorator
