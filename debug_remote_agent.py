#!/usr/bin/env python3
"""
Debug script to test the actual agent behavior on remote system
"""
import sys
import json
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def debug_remote_agent():
    """Debug the remote agent behavior"""
    try:
        print("=== DEBUGGING REMOTE AGENT EXTENDED NODE DATA ===\n")
        
        # Test 1: Check if we can import the modular components
        print("1. Testing imports...")
        try:
            from src.agents.base_agent import BaseAgent, AgentFactory
            from src.core.config import create_sample_multi_config
            print("✓ Modular components imported successfully")
        except Exception as e:
            print(f"❌ Import failed: {e}")
            return
        
        # Test 2: Check if we can connect to Meshtastic and get raw data
        print("\n2. Testing Meshtastic connection...")
        try:
            import meshtastic
            import meshtastic.serial_interface
            
            interface = meshtastic.serial_interface.SerialInterface()
            
            if hasattr(interface, 'nodesByNum') and interface.nodesByNum:
                nodes = interface.nodesByNum
                print(f"✓ Connected to Meshtastic: {len(nodes)} nodes found")
                
                # Count nodes with extended data
                nodes_with_metrics = 0
                nodes_with_hops = 0
                
                for node in nodes.values():
                    if isinstance(node, dict):
                        if node.get('deviceMetrics'):
                            nodes_with_metrics += 1
                        if node.get('hopsAway') is not None:
                            nodes_with_hops += 1
                
                print(f"  - {nodes_with_metrics} nodes have deviceMetrics")
                print(f"  - {nodes_with_hops} nodes have hopsAway")
                
            else:
                print("❌ No nodesByNum found in interface")
                return
                
            interface.close()
            
        except Exception as e:
            print(f"❌ Meshtastic connection failed: {e}")
            return
        
        # Test 3: Test agent creation and extended node data collection  
        print("\n3. Testing agent extended node data collection...")
        
        # Find config file
        config_files = list(Path('.').glob('*agent*.ini'))
        if not config_files:
            config_files = list(Path('.').glob('*.ini'))
        
        if not config_files:
            print("Creating test config...")
            create_sample_multi_config('debug_config.ini')
            config_file = 'debug_config.ini'
        else:
            config_file = str(config_files[0])
            
        print(f"Using config: {config_file}")
        
        # Create agent
        agent = AgentFactory.create_agent('multi_server', config_file)
        print(f"✓ Agent created: {agent.agent_config.id}")
        
        # Connect to Meshtastic
        if agent.connect_to_meshtastic():
            print("✓ Agent connected to Meshtastic")
            
            # Test extended node data collection
            nodes_data = agent.get_extended_node_data()
            print(f"✓ Collected extended data for {len(nodes_data)} nodes")
            
            if nodes_data:
                # Show sample data
                sample_nodes = list(nodes_data.items())[:3]
                for node_id, node_data in sample_nodes:
                    print(f"\nNode {node_id}:")
                    
                    device_metrics = node_data.get('deviceMetrics', {})
                    print(f"  deviceMetrics: {device_metrics}")
                    
                    if device_metrics and any(v is not None for v in device_metrics.values()):
                        print("  ✓ Has device metrics with values")
                    else:
                        print("  ❌ No device metrics or all None")
                        
                    print(f"  hopsAway: {node_data.get('hopsAway')}")
                    print(f"  lastHeard: {node_data.get('lastHeard')}")
                    
                # Test 4: Simulate sending data to server
                print(f"\n4. Testing nodedb data preparation...")
                
                # Check if we would send this data
                non_empty_nodes = 0
                for node_id, node_data in nodes_data.items():
                    device_metrics = node_data.get('deviceMetrics', {})
                    if device_metrics and any(v is not None for v in device_metrics.values()):
                        non_empty_nodes += 1
                
                print(f"Would send data for {non_empty_nodes} nodes with actual metrics")
                
                if non_empty_nodes > 0:
                    print("✓ Extended data is available and would be sent")
                    
                    # Show what the actual payload would look like
                    sample_payload = {
                        'agent_id': agent.agent_config.id,
                        'timestamp': 'TIMESTAMP_HERE',
                        'nodes': dict(list(nodes_data.items())[:2])  # First 2 nodes
                    }
                    
                    print(f"\nSample payload structure:")
                    print(json.dumps(sample_payload, indent=2, default=str))
                    
                else:
                    print("❌ No nodes have extended metrics - payload would be empty")
                    
            else:
                print("❌ No extended node data collected")
                
            agent.disconnect_from_meshtastic()
            
        else:
            print("❌ Agent failed to connect to Meshtastic")
            
        print(f"\n=== DIAGNOSIS COMPLETE ===")
        print(f"If this shows extended data is available but API still shows null:")
        print(f"1. Check that the remote agent is actually running the updated code")
        print(f"2. Check agent logs for 'Preparing to send nodedb data' messages") 
        print(f"3. Check server logs for nodedb endpoint calls")
        print(f"4. Verify the agent config points to the correct server")
        
    except Exception as e:
        print(f"❌ Debug failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_remote_agent()