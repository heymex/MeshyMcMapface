#!/usr/bin/env python3
"""
Simple test to check Meshtastic interface directly
"""
import json

def test_meshtastic_direct():
    """Test Meshtastic interface directly"""
    try:
        print("Importing meshtastic library...")
        import meshtastic
        import meshtastic.serial_interface
        print("✓ Meshtastic library imported successfully")
        
        print("\nAttempting to connect to Meshtastic device...")
        interface = meshtastic.serial_interface.SerialInterface()
        print("✓ Connected to Meshtastic device")
        
        print(f"\nInterface type: {type(interface)}")
        print(f"Interface dir: {[attr for attr in dir(interface) if not attr.startswith('_') and not callable(getattr(interface, attr))]}")
        
        # Check for nodesByNum
        if hasattr(interface, 'nodesByNum'):
            nodes = interface.nodesByNum
            print(f"\n✓ Found nodesByNum with {len(nodes)} nodes")
            
            if len(nodes) == 0:
                print("⚠️  No nodes in nodesByNum - this is likely the issue!")
                print("   Nodes need time to be discovered after connecting.")
                print("   Try running this again after the device has been connected for a while.")
            else:
                print("\nNode details:")
                for i, (node_num, node) in enumerate(nodes.items()):
                    if i >= 3:  # Only show first 3
                        print(f"... and {len(nodes) - 3} more nodes")
                        break
                        
                    print(f"\nNode {i+1}: 0x{node_num:08x}")
                    print(f"  Type: {type(node)}")
                    
                    # User info
                    if hasattr(node, 'user') and node.user:
                        user = node.user
                        print(f"  User: {getattr(user, 'longName', 'N/A')} ({getattr(user, 'shortName', 'N/A')})")
                    else:
                        print("  User: None")
                    
                    # Device metrics - this is what we need for extended data
                    if hasattr(node, 'deviceMetrics') and node.deviceMetrics:
                        metrics = node.deviceMetrics
                        print(f"  ✓ Device Metrics found:")
                        print(f"    Battery: {getattr(metrics, 'batteryLevel', None)}")
                        print(f"    Voltage: {getattr(metrics, 'voltage', None)}")
                        print(f"    Channel Util: {getattr(metrics, 'channelUtilization', None)}")
                        print(f"    Air Util TX: {getattr(metrics, 'airUtilTx', None)}")
                        print(f"    Uptime: {getattr(metrics, 'uptimeSeconds', None)}")
                    else:
                        print("  ❌ No device metrics found")
                    
                    # Other fields
                    print(f"  Hops: {getattr(node, 'hopsAway', None)}")
                    print(f"  Last heard: {getattr(node, 'lastHeard', None)}")
        else:
            print("❌ No nodesByNum attribute found")
        
        # Check for regular nodes attribute
        if hasattr(interface, 'nodes'):
            print(f"\nAlso found 'nodes' attribute: {type(interface.nodes)}")
        
        interface.close()
        print("\n✓ Interface closed")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Install meshtastic with: pip install meshtastic")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure a Meshtastic device is connected")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_meshtastic_direct()