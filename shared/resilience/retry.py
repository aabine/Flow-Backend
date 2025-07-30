"""
Retry Logic with Exponential Backoff for Flow-Backend Services
Provides resilient retry mechanisms for transient failures
"""

import asyncio
import random
import time
from typing import Callable, Any, Optional, List, Type, Union
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3                    # Maximum number of retry attempts
    base_delay: float = 1.0                  # Base delay in seconds
    max_delay: float = 60.0                  # Maximum delay in seconds
    exponential_base: float = 2.0            # Exponential backoff base
    jitter: bool = True                      # Add random jitter to delays
    retryable_exceptions: List[Type[Exception]] = None  # Exceptions that trigger retry
    non_retryable_exceptions: List[Type[Exception]] = None  # Exceptions that don't trigger retry


class RetryExhaustedError(Exception):
    """Exception raised when all retry attempts are exhausted."""
    
    def __init__(self, attempts: int, last_exception: Exception):
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(f"Retry exhausted after {attempts} attempts. Last error: {str(last_exception)}")


class RetryHandler:
    """Handles retry logic with various backoff strategies."""
    
    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
        
        # Default retryable exceptions (transient errors)
        if self.config.retryable_exceptions is None:
            self.config.retryable_exceptions = [
                ConnectionError,
                TimeoutError,
                asyncio.TimeoutError,
                OSError,  # Network-related errors
            ]
        
        # Default non-retryable exceptions (permanent errors)
        if self.config.non_retryable_exceptions is None:
            self.config.non_retryable_exceptions = [
                ValueError,
                TypeError,
                KeyError,
                AttributeError,
                PermissionError,
            ]
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with retry logic."""
        last_exception = None
        
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                # Log retry attempt
                if attempt > 1:
                    logger.info(
                        f"Retry attempt {attempt}/{self.config.max_attempts}",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt,
                            "max_attempts": self.config.max_attempts,
                            "last_error": str(last_exception) if last_exception else None
                        }
                    )
                
                # Execute the function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    # Run sync function in thread pool
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, lambda: func(*args, **kwargs))
                
                # Success - log if this was a retry
                if attempt > 1:
                    logger.info(
                        f"Function succeeded on retry attempt {attempt}",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt,
                            "total_attempts": attempt
                        }
                    )
                
                return result
                
            except Exception as e:
                last_exception = e
                
                # Check if this exception should trigger a retry
                if not self._should_retry(e):
                    logger.info(
                        f"Non-retryable exception, not retrying: {type(e).__name__}",
                        extra={
                            "function": func.__name__,
                            "exception": type(e).__name__,
                            "error": str(e),
                            "attempt": attempt
                        }
                    )
                    raise e
                
                # If this is the last attempt, raise the exception
                if attempt >= self.config.max_attempts:
                    logger.error(
                        f"All retry attempts exhausted for function {func.__name__}",
                        extra={
                            "function": func.__name__,
                            "total_attempts": attempt,
                            "final_error": str(e)
                        }
                    )
                    raise RetryExhaustedError(attempt, e)
                
                # Calculate delay for next attempt
                delay = self._calculate_delay(attempt)
                
                logger.warning(
                    f"Function failed, retrying in {delay:.2f}s",
                    extra={
                        "function": func.__name__,
                        "attempt": attempt,
                        "max_attempts": self.config.max_attempts,
                        "delay_seconds": delay,
                        "exception": type(e).__name__,
                        "error": str(e)
                    }
                )
                
                # Wait before retry
                await asyncio.sleep(delay)
        
        # This should never be reached, but just in case
        raise RetryExhaustedError(self.config.max_attempts, last_exception)
    
    def _should_retry(self, exception: Exception) -> bool:
        """Determine if an exception should trigger a retry."""
        # Check non-retryable exceptions first
        for non_retryable in self.config.non_retryable_exceptions:
            if isinstance(exception, non_retryable):
                return False
        
        # Check retryable exceptions
        for retryable in self.config.retryable_exceptions:
            if isinstance(exception, retryable):
                return True
        
        # Default: don't retry unknown exceptions
        return False
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt using exponential backoff."""
        # Calculate exponential delay
        delay = self.config.base_delay * (self.config.exponential_base ** (attempt - 1))
        
        # Apply maximum delay limit
        delay = min(delay, self.config.max_delay)
        
        # Add jitter to prevent thundering herd
        if self.config.jitter:
            # Add random jitter up to 25% of the delay
            jitter_amount = delay * 0.25
            delay += random.uniform(-jitter_amount, jitter_amount)
            delay = max(0, delay)  # Ensure delay is not negative
        
        return delay


class RetryWithCircuitBreaker:
    """Combines retry logic with circuit breaker pattern."""
    
    def __init__(self, retry_config: RetryConfig = None, circuit_breaker = None):
        self.retry_handler = RetryHandler(retry_config)
        self.circuit_breaker = circuit_breaker
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with both retry and circuit breaker protection."""
        if self.circuit_breaker:
            # Use circuit breaker with retry
            return await self.retry_handler.execute(
                self.circuit_breaker.call, func, *args, **kwargs
            )
        else:
            # Use retry only
            return await self.retry_handler.execute(func, *args, **kwargs)


def retry(config: RetryConfig = None):
    """Decorator for applying retry logic to functions."""
    retry_handler = RetryHandler(config)
    
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            return await retry_handler.execute(func, *args, **kwargs)
        return wrapper
    return decorator


def retry_with_exponential_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: List[Type[Exception]] = None
):
    """Convenience decorator for exponential backoff retry."""
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter=jitter,
        retryable_exceptions=retryable_exceptions
    )
    return retry(config)


# Predefined retry configurations for common scenarios
class RetryConfigs:
    """Predefined retry configurations for common use cases."""
    
    # Quick retry for fast operations
    QUICK = RetryConfig(
        max_attempts=3,
        base_delay=0.1,
        max_delay=1.0,
        exponential_base=2.0
    )
    
    # Standard retry for normal operations
    STANDARD = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=10.0,
        exponential_base=2.0
    )
    
    # Aggressive retry for critical operations
    AGGRESSIVE = RetryConfig(
        max_attempts=5,
        base_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0
    )
    
    # Database operations
    DATABASE = RetryConfig(
        max_attempts=3,
        base_delay=0.5,
        max_delay=5.0,
        exponential_base=2.0,
        retryable_exceptions=[
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError,
            OSError
        ]
    )
    
    # HTTP requests
    HTTP = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=15.0,
        exponential_base=2.0,
        retryable_exceptions=[
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError,
            OSError
        ]
    )
    
    # File operations
    FILE_IO = RetryConfig(
        max_attempts=3,
        base_delay=0.1,
        max_delay=2.0,
        exponential_base=2.0,
        retryable_exceptions=[
            OSError,
            IOError,
            PermissionError
        ],
        non_retryable_exceptions=[
            FileNotFoundError,
            IsADirectoryError
        ]
    )
