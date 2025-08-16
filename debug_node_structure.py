#!/usr/bin/env python3
"""
Debug script to examine the actual structure of nodes from Meshtastic
"""
import json

def debug_node_structure():
    """Debug the actual structure of nodes"""
    try:
        print("Importing meshtastic library...")
        import meshtastic
        import meshtastic.serial_interface
        
        print("Connecting to Meshtastic device...")
        interface = meshtastic.serial_interface.SerialInterface()
        
        if hasattr(interface, 'nodesByNum') and interface.nodesByNum:
            nodes = interface.nodesByNum
            print(f"Found {len(nodes)} nodes")
            
            # Look at the first few nodes in detail
            for i, (node_num, node) in enumerate(nodes.items()):
                if i >= 3:  # Only examine first 3 nodes
                    break
                    
                print(f"\n=== NODE {i+1}: 0x{node_num:08x} ===")
                print(f"Type: {type(node)}")
                
                if isinstance(node, dict):
                    print("Node is a dictionary with keys:")
                    for key in node.keys():
                        value = node[key]
                        print(f"  {key}: {type(value)} = {value}")
                        
                        # If it's a nested dict, show its structure too
                        if isinstance(value, dict) and value:
                            print(f"    {key} contents:")
                            for subkey, subvalue in value.items():
                                print(f"      {subkey}: {type(subvalue)} = {subvalue}")
                else:
                    print("Node attributes:")
                    for attr in dir(node):
                        if not attr.startswith('_'):
                            try:
                                value = getattr(node, attr)
                                print(f"  {attr}: {type(value)} = {value}")
                            except:
                                print(f"  {attr}: <error getting value>")
                
                print(f"Raw node data: {json.dumps(node, indent=2, default=str)}")
                
            # Also check if nodes have different structures
            all_keys = set()
            for node in nodes.values():
                if isinstance(node, dict):
                    all_keys.update(node.keys())
            
            print(f"\nAll unique keys found across all nodes: {sorted(all_keys)}")
            
            # Count how many nodes have each type of data
            counts = {}
            for key in all_keys:
                counts[key] = sum(1 for node in nodes.values() 
                                if isinstance(node, dict) and key in node and node[key])
            
            print(f"\nData availability counts (out of {len(nodes)} nodes):")
            for key, count in sorted(counts.items()):
                print(f"  {key}: {count} nodes have this data")
        
        interface.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_node_structure()