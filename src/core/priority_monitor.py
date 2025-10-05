"""
Priority Node Monitor for MeshyMcMapface
Monitors priority nodes for freshness and triggers proactive updates
"""
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Set, Optional

from .config import AgentConfig
from .database import RouteCacheRepository


class PriorityNodeMonitor:
    """Monitors priority nodes for freshness and triggers updates"""
    
    def __init__(self, agent_config: AgentConfig, route_cache: RouteCacheRepository, 
                 traceroute_manager, logger=None):
        self.agent_config = agent_config
        self.route_cache = route_cache
        self.traceroute_manager = traceroute_manager
        self.logger = logger or logging.getLogger(__name__)
        
        self.priority_nodes = set(agent_config.priority_nodes or [])
        self.running = False
        self.last_check_time = {}  # Track last check time for each priority node
        self.refresh_stats = {
            'total_refreshes': 0,
            'successful_refreshes': 0,
            'failed_refreshes': 0,
            'proactive_refreshes': 0,
            'stale_triggered_refreshes': 0
        }
        
        if self.priority_nodes:
            self.logger.info(f"Priority monitor initialized for {len(self.priority_nodes)} nodes: {list(self.priority_nodes)}")
        else:
            self.logger.info("Priority monitor initialized but no priority nodes configured")
    
    async def start_monitoring(self):
        """Start the priority node monitoring service"""
        if not self.priority_nodes:
            self.logger.info("No priority nodes configured, monitor will not run")
            return
        
        self.running = True
        self.logger.info(f"Starting priority node monitoring with {self.agent_config.priority_check_interval}s intervals")
        
        while self.running:
            try:
                await self._monitoring_cycle()
                
                # Sleep for priority check interval
                await asyncio.sleep(self.agent_config.priority_check_interval)
                
            except Exception as e:
                self.logger.error(f"Error in priority node monitoring cycle: {e}")
                await asyncio.sleep(60)  # Fallback delay on error
    
    def stop_monitoring(self):
        """Stop the priority node monitoring service"""
        self.running = False
        self.logger.info("Priority node monitoring stopped")
    
    async def _monitoring_cycle(self):
        """Execute one monitoring cycle"""
        self.logger.debug(f"Starting priority monitoring cycle for {len(self.priority_nodes)} nodes")
        
        # Check for stale priority routes
        await self._check_priority_node_freshness()
        
        # Proactive priority traces
        await self._proactive_priority_traces()
        
        # Log stats periodically
        if self.refresh_stats['total_refreshes'] > 0 and self.refresh_stats['total_refreshes'] % 10 == 0:
            self._log_refresh_stats()
    
    async def _check_priority_node_freshness(self):
        """Check if priority node data is getting stale"""
        try:
            stale_routes = self.route_cache.get_stale_priority_routes(
                self.agent_config.id,
                list(self.priority_nodes),
                staleness_threshold_hours=6
            )
            
            if stale_routes:
                self.logger.info(f"Found {len(stale_routes)} stale priority routes, triggering refresh")
                
                for route_info in stale_routes:
                    try:
                        target_node = route_info['target']
                        self.logger.info(f"Refreshing stale priority route to {target_node}")
                        
                        route_result = await self.traceroute_manager.traceroute_to_node(
                            target_node,
                            is_priority=True
                        )
                        
                        self.refresh_stats['total_refreshes'] += 1
                        self.refresh_stats['stale_triggered_refreshes'] += 1
                        
                        if route_result:
                            self.refresh_stats['successful_refreshes'] += 1
                            self.logger.info(f"Successfully refreshed stale route to {target_node}")
                        else:
                            self.refresh_stats['failed_refreshes'] += 1
                            self.logger.warning(f"Failed to refresh stale route to {target_node}")
                            
                    except Exception as e:
                        self.logger.error(f"Error refreshing stale route to {route_info['target']}: {e}")
                        self.refresh_stats['failed_refreshes'] += 1
            else:
                self.logger.debug("No stale priority routes found")
                
        except Exception as e:
            self.logger.error(f"Error checking priority node freshness: {e}")
    
    async def _proactive_priority_traces(self):
        """Proactively trace to priority nodes even if not stale"""
        for priority_node in self.priority_nodes:
            try:
                # Check when we last proactively traced to this priority node
                last_trace_time = self.last_check_time.get(priority_node, 0)
                current_time = time.time()
                
                # Proactive trace every 2 hours for priority nodes (vs checking staleness every 6 hours)
                proactive_interval = 2 * 3600  # 2 hours
                
                if current_time - last_trace_time > proactive_interval:
                    self.logger.info(f"Proactive trace to priority node: {priority_node}")
                    
                    route_result = await self.traceroute_manager.traceroute_to_node(
                        priority_node,
                        is_priority=True
                    )
                    
                    self.refresh_stats['total_refreshes'] += 1
                    self.refresh_stats['proactive_refreshes'] += 1
                    self.last_check_time[priority_node] = current_time
                    
                    if route_result:
                        self.refresh_stats['successful_refreshes'] += 1
                        self.logger.info(f"Proactive trace to {priority_node} successful")
                    else:
                        self.refresh_stats['failed_refreshes'] += 1
                        self.logger.warning(f"Proactive trace to {priority_node} failed")
                else:
                    time_until_next = proactive_interval - (current_time - last_trace_time)
                    self.logger.debug(f"Priority node {priority_node} traced {(current_time - last_trace_time)/3600:.1f}h ago, next in {time_until_next/3600:.1f}h")
                    
            except Exception as e:
                self.logger.error(f"Error in proactive trace to {priority_node}: {e}")
                self.refresh_stats['failed_refreshes'] += 1
    
    async def force_refresh_priority_node(self, node_id: str) -> bool:
        """Force refresh a specific priority node"""
        if node_id not in self.priority_nodes:
            self.logger.warning(f"Node {node_id} is not in priority list, cannot force refresh")
            return False
        
        try:
            self.logger.info(f"Force refreshing priority node: {node_id}")
            
            route_result = await self.traceroute_manager.traceroute_to_node(
                node_id,
                is_priority=True
            )
            
            self.refresh_stats['total_refreshes'] += 1
            self.last_check_time[node_id] = time.time()
            
            if route_result:
                self.refresh_stats['successful_refreshes'] += 1
                self.logger.info(f"Force refresh of {node_id} successful")
                return True
            else:
                self.refresh_stats['failed_refreshes'] += 1
                self.logger.warning(f"Force refresh of {node_id} failed")
                return False
                
        except Exception as e:
            self.logger.error(f"Error force refreshing {node_id}: {e}")
            self.refresh_stats['failed_refreshes'] += 1
            return False
    
    async def force_refresh_all_priority_nodes(self) -> Dict[str, bool]:
        """Force refresh all priority nodes"""
        results = {}
        
        self.logger.info(f"Force refreshing all {len(self.priority_nodes)} priority nodes")
        
        for priority_node in self.priority_nodes:
            results[priority_node] = await self.force_refresh_priority_node(priority_node)
            # Small delay between traces to avoid overwhelming the mesh
            await asyncio.sleep(2)
        
        successful = sum(1 for success in results.values() if success)
        self.logger.info(f"Force refresh completed: {successful}/{len(results)} successful")
        
        return results
    
    def get_priority_monitor_stats(self) -> Dict:
        """Get comprehensive priority monitoring statistics"""
        stats = {
            'priority_nodes': {
                'total': len(self.priority_nodes),
                'nodes': list(self.priority_nodes)
            },
            'refresh_stats': self.refresh_stats.copy(),
            'monitoring': {
                'running': self.running,
                'check_interval_seconds': self.agent_config.priority_check_interval,
                'cache_duration_hours': self.agent_config.priority_cache_duration
            },
            'last_check_times': {}
        }
        
        # Add last check times with human-readable format
        current_time = time.time()
        for node_id, last_time in self.last_check_time.items():
            hours_ago = (current_time - last_time) / 3600
            stats['last_check_times'][node_id] = {
                'timestamp': datetime.fromtimestamp(last_time, timezone.utc).isoformat(),
                'hours_ago': round(hours_ago, 1)
            }
        
        # Add traceroute manager priority stats if available
        if hasattr(self.traceroute_manager, 'get_priority_stats'):
            stats['traceroute_priority_stats'] = self.traceroute_manager.get_priority_stats()
        
        return stats
    
    def _log_refresh_stats(self):
        """Log refresh statistics"""
        stats = self.refresh_stats
        success_rate = (stats['successful_refreshes'] / stats['total_refreshes'] * 100) if stats['total_refreshes'] > 0 else 0
        
        self.logger.info(f"Priority refresh stats: {stats['total_refreshes']} total "
                        f"({stats['successful_refreshes']} success, {stats['failed_refreshes']} failed, "
                        f"{success_rate:.1f}% success rate) - "
                        f"Proactive: {stats['proactive_refreshes']}, Stale-triggered: {stats['stale_triggered_refreshes']}")
    
    def add_priority_node(self, node_id: str):
        """Add a node to priority monitoring"""
        if node_id not in self.priority_nodes:
            self.priority_nodes.add(node_id)
            self.logger.info(f"Added priority node: {node_id}")
            # Trigger immediate refresh for new priority node
            if self.running:
                asyncio.create_task(self.force_refresh_priority_node(node_id))
    
    def remove_priority_node(self, node_id: str):
        """Remove a node from priority monitoring"""
        if node_id in self.priority_nodes:
            self.priority_nodes.discard(node_id)
            if node_id in self.last_check_time:
                del self.last_check_time[node_id]
            self.logger.info(f"Removed priority node: {node_id}")
    
    def on_priority_node_seen(self, node_id: str, packet_data: Dict):
        """Called when a priority node is seen on the network"""
        if node_id in self.priority_nodes:
            self.logger.debug(f"Priority node {node_id} seen on network")
            
            # Check if we need to refresh this node's route data
            last_check = self.last_check_time.get(node_id, 0)
            hours_since_check = (time.time() - last_check) / 3600
            
            # If we haven't checked this priority node in a while, trigger refresh
            if hours_since_check > 4:  # 4 hours trigger threshold
                self.logger.info(f"Priority node {node_id} seen but last checked {hours_since_check:.1f}h ago, triggering refresh")
                if self.running:
                    asyncio.create_task(self.force_refresh_priority_node(node_id))