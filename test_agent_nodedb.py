#!/usr/bin/env python3
"""
Test script to check if agents can collect extended node data
"""
import asyncio
import json
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.agents.base_agent import BaseAgent

def test_base_agent_nodedb():
    """Test if base agent can collect extended node data"""
    try:
        # Create a base agent with test config
        print("Creating base agent...")
        
        # For testing, we'll use the single agent instead since it's simpler
        sys.path.insert(0, str(Path(__file__).parent))
        
        # Import the single agent module
        import importlib.util
        spec = importlib.util.spec_from_file_location("mmm_single_agent", "mmm-single-agent.py")
        mmm_single_agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mmm_single_agent)
        MeshyMcMapfaceAgent = mmm_single_agent.MeshyMcMapfaceAgent
        
        print("Looking for agent config file...")
        config_files = list(Path('.').glob('*agent*.ini'))
        if not config_files:
            config_files = list(Path('.').glob('*.ini'))
        
        if not config_files:
            print("No config files found. Creating test config...")
            # Create minimal test config
            test_config = """[agent]
id = test_agent
location_name = Test Location
location_lat = 37.7749
location_lon = -122.4194

[server]
url = http://localhost:8082
api_key = test-key
report_interval = 30

[meshtastic]
connection_type = auto
"""
            with open('test_config.ini', 'w') as f:
                f.write(test_config)
            config_file = 'test_config.ini'
        else:
            config_file = str(config_files[0])
            print(f"Using config file: {config_file}")
        
        # Create agent
        agent = MeshyMcMapfaceAgent(config_file)
        
        # Try to connect
        print("Attempting to connect to Meshtastic device...")
        if agent.connect_to_node():
            print("Connected successfully!")
            
            # Test nodedb collection
            print("Testing nodedb data collection...")
            
            if agent.interface and hasattr(agent.interface, 'nodesByNum'):
                nodes = agent.interface.nodesByNum
                print(f"Found {len(nodes)} nodes in nodesByNum")
                
                for node_num, node in list(nodes.items())[:3]:  # Test first 3 nodes
                    print(f"\nNode {node_num:08x}:")
                    if hasattr(node, 'user') and node.user:
                        print(f"  User: {getattr(node.user, 'longName', 'N/A')}")
                    if hasattr(node, 'deviceMetrics') and node.deviceMetrics:
                        metrics = node.deviceMetrics
                        print(f"  Battery: {getattr(metrics, 'batteryLevel', 'N/A')}")
                        print(f"  Channel Util: {getattr(metrics, 'channelUtilization', 'N/A')}")
                    else:
                        print("  No device metrics")
                        
            else:
                print("No nodesByNum found in interface")
                print(f"Interface attributes: {[attr for attr in dir(agent.interface) if not attr.startswith('_')]}")
            
            # Test the send_nodedb_to_server method 
            print("\nTesting nodedb data preparation...")
            nodes_data = {}
            if hasattr(agent.interface, 'nodesByNum') and agent.interface.nodesByNum:
                for node_num, node in agent.interface.nodesByNum.items():
                    node_id = f"!{node_num:08x}"
                    node_data = {'user': {}, 'position': {}, 'deviceMetrics': {}}
                    
                    if hasattr(node, 'deviceMetrics') and node.deviceMetrics:
                        metrics = node.deviceMetrics
                        node_data['deviceMetrics'] = {
                            'batteryLevel': getattr(metrics, 'batteryLevel', None),
                            'voltage': getattr(metrics, 'voltage', None),
                            'channelUtilization': getattr(metrics, 'channelUtilization', None),
                            'airUtilTx': getattr(metrics, 'airUtilTx', None),
                            'uptimeSeconds': getattr(metrics, 'uptimeSeconds', None)
                        }
                    
                    nodes_data[node_id] = node_data
            
            print(f"Prepared nodedb data for {len(nodes_data)} nodes")
            if nodes_data:
                # Show sample data
                sample_node = list(nodes_data.items())[0]
                print(f"Sample node data: {json.dumps(sample_node[1], indent=2)}")
            
            agent.interface.close()
            
        else:
            print("Failed to connect to Meshtastic device")
            print("This could be normal if no device is connected")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_base_agent_nodedb()