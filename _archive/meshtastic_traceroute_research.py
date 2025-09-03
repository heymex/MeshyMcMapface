#!/usr/bin/env python3
"""
Research existing Meshtastic traceroute functionality
"""

def research_existing_traceroute():
    """Research how to use Meshtastic's built-in traceroute"""
    
    print("=== MESHTASTIC BUILT-IN TRACEROUTE RESEARCH ===\n")
    
    try:
        import meshtastic
        import meshtastic.serial_interface
        
        print("1. Checking for traceroute methods in Meshtastic interface...")
        interface = meshtastic.serial_interface.SerialInterface()
        
        # Look for traceroute-related methods
        methods = [method for method in dir(interface) if not method.startswith('_')]
        traceroute_methods = [m for m in methods if 'trace' in m.lower() or 'route' in m.lower()]
        
        print(f"All interface methods: {methods}")
        print(f"Traceroute-related methods: {traceroute_methods}")
        
        # Check for specific traceroute method
        if hasattr(interface, 'traceroute'):
            print("✓ Found interface.traceroute method!")
            print(f"Traceroute method signature: {interface.traceroute.__doc__}")
        
        # Check for sendData with traceroute packet type
        if hasattr(interface, 'sendData'):
            print("✓ Found interface.sendData - can send custom packets")
            
        print("\n2. Checking for traceroute packet types...")
        
        # Check for traceroute in portnums
        try:
            from meshtastic import portnums_pb2
            portnum_attrs = [attr for attr in dir(portnums_pb2) if not attr.startswith('_')]
            traceroute_ports = [attr for attr in portnum_attrs if 'trace' in attr.lower() or 'route' in attr.lower()]
            print(f"Traceroute-related port numbers: {traceroute_ports}")
            
            # Check for TRACEROUTE_APP specifically
            if hasattr(portnums_pb2, 'TRACEROUTE_APP'):
                print(f"✓ Found TRACEROUTE_APP port: {portnums_pb2.TRACEROUTE_APP}")
        except ImportError:
            print("Could not import portnums_pb2")
        
        # Check for routing-related message types
        try:
            from meshtastic import mesh_pb2
            mesh_attrs = [attr for attr in dir(mesh_pb2) if not attr.startswith('_')]
            routing_attrs = [attr for attr in mesh_attrs if 'route' in attr.lower() or 'trace' in attr.lower()]
            print(f"Routing-related mesh types: {routing_attrs}")
        except ImportError:
            print("Could not import mesh_pb2")
            
        print("\n3. Testing direct traceroute call...")
        
        # Try to call traceroute if it exists
        if hasattr(interface, 'traceroute'):
            print("Attempting to call traceroute method...")
            try:
                # Get a target node to traceroute to
                if hasattr(interface, 'nodesByNum') and interface.nodesByNum:
                    target_node = list(interface.nodesByNum.keys())[0]
                    print(f"Testing traceroute to node: 0x{target_node:08x}")
                    
                    # Try different possible signatures
                    result = interface.traceroute(target_node)
                    print(f"Traceroute result: {result}")
                else:
                    print("No nodes available for traceroute test")
            except Exception as e:
                print(f"Traceroute call failed: {e}")
        
        print("\n4. Checking for command-line traceroute functionality...")
        
        # Check if we can access the CLI functionality
        try:
            import subprocess
            result = subprocess.run(['meshtastic', '--help'], capture_output=True, text=True)
            if 'traceroute' in result.stdout:
                print("✓ CLI traceroute found in help")
                
                # Try to get traceroute help
                trace_help = subprocess.run(['meshtastic', '--traceroute', '--help'], 
                                          capture_output=True, text=True)
                print(f"Traceroute help:\n{trace_help.stdout}")
            else:
                print("No traceroute in CLI help")
        except Exception as e:
            print(f"Could not check CLI: {e}")
        
        interface.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n=== INTEGRATION STRATEGY ===")
    print("""
    If Meshtastic has built-in traceroute, we should:
    
    1. Use the existing traceroute API directly
    2. Parse the traceroute results to get the complete path
    3. Store the results in our network_routes table
    4. Build the topology visualization from real traceroute data
    
    This is much better than reinventing traceroute!
    """)

if __name__ == "__main__":
    research_existing_traceroute()