#!/usr/bin/env python3
"""
Process existing packets to populate missing node data
"""

import asyncio
import aiosqlite
import json
from datetime import datetime, timezone

async def process_packets_to_update_nodes():
    """Process existing packets to extract and update node information"""
    
    db = await aiosqlite.connect('distributed_meshview.db')
    
    # Get all packets with payload data
    cursor = await db.execute('''
        SELECT from_node, type, payload, rssi, snr, timestamp, agent_id
        FROM packets 
        WHERE payload IS NOT NULL
        ORDER BY timestamp DESC
    ''')
    packets = await cursor.fetchall()
    
    print(f"Processing {len(packets)} packets to update node data...")
    
    node_updates = {}
    
    for packet in packets:
        from_node, ptype, payload, rssi, snr, timestamp, agent_id = packet
        
        if from_node not in node_updates:
            node_updates[from_node] = {
                'battery_level': None,
                'rssi': rssi,
                'snr': snr,
                'position_lat': None,
                'position_lon': None,
                'short_name': None,
                'long_name': None,
                'hw_model': None,
                'role': None,
                'last_updated': timestamp,
                'agent_id': agent_id
            }
        
        # Update with more recent data
        if timestamp > node_updates[from_node]['last_updated']:
            node_updates[from_node]['last_updated'] = timestamp
            node_updates[from_node]['agent_id'] = agent_id
            if rssi:
                node_updates[from_node]['rssi'] = rssi
            if snr:
                node_updates[from_node]['snr'] = snr
        
        # Process payload based on packet type
        try:
            if payload:
                payload_data = json.loads(payload) if payload.startswith('{') else payload
                
                if ptype == 'user_info' and isinstance(payload_data, dict):
                    # Extract user info
                    if 'short_name' in payload_data:
                        node_updates[from_node]['short_name'] = payload_data['short_name']
                    if 'long_name' in payload_data:
                        node_updates[from_node]['long_name'] = payload_data['long_name']
                    if 'hw_model' in payload_data:
                        node_updates[from_node]['hw_model'] = payload_data['hw_model']
                    if 'role' in payload_data:
                        node_updates[from_node]['role'] = payload_data['role']
                
                elif ptype == 'position' and isinstance(payload_data, dict):
                    # Extract position info
                    if 'latitude' in payload_data and payload_data['latitude']:
                        node_updates[from_node]['position_lat'] = float(payload_data['latitude'])
                    if 'longitude' in payload_data and payload_data['longitude']:
                        node_updates[from_node]['position_lon'] = float(payload_data['longitude'])
                
                elif ptype == 'telemetry' and isinstance(payload_data, dict):
                    # Extract telemetry info
                    if 'device_metrics' in payload_data:
                        dm = payload_data['device_metrics']
                        if 'battery_level' in dm and dm['battery_level']:
                            node_updates[from_node]['battery_level'] = int(dm['battery_level'])
                
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            # Skip malformed payloads
            continue
    
    print(f"Extracted data for {len(node_updates)} nodes")
    
    # Update nodes table
    updated_count = 0
    for node_id, data in node_updates.items():
        # Update nodes table
        await db.execute('''
            UPDATE nodes 
            SET battery_level = ?, rssi = ?, snr = ?, 
                position_lat = ?, position_lon = ?, updated_at = ?
            WHERE node_id = ?
        ''', (
            data['battery_level'], data['rssi'], data['snr'],
            data['position_lat'], data['position_lon'], 
            data['last_updated'], node_id
        ))
        
        # Update user_info table
        await db.execute('''
            INSERT OR REPLACE INTO user_info 
            (node_id, short_name, long_name, hw_model, role, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            node_id, data['short_name'], data['long_name'], 
            data['hw_model'], data['role'], data['last_updated']
        ))
        
        updated_count += 1
    
    await db.commit()
    await db.close()
    
    print(f"✅ Updated {updated_count} nodes with rich data!")
    print("🌐 Refresh the nodes page to see the improvements!")

if __name__ == "__main__":
    asyncio.run(process_packets_to_update_nodes())