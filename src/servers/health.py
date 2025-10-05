"""
Server health monitoring and management
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from ..core.config import ServerConfig
from ..core.database import ServerHealthRepository


class ServerHealthMonitor:
    """Monitors health of individual servers"""
    
    def __init__(self, server_config: ServerConfig, health_repo: ServerHealthRepository):
        self.config = server_config
        self.health_repo = health_repo
        self.logger = logging.getLogger(__name__)
        
        # Initialize health state
        self._load_health_state()
    
    def _load_health_state(self):
        """Load health state from database"""
        health_data = self.health_repo.get_server_health(self.config.name)
        if health_data:
            self.config.last_success = health_data.get('last_success')
            self.config.consecutive_failures = health_data.get('consecutive_failures', 0)
            self.config.is_healthy = health_data.get('is_healthy', True)
    
    def record_success(self):
        """Record a successful operation"""
        self.config.consecutive_failures = 0
        self.config.is_healthy = True
        self.config.last_success = datetime.now(timezone.utc).isoformat()
        
        # Update database
        self.health_repo.update_server_health(self.config.name, success=True)
        
        self.logger.debug(f"Server {self.config.name} operation successful")
    
    def record_failure(self):
        """Record a failed operation"""
        self.config.consecutive_failures += 1
        
        # Mark as unhealthy after max_retries consecutive failures
        if self.config.consecutive_failures >= self.config.max_retries:
            self.config.is_healthy = False
            self.logger.warning(f"Server {self.config.name} marked as unhealthy after {self.config.consecutive_failures} failures")
        
        # Update database
        self.health_repo.update_server_health(self.config.name, success=False)
        
        self.logger.debug(f"Server {self.config.name} operation failed (failures: {self.config.consecutive_failures})")
    
    def is_healthy(self) -> bool:
        """Check if server is considered healthy"""
        return self.config.is_healthy and self.config.enabled
    
    def should_retry(self) -> bool:
        """Check if operations should be retried on this server"""
        return self.config.consecutive_failures < self.config.max_retries
    
    def get_health_info(self) -> Dict:
        """Get current health information"""
        return {
            'name': self.config.name,
            'enabled': self.config.enabled,
            'is_healthy': self.config.is_healthy,
            'consecutive_failures': self.config.consecutive_failures,
            'max_retries': self.config.max_retries,
            'last_success': self.config.last_success,
            'priority': self.config.priority
        }
    
    def reset_health(self):
        """Reset health state (useful for manual recovery)"""
        self.config.consecutive_failures = 0
        self.config.is_healthy = True
        self.logger.info(f"Reset health state for server {self.config.name}")


class MultiServerHealthMonitor:
    """Monitors health of multiple servers"""
    
    def __init__(self, server_configs: Dict[str, ServerConfig], health_repo: ServerHealthRepository):
        self.monitors = {}
        self.health_repo = health_repo
        self.logger = logging.getLogger(__name__)
        
        # Create health monitors for each server
        for name, config in server_configs.items():
            self.monitors[name] = ServerHealthMonitor(config, health_repo)
    
    def record_success(self, server_name: str):
        """Record success for a specific server"""
        if server_name in self.monitors:
            self.monitors[server_name].record_success()
        else:
            self.logger.warning(f"Attempted to record success for unknown server: {server_name}")
    
    def record_failure(self, server_name: str):
        """Record failure for a specific server"""
        if server_name in self.monitors:
            self.monitors[server_name].record_failure()
        else:
            self.logger.warning(f"Attempted to record failure for unknown server: {server_name}")
    
    def is_server_healthy(self, server_name: str) -> bool:
        """Check if a specific server is healthy"""
        if server_name in self.monitors:
            return self.monitors[server_name].is_healthy()
        return False
    
    def should_retry_server(self, server_name: str) -> bool:
        """Check if operations should be retried on a specific server"""
        if server_name in self.monitors:
            return self.monitors[server_name].should_retry()
        return False
    
    def get_healthy_servers(self) -> Dict[str, ServerHealthMonitor]:
        """Get all healthy servers"""
        return {name: monitor for name, monitor in self.monitors.items() 
                if monitor.is_healthy()}
    
    def get_unhealthy_servers(self) -> Dict[str, ServerHealthMonitor]:
        """Get all unhealthy servers"""
        return {name: monitor for name, monitor in self.monitors.items() 
                if not monitor.is_healthy()}
    
    def get_all_health_info(self) -> Dict[str, Dict]:
        """Get health information for all servers"""
        return {name: monitor.get_health_info() 
                for name, monitor in self.monitors.items()}
    
    def reset_all_health(self):
        """Reset health state for all servers"""
        for monitor in self.monitors.values():
            monitor.reset_health()
        self.logger.info("Reset health state for all servers")
    
    def reset_server_health(self, server_name: str):
        """Reset health state for a specific server"""
        if server_name in self.monitors:
            self.monitors[server_name].reset_health()
        else:
            self.logger.warning(f"Attempted to reset health for unknown server: {server_name}")
    
    def add_server_monitor(self, server_name: str, config: ServerConfig):
        """Add a new server monitor"""
        self.monitors[server_name] = ServerHealthMonitor(config, self.health_repo)
        self.logger.info(f"Added health monitor for server: {server_name}")
    
    def remove_server_monitor(self, server_name: str):
        """Remove a server monitor"""
        if server_name in self.monitors:
            del self.monitors[server_name]
            self.logger.info(f"Removed health monitor for server: {server_name}")
    
    async def periodic_health_check(self, server_client, interval_minutes: int = 5):
        """Perform periodic health checks on all servers"""
        while True:
            try:
                self.logger.debug("Performing periodic health checks")
                
                # Get health status from all servers
                health_results = await server_client.health_check_all()
                
                # Update health state based on results
                for server_name, is_healthy in health_results.items():
                    if is_healthy:
                        self.record_success(server_name)
                    else:
                        self.record_failure(server_name)
                
                # Log summary
                healthy_count = len(self.get_healthy_servers())
                total_count = len(self.monitors)
                self.logger.info(f"Health check complete: {healthy_count}/{total_count} servers healthy")
                
            except Exception as e:
                self.logger.error(f"Error during periodic health check: {e}")
            
            # Wait for next check
            await asyncio.sleep(interval_minutes * 60)
    
    def get_server_priority_order(self) -> list:
        """Get servers ordered by priority (healthy servers first)"""
        # Get all monitors
        all_monitors = list(self.monitors.values())
        
        # Separate healthy and unhealthy
        healthy = [m for m in all_monitors if m.is_healthy()]
        unhealthy = [m for m in all_monitors if not m.is_healthy()]
        
        # Sort each group by priority
        healthy.sort(key=lambda m: m.config.priority)
        unhealthy.sort(key=lambda m: m.config.priority)
        
        # Return server names in priority order
        return [m.config.name for m in healthy + unhealthy]