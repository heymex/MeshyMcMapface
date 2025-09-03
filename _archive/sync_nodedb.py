#!/usr/bin/env python3
"""
Script to sync meshtastic nodedb data to the server
"""

import json
import subprocess
import aiohttp
import asyncio
from datetime import datetime, timezone

async def get_nodedb_data():
    """Get node data from meshtastic command"""
    try:
        # Run meshtastic --info and capture JSON output
        result = subprocess.run(['meshtastic', '--info'], 
                              capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"Meshtastic command failed: {result.stderr}")
            return None
            
        # Parse the output to extract the nodes data
        output = result.stdout
        
        # Look for "Nodes in mesh:" section
        if "Nodes in mesh:" not in output:
            print("No 'Nodes in mesh:' section found in output")
            return None
            
        # Extract the JSON part after "Nodes in mesh:"
        json_start = output.find("Nodes in mesh:") + len("Nodes in mesh:")
        json_part = output[json_start:].strip()
        
        # Find the JSON object (starts with { and ends with })
        brace_count = 0
        json_end = 0
        for i, char in enumerate(json_part):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break
        
        if json_end == 0:
            print("Could not find complete JSON object")
            return None
            
        json_data = json_part[:json_end]
        nodes = json.loads(json_data)
        print(f"Found {len(nodes)} nodes in meshtastic nodedb")
        return nodes
        
    except subprocess.TimeoutExpired:
        print("Meshtastic command timed out")
        return None
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}")
        return None
    except Exception as e:
        print(f"Error getting nodedb data: {e}")
        return None

async def sync_to_server(nodes_data):
    """Send nodedb data to server"""
    if not nodes_data:
        return
        
    payload = {
        'agent_id': 'agent_003',  # Use the configured agent ID
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'nodes': nodes_data
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'http://localhost:8082/api/agent/nodedb',
                headers={'X-API-Key': 'acvrpeyvh1ZbR1ySdlLy25Z9Qvg5Vpnx'},
                json=payload
            ) as response:
                result = await response.json()
                print(f"Server response: {result}")
                
    except Exception as e:
        print(f"Error sending to server: {e}")

async def main():
    print("Syncing meshtastic nodedb to server...")
    nodes_data = await get_nodedb_data()
    if nodes_data:
        await sync_to_server(nodes_data)
        print("Sync completed!")
    else:
        print("No nodedb data to sync")

if __name__ == "__main__":
    asyncio.run(main())