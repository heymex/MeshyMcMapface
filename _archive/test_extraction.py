#!/usr/bin/env python3
"""
Test the actual data extraction logic
"""
import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def test_extraction():
    """Test the actual extraction logic"""
    try:
        import meshtastic
        import meshtastic.serial_interface
        
        print("Connecting to test extraction...")
        interface = meshtastic.serial_interface.SerialInterface()
        
        if hasattr(interface, 'nodesByNum') and interface.nodesByNum:
            nodes = interface.nodesByNum
            print(f"Found {len(nodes)} nodes")
            
            # Test the extraction logic on the first node with deviceMetrics
            for node_num, node in nodes.items():
                if isinstance(node, dict) and node.get('deviceMetrics'):
                    print(f"\nTesting extraction on node 0x{node_num:08x}")
                    
                    # This is the logic from base_agent.py
                    node_id = f"!{node_num:08x}"
                    node_data = {
                        'user': {},
                        'position': {},
                        'deviceMetrics': {}
                    }
                    
                    # Extract using the current logic
                    if isinstance(node, dict):
                        user_data = node.get('user', {})
                        position_data = node.get('position', {})
                        device_metrics = node.get('deviceMetrics', {})
                        
                        print(f"Raw device_metrics: {device_metrics}")
                        print(f"device_metrics type: {type(device_metrics)}")
                        print(f"device_metrics bool: {bool(device_metrics)}")
                        
                        # Extract user information
                        if user_data:
                            node_data['user'] = {
                                'id': user_data.get('id', '') or node_id,
                                'longName': user_data.get('longName', ''),
                                'shortName': user_data.get('shortName', ''),
                                'macaddr': user_data.get('macaddr', ''),
                                'hwModel': user_data.get('hwModel', 0),
                                'role': user_data.get('role', 0),
                                'isLicensed': user_data.get('isLicensed', False)
                            }
                            print(f"Extracted user: {node_data['user']}")
                        
                        # Extract position information
                        if position_data:
                            node_data['position'] = {
                                'latitude': position_data.get('latitude', 0),
                                'longitude': position_data.get('longitude', 0),
                                'altitude': position_data.get('altitude', 0),
                                'time': position_data.get('time', 0)
                            }
                            print(f"Extracted position: {node_data['position']}")
                        
                        # Extract device metrics
                        if device_metrics:
                            node_data['deviceMetrics'] = {
                                'batteryLevel': device_metrics.get('batteryLevel'),
                                'voltage': device_metrics.get('voltage'),
                                'channelUtilization': device_metrics.get('channelUtilization'),
                                'airUtilTx': device_metrics.get('airUtilTx'),
                                'uptimeSeconds': device_metrics.get('uptimeSeconds')
                            }
                            print(f"Extracted deviceMetrics: {node_data['deviceMetrics']}")
                        else:
                            print("No device metrics to extract")
                        
                        # Add other node-level fields
                        node_data['hopsAway'] = node.get('hopsAway')
                        node_data['lastHeard'] = node.get('lastHeard')
                        node_data['isFavorite'] = node.get('isFavorite', False)
                        
                        print(f"Final node_data: {node_data}")
                    
                    break  # Only test first node with deviceMetrics
            
        interface.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_extraction()