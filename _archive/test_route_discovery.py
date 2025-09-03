#!/usr/bin/env python3
"""
Test route discovery functionality manually
"""

import asyncio
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Also add the project root to handle imports
sys.path.insert(0, os.path.dirname(__file__))

try:
    # Import the actual traceroute integration directly (absolute import)
    import meshtastic_traceroute_integration
    MeshtasticTracerouteManager = meshtastic_traceroute_integration.MeshtasticTracerouteManager
    
    # Try simpler approach - check if we can at least import meshtastic
    import meshtastic
    import meshtastic.serial_interface
    import meshtastic.tcp_interface
    
    async def test_simple_route_discovery():
        """Simple test of route discovery functionality"""
        print("🧪 Testing Route Discovery (Simplified)")
        print("=" * 50)
        
        try:
            # Test 1: Can we import and create the traceroute manager?
            print("📦 Testing imports...")
            print("✅ Successfully imported meshtastic and traceroute integration")
            
            # Test 2: Try to connect to Meshtastic device directly
            print("🔌 Testing Meshtastic connection...")
            
            # Try different connection methods
            interface = None
            
            # Method 1: Try serial connection
            try:
                interface = meshtastic.serial_interface.SerialInterface()
                print("✅ Connected via Serial")
            except Exception as e:
                print(f"⚠️  Serial connection failed: {e}")
                
                # Method 2: Try TCP connection
                try:
                    interface = meshtastic.tcp_interface.TCPInterface()
                    print("✅ Connected via TCP")
                except Exception as e:
                    print(f"⚠️  TCP connection failed: {e}")
            
            if interface:
                print("🎯 Meshtastic interface created successfully")
                
                # Test 3: Create traceroute manager
                traceroute_manager = MeshtasticTracerouteManager(
                    interface,
                    "test_agent",
                    None  # logger
                )
                print("✅ Traceroute manager created")
                
                # Test 4: Check for known nodes
                if hasattr(interface, 'nodesByNum') and interface.nodesByNum:
                    node_count = len(interface.nodesByNum)
                    print(f"🔍 Found {node_count} known nodes")
                    
                    if node_count > 0:
                        # Show first few nodes
                        node_ids = [f"!{num:08x}" for num in list(interface.nodesByNum.keys())[:5]]
                        print(f"📡 Sample nodes: {', '.join(node_ids)}")
                        
                        # Test 5: Try simple route discovery
                        print("🛣️  Testing route discovery to one node...")
                        
                        target_nodes = node_ids[:2]  # Just test 2 nodes
                        routes = await traceroute_manager.discover_all_routes(target_nodes)
                        
                        if routes:
                            print(f"🎉 SUCCESS! Discovered {len(routes)} routes:")
                            for route in routes:
                                path = ' → '.join(route.get('route_path', []))
                                print(f"  🛣️  {route.get('source_node_id')} to {route.get('target_node_id')}: {path}")
                                
                            # Test 6: Try sending to server
                            print("📤 Testing server submission...")
                            payload = {
                                'agent_id': 'test_agent',
                                'timestamp': 'now',
                                'routes': routes
                            }
                            
                            import json
                            import requests
                            
                            try:
                                response = requests.post('http://10.10.149.23:8082/api/agent/routes', 
                                                       json=payload, timeout=10)
                                if response.status_code == 200:
                                    print("✅ Successfully sent routes to server!")
                                    print("🌐 Check http://10.10.149.23:8082/api/routes to see the data")
                                else:
                                    print(f"⚠️  Server responded with status {response.status_code}")
                            except Exception as e:
                                print(f"⚠️  Could not reach server: {e}")
                                
                        else:
                            print("⚠️  No routes discovered - this might be normal if traceroute times out")
                    else:
                        print("⚠️  No nodes found in nodesByNum")
                else:
                    print("⚠️  No nodesByNum available - device might not be ready")
                
                # Clean up
                try:
                    interface.close()
                except:
                    pass
                    
            else:
                print("❌ Could not establish Meshtastic connection")
                print("💡 Make sure your Meshtastic device is connected via USB or network")
                
        except Exception as e:
            print(f"❌ Error during test: {e}")
            import traceback
            traceback.print_exc()

    if __name__ == "__main__":
        asyncio.run(test_simple_route_discovery())

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("💡 Make sure you're running from the project root directory")