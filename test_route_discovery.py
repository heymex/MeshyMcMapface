#!/usr/bin/env python3
"""
Test route discovery functionality manually
"""

import asyncio
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from agents.base_agent import BaseAgent
    from core.config import ConfigManager
    
    class TestAgent(BaseAgent):
        """Test agent to trigger route discovery"""
        
        async def _handle_processed_packet(self, packet_data):
            """Handle processed packets - minimal implementation"""
            pass
        
        async def _handle_connection_established(self):
            """Handle connection established - minimal implementation"""
            pass
        
        async def _handle_node_updated(self, node):
            """Handle node updated - minimal implementation"""
            pass
        
        async def send_route_data_to_server(self, route_results):
            """Send route data to server - minimal implementation"""
            print(f"📤 Would send {len(route_results)} routes to server:")
            for route in route_results[:3]:  # Show first 3 routes
                print(f"  🛣️  {route.get('source_node_id')} → {route.get('target_node_id')} ({route.get('hop_count')} hops)")
    
    async def test_route_discovery():
        """Test route discovery functionality"""
        print("🧪 Testing Route Discovery")
        print("=" * 50)
        
        # Try to create a test agent
        try:
            config_file = "agent_config.ini"  # Adjust path if needed
            
            if not os.path.exists(config_file):
                print(f"❌ Config file not found: {config_file}")
                print("💡 Create a config file or adjust the path")
                return
            
            agent = TestAgent(config_file)
            
            # Check if Meshtastic connection works
            print("🔌 Testing Meshtastic connection...")
            if agent.connect_to_meshtastic():
                print("✅ Connected to Meshtastic device")
                
                # Check if traceroute manager initialized
                if agent.traceroute_manager:
                    print("✅ Traceroute manager initialized")
                    
                    # Get known nodes
                    known_nodes = agent._get_known_nodes_for_traceroute()
                    print(f"🔍 Found {len(known_nodes)} known nodes")
                    
                    if known_nodes:
                        print("📡 Known nodes:", ', '.join(known_nodes[:5]))
                        
                        # Try route discovery
                        print("🛣️  Starting route discovery...")
                        routes = await agent.discover_network_routes()
                        
                        if routes:
                            print(f"✅ Discovered {len(routes)} routes!")
                            await agent.send_route_data_to_server(routes)
                        else:
                            print("⚠️  No routes discovered")
                    else:
                        print("⚠️  No known nodes to traceroute to")
                else:
                    print("❌ Traceroute manager not initialized")
            else:
                print("❌ Could not connect to Meshtastic device")
                
        except Exception as e:
            print(f"❌ Error during test: {e}")
            import traceback
            traceback.print_exc()

    if __name__ == "__main__":
        asyncio.run(test_route_discovery())

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("💡 Make sure you're running from the project root directory")