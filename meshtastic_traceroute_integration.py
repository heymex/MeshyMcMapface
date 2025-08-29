#!/usr/bin/env python3
"""
Integration with Meshtastic's built-in traceroute functionality
"""

import json
import uuid
import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable
import google.protobuf.json_format
from meshtastic import mesh_pb2

class MeshtasticTracerouteManager:
    """Manages traceroute operations using Meshtastic's built-in functionality"""
    
    def __init__(self, interface, agent_id: str, logger=None, route_cache=None):
        self.interface = interface
        self.agent_id = agent_id
        self.logger = logger or self._default_logger()
        self.route_cache = route_cache  # RouteCacheRepository instance for persistent caching
        self.pending_traceroutes: Dict[str, Dict] = {}
        self.traceroute_results: List[Dict] = []
        self.completed_routes = []  # Buffer for successful routes ready to send to server
        
    def _default_logger(self):
        import logging
        return logging.getLogger(__name__)
    
    async def discover_all_routes(self, target_nodes: List[str], 
                                hop_limit: int = 7, 
                                channel_index: int = 0,
                                delay_between_traces: float = 2.0) -> List[Dict]:
        """
        Perform traceroutes to all target nodes and return route data
        
        Args:
            target_nodes: List of node IDs to traceroute to
            hop_limit: Maximum hops to trace
            channel_index: Channel to use for traceroute
            delay_between_traces: Delay between traceroute calls
            
        Returns:
            List of route discovery results
        """
        results = []
        
        for target_node in target_nodes:
            try:
                self.logger.info(f"Starting traceroute to {target_node}")
                
                # Perform traceroute using Meshtastic's built-in method
                route_result = await self.traceroute_to_node(
                    target_node, hop_limit, channel_index
                )
                
                if route_result:
                    results.append(route_result)
                    self.logger.info(f"Traceroute to {target_node} completed: {route_result['hop_count']} hops")
                else:
                    self.logger.warning(f"Traceroute to {target_node} failed")
                
                # Delay between traceroutes to avoid overwhelming the mesh
                if delay_between_traces > 0:
                    await asyncio.sleep(delay_between_traces)
                    
            except Exception as e:
                self.logger.error(f"Error tracerouting to {target_node}: {e}")
                continue
        
        return results
    
    async def traceroute_to_node(self, target_node: str, 
                                hop_limit: int = 7,
                                channel_index: int = 0,
                                timeout: float = 30.0) -> Optional[Dict]:
        """
        Perform traceroute to a specific node
        
        Args:
            target_node: Target node ID (e.g., "!12345678")
            hop_limit: Maximum hops to trace
            channel_index: Channel index
            timeout: Timeout in seconds
            
        Returns:
            Route data dict or None if failed
        """
        # Check cache first if available
        if self.route_cache:
            try:
                source_node = self._get_local_node_id()
                cached_route = self.route_cache.get_cached_route(source_node, target_node, self.agent_id)
                if cached_route:
                    self.logger.info(f"Using cached route to {target_node}: {cached_route['hop_count']} hops")
                    return cached_route
            except Exception as e:
                self.logger.warning(f"Error checking route cache: {e}")
        
        discovery_id = str(uuid.uuid4())
        start_time = time.time()
        
        try:
            # Convert node ID to number if needed
            if target_node.startswith('!'):
                target_num = int(target_node[1:], 16)
            else:
                target_num = int(target_node, 16)
            
            self.logger.debug(f"Traceroute {discovery_id}: {target_node} (0x{target_num:08x})")
            
            # Store pending traceroute info
            self.pending_traceroutes[discovery_id] = {
                'target_node': target_node,
                'target_num': target_num,
                'start_time': start_time,
                'hop_limit': hop_limit,
                'channel_index': channel_index
            }
            
            # Setup response handler - hook into the actual onResponseTraceRoute method
            original_handler = getattr(self.interface, 'onResponseTraceRoute', None)
            
            def traceroute_response_handler(response):
                self._handle_traceroute_response(discovery_id, response, original_handler)
            
            self.interface.onResponseTraceRoute = traceroute_response_handler
            
            # Call Meshtastic's built-in traceroute
            self.interface.sendTraceRoute(target_num, hop_limit, channel_index)
            
            # Wait for response with timeout
            result = await self._wait_for_traceroute_result(discovery_id, timeout)
            
            # Restore original handler
            if original_handler:
                self.interface.onResponseTraceRoute = original_handler
            
            return result
            
        except Exception as e:
            self.logger.error(f"Traceroute failed: {e}")
            if discovery_id in self.pending_traceroutes:
                del self.pending_traceroutes[discovery_id]
            return None
    
    def _handle_traceroute_response(self, discovery_id: str, response, original_handler: Optional[Callable]):
        """Handle traceroute response from Meshtastic"""
        try:
            if discovery_id not in self.pending_traceroutes:
                self.logger.warning(f"Received response for unknown traceroute: {discovery_id}")
                return
            
            pending = self.pending_traceroutes[discovery_id]
            end_time = time.time()
            
            # Parse the traceroute response using actual Meshtastic format
            route_data = self._parse_meshtastic_traceroute_response(response, pending, end_time)
            
            # Store the result
            self.traceroute_results.append({
                'discovery_id': discovery_id,
                'route_data': route_data,
                'completed': True
            })
            
            # Store successful routes in buffer for periodic collection
            if route_data.get('success', False) and len(route_data.get('route_path', [])) > 1:
                self.completed_routes.append(route_data)
                self.logger.info(f"Buffered route for server: {' -> '.join(route_data['route_path'])}")
                
                # Cache successful route if cache is available
                if self.route_cache:
                    try:
                        cache_success = self.route_cache.store_route(route_data, self.agent_id)
                        if cache_success:
                            self.logger.debug(f"Cached route: {route_data['source_node_id']} -> {route_data['target_node_id']}")
                    except Exception as e:
                        self.logger.warning(f"Error caching route: {e}")
            
            # Clean up
            del self.pending_traceroutes[discovery_id]
            
            self.logger.info(f"Traceroute {discovery_id} completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error handling traceroute response: {e}")
        
        # Call original handler if it exists
        if original_handler:
            original_handler(response)
    
    def _parse_meshtastic_traceroute_response(self, response, pending: Dict, end_time: float) -> Dict:
        """Parse actual Meshtastic traceroute response into our format"""
        
        route_path = []
        hop_count = 0
        snr_data = []
        route_back = []
        snr_back_data = []
        
        try:
            # Parse RouteDiscovery protobuf message from response
            if 'decoded' in response and 'payload' in response['decoded']:
                route_discovery = mesh_pb2.RouteDiscovery()
                route_discovery.ParseFromString(response['decoded']['payload'])
                
                # Convert to dict for easier processing
                route_dict = google.protobuf.json_format.MessageToDict(route_discovery)
                
                # Build forward route path
                route_path = [self._get_local_node_id()]  # Start with source
                
                # Add intermediate nodes from route
                if 'route' in route_dict:
                    for node_num in route_dict['route']:
                        node_id = f"!{node_num:08x}"
                        route_path.append(node_id)
                
                # Add destination
                dest_id = f"!{response['to']:08x}"
                route_path.append(dest_id)
                
                # Extract SNR data towards destination  
                if 'snrTowards' in route_dict:
                    # SNR values are scaled by 4 in protobuf
                    snr_data = [snr / 4.0 for snr in route_dict['snrTowards']]
                
                # Extract return route if available
                if 'routeBack' in route_dict:
                    route_back = [f"!{node_num:08x}" for node_num in route_dict['routeBack']]
                    
                if 'snrBack' in route_dict:
                    snr_back_data = [snr / 4.0 for snr in route_dict['snrBack']]
                
                hop_count = len(route_path) - 1 if len(route_path) > 1 else 0
                
                self.logger.debug(f"Parsed route: {' -> '.join(route_path)}")
                self.logger.debug(f"SNR towards: {snr_data}")
                
            else:
                self.logger.warning("No decoded payload in traceroute response")
                # Fallback: direct route
                route_path = [self._get_local_node_id(), pending['target_node']]
                hop_count = 1
            
        except Exception as e:
            self.logger.warning(f"Error parsing traceroute response: {e}")
            # Fallback: basic route info
            route_path = [self._get_local_node_id(), pending['target_node']]
            hop_count = 1
        
        return {
            'discovery_id': str(uuid.uuid4()),
            'source_node_id': self._get_local_node_id(),
            'target_node_id': pending['target_node'],
            'agent_id': self.agent_id,
            'route_path': route_path,
            'hop_count': hop_count,
            'route_back': route_back,
            'total_time_ms': int((end_time - pending['start_time']) * 1000),
            'discovery_timestamp': datetime.fromtimestamp(pending['start_time'], timezone.utc).isoformat(),
            'response_timestamp': datetime.fromtimestamp(end_time, timezone.utc).isoformat(),
            'success': len(route_path) > 1,
            'channel_index': pending['channel_index'],
            'snr_towards': snr_data,
            'snr_back': snr_back_data,
            'discovery_method': 'meshtastic_traceroute'
        }
    
    def get_and_clear_completed_routes(self) -> List[Dict]:
        """Get all completed routes and clear the buffer"""
        if not hasattr(self, 'completed_routes') or self.completed_routes is None:
            self.completed_routes = []
        routes = self.completed_routes.copy()
        self.completed_routes.clear()
        return routes
    
    def cleanup_expired_cache(self):
        """Clean up expired routes from cache"""
        if self.route_cache:
            try:
                self.route_cache.cleanup_expired_routes()
            except Exception as e:
                self.logger.error(f"Error cleaning up expired cache: {e}")
    
    def get_cache_stats(self) -> Dict:
        """Get route cache statistics"""
        if self.route_cache:
            try:
                return self.route_cache.get_cache_stats(self.agent_id)
            except Exception as e:
                self.logger.error(f"Error getting cache stats: {e}")
                return {}
        return {}
    
    def _get_local_node_id(self) -> str:
        """Get the local node ID"""
        try:
            if hasattr(self.interface, 'myInfo') and self.interface.myInfo:
                return f"!{self.interface.myInfo.my_node_num:08x}"
        except:
            pass
        return "!00000000"  # Fallback
    
    async def _wait_for_traceroute_result(self, discovery_id: str, timeout: float) -> Optional[Dict]:
        """Wait for traceroute result with timeout"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Check if result is available
            for result in self.traceroute_results:
                if result['discovery_id'] == discovery_id and result['completed']:
                    self.traceroute_results.remove(result)
                    return result['route_data']
            
            await asyncio.sleep(0.1)
        
        # Timeout
        self.logger.warning(f"Traceroute {discovery_id} timed out")
        if discovery_id in self.pending_traceroutes:
            del self.pending_traceroutes[discovery_id]
        
        return None
    
    async def periodic_route_discovery(self, interval_minutes: int = 30):
        """
        Periodically discover routes to all known nodes
        
        Args:
            interval_minutes: Minutes between discovery cycles
        """
        while True:
            try:
                self.logger.info("Starting periodic route discovery")
                
                # Get all known nodes
                known_nodes = self._get_known_nodes()
                
                if known_nodes:
                    # Discover routes to all nodes
                    results = await self.discover_all_routes(known_nodes)
                    
                    self.logger.info(f"Route discovery completed: {len(results)} successful routes")
                    
                    # Return results for storage by calling code
                    yield results
                else:
                    self.logger.info("No known nodes for route discovery")
                
            except Exception as e:
                self.logger.error(f"Error in periodic route discovery: {e}")
            
            # Wait for next cycle
            await asyncio.sleep(interval_minutes * 60)
    
    def _get_known_nodes(self) -> List[str]:
        """Get list of known node IDs from the interface"""
        nodes = []
        
        try:
            if hasattr(self.interface, 'nodesByNum') and self.interface.nodesByNum:
                # Safely iterate over nodesByNum keys
                node_keys = self.interface.nodesByNum.keys() if self.interface.nodesByNum else []
                for node_num in node_keys:
                    node_id = f"!{node_num:08x}"
                    # Skip our own node
                    if node_id != self._get_local_node_id():
                        nodes.append(node_id)
        except Exception as e:
            self.logger.error(f"Error getting known nodes: {e}")
        
        return nodes

# Integration example for the agent
def integrate_traceroute_into_agent():
    """Example of how to integrate this into the existing agent"""
    
    example_code = '''
    # In src/agents/base_agent.py or multi_server_agent.py:
    
    from meshtastic_traceroute_integration import MeshtasticTracerouteManager
    
    class BaseAgent:
        def __init__(self, config_file: str):
            # ... existing init code ...
            self.traceroute_manager = None
        
        def connect_to_meshtastic(self) -> bool:
            success = super().connect_to_meshtastic()
            if success:
                # Initialize traceroute manager
                connection = self.connection_manager.get_connection()
                self.traceroute_manager = MeshtasticTracerouteManager(
                    connection.interface, 
                    self.agent_config.id,
                    self.logger
                )
            return success
        
        async def run(self):
            # ... existing run code ...
            
            # Start periodic route discovery
            if self.traceroute_manager:
                async for route_results in self.traceroute_manager.periodic_route_discovery(30):
                    # Send route data to server
                    await self.send_route_data_to_server(route_results)
        
        async def send_route_data_to_server(self, route_results: List[Dict]):
            """Send discovered routes to server"""
            if not route_results:
                return
                
            payload = {
                'agent_id': self.agent_config.id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'routes': route_results
            }
            
            # Send to server's new /api/agent/routes endpoint
            # Implementation depends on whether using single or multi-server agent
    '''
    
    return example_code

if __name__ == "__main__":
    print("=== MESHTASTIC TRACEROUTE INTEGRATION ===")
    print("This module integrates with Meshtastic's built-in traceroute functionality")
    print("to discover actual network routes and build topology maps.")
    print("")
    print("Key features:")
    print("- Uses existing sendTraceRoute() method")
    print("- Handles traceroute responses asynchronously") 
    print("- Stores complete route paths in database")
    print("- Enables true network topology visualization")
    print("")
    print("Integration example:")
    print(integrate_traceroute_into_agent())