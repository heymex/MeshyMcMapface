#!/usr/bin/env python3
"""
Test script to check extended node data collection with modular architecture
"""
import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def test_modular_agent_nodedb():
    """Test modular agent's extended node data collection"""
    try:
        print("Testing modular agent nodedb collection...")
        
        # Import modular components
        from src.agents.base_agent import BaseAgent, AgentFactory
        from src.core.config import create_sample_multi_config
        
        # Check if config exists, create if not
        config_file = 'test_multi_config.ini'
        if not Path(config_file).exists():
            print(f"Creating test config: {config_file}")
            create_sample_multi_config(config_file)
        
        print(f"Using config file: {config_file}")
        
        # Create a multi-server agent
        print("Creating multi-server agent...")
        agent = AgentFactory.create_agent('multi_server', config_file)
        
        print(f"Agent created: {type(agent)}")
        print(f"Agent ID: {agent.agent_config.id}")
        print(f"Location: {agent.agent_config.location_name}")
        
        # Try to connect to Meshtastic
        print("\nAttempting Meshtastic connection...")
        if agent.connect_to_meshtastic():
            print("✓ Connected to Meshtastic device")
            
            # Test extended node data collection
            print("\nTesting extended node data collection...")
            nodes_data = agent.get_extended_node_data()
            
            print(f"Collected data for {len(nodes_data)} nodes")
            
            if nodes_data:
                print("\nExtended node data found:")
                for node_id, node_data in list(nodes_data.items())[:3]:  # Show first 3
                    print(f"\nNode {node_id}:")
                    
                    user = node_data.get('user', {})
                    if user.get('longName'):
                        print(f"  Name: {user.get('longName')} ({user.get('shortName')})")
                    
                    device_metrics = node_data.get('deviceMetrics', {})
                    print(f"  Device Metrics (raw): {device_metrics}")
                    if device_metrics and any(v is not None for v in device_metrics.values()):
                        print(f"  Device Metrics (processed):")
                        for key, value in device_metrics.items():
                            print(f"    {key}: {value}")
                    else:
                        print(f"  Device Metrics: All None/empty or missing")
                    
                    # Check other fields
                    if node_data.get('hopsAway') is not None:
                        print(f"  Hops Away: {node_data.get('hopsAway')}")
                    if node_data.get('lastHeard') is not None:
                        print(f"  Last Heard: {node_data.get('lastHeard')}")
                
                if len(nodes_data) > 3:
                    print(f"\n... and {len(nodes_data) - 3} more nodes")
            else:
                print("❌ No extended node data collected")
                
                # Debug the connection
                connection = agent.connection_manager.get_connection()
                if connection and connection.interface:
                    interface = connection.interface
                    if hasattr(interface, 'nodesByNum'):
                        nodes = interface.nodesByNum
                        print(f"  Raw interface has {len(nodes)} nodes in nodesByNum")
                        if len(nodes) == 0:
                            print("  → No nodes discovered yet - device needs time to hear from mesh")
                        else:
                            print("  → Nodes exist but extended data extraction failed")
                            # Show first node raw data
                            first_node = list(nodes.values())[0]
                            print(f"  → Sample node type: {type(first_node)}")
                            print(f"  → Sample node attributes: {[attr for attr in dir(first_node) if not attr.startswith('_')]}")
                    else:
                        print("  → Interface has no nodesByNum attribute")
                else:
                    print("  → No connection or interface available")
            
            # Cleanup
            agent.disconnect_from_meshtastic()
            print("\n✓ Disconnected from Meshtastic")
            
        else:
            print("❌ Failed to connect to Meshtastic device")
            print("This is normal if no Meshtastic device is connected")
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're in the MeshyMcMapface directory")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_modular_agent_nodedb()