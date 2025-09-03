#!/usr/bin/env python3
"""
Create test traceroute data to demonstrate visualization
"""

import asyncio
import aiosqlite
import json
from datetime import datetime, timezone
import requests
import uuid

async def create_test_data():
    """Create comprehensive test data including agents, nodes, and traceroute data"""
    
    db = await aiosqlite.connect('distributed_meshview.db')
    
    # Test agent data
    test_agents = [
        {
            'agent_id': 'agent_001',
            'location_name': 'Seattle Hub',
            'coordinates': [47.6062, -122.3321],  # Seattle
            'last_seen': datetime.now(timezone.utc).isoformat(),
            'packet_count': 150
        },
        {
            'agent_id': 'agent_002', 
            'location_name': 'Portland Hub',
            'coordinates': [45.5152, -122.6784],  # Portland
            'last_seen': datetime.now(timezone.utc).isoformat(),
            'packet_count': 89
        }
    ]
    
    # Test node data with realistic positions and names
    test_nodes = [
        {
            'node_id': '!12345678',
            'short_name': 'SEA1',
            'long_name': 'Seattle Node 1',
            'lat': 47.6062,
            'lng': -122.3321,
            'hw_model': 'HELTEC_V3',
            'role': 'ROUTER',
            'battery_level': 85,
            'rssi': -75,
            'snr': 8.5
        },
        {
            'node_id': '!23456789',
            'short_name': 'SEA2',
            'long_name': 'Seattle Node 2',
            'lat': 47.6205,
            'lng': -122.3493,
            'hw_model': 'TBEAM',
            'role': 'CLIENT',
            'battery_level': 45,
            'rssi': -82,
            'snr': 6.2
        },
        {
            'node_id': '!34567890',
            'short_name': 'PDX1',
            'long_name': 'Portland Node 1',
            'lat': 45.5152,
            'lng': -122.6784,
            'hw_model': 'HELTEC_V3',
            'role': 'ROUTER',
            'battery_level': 92,
            'rssi': -70,
            'snr': 9.1
        },
        {
            'node_id': '!45678901',
            'short_name': 'MIDW',
            'long_name': 'Midway Repeater',
            'lat': 46.5607,
            'lng': -122.5052,  # Between Seattle and Portland
            'hw_model': 'HELTEC_V2',
            'role': 'REPEATER',
            'battery_level': 15,  # Low battery to test override
            'rssi': -68,
            'snr': 7.8
        },
        {
            'node_id': '!56789012',
            'short_name': 'EAST',
            'long_name': 'Eastern Node',
            'lat': 47.6587,
            'lng': -122.1234,
            'hw_model': 'TBEAM',
            'role': 'CLIENT',
            'battery_level': 78,
            'rssi': -88,
            'snr': 4.5
        }
    ]
    
    # Insert test agents
    for agent in test_agents:
        await db.execute('''
            INSERT OR REPLACE INTO agents 
            (agent_id, location_name, location_lat, location_lon, last_seen, packet_count, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            agent['agent_id'],
            agent['location_name'], 
            agent['coordinates'][0],  # lat
            agent['coordinates'][1],  # lon
            agent['last_seen'],
            agent['packet_count'],
            'active'
        ))
    
    # Insert test nodes
    for node in test_nodes:
        # Insert into nodes table
        await db.execute('''
            INSERT OR REPLACE INTO nodes 
            (node_id, agent_id, last_seen, battery_level, position_lat, position_lon, 
             rssi, snr, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            node['node_id'],
            test_agents[0]['agent_id'],  # Associate with first agent
            datetime.now(timezone.utc).isoformat(),
            node['battery_level'],
            node['lat'],
            node['lng'],
            node['rssi'],
            node['snr'],
            datetime.now(timezone.utc).isoformat()
        ))
        
        # Insert into user_info table
        await db.execute('''
            INSERT OR REPLACE INTO user_info 
            (node_id, short_name, long_name, agent_id, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            node['node_id'],
            node['short_name'],
            node['long_name'], 
            test_agents[0]['agent_id'],
            datetime.now(timezone.utc).isoformat()
        ))
    
    # Create comprehensive traceroute data showing complex network paths
    test_routes = [
        {
            'discovery_id': str(uuid.uuid4()),
            'source_node_id': '!12345678',  # SEA1
            'target_node_id': '!34567890',  # PDX1
            'agent_id': 'agent_001',
            'route_path': ['!12345678', '!45678901', '!34567890'],  # SEA1 -> MIDW -> PDX1
            'hop_count': 2,
            'total_time_ms': 850,
            'discovery_timestamp': datetime.now(timezone.utc).isoformat(),
            'response_timestamp': datetime.now(timezone.utc).isoformat(),
            'success': True
        },
        {
            'discovery_id': str(uuid.uuid4()),
            'source_node_id': '!12345678',  # SEA1
            'target_node_id': '!56789012',  # EAST
            'agent_id': 'agent_001',
            'route_path': ['!12345678', '!23456789', '!56789012'],  # SEA1 -> SEA2 -> EAST
            'hop_count': 2,
            'total_time_ms': 450,
            'discovery_timestamp': datetime.now(timezone.utc).isoformat(),
            'response_timestamp': datetime.now(timezone.utc).isoformat(),
            'success': True
        },
        {
            'discovery_id': str(uuid.uuid4()),
            'source_node_id': '!23456789',  # SEA2
            'target_node_id': '!34567890',  # PDX1
            'agent_id': 'agent_001',
            'route_path': ['!23456789', '!12345678', '!45678901', '!34567890'],  # SEA2 -> SEA1 -> MIDW -> PDX1
            'hop_count': 3,
            'total_time_ms': 1200,
            'discovery_timestamp': datetime.now(timezone.utc).isoformat(),
            'response_timestamp': datetime.now(timezone.utc).isoformat(),
            'success': True
        },
        {
            'discovery_id': str(uuid.uuid4()),
            'source_node_id': '!34567890',  # PDX1
            'target_node_id': '!56789012',  # EAST (long path)
            'agent_id': 'agent_002',
            'route_path': ['!34567890', '!45678901', '!12345678', '!23456789', '!56789012'],  # PDX1 -> MIDW -> SEA1 -> SEA2 -> EAST
            'hop_count': 4,
            'total_time_ms': 2100,
            'discovery_timestamp': datetime.now(timezone.utc).isoformat(),
            'response_timestamp': datetime.now(timezone.utc).isoformat(),
            'success': True
        }
    ]
    
    # Insert traceroute data
    for route in test_routes:
        await db.execute('''
            INSERT INTO network_routes
            (discovery_id, source_node_id, target_node_id, agent_id, route_path,
             hop_count, total_time_ms, discovery_timestamp, response_timestamp, success)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            route['discovery_id'],
            route['source_node_id'],
            route['target_node_id'], 
            route['agent_id'],
            json.dumps(route['route_path']),
            route['hop_count'],
            route['total_time_ms'],
            route['discovery_timestamp'],
            route['response_timestamp'],
            route['success']
        ))
        
        # Create route segments
        for i in range(len(route['route_path']) - 1):
            from_node = route['route_path'][i]
            to_node = route['route_path'][i + 1]
            
            await db.execute('''
                INSERT INTO route_segments
                (discovery_id, from_node_id, to_node_id, segment_order, agent_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                route['discovery_id'],
                from_node,
                to_node,
                i,
                route['agent_id'],
                route['discovery_timestamp']
            ))
    
    # Create some test packet data for connections
    test_packets = [
        {
            'from_node': '!12345678',
            'to_node': '!23456789',
            'type': 'TEXT_MESSAGE_APP',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'agent_id': 'agent_001'
        },
        {
            'from_node': '!23456789',
            'to_node': '!56789012',
            'type': 'POSITION_APP',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'agent_id': 'agent_001'
        },
        {
            'from_node': '!12345678',
            'to_node': '!45678901',
            'type': 'TELEMETRY_APP',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'agent_id': 'agent_001'
        }
    ]
    
    for packet in test_packets:
        await db.execute('''
            INSERT INTO packets
            (from_node, to_node, type, timestamp, agent_id, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            packet['from_node'],
            packet['to_node'],
            packet['type'],
            packet['timestamp'],
            packet['agent_id'],
            '{}'
        ))
    
    await db.commit()
    await db.close()
    
    print("✅ Test data created successfully!")
    print("📍 Agents: Seattle Hub, Portland Hub")
    print("🔗 Nodes: SEA1, SEA2, PDX1, MIDW (low battery), EAST")
    print("🛣️  Routes: 4 traceroute paths showing network topology")
    print("📡 Packets: Connection data between nodes")
    print("")
    print("🌐 View the visualization at: http://localhost:8082/map")

if __name__ == "__main__":
    asyncio.run(create_test_data())