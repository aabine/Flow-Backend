"""
Graceful Shutdown Handler for Flow-Backend Services
Ensures clean shutdown of services with proper resource cleanup
"""

import asyncio
import signal
import sys
from typing import List, Callable, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class GracefulShutdownHandler:
    """Handles graceful shutdown of services."""
    
    def __init__(self, service_name: str, shutdown_timeout: int = 30):
        self.service_name = service_name
        self.shutdown_timeout = shutdown_timeout
        self.shutdown_callbacks: List[Callable] = []
        self.is_shutting_down = False
        self.shutdown_event = asyncio.Event()
        
        # Register signal handlers
        self._register_signal_handlers()
    
    def _register_signal_handlers(self):
        """Register signal handlers for graceful shutdown."""
        if sys.platform != "win32":
            # Unix signals
            for sig in [signal.SIGTERM, signal.SIGINT]:
                signal.signal(sig, self._signal_handler)
        else:
            # Windows signals
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum: int, frame):
        """Handle shutdown signals."""
        signal_name = signal.Signals(signum).name
        logger.info(
            f"Received {signal_name} signal, initiating graceful shutdown",
            extra={
                "service": self.service_name,
                "signal": signal_name,
                "signal_number": signum
            }
        )
        
        # Set shutdown flag and event
        self.is_shutting_down = True
        
        # Schedule shutdown in the event loop
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        if loop:
            loop.create_task(self._shutdown())
    
    def register_shutdown_callback(self, callback: Callable, *args, **kwargs):
        """Register a callback to be called during shutdown."""
        async def wrapper():
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
                logger.info(f"Shutdown callback completed: {callback.__name__}")
            except Exception as e:
                logger.error(f"Error in shutdown callback {callback.__name__}: {str(e)}")
        
        self.shutdown_callbacks.append(wrapper)
        logger.info(f"Registered shutdown callback: {callback.__name__}")
    
    async def _shutdown(self):
        """Perform graceful shutdown."""
        if self.shutdown_event.is_set():
            return  # Already shutting down
        
        self.shutdown_event.set()
        shutdown_start = datetime.utcnow()
        
        logger.info(
            f"Starting graceful shutdown of {self.service_name}",
            extra={
                "service": self.service_name,
                "shutdown_timeout": self.shutdown_timeout,
                "registered_callbacks": len(self.shutdown_callbacks)
            }
        )
        
        try:
            # Execute shutdown callbacks with timeout
            if self.shutdown_callbacks:
                logger.info(f"Executing {len(self.shutdown_callbacks)} shutdown callbacks")
                
                # Run all callbacks concurrently with timeout
                await asyncio.wait_for(
                    asyncio.gather(*self.shutdown_callbacks, return_exceptions=True),
                    timeout=self.shutdown_timeout
                )
            
            shutdown_duration = (datetime.utcnow() - shutdown_start).total_seconds()
            logger.info(
                f"Graceful shutdown completed in {shutdown_duration:.2f}s",
                extra={
                    "service": self.service_name,
                    "shutdown_duration_seconds": shutdown_duration
                }
            )
            
        except asyncio.TimeoutError:
            logger.warning(
                f"Shutdown timeout exceeded ({self.shutdown_timeout}s), forcing shutdown",
                extra={
                    "service": self.service_name,
                    "shutdown_timeout": self.shutdown_timeout
                }
            )
        except Exception as e:
            logger.error(
                f"Error during graceful shutdown: {str(e)}",
                extra={
                    "service": self.service_name,
                    "error": str(e)
                }
            )
        finally:
            # Force exit
            logger.info(f"Exiting {self.service_name}")
            sys.exit(0)
    
    async def wait_for_shutdown(self):
        """Wait for shutdown signal."""
        await self.shutdown_event.wait()
    
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self.is_shutting_down


class ServiceLifecycleManager:
    """Manages the complete lifecycle of a service."""
    
    def __init__(self, service_name: str, shutdown_timeout: int = 30):
        self.service_name = service_name
        self.shutdown_handler = GracefulShutdownHandler(service_name, shutdown_timeout)
        self.startup_callbacks: List[Callable] = []
        self.health_check_callbacks: List[Callable] = []
        
    def register_startup_callback(self, callback: Callable, *args, **kwargs):
        """Register a callback to be called during startup."""
        async def wrapper():
            try:
                if asyncio.iscoroutinefunction(callback):
                    result = await callback(*args, **kwargs)
                else:
                    result = callback(*args, **kwargs)
                logger.info(f"Startup callback completed: {callback.__name__}")
                return result
            except Exception as e:
                logger.error(f"Error in startup callback {callback.__name__}: {str(e)}")
                raise
        
        self.startup_callbacks.append(wrapper)
        logger.info(f"Registered startup callback: {callback.__name__}")
    
    def register_shutdown_callback(self, callback: Callable, *args, **kwargs):
        """Register a callback to be called during shutdown."""
        self.shutdown_handler.register_shutdown_callback(callback, *args, **kwargs)
    
    def register_health_check(self, callback: Callable, *args, **kwargs):
        """Register a health check callback."""
        async def wrapper():
            try:
                if asyncio.iscoroutinefunction(callback):
                    return await callback(*args, **kwargs)
                else:
                    return callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Health check failed {callback.__name__}: {str(e)}")
                return False
        
        self.health_check_callbacks.append(wrapper)
        logger.info(f"Registered health check: {callback.__name__}")
    
    async def startup(self):
        """Execute startup sequence."""
        startup_start = datetime.utcnow()
        
        logger.info(
            f"Starting up {self.service_name}",
            extra={
                "service": self.service_name,
                "startup_callbacks": len(self.startup_callbacks)
            }
        )
        
        try:
            # Execute startup callbacks
            if self.startup_callbacks:
                logger.info(f"Executing {len(self.startup_callbacks)} startup callbacks")
                
                for callback in self.startup_callbacks:
                    await callback()
            
            startup_duration = (datetime.utcnow() - startup_start).total_seconds()
            logger.info(
                f"Startup completed in {startup_duration:.2f}s",
                extra={
                    "service": self.service_name,
                    "startup_duration_seconds": startup_duration
                }
            )
            
        except Exception as e:
            logger.error(
                f"Startup failed: {str(e)}",
                extra={
                    "service": self.service_name,
                    "error": str(e)
                }
            )
            raise
    
    async def health_check(self) -> bool:
        """Execute health checks."""
        if not self.health_check_callbacks:
            return True
        
        try:
            results = await asyncio.gather(
                *self.health_check_callbacks,
                return_exceptions=True
            )
            
            # Check if all health checks passed
            all_healthy = all(
                result is True or (isinstance(result, bool) and result)
                for result in results
                if not isinstance(result, Exception)
            )
            
            return all_healthy
            
        except Exception as e:
            logger.error(f"Health check execution failed: {str(e)}")
            return False
    
    async def run_until_shutdown(self):
        """Run service until shutdown signal is received."""
        logger.info(f"Service {self.service_name} is running, waiting for shutdown signal")
        await self.shutdown_handler.wait_for_shutdown()
    
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self.shutdown_handler.is_shutdown_requested()


# Common shutdown callbacks for different types of resources

async def close_database_connections(db_engine):
    """Shutdown callback for closing database connections."""
    logger.info("Closing database connections")
    try:
        await db_engine.dispose()
        logger.info("Database connections closed successfully")
    except Exception as e:
        logger.error(f"Error closing database connections: {str(e)}")


async def close_redis_connections(redis_client):
    """Shutdown callback for closing Redis connections."""
    logger.info("Closing Redis connections")
    try:
        await redis_client.close()
        logger.info("Redis connections closed successfully")
    except Exception as e:
        logger.error(f"Error closing Redis connections: {str(e)}")


async def stop_background_tasks(tasks: List[asyncio.Task]):
    """Shutdown callback for stopping background tasks."""
    logger.info(f"Stopping {len(tasks)} background tasks")
    try:
        for task in tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete cancellation
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Background tasks stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping background tasks: {str(e)}")


def save_application_state(state_data: dict, file_path: str):
    """Shutdown callback for saving application state."""
    logger.info(f"Saving application state to {file_path}")
    try:
        import json
        with open(file_path, 'w') as f:
            json.dump(state_data, f, indent=2, default=str)
        logger.info("Application state saved successfully")
    except Exception as e:
        logger.error(f"Error saving application state: {str(e)}")
