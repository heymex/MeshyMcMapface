#!/usr/bin/env python3
"""
Debug script to check what node data is available from Meshtastic interface
"""
import json
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

try:
    import meshtastic
    from meshtastic import serial_interface
except ImportError:
    print("Meshtastic library not found. Install with: pip install meshtastic")
    sys.exit(1)

def debug_interface():
    """Debug the Meshtastic interface node data"""
    try:
        print("Connecting to Meshtastic device...")
        # Try to auto-connect
        interface = serial_interface.SerialInterface()
        
        print(f"Connected! Interface type: {type(interface)}")
        print(f"Interface attributes: {[attr for attr in dir(interface) if not attr.startswith('_')]}")
        
        # Check for nodes data
        if hasattr(interface, 'nodesByNum') and interface.nodesByNum:
            print(f"\nFound {len(interface.nodesByNum)} nodes in nodesByNum:")
            for node_num, node in interface.nodesByNum.items():
                print(f"\nNode {node_num} (0x{node_num:08x}):")
                print(f"  Type: {type(node)}")
                print(f"  Attributes: {[attr for attr in dir(node) if not attr.startswith('_')]}")
                
                # Check user info
                if hasattr(node, 'user') and node.user:
                    user = node.user
                    print(f"  User: {getattr(user, 'longName', 'Unknown')} ({getattr(user, 'shortName', 'N/A')})")
                    print(f"    ID: {getattr(user, 'id', 'N/A')}")
                    print(f"    HW Model: {getattr(user, 'hwModel', 'N/A')}")
                else:
                    print("  User: None")
                
                # Check device metrics
                if hasattr(node, 'deviceMetrics') and node.deviceMetrics:
                    metrics = node.deviceMetrics
                    print(f"  Device Metrics:")
                    print(f"    Battery: {getattr(metrics, 'batteryLevel', 'N/A')}%")
                    print(f"    Voltage: {getattr(metrics, 'voltage', 'N/A')}V")
                    print(f"    Channel Util: {getattr(metrics, 'channelUtilization', 'N/A')}%")
                    print(f"    Air Util TX: {getattr(metrics, 'airUtilTx', 'N/A')}%")
                    print(f"    Uptime: {getattr(metrics, 'uptimeSeconds', 'N/A')}s")
                else:
                    print("  Device Metrics: None")
                
                # Check position
                if hasattr(node, 'position') and node.position:
                    pos = node.position
                    print(f"  Position: {getattr(pos, 'latitude', 'N/A')}, {getattr(pos, 'longitude', 'N/A')}")
                else:
                    print("  Position: None")
                
                # Check other fields
                print(f"  Hops Away: {getattr(node, 'hopsAway', 'N/A')}")
                print(f"  Last Heard: {getattr(node, 'lastHeard', 'N/A')}")
                print(f"  Is Favorite: {getattr(node, 'isFavorite', 'N/A')}")
                
        else:
            print("No nodesByNum data found")
            
        # Check for nodes attribute
        if hasattr(interface, 'nodes'):
            print(f"\nInterface also has 'nodes' attribute: {type(interface.nodes)}")
        else:
            print("\nInterface does not have 'nodes' attribute")
            
        interface.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_interface()