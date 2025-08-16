#!/usr/bin/env python3
"""
Example of integrating Meshtastic traceroute functionality into existing agents
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List
from meshtastic_traceroute_integration import MeshtasticTracerouteManager

class ExampleAgentWithTraceroute:
    """Example showing how to add traceroute to existing agents"""
    
    def __init__(self, agent_config):
        self.agent_config = agent_config
        self.logger = None  # Set from agent config
        self.connection_manager = None  # Set from agent
        self.traceroute_manager = None
        
    def connect_to_meshtastic(self) -> bool:
        """Enhanced connection method with traceroute manager setup"""
        # ... existing connection code ...
        
        connection = self.connection_manager.get_connection()
        if connection and connection.interface:
            # Initialize traceroute manager
            self.traceroute_manager = MeshtasticTracerouteManager(
                connection.interface,
                self.agent_config.id,
                self.logger
            )
            self.logger.info("Traceroute manager initialized")
            return True
        return False
    
    async def discover_network_routes(self) -> List[Dict]:
        """Discover routes to all known nodes using traceroute"""
        if not self.traceroute_manager:
            self.logger.warning("Traceroute manager not initialized")
            return []
        
        # Get all known nodes
        known_nodes = self._get_known_nodes()
        self.logger.info(f"Starting route discovery for {len(known_nodes)} nodes")
        
        # Perform traceroutes to all nodes
        results = await self.traceroute_manager.discover_all_routes(
            known_nodes,
            hop_limit=7,
            channel_index=0,
            delay_between_traces=3.0  # 3 second delay to avoid overwhelming mesh
        )
        
        self.logger.info(f"Route discovery completed: {len(results)} successful routes")
        return results
    
    def _get_known_nodes(self) -> List[str]:
        """Get list of known node IDs from interface"""
        nodes = []
        try:
            connection = self.connection_manager.get_connection()
            if hasattr(connection.interface, 'nodesByNum') and connection.interface.nodesByNum:
                local_node_id = self._get_local_node_id()
                for node_num in connection.interface.nodesByNum.keys():
                    node_id = f"!{node_num:08x}"
                    # Skip our own node
                    if node_id != local_node_id:
                        nodes.append(node_id)
        except Exception as e:
            self.logger.error(f"Error getting known nodes: {e}")
        
        return nodes
    
    def _get_local_node_id(self) -> str:
        """Get local node ID"""
        try:
            connection = self.connection_manager.get_connection()
            if hasattr(connection.interface, 'myInfo') and connection.interface.myInfo:
                return f"!{connection.interface.myInfo.my_node_num:08x}"
        except:
            pass
        return "!00000000"
    
    async def send_route_data_to_server(self, route_results: List[Dict]):
        """Send discovered route data to server"""
        if not route_results:
            return
        
        payload = {
            'agent_id': self.agent_config.id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'routes': route_results,
            'discovery_type': 'traceroute'
        }
        
        self.logger.info(f"Sending {len(route_results)} routes to server")
        
        # For single-server agent: send to server_url
        # For multi-server agent: send to all configured servers
        # Implementation depends on agent type
        
        # Example for single server:
        # async with aiohttp.ClientSession() as session:
        #     async with session.post(
        #         f"{self.server_url}/api/agent/routes",
        #         json=payload,
        #         headers={'Authorization': f'Bearer {self.token}'}
        #     ) as response:
        #         if response.status == 200:
        #             self.logger.info("Route data sent successfully")
        #         else:
        #             self.logger.error(f"Failed to send route data: {response.status}")
    
    async def periodic_route_discovery(self, interval_minutes: int = 60):
        """Periodically discover routes and send to server"""
        while True:
            try:
                self.logger.info("Starting periodic route discovery cycle")
                
                # Discover routes
                route_results = await self.discover_network_routes()
                
                # Send to server
                if route_results:
                    await self.send_route_data_to_server(route_results)
                else:
                    self.logger.info("No routes discovered this cycle")
                
            except Exception as e:
                self.logger.error(f"Error in periodic route discovery: {e}")
            
            # Wait for next cycle
            self.logger.info(f"Sleeping for {interval_minutes} minutes until next route discovery")
            await asyncio.sleep(interval_minutes * 60)
    
    async def run_enhanced_agent(self):
        """Main agent run loop with traceroute capability"""
        
        # Start periodic route discovery task
        route_discovery_task = asyncio.create_task(
            self.periodic_route_discovery(interval_minutes=30)
        )
        
        # ... existing agent main loop ...
        
        try:
            # Run existing agent tasks alongside route discovery
            await asyncio.gather(
                route_discovery_task,
                # ... other existing agent tasks ...
            )
        except KeyboardInterrupt:
            self.logger.info("Shutting down agent...")
            route_discovery_task.cancel()


def integrate_traceroute_into_existing_agents():
    """Instructions for integrating traceroute into existing agents"""
    
    integration_guide = '''
    === INTEGRATION GUIDE ===
    
    To add traceroute capability to existing agents:
    
    1. **Add to Agent Initialization**:
       - Import MeshtasticTracerouteManager
       - Initialize in connect_to_meshtastic() method
       
    2. **Add Route Discovery Methods**:
       - discover_network_routes()
       - send_route_data_to_server()
       - periodic_route_discovery()
       
    3. **Update Main Run Loop**:
       - Add periodic route discovery as async task
       - Run alongside existing agent operations
       
    4. **Update Server API**:
       - Add /api/agent/routes endpoint
       - Store route data in network_routes table
       - Update topology visualization to use real routes
       
    5. **Database Integration**:
       - Routes stored with agent_id, timestamp, path data
       - SNR data for link quality analysis
       - Both forward and return routes captured
       
    6. **Configuration Options**:
       - route_discovery_interval: How often to run traceroutes
       - traceroute_hop_limit: Maximum hops to trace
       - traceroute_delay: Delay between individual traceroutes
       - route_confidence_threshold: Minimum confidence for storage
    
    === BENEFITS ===
    
    With real traceroute data, the application can now:
    - Show actual routing paths instead of just hop counts
    - Build complete network topology maps with connection lines
    - Analyze routing efficiency and detect bottlenecks
    - Track routing changes over time
    - Provide multi-agent perspective on network topology
    - Enable advanced network analysis and optimization
    '''
    
    return integration_guide


if __name__ == "__main__":
    print("=== MESHTASTIC TRACEROUTE INTEGRATION EXAMPLE ===")
    print()
    print("This example shows how to integrate the real Meshtastic traceroute")
    print("functionality into the existing agent architecture.")
    print()
    print(integrate_traceroute_into_existing_agents())