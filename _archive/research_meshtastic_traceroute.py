#!/usr/bin/env python3
"""
Research Meshtastic traceroute capabilities
"""

def research_meshtastic_traceroute():
    """Research how to do traceroutes with Meshtastic"""
    
    print("=== MESHTASTIC TRACEROUTE RESEARCH ===\n")
    
    try:
        import meshtastic
        import meshtastic.serial_interface
        
        print("1. Checking Meshtastic interface capabilities...")
        interface = meshtastic.serial_interface.SerialInterface()
        
        print(f"Interface methods: {[method for method in dir(interface) if not method.startswith('_')]}")
        
        # Check if there's a traceroute method
        if hasattr(interface, 'traceroute'):
            print("✓ Found traceroute method!")
        else:
            print("❌ No direct traceroute method found")
        
        # Check for route discovery methods
        route_methods = [method for method in dir(interface) if 'route' in method.lower()]
        if route_methods:
            print(f"Route-related methods: {route_methods}")
        else:
            print("No route-related methods found")
        
        # Check for mesh-specific methods
        mesh_methods = [method for method in dir(interface) if 'mesh' in method.lower()]
        if mesh_methods:
            print(f"Mesh-related methods: {mesh_methods}")
            
        # Check for node/neighbor discovery
        discovery_methods = [method for method in dir(interface) if any(word in method.lower() for word in ['neighbor', 'discover', 'scan', 'ping'])]
        if discovery_methods:
            print(f"Discovery methods: {discovery_methods}")
        
        print("\n2. Checking message sending capabilities...")
        
        # Check if we can send custom messages/pings
        if hasattr(interface, 'sendText'):
            print("✓ Can send text messages")
        if hasattr(interface, 'sendData'):
            print("✓ Can send data")
        if hasattr(interface, 'sendPosition'):
            print("✓ Can send position")
            
        print("\n3. Checking packet types and portnum options...")
        
        # Try to import packet types
        try:
            from meshtastic import portnums_pb2
            print("Available port numbers:")
            for attr in dir(portnums_pb2):
                if not attr.startswith('_') and attr.isupper():
                    value = getattr(portnums_pb2, attr)
                    print(f"  {attr}: {value}")
        except ImportError:
            print("Could not import portnums_pb2")
            
        # Check for routing-related packet types
        try:
            from meshtastic import mesh_pb2
            print("\nMesh packet types:")
            for attr in dir(mesh_pb2):
                if 'routing' in attr.lower() or 'route' in attr.lower():
                    print(f"  {attr}")
        except ImportError:
            print("Could not import mesh_pb2")
        
        print("\n4. Checking node database for routing info...")
        
        if hasattr(interface, 'nodesByNum') and interface.nodesByNum:
            sample_node = list(interface.nodesByNum.values())[0]
            print(f"Sample node structure: {list(sample_node.keys()) if isinstance(sample_node, dict) else dir(sample_node)}")
            
            # Look for routing-related fields
            if isinstance(sample_node, dict):
                routing_fields = [key for key in sample_node.keys() if 'route' in key.lower() or 'path' in key.lower() or 'next' in key.lower()]
                if routing_fields:
                    print(f"Routing-related fields in nodes: {routing_fields}")
                else:
                    print("No obvious routing fields in node data")
        
        interface.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n=== MESHTASTIC TRACEROUTE ALTERNATIVES ===")
    print("""
    If Meshtastic doesn't have built-in traceroute, we can implement it by:
    
    1. **Ping-based Discovery**: Send ping messages with increasing hop limits
    2. **Custom Traceroute Protocol**: Send special messages that record the path
    3. **Passive Route Learning**: Analyze packet headers to infer routing
    4. **Router Interrogation**: Query intermediate nodes for their routing tables
    
    Key Meshtastic Features to Leverage:
    - hopLimit field in packets (shows remaining hops)
    - SNR/RSSI for direct connection detection  
    - Custom message types for route discovery
    - Node database for known mesh participants
    """)

if __name__ == "__main__":
    research_meshtastic_traceroute()