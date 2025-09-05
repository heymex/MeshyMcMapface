#!/usr/bin/env python3
"""
Enhanced MeshyMcMapface Server MVP - Receives data from multiple agents
"""

import asyncio
import aiohttp
from aiohttp import web, web_middlewares
import aiosqlite
import json
import logging
from datetime import datetime, timezone
import configparser
import argparse
from pathlib import Path
import hashlib
import secrets
import sys
from typing import Dict, List, Optional

# Add src directory to Python path for access to logging utilities
sys.path.insert(0, str(Path(__file__).parent / 'src'))

class DistributedMeshyMcMapfaceServer:
    def __init__(self, config_file: str):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        
        # Configuration
        self.bind_host = self.config.get('server', 'host', fallback='localhost')
        self.bind_port = self.config.getint('server', 'port', fallback=8082)
        self.db_path = self.config.get('database', 'path', fallback='distributed_meshview.db')
        
        # API Keys for agents
        self.api_keys = {}
        if self.config.has_section('api_keys'):
            self.api_keys = dict(self.config.items('api_keys'))
        
        # Get logger (logging setup handled by main function)
        self.logger = logging.getLogger(__name__)
        
        # Web app
        self.app = web.Application(middlewares=[self.auth_middleware])
        self.setup_routes()
    
    async def setup_database(self):
        """Initialize SQLite database with tables for distributed data"""
        self.db = await aiosqlite.connect(self.db_path)
        
        # Agents table
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                location_name TEXT,
                location_lat REAL,
                location_lon REAL,
                last_seen TEXT,
                packet_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            )
        ''')
        
        # Enhanced packets table with agent information
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT,
                timestamp TEXT,
                from_node TEXT,
                to_node TEXT,
                packet_id INTEGER,
                channel INTEGER,
                type TEXT,
                payload TEXT,
                rssi INTEGER,
                snr REAL,
                hop_limit INTEGER,
                want_ack BOOLEAN,
                import_time TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES agents (agent_id)
            )
        ''')
        
        # Enhanced nodes table with agent tracking
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT,
                agent_id TEXT,
                last_seen TEXT,
                battery_level INTEGER,
                position_lat REAL,
                position_lon REAL,
                rssi INTEGER,
                snr REAL,
                updated_at TEXT,
                PRIMARY KEY (node_id, agent_id),
                FOREIGN KEY (agent_id) REFERENCES agents (agent_id)
            )
        ''')
        
        # Agent health metrics
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS agent_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT,
                timestamp TEXT,
                packets_received INTEGER,
                nodes_active INTEGER,
                connection_status TEXT,
                FOREIGN KEY (agent_id) REFERENCES agents (agent_id)
            )
        ''')
        
        # User info table for node names and detailed info
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS user_info (
                node_id TEXT PRIMARY KEY,
                short_name TEXT,
                long_name TEXT,
                macaddr TEXT,
                hw_model TEXT,
                role TEXT,
                battery_level INTEGER,
                voltage REAL,
                channel_utilization REAL,
                air_util_tx REAL,
                uptime_seconds INTEGER,
                hops_away INTEGER,
                last_heard INTEGER,
                is_favorite BOOLEAN DEFAULT 0,
                is_licensed BOOLEAN DEFAULT 0,
                last_updated TEXT,
                first_seen_by_agent TEXT,
                data_source TEXT DEFAULT 'packet'
            )
        ''')
        
        # Create indexes for performance
        # Network topology tables for mesh network mapping
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS node_topology (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                hops_away INTEGER,
                snr REAL,
                rssi INTEGER,
                last_heard INTEGER,
                timestamp TEXT NOT NULL,
                UNIQUE(node_id, agent_id) ON CONFLICT REPLACE
            )
        ''')
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS direct_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_node_id TEXT NOT NULL,
                to_node_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                snr REAL,
                rssi INTEGER,
                link_quality REAL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                packet_count INTEGER DEFAULT 1,
                UNIQUE(from_node_id, to_node_id, agent_id) ON CONFLICT REPLACE
            )
        ''')
        
        # Network routes table for complete discovered routes  
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS network_routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discovery_id TEXT NOT NULL,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                route_path TEXT NOT NULL,  -- JSON array of node IDs
                hop_count INTEGER NOT NULL,
                total_time_ms INTEGER,     -- Round-trip time
                discovery_timestamp TEXT NOT NULL,
                response_timestamp TEXT,
                success BOOLEAN DEFAULT FALSE,
                UNIQUE(discovery_id, agent_id) ON CONFLICT REPLACE
            )
        ''')
        
        # Route segments table for individual links in discovered routes
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS route_segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discovery_id TEXT NOT NULL,
                from_node_id TEXT NOT NULL,
                to_node_id TEXT NOT NULL,
                segment_order INTEGER NOT NULL,  -- Position in the route (0, 1, 2...)
                agent_id TEXT NOT NULL,
                link_quality REAL,
                timestamp TEXT NOT NULL,
                UNIQUE(discovery_id, segment_order, agent_id) ON CONFLICT REPLACE
            )
        ''')

        # Create indexes for performance
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_packets_timestamp ON packets(timestamp)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_packets_agent ON packets(agent_id)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_nodes_agent ON nodes(agent_id)')
        
        # Topology table indexes
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_topology_node_agent ON node_topology(node_id, agent_id)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_topology_agent ON node_topology(agent_id)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_topology_timestamp ON node_topology(timestamp)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_connections_from_to ON direct_connections(from_node_id, to_node_id)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_connections_agent ON direct_connections(agent_id)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_connections_last_seen ON direct_connections(last_seen)')
        
        # Route table indexes
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_routes_discovery_id ON network_routes(discovery_id)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_routes_source_target ON network_routes(source_node_id, target_node_id)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_routes_agent ON network_routes(agent_id)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_routes_timestamp ON network_routes(discovery_timestamp)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_segments_discovery_id ON route_segments(discovery_id)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_segments_from_to ON route_segments(from_node_id, to_node_id)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_segments_order ON route_segments(discovery_id, segment_order)')
        
        await self.db.commit()
        self.logger.info("Database initialized")
    
    def setup_routes(self):
        """Setup web routes"""
        # API routes
        self.app.router.add_post('/api/agent/register', self.register_agent)
        self.app.router.add_post('/api/agent/data', self.receive_agent_data)
        self.app.router.add_post('/api/agent/nodedb', self.receive_nodedb_data)
        self.app.router.add_post('/api/agent/routes', self.receive_route_data)
        self.app.router.add_get('/api/agents', self.list_agents)
        self.app.router.add_get('/api/agents/{agent_id}/status', self.agent_status)
        self.app.router.add_get('/api/packets', self.get_packets)
        self.app.router.add_get('/api/nodes', self.get_nodes)
        self.app.router.add_get('/api/nodes/detailed', self.get_nodes_detailed)
        self.app.router.add_get('/api/topology', self.get_topology)
        self.app.router.add_get('/api/connections', self.get_connections)
        self.app.router.add_get('/api/routes', self.get_routes)
        self.app.router.add_get('/api/stats', self.get_stats)
        self.app.router.add_get('/api/debug/agents', self.debug_agents)  # Debug endpoint
        self.app.router.add_get('/api/debug/nodes', self.debug_nodes)  # Debug nodes
        self.app.router.add_get('/api/debug/packets', self.debug_packets)  # Debug packets
        
        # Web UI routes
        self.app.router.add_get('/', self.dashboard)
        self.app.router.add_get('/agents', self.agents_page)
        self.app.router.add_get('/packets', self.packets_page)
        self.app.router.add_get('/nodes', self.nodes_page)
        self.app.router.add_get('/map', self.map_page)
        
        # Static files (CSS, JS) - optional
        try:
            from pathlib import Path
            if Path('static').exists():
                self.app.router.add_static('/static/', path='static/', name='static')
        except Exception as e:
            self.logger.debug(f"Static files directory not found: {e}")
    
    @web_middlewares.middleware
    async def auth_middleware(self, request, handler):
        """Authentication middleware for API endpoints"""
        # Skip auth for debug endpoints and web UI API calls
        if (request.path.startswith('/api/debug/') or 
            request.path in ['/api/agents', '/api/packets', '/api/nodes', '/api/stats'] or
            request.method == 'GET'):
            return await handler(request)
            
        # Require auth for POST endpoints (agent data submission)
        if request.path.startswith('/api/'):
            api_key = request.headers.get('X-API-Key')
            if not api_key or api_key not in self.api_keys.values():
                return web.json_response({'error': 'Invalid API key'}, status=401)
        
        return await handler(request)
    
    async def register_agent(self, request):
        """Register a new agent"""
        try:
            data = await request.json()
            
            agent_id = data['agent_id']
            location_name = data['location']['name']
            location_lat = data['location']['coordinates'][0]
            location_lon = data['location']['coordinates'][1]
            
            await self.db.execute('''
                INSERT OR REPLACE INTO agents 
                (agent_id, location_name, location_lat, location_lon, last_seen, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (agent_id, location_name, location_lat, location_lon, 
                  datetime.now(timezone.utc).isoformat(), 'active'))
            
            await self.db.commit()
            
            self.logger.info(f"Registered agent: {agent_id} at {location_name}")
            return web.json_response({'status': 'success', 'agent_id': agent_id})
            
        except Exception as e:
            self.logger.error(f"Error registering agent: {e}")
            return web.json_response({'error': str(e)}, status=400)
    
    async def receive_agent_data(self, request):
        """Receive data from agent"""
        try:
            data = await request.json()
            
            agent_id = data['agent_id']
            timestamp = data['timestamp']
            packets = data.get('packets', [])
            node_status = data.get('node_status', [])
            
            # Update agent last seen
            await self.db.execute('''
                UPDATE agents 
                SET last_seen = ?, packet_count = packet_count + ?
                WHERE agent_id = ?
            ''', (timestamp, len(packets), agent_id))
            
            # Insert packets and handle user_info
            for packet in packets:
                await self.db.execute('''
                    INSERT INTO packets 
                    (agent_id, timestamp, from_node, to_node, packet_id, channel, 
                     type, payload, rssi, snr, hop_limit, want_ack)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    agent_id, packet['timestamp'], packet.get('from_node'),
                    packet.get('to_node'), packet.get('packet_id'), packet.get('channel'),
                    packet.get('type'), json.dumps(packet.get('payload')),
                    packet.get('rssi'), packet.get('snr'), packet.get('hop_limit'),
                    packet.get('want_ack')
                ))
                
                # Detect direct connections based on signal strength
                from_node = packet.get('from_node')
                to_node = packet.get('to_node')
                rssi = packet.get('rssi')
                snr = packet.get('snr')
                
                # Only process if we have signal data and valid nodes
                if (from_node and to_node and from_node != to_node and 
                    from_node not in ['^all', '^local'] and to_node not in ['^all', '^local'] and
                    (rssi is not None or snr is not None)):
                    
                    # Calculate link quality (higher SNR = better quality)
                    link_quality = None
                    if snr is not None:
                        # Simple quality metric: SNR > 10 = excellent, > 0 = good, < -10 = poor
                        if snr > 10:
                            link_quality = 1.0
                        elif snr > 0:
                            link_quality = 0.8
                        elif snr > -10:
                            link_quality = 0.5
                        else:
                            link_quality = 0.2
                    
                    # Store direct connection (bidirectional - from -> to)
                    await self.db.execute('''
                        INSERT INTO direct_connections 
                        (from_node_id, to_node_id, agent_id, snr, rssi, link_quality, first_seen, last_seen, packet_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                        ON CONFLICT(from_node_id, to_node_id, agent_id) DO UPDATE SET
                            snr = COALESCE(excluded.snr, snr),
                            rssi = COALESCE(excluded.rssi, rssi),
                            link_quality = COALESCE(excluded.link_quality, link_quality),
                            last_seen = excluded.last_seen,
                            packet_count = packet_count + 1
                    ''', (from_node, to_node, agent_id, snr, rssi, link_quality, packet['timestamp'], packet['timestamp']))
                
                # Handle user_info packets to store names
                if packet.get('type') == 'user_info' and packet.get('payload'):
                    payload = packet['payload']
                    node_id = packet.get('from_node')
                    if node_id and isinstance(payload, dict):
                        await self.db.execute('''
                            INSERT OR REPLACE INTO user_info
                            (node_id, short_name, long_name, macaddr, last_updated, first_seen_by_agent)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            node_id,
                            payload.get('short_name', ''),
                            payload.get('long_name', ''),
                            payload.get('macaddr', ''),
                            packet['timestamp'],
                            agent_id
                        ))
            
            # Update node status
            for node in node_status:
                if not node['node_id']:
                    continue
                    
                position_lat, position_lon = None, None
                if node.get('position'):
                    position_lat, position_lon = node['position']
                
                await self.db.execute('''
                    INSERT OR REPLACE INTO nodes
                    (node_id, agent_id, last_seen, battery_level, position_lat, 
                     position_lon, rssi, snr, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    node['node_id'], agent_id, node['last_seen'],
                    node.get('battery_level'), position_lat, position_lon,
                    node.get('rssi'), node.get('snr'), timestamp
                ))
            
            # Record health metrics
            await self.db.execute('''
                INSERT INTO agent_health
                (agent_id, timestamp, packets_received, nodes_active, connection_status)
                VALUES (?, ?, ?, ?, ?)
            ''', (agent_id, timestamp, len(packets), len(node_status), 'connected'))
            
            await self.db.commit()
            
            self.logger.debug(f"Received {len(packets)} packets from {agent_id}")
            return web.json_response({'status': 'success', 'received': len(packets)})
            
        except Exception as e:
            self.logger.error(f"Error receiving agent data: {e}")
            return web.json_response({'error': str(e)}, status=400)
    
    async def receive_nodedb_data(self, request):
        """Receive nodedb data from meshtastic command output"""
        try:
            data = await request.json()
            
            agent_id = data['agent_id']
            timestamp = data['timestamp']
            nodes_data = data.get('nodes', {})
            
            # Update agent last seen
            await self.db.execute('''
                UPDATE agents SET last_seen = ? WHERE agent_id = ?
            ''', (timestamp, agent_id))
            
            # Process each node from meshtastic --info output
            for node_id, node_info in nodes_data.items():
                user = node_info.get('user', {})
                position = node_info.get('position', {})
                device_metrics = node_info.get('deviceMetrics', {})
                
                # Update user_info with rich data
                await self.db.execute('''
                    INSERT OR REPLACE INTO user_info
                    (node_id, short_name, long_name, macaddr, hw_model, role,
                     battery_level, voltage, channel_utilization, air_util_tx,
                     uptime_seconds, hops_away, last_heard, is_favorite, is_licensed,
                     last_updated, first_seen_by_agent, data_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    node_id,
                    user.get('shortName', ''),
                    user.get('longName', ''),
                    user.get('macaddr', ''),
                    user.get('hwModel', ''),
                    user.get('role', ''),
                    device_metrics.get('batteryLevel'),
                    device_metrics.get('voltage'),
                    device_metrics.get('channelUtilization'),
                    device_metrics.get('airUtilTx'),
                    device_metrics.get('uptimeSeconds'),
                    node_info.get('hopsAway'),
                    node_info.get('lastHeard'),
                    node_info.get('isFavorite', False),
                    user.get('isLicensed', False),
                    timestamp,
                    agent_id,
                    'meshtastic_cmd'
                ))
                
                # Also update position if available
                if position.get('latitude') and position.get('longitude'):
                    await self.db.execute('''
                        INSERT OR REPLACE INTO nodes
                        (node_id, agent_id, last_seen, battery_level, position_lat, 
                         position_lon, rssi, snr, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        node_id, agent_id, timestamp,
                        device_metrics.get('batteryLevel'),
                        position.get('latitude'), position.get('longitude'),
                        None, node_info.get('snr'), timestamp
                    ))
            
            # Store topology data in new topology tables
            for node_id, node_info in nodes_data.items():
                # Store per-agent topology data
                await self.db.execute('''
                    INSERT OR REPLACE INTO node_topology
                    (node_id, agent_id, hops_away, snr, rssi, last_heard, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    node_id,
                    agent_id,
                    node_info.get('hopsAway'),
                    node_info.get('snr'),
                    None,  # rssi not available in nodedb data
                    node_info.get('lastHeard'),
                    timestamp
                ))
            
            await self.db.commit()
            
            self.logger.info(f"Updated nodedb data for {len(nodes_data)} nodes from {agent_id}")
            self.logger.info(f"Stored topology data for {len(nodes_data)} node-agent relationships")
            return web.json_response({'status': 'success', 'updated': len(nodes_data)})
            
        except Exception as e:
            self.logger.error(f"Error receiving nodedb data: {e}")
            return web.json_response({'error': str(e)}, status=400)

    async def receive_route_data(self, request):
        """Receive route discovery data from agents"""
        try:
            data = await request.json()
            
            agent_id = data['agent_id']
            timestamp = data['timestamp']
            routes = data.get('routes', [])
            discovery_type = data.get('discovery_type', 'unknown')
            
            # Update agent last seen
            await self.db.execute('''
                UPDATE agents SET last_seen = ? WHERE agent_id = ?
            ''', (timestamp, agent_id))
            
            # Process each discovered route
            for route in routes:
                discovery_id = route.get('discovery_id')
                source_node_id = route.get('source_node_id')
                target_node_id = route.get('target_node_id')
                route_path = route.get('route_path', [])
                hop_count = route.get('hop_count', 0)
                total_time_ms = route.get('total_time_ms')
                discovery_timestamp = route.get('discovery_timestamp')
                response_timestamp = route.get('response_timestamp')
                success = route.get('success', False)
                channel_index = route.get('channel_index', 0)
                snr_towards = route.get('snr_towards', [])
                snr_back = route.get('snr_back', [])
                route_back = route.get('route_back', [])
                discovery_method = route.get('discovery_method', discovery_type)
                
                # Store the complete route
                await self.db.execute('''
                    INSERT OR REPLACE INTO network_routes
                    (discovery_id, source_node_id, target_node_id, agent_id, route_path,
                     hop_count, total_time_ms, discovery_timestamp, response_timestamp, success)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    discovery_id, source_node_id, target_node_id, agent_id,
                    json.dumps(route_path), hop_count, total_time_ms,
                    discovery_timestamp, response_timestamp, success
                ))
                
                # Store individual route segments for forward path
                for i in range(len(route_path) - 1):
                    from_node = route_path[i]
                    to_node = route_path[i + 1]
                    snr_value = snr_towards[i] if i < len(snr_towards) else None
                    
                    await self.db.execute('''
                        INSERT OR REPLACE INTO route_segments
                        (discovery_id, from_node_id, to_node_id, segment_order,
                         agent_id, timestamp, link_quality)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        discovery_id, from_node, to_node, i,
                        agent_id, timestamp, snr_value
                    ))
                
                # Store return route segments if available (with separate discovery_id)
                if route_back:
                    for i in range(len(route_back) - 1):
                        from_node = route_back[i]
                        to_node = route_back[i + 1]
                        snr_value = snr_back[i] if i < len(snr_back) else None
                        
                        await self.db.execute('''
                            INSERT OR REPLACE INTO route_segments
                            (discovery_id, from_node_id, to_node_id, segment_order,
                             agent_id, timestamp, link_quality)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            f"{discovery_id}_back", from_node, to_node, i,
                            agent_id, timestamp, snr_value
                        ))
            
            await self.db.commit()
            
            self.logger.info(f"Stored {len(routes)} routes from {agent_id} using {discovery_type}")
            return web.json_response({'status': 'success', 'routes_stored': len(routes)})
            
        except Exception as e:
            self.logger.error(f"Error receiving route data: {e}")
            return web.json_response({'error': str(e)}, status=400)
    
    async def list_agents(self, request):
        """List all registered agents"""
        try:
            cursor = await self.db.execute('''
                SELECT agent_id, location_name, location_lat, location_lon, 
                       last_seen, packet_count, status
                FROM agents
                ORDER BY last_seen DESC
            ''')
            agents = await cursor.fetchall()
            
            result = []
            for agent in agents:
                result.append({
                    'agent_id': agent[0],
                    'location_name': agent[1],
                    'coordinates': [agent[2], agent[3]],
                    'last_seen': agent[4],
                    'packet_count': agent[5],
                    'status': agent[6]
                })
            
            return web.json_response({'agents': result})
            
        except Exception as e:
            self.logger.error(f"Error listing agents: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def agent_status(self, request):
        """Get detailed status for a specific agent"""
        try:
            agent_id = request.match_info['agent_id']
            
            # Get agent info
            cursor = await self.db.execute('''
                SELECT * FROM agents WHERE agent_id = ?
            ''', (agent_id,))
            agent = await cursor.fetchone()
            
            if not agent:
                return web.json_response({'error': 'Agent not found'}, status=404)
            
            # Get recent health metrics
            cursor = await self.db.execute('''
                SELECT * FROM agent_health 
                WHERE agent_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 10
            ''', (agent_id,))
            health = await cursor.fetchall()
            
            # Get active nodes
            cursor = await self.db.execute('''
                SELECT COUNT(*) FROM nodes 
                WHERE agent_id = ? AND datetime(updated_at) > datetime('now', '-1 hour')
            ''', (agent_id,))
            active_nodes = await cursor.fetchone()
            
            result = {
                'agent_id': agent[0],
                'location_name': agent[1],
                'coordinates': [agent[2], agent[3]],
                'last_seen': agent[4],
                'packet_count': agent[5],
                'status': agent[6],
                'active_nodes': active_nodes[0] if active_nodes else 0,
                'recent_health': [
                    {
                        'timestamp': h[2],
                        'packets_received': h[3],
                        'nodes_active': h[4],
                        'connection_status': h[5]
                    } for h in health
                ]
            }
            
            return web.json_response(result)
            
        except Exception as e:
            self.logger.error(f"Error getting agent status: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def debug_agents(self, request):
        """Debug endpoint to check agents in database"""
        try:
            cursor = await self.db.execute('SELECT * FROM agents')
            agents = await cursor.fetchall()
            
            self.logger.info(f"Debug: Found {len(agents)} agents in database")
            for agent in agents:
                self.logger.info(f"Debug: Agent {agent}")
            
            return web.json_response({
                'count': len(agents),
                'agents': [
                    {
                        'agent_id': a[0],
                        'location_name': a[1], 
                        'location_lat': a[2],
                        'location_lon': a[3],
                        'last_seen': a[4],
                        'packet_count': a[5],
                        'status': a[6]
                    } for a in agents
                ]
            })
            
        except Exception as e:
            self.logger.error(f"Error in debug endpoint: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def debug_nodes(self, request):
        """Debug endpoint to check nodes in database"""
        try:
            cursor = await self.db.execute('SELECT * FROM nodes')
            nodes = await cursor.fetchall()
            
            self.logger.info(f"Debug: Found {len(nodes)} nodes in database")
            for node in nodes:
                self.logger.info(f"Debug: Node {node}")
            
            return web.json_response({
                'count': len(nodes),
                'nodes': [
                    {
                        'node_id': n[0],
                        'agent_id': n[1],
                        'last_seen': n[2],
                        'battery_level': n[3],
                        'position_lat': n[4],
                        'position_lon': n[5],
                        'rssi': n[6],
                        'snr': n[7],
                        'updated_at': n[8]
                    } for n in nodes
                ]
            })
            
        except Exception as e:
            self.logger.error(f"Error in debug nodes endpoint: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def debug_packets(self, request):
        """Debug endpoint to check recent packets"""
        try:
            cursor = await self.db.execute('''
                SELECT * FROM packets 
                ORDER BY timestamp DESC 
                LIMIT 20
            ''')
            packets = await cursor.fetchall()
            
            self.logger.info(f"Debug: Found {len(packets)} recent packets in database")
            
            return web.json_response({
                'count': len(packets),
                'packets': [
                    {
                        'id': p[0],
                        'agent_id': p[1],
                        'timestamp': p[2],
                        'from_node': p[3],
                        'to_node': p[4],
                        'type': p[7],
                        'rssi': p[9],
                        'snr': p[10]
                    } for p in packets
                ]
            })
            
        except Exception as e:
            self.logger.error(f"Error in debug packets endpoint: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def get_packets(self, request):
        """Get recent packets with filtering options"""
        try:
            # Parse query parameters
            limit = int(request.query.get('limit', 100))
            agent_id = request.query.get('agent_id')
            packet_type = request.query.get('type')
            hours = int(request.query.get('hours', 72))
            
            # Build query with node name information - explicit column order
            query = '''
                SELECT p.id, p.agent_id, p.timestamp, p.from_node, p.to_node, 
                       p.packet_id, p.channel, p.type, p.payload, p.rssi, p.snr, 
                       p.hop_limit, p.want_ack,
                       a.location_name,
                       uf.short_name as from_short_name, uf.long_name as from_long_name, 
                       uf.hw_model as from_hw_model, uf.role as from_role,
                       ut.short_name as to_short_name, ut.long_name as to_long_name,
                       ut.hw_model as to_hw_model, ut.role as to_role,
                       uf.hops_away as from_hops_away, ut.hops_away as to_hops_away
                FROM packets p
                JOIN agents a ON p.agent_id = a.agent_id
                LEFT JOIN user_info uf ON p.from_node = uf.node_id
                LEFT JOIN user_info ut ON p.to_node = ut.node_id
                WHERE datetime(p.timestamp) > datetime('now', '-{} hours')
            '''.format(hours)
            params = []
            
            if agent_id and agent_id != 'all':
                query += ' AND p.agent_id = ?'
                params.append(agent_id)
            
            if packet_type:
                query += ' AND p.type = ?'
                params.append(packet_type)
            
            query += ' ORDER BY p.timestamp DESC LIMIT ?'
            params.append(limit)
            
            cursor = await self.db.execute(query, params)
            packets = await cursor.fetchall()
            
            result = []
            for packet in packets:
                # New column indices based on explicit SELECT:
                # 0=id, 1=agent_id, 2=timestamp, 3=from_node, 4=to_node, 
                # 5=packet_id, 6=channel, 7=type, 8=payload, 9=rssi, 10=snr, 
                # 11=hop_limit, 12=want_ack, 13=location_name,
                # 14=from_short_name, 15=from_long_name, 16=from_hw_model, 17=from_role,
                # 18=to_short_name, 19=to_long_name, 20=to_hw_model, 21=to_role,
                # 22=from_hops_away, 23=to_hops_away
                
                # Format from_node with name
                from_display = packet[3]  # from_node ID
                if packet[14] and packet[15]:  # from_short_name and from_long_name
                    from_display = f"{packet[14]} ({packet[15]})"
                elif packet[14]:  # just short_name
                    from_display = f"{packet[14]} ({packet[3]})"
                elif packet[15]:  # just long_name
                    from_display = f"{packet[15]} ({packet[3]})"
                
                # Format to_node with name
                to_display = packet[4] if packet[4] else 'Broadcast'  # to_node ID
                if packet[4] and packet[18] and packet[19]:  # to_short_name and to_long_name
                    to_display = f"{packet[18]} ({packet[19]})"
                elif packet[4] and packet[18]:  # just short_name
                    to_display = f"{packet[18]} ({packet[4]})"
                elif packet[4] and packet[19]:  # just long_name
                    to_display = f"{packet[19]} ({packet[4]})"
                
                result.append({
                    'id': packet[0],
                    'agent_id': packet[1],
                    'agent_location': packet[13],
                    'timestamp': packet[2],
                    'from_node': packet[3],
                    'from_node_display': from_display,
                    'from_hw_model': packet[16],
                    'from_role': packet[17],
                    'from_hops': packet[22],  # from hops_away
                    'to_node': packet[4],
                    'to_node_display': to_display,
                    'to_hw_model': packet[20],
                    'to_role': packet[21],
                    'to_hops': packet[23],  # to hops_away
                    'type': packet[7],
                    'payload': json.loads(packet[8]) if packet[8] else None,
                    'rssi': packet[9],
                    'snr': packet[10]
                })
            
            return web.json_response({'packets': result})
            
        except Exception as e:
            self.logger.error(f"Error getting packets: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def get_nodes(self, request):
        """Get node information across all agents"""
        try:
            agent_id = request.query.get('agent_id')
            hours = int(request.query.get('hours', 72))
            
            # Build query
            query = '''
                SELECT n.node_id, n.agent_id, a.location_name, n.last_seen,
                       n.battery_level, n.position_lat, n.position_lon,
                       n.rssi, n.snr, n.updated_at
                FROM nodes n
                JOIN agents a ON n.agent_id = a.agent_id
                WHERE datetime(n.updated_at) > datetime('now', '-{} hours')
            '''.format(hours)
            params = []
            
            if agent_id and agent_id != 'all':
                query += ' AND n.agent_id = ?'
                params.append(agent_id)
            
            query += ' ORDER BY n.updated_at DESC'
            
            cursor = await self.db.execute(query, params)
            nodes = await cursor.fetchall()
            
            result = []
            for node in nodes:
                result.append({
                    'node_id': node[0],
                    'agent_id': node[1],
                    'agent_location': node[2],
                    'last_seen': node[3],
                    'battery_level': node[4],
                    'position': [node[5], node[6]] if node[5] and node[6] else None,
                    'rssi': node[7],
                    'snr': node[8],
                    'updated_at': node[9]
                })
            
            return web.json_response({'nodes': result})
            
        except Exception as e:
            self.logger.error(f"Error getting nodes: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def get_nodes_detailed(self, request):
        """Get detailed node information with packet history and user info - OPTIMIZED"""
        try:
            hours = int(request.query.get('hours', 72))
            limit = int(request.query.get('limit', 50))  # Reduced default limit
            
            # OPTIMIZATION: Single query to get all nodes with basic info
            nodes_query = '''
                SELECT n.node_id, 
                       u.short_name, u.long_name, u.macaddr, u.hw_model, u.role,
                       COALESCE(u.battery_level, n.battery_level) as battery_level,
                       n.position_lat, n.position_lon,
                       n.rssi, n.snr, n.updated_at,
                       u.voltage, u.channel_utilization, u.air_util_tx, u.uptime_seconds, u.hops_away
                FROM nodes n
                LEFT JOIN user_info u ON n.node_id = u.node_id
                WHERE datetime(n.updated_at) > datetime('now', '-{} hours')
                ORDER BY n.updated_at DESC
                LIMIT ?
            '''.format(hours)
            
            cursor = await self.db.execute(nodes_query, (limit,))
            nodes = await cursor.fetchall()
            
            if not nodes:
                return web.json_response({'nodes': []})
            
            # Get all node IDs for batch queries
            node_ids = [node[0] for node in nodes]
            node_ids_placeholder = ','.join(['?' for _ in node_ids])
            
            # OPTIMIZATION: Batch query for packet counts
            packet_counts_query = '''
                SELECT p.from_node, 
                       COUNT(*) as packet_count,
                       COUNT(DISTINCT p.agent_id) as agent_count,
                       GROUP_CONCAT(DISTINCT a.location_name) as seeing_agents
                FROM packets p
                JOIN agents a ON p.agent_id = a.agent_id
                WHERE p.from_node IN ({}) 
                AND datetime(p.timestamp) > datetime('now', '-{} hours')
                GROUP BY p.from_node
            '''.format(node_ids_placeholder, hours)
            
            packet_cursor = await self.db.execute(packet_counts_query, node_ids)
            packet_data = {row[0]: row[1:] for row in await packet_cursor.fetchall()}
            
            # OPTIMIZATION: Batch query for routes (simplified - only get best routes)
            routes_query = '''
                SELECT r.target_node_id, r.agent_id, r.hop_count, r.route_path, 
                       r.discovery_timestamp, a.location_name, a.agent_id as agent_short_id
                FROM network_routes r
                JOIN agents a ON r.agent_id = a.agent_id
                WHERE r.target_node_id IN ({})
                AND r.success = 1
                AND datetime(r.discovery_timestamp) > datetime('now', '-{} hours')
                GROUP BY r.target_node_id, r.agent_id
                HAVING r.discovery_timestamp = MAX(r.discovery_timestamp)
            '''.format(node_ids_placeholder, hours)
            
            routes_cursor = await self.db.execute(routes_query, node_ids)
            routes_data = {}
            for row in await routes_cursor.fetchall():
                node_id = row[0]
                if node_id not in routes_data:
                    routes_data[node_id] = []
                
                route_path = json.loads(row[3]) if row[3] else []
                routes_data[node_id].append({
                    'agent_id': row[6],
                    'location_name': row[5],
                    'hop_count': row[2],
                    'route_path': route_path,
                    'discovery_timestamp': row[4],
                    'route_type': 'traceroute'
                })
            
            # OPTIMIZATION: Skip individual packet queries - just get counts above
            
            # Build result efficiently
            result = []
            for node in nodes:
                node_id = node[0]
                
                # Get packet data from batch query
                pkt_data = packet_data.get(node_id, (0, 0, ''))
                
                node_data = {
                    'node_id': node_id,
                    'short_name': node[1] or '',
                    'long_name': node[2] or '',
                    'macaddr': node[3] or '',
                    'hw_model': node[4] or '',
                    'role': node[5] or '',
                    'battery_level': node[6],
                    'position': [node[7], node[8]] if node[7] and node[8] else None,
                    'rssi': node[9],
                    'snr': node[10],
                    'updated_at': node[11],
                    'voltage': node[12],
                    'channel_utilization': node[13],
                    'air_util_tx': node[14],
                    'uptime_seconds': node[15],
                    'hops_away': node[16],
                    'packet_count': pkt_data[0],
                    'agent_count': pkt_data[1],
                    'seeing_agents': pkt_data[2].split(',') if pkt_data[2] else [],
                    'agent_routes': {route['agent_id']: route for route in routes_data.get(node_id, [])},
                    'recent_packets': []  # Simplified - removed individual packet queries for performance
                }
                
                result.append(node_data)
            
            return web.json_response({'nodes': result})
            
        except Exception as e:
            self.logger.error(f"Error getting detailed nodes: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def get_stats(self, request):
        """Get overall system statistics"""
        try:
            # Total agents
            cursor = await self.db.execute('SELECT COUNT(*) FROM agents')
            total_agents = (await cursor.fetchone())[0]
            
            # Active agents (seen in last hour)
            cursor = await self.db.execute('''
                SELECT COUNT(*) FROM agents 
                WHERE datetime(last_seen) > datetime('now', '-1 hour')
            ''')
            active_agents = (await cursor.fetchone())[0]
            
            # Total packets
            cursor = await self.db.execute('SELECT COUNT(*) FROM packets')
            total_packets = (await cursor.fetchone())[0]
            
            # Packets in last hour
            cursor = await self.db.execute('''
                SELECT COUNT(*) FROM packets 
                WHERE datetime(timestamp) > datetime('now', '-1 hour')
            ''')
            recent_packets = (await cursor.fetchone())[0]
            
            # Total unique nodes
            cursor = await self.db.execute('SELECT COUNT(DISTINCT node_id) FROM nodes')
            total_nodes = (await cursor.fetchone())[0]
            
            # Active nodes (seen in last hour)
            cursor = await self.db.execute('''
                SELECT COUNT(DISTINCT node_id) FROM nodes 
                WHERE datetime(updated_at) > datetime('now', '-1 hour')
            ''')
            active_nodes = (await cursor.fetchone())[0]
            
            # Packet types breakdown
            cursor = await self.db.execute('''
                SELECT type, COUNT(*) 
                FROM packets 
                WHERE datetime(timestamp) > datetime('now', '-24 hours')
                GROUP BY type
                ORDER BY COUNT(*) DESC
            ''')
            packet_types = await cursor.fetchall()
            
            result = {
                'agents': {
                    'total': total_agents,
                    'active': active_agents
                },
                'packets': {
                    'total': total_packets,
                    'recent_hour': recent_packets
                },
                'nodes': {
                    'total': total_nodes,
                    'active': active_nodes
                },
                'packet_types': [
                    {'type': pt[0], 'count': pt[1]} 
                    for pt in packet_types
                ]
            }
            
            return web.json_response(result)
            
        except Exception as e:
            self.logger.error(f"Error getting stats: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def get_topology(self, request):
        """Get network topology data showing hops from each agent to each node"""
        try:
            agent_id = request.query.get('agent_id')
            hours = int(request.query.get('hours', 24))
            
            query = '''
                SELECT nt.node_id, nt.agent_id, nt.hops_away, nt.snr, nt.rssi,
                       nt.last_heard, nt.timestamp,
                       u.short_name, u.long_name, u.hw_model,
                       a.location_name as agent_location
                FROM node_topology nt
                LEFT JOIN user_info u ON nt.node_id = u.node_id
                LEFT JOIN agents a ON nt.agent_id = a.agent_id
                WHERE datetime(nt.timestamp) > datetime('now', '-{} hours')
            '''.format(hours)
            
            params = []
            if agent_id and agent_id != 'all':
                query += ' AND nt.agent_id = ?'
                params.append(agent_id)
            
            query += ' ORDER BY nt.node_id, nt.agent_id'
            
            cursor = await self.db.execute(query, params)
            rows = await cursor.fetchall()
            
            # Group by node_id
            topology = {}
            for row in rows:
                node_id = row[0]
                if node_id not in topology:
                    topology[node_id] = {
                        'node_id': node_id,
                        'short_name': row[7],
                        'long_name': row[8],
                        'hw_model': row[9],
                        'agents': {}
                    }
                
                agent_id = row[1]
                topology[node_id]['agents'][agent_id] = {
                    'agent_id': agent_id,
                    'agent_location': row[10],
                    'hops_away': row[2],
                    'snr': row[3],
                    'rssi': row[4],
                    'last_heard': row[5],
                    'timestamp': row[6]
                }
            
            return web.json_response({'topology': list(topology.values())})
            
        except Exception as e:
            self.logger.error(f"Error getting topology: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def get_connections(self, request):
        """Get direct connections between nodes for network graph visualization"""
        try:
            agent_id = request.query.get('agent_id')
            hours = int(request.query.get('hours', 24))
            min_quality = float(request.query.get('min_quality', 0.0))
            
            query = '''
                SELECT dc.from_node_id, dc.to_node_id, dc.agent_id,
                       dc.snr, dc.rssi, dc.link_quality,
                       dc.first_seen, dc.last_seen, dc.packet_count,
                       uf.short_name as from_name, uf.long_name as from_long_name,
                       ut.short_name as to_name, ut.long_name as to_long_name,
                       a.location_name as agent_location
                FROM direct_connections dc
                LEFT JOIN user_info uf ON dc.from_node_id = uf.node_id
                LEFT JOIN user_info ut ON dc.to_node_id = ut.node_id
                LEFT JOIN agents a ON dc.agent_id = a.agent_id
                WHERE datetime(dc.last_seen) > datetime('now', '-{} hours')
                  AND (dc.link_quality IS NULL OR dc.link_quality >= ?)
            '''.format(hours)
            
            params = [min_quality]
            if agent_id and agent_id != 'all':
                query += ' AND dc.agent_id = ?'
                params.append(agent_id)
            
            query += ' ORDER BY dc.link_quality DESC, dc.packet_count DESC'
            
            cursor = await self.db.execute(query, params)
            rows = await cursor.fetchall()
            
            connections = []
            for row in rows:
                connections.append({
                    'from_node_id': row[0],
                    'to_node_id': row[1],
                    'agent_id': row[2],
                    'snr': row[3],
                    'rssi': row[4],
                    'link_quality': row[5],
                    'first_seen': row[6],
                    'last_seen': row[7],
                    'packet_count': row[8],
                    'from_name': row[9],
                    'from_long_name': row[10],
                    'to_name': row[11],
                    'to_long_name': row[12],
                    'agent_location': row[13]
                })
            
            return web.json_response({'connections': connections})
            
        except Exception as e:
            self.logger.error(f"Error getting connections: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def get_routes(self, request):
        """Get discovered network routes for graph analysis"""
        try:
            agent_id = request.query.get('agent_id')
            source_node = request.query.get('source_node')
            target_node = request.query.get('target_node')
            hours = int(request.query.get('hours', 24))
            successful_only = request.query.get('successful_only', 'true').lower() == 'true'
            
            query = '''
                SELECT nr.discovery_id, nr.source_node_id, nr.target_node_id, 
                       nr.agent_id, nr.route_path, nr.hop_count,
                       nr.total_time_ms, nr.discovery_timestamp, nr.response_timestamp,
                       nr.success,
                       us.short_name as source_name, us.long_name as source_long_name,
                       ut.short_name as target_name, ut.long_name as target_long_name,
                       a.location_name as agent_location
                FROM network_routes nr
                LEFT JOIN user_info us ON nr.source_node_id = us.node_id
                LEFT JOIN user_info ut ON nr.target_node_id = ut.node_id
                LEFT JOIN agents a ON nr.agent_id = a.agent_id
                WHERE datetime(nr.discovery_timestamp) > datetime('now', '-{} hours')
            '''.format(hours)
            
            params = []
            
            if successful_only:
                query += ' AND nr.success = 1'
            
            if agent_id and agent_id != 'all':
                query += ' AND nr.agent_id = ?'
                params.append(agent_id)
                
            if source_node:
                query += ' AND nr.source_node_id = ?'
                params.append(source_node)
                
            if target_node:
                query += ' AND nr.target_node_id = ?'
                params.append(target_node)
            
            query += ' ORDER BY nr.discovery_timestamp DESC, nr.hop_count ASC'
            
            cursor = await self.db.execute(query, params)
            rows = await cursor.fetchall()
            
            routes = []
            for row in rows:
                # Parse the JSON route path
                route_path = []
                try:
                    import json
                    route_path = json.loads(row[4]) if row[4] else []
                except:
                    route_path = []
                
                routes.append({
                    'discovery_id': row[0],
                    'source_node_id': row[1],
                    'target_node_id': row[2],
                    'agent_id': row[3],
                    'route_path': route_path,
                    'hop_count': row[5],
                    'total_time_ms': row[6],
                    'discovery_timestamp': row[7],
                    'response_timestamp': row[8],
                    'success': bool(row[9]),
                    'source_name': row[10],
                    'source_long_name': row[11],
                    'target_name': row[12],
                    'target_long_name': row[13],
                    'agent_location': row[14]
                })
            
            return web.json_response({'routes': routes})
            
        except Exception as e:
            self.logger.error(f"Error getting routes: {e}")
            return web.json_response({'error': str(e)}, status=500)
    
    async def dashboard(self, request):
        """Main dashboard page"""
        html = '''
<!DOCTYPE html>
<html>
<head>
    <title>MeshyMcMapface Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        /* CSS Custom Properties for Light/Dark themes */
        :root {
            --bg-primary: #f5f5f5;
            --bg-secondary: white;
            --bg-tertiary: #f8f9fa;
            --text-primary: #333;
            --text-secondary: #666;
            --border-color: #ddd;
            --shadow-color: rgba(0,0,0,0.1);
            --accent-color: #2196F3;
            --accent-hover: #e3f2fd;
            --success-color: #4CAF50;
            --error-color: #f44336;
        }
        
        [data-theme="dark"] {
            --bg-primary: #121212;
            --bg-secondary: #1e1e1e;
            --bg-tertiary: #2d2d2d;
            --text-primary: #e0e0e0;
            --text-secondary: #b0b0b0;
            --border-color: #404040;
            --shadow-color: rgba(0,0,0,0.3);
            --accent-color: #64b5f6;
            --accent-hover: #1e3a5f;
            --success-color: #66bb6a;
            --error-color: #ef5350;
        }

        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: var(--bg-primary); color: var(--text-primary); }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: var(--bg-secondary); padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px var(--shadow-color); }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .stat-card { background: var(--bg-secondary); padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px var(--shadow-color); text-align: center; }
        .stat-number { font-size: 2em; font-weight: bold; color: var(--accent-color); }
        .stat-label { color: var(--text-secondary); margin-top: 5px; }
        .section { background: var(--bg-secondary); padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px var(--shadow-color); }
        .section h2 { margin-top: 0; color: var(--text-primary); }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 10px; text-align: left; border-bottom: 1px solid var(--border-color); color: var(--text-primary); }
        .table th { background: var(--bg-tertiary); }
        .status-active { color: var(--success-color); font-weight: bold; }
        .status-inactive { color: var(--error-color); }
        .nav { display: flex; gap: 20px; margin-bottom: 20px; align-items: center; }
        .nav a { color: var(--accent-color); text-decoration: none; padding: 10px 20px; background: var(--bg-secondary); border-radius: 4px; }
        .nav a:hover { background: var(--accent-hover); }
        
        /* Dark mode toggle */
        .theme-toggle {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-left: auto;
        }
        .theme-toggle:hover {
            background: var(--accent-hover);
        }
    </style>
    <script>
        // Theme initialization - must run before page renders to avoid flash
        (function() {
            const theme = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', theme);
        })();
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>MeshyMcMapface Dashboard</h1>
            <p>Real-time monitoring of distributed Meshtastic mesh networks</p>
        </div>
        
        <div class="nav">
            <a href="/">Dashboard</a>
            <a href="/agents">Agents</a>
            <a href="/packets">Packets</a>
            <a href="/nodes">Nodes</a>
            <a href="/map">Map</a>
            <button class="theme-toggle" onclick="toggleTheme()" id="theme-toggle">🌙 Dark</button>
        </div>
        
        <div class="stats-grid" id="stats-grid">
            <div class="stat-card">
                <div class="stat-number" id="total-agents">-</div>
                <div class="stat-label">Total Agents</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="active-agents">-</div>
                <div class="stat-label">Active Agents</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="total-packets">-</div>
                <div class="stat-label">Total Packets</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="recent-packets">-</div>
                <div class="stat-label">Last Hour</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="total-nodes">-</div>
                <div class="stat-label">Total Nodes</div>
            </div>
            <div class="stat-card">
                <div class="stat-number" id="active-nodes">-</div>
                <div class="stat-label">Active Nodes</div>
            </div>
        </div>
        
        <div class="section">
            <h2>Recent Agents</h2>
            <table class="table" id="agents-table">
                <thead>
                    <tr>
                        <th>Agent ID</th>
                        <th>Location</th>
                        <th>Last Seen</th>
                        <th>Packets</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
        
        <div class="section">
            <h2>Recent Packets</h2>
            <table class="table" id="packets-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Agent</th>
                        <th>From</th>
                        <th>Type</th>
                        <th>RSSI</th>
                        <th>SNR</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
    </div>
    
    <script>
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                
                document.getElementById('total-agents').textContent = data.agents.total;
                document.getElementById('active-agents').textContent = data.agents.active;
                document.getElementById('total-packets').textContent = data.packets.total;
                document.getElementById('recent-packets').textContent = data.packets.recent_hour;
                document.getElementById('total-nodes').textContent = data.nodes.total;
                document.getElementById('active-nodes').textContent = data.nodes.active;
            } catch (error) {
                console.error('Error loading stats:', error);
            }
        }
        
        async function loadAgents() {
            try {
                console.log('Loading agents for dashboard...');
                const response = await fetch('/api/agents');
                console.log('Dashboard agents response:', response.status);
                
                if (!response.ok) {
                    console.error('Failed to fetch agents for dashboard:', response.status);
                    return;
                }
                
                const data = await response.json();
                console.log('Dashboard agents data:', data);
                
                const tbody = document.querySelector('#agents-table tbody');
                tbody.innerHTML = '';
                
                if (!data.agents || data.agents.length === 0) {
                    const row = tbody.insertRow();
                    row.innerHTML = '<td colspan="5" style="text-align: center;">No agents registered</td>';
                    return;
                }
                
                data.agents.slice(0, 10).forEach(agent => {
                    const row = tbody.insertRow();
                    const lastSeen = new Date(agent.last_seen).toLocaleString();
                    const isActive = new Date() - new Date(agent.last_seen) < 60 * 60 * 1000;
                    
                    row.innerHTML = `
                        <td>${agent.agent_id}</td>
                        <td>${agent.location_name}</td>
                        <td>${lastSeen}</td>
                        <td>${agent.packet_count}</td>
                        <td class="${isActive ? 'status-active' : 'status-inactive'}">
                            ${isActive ? 'Active' : 'Inactive'}
                        </td>
                    `;
                });
            } catch (error) {
                console.error('Error loading agents for dashboard:', error);
            }
        }
        
        async function loadRecentPackets() {
            try {
                const response = await fetch('/api/packets?limit=20');
                const data = await response.json();
                
                const tbody = document.querySelector('#packets-table tbody');
                tbody.innerHTML = '';
                
                data.packets.forEach(packet => {
                    const row = tbody.insertRow();
                    const timestamp = new Date(packet.timestamp).toLocaleString();
                    
                    row.innerHTML = `
                        <td>${timestamp}</td>
                        <td>${packet.agent_location}</td>
                        <td>${packet.from_node}</td>
                        <td>${packet.type}</td>
                        <td>${packet.rssi || '-'}</td>
                        <td>${packet.snr || '-'}</td>
                    `;
                });
            } catch (error) {
                console.error('Error loading packets:', error);
            }
        }
        
        // Theme toggle functions
        function toggleTheme() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme') || 'light';
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeToggleText(newTheme);
        }
        
        function updateThemeToggleText(theme) {
            const toggle = document.getElementById('theme-toggle');
            if (toggle) {
                toggle.textContent = theme === 'light' ? '🌙 Dark' : '☀️ Light';
            }
        }
        
        // Initialize theme toggle text on load
        window.addEventListener('DOMContentLoaded', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
            updateThemeToggleText(currentTheme);
        });
        
        // Initial load
        loadStats();
        loadAgents();
        loadRecentPackets();
        
        // Refresh every 30 seconds
        setInterval(() => {
            loadStats();
            loadAgents();
            loadRecentPackets();
        }, 30000);
    </script>
</body>
</html>
        '''
        return web.Response(text=html, content_type='text/html')
    
    async def agents_page(self, request):
        """Agents management page"""
        html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Agents - MeshyMcMapface</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        /* CSS Custom Properties for theming */
        :root {
            --bg-primary: #f5f5f5;
            --bg-secondary: white;
            --bg-tertiary: #f8f9fa;
            --text-primary: #333;
            --text-secondary: #666;
            --accent-color: #2196F3;
            --accent-hover: #e3f2fd;
            --border-color: #ddd;
            --shadow-color: rgba(0,0,0,0.1);
            --success-color: #4CAF50;
            --error-color: #f44336;
        }
        
        [data-theme="dark"] {
            --bg-primary: #121212;
            --bg-secondary: #1e1e1e;
            --bg-tertiary: #2a2a2a;
            --text-primary: #e0e0e0;
            --text-secondary: #b0b0b0;
            --accent-color: #64b5f6;
            --accent-hover: #1a237e;
            --border-color: #404040;
            --shadow-color: rgba(0,0,0,0.3);
            --success-color: #81c784;
            --error-color: #e57373;
        }

        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: var(--bg-primary); color: var(--text-primary); }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: var(--bg-secondary); padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px var(--shadow-color); }
        .section { background: var(--bg-secondary); padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px var(--shadow-color); }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 12px; text-align: left; border-bottom: 1px solid var(--border-color); color: var(--text-primary); }
        .table th { background: var(--bg-tertiary); }
        .status-active { color: var(--success-color); font-weight: bold; }
        .status-inactive { color: var(--error-color); }
        .nav { display: flex; gap: 20px; margin-bottom: 20px; align-items: center; }
        .nav a { color: var(--accent-color); text-decoration: none; padding: 10px 20px; background: var(--bg-secondary); border-radius: 4px; }
        .nav a:hover { background: var(--accent-hover); }
        .nav a.active { background: var(--accent-color); color: white; }
        
        /* Dark mode toggle */
        .theme-toggle {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-left: auto;
        }
        .theme-toggle:hover {
            background: var(--accent-hover);
        }
    </style>
    <script>
        // Theme initialization - must run before page renders to avoid flash
        (function() {
            const theme = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', theme);
        })();
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Agent Management</h1>
            <p>Monitor and manage distributed mesh agents</p>
        </div>
        
        <div class="nav">
            <a href="/">Dashboard</a>
            <a href="/agents" class="active">Agents</a>
            <a href="/packets">Packets</a>
            <a href="/nodes">Nodes</a>
            <a href="/map">Map</a>
            <button class="theme-toggle" onclick="toggleTheme()" id="theme-toggle">🌙 Dark</button>
        </div>
        
        <div class="section">
            <h2>All Agents</h2>
            <table class="table" id="agents-table">
                <thead>
                    <tr>
                        <th>Agent ID</th>
                        <th>Location</th>
                        <th>Coordinates</th>
                        <th>Last Seen</th>
                        <th>Total Packets</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
    </div>
    
    <script>
        async function loadAllAgents() {
            try {
                console.log('Loading agents...');
                const response = await fetch('/api/agents');
                console.log('Response status:', response.status);
                
                if (!response.ok) {
                    console.error('Failed to fetch agents:', response.status, response.statusText);
                    return;
                }
                
                const data = await response.json();
                console.log('Agents data:', data);
                
                const tbody = document.querySelector('#agents-table tbody');
                tbody.innerHTML = '';
                
                if (!data.agents || data.agents.length === 0) {
                    console.log('No agents found');
                    const row = tbody.insertRow();
                    row.innerHTML = '<td colspan="6" style="text-align: center;">No agents registered</td>';
                    return;
                }
                
                data.agents.forEach(agent => {
                    const row = tbody.insertRow();
                    const lastSeen = new Date(agent.last_seen).toLocaleString();
                    const isActive = new Date() - new Date(agent.last_seen) < 60 * 60 * 1000;
                    const coords = `${agent.coordinates[0].toFixed(4)}, ${agent.coordinates[1].toFixed(4)}`;
                    
                    row.innerHTML = `
                        <td>${agent.agent_id}</td>
                        <td>${agent.location_name}</td>
                        <td>${coords}</td>
                        <td>${lastSeen}</td>
                        <td>${agent.packet_count}</td>
                        <td class="${isActive ? 'status-active' : 'status-inactive'}">
                            ${isActive ? 'Active' : 'Inactive'}
                        </td>
                    `;
                });
            } catch (error) {
                console.error('Error loading agents:', error);
            }
        }
        
        // Theme toggle functions
        function toggleTheme() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme') || 'light';
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeToggleText(newTheme);
        }
        
        function updateThemeToggleText(theme) {
            const toggle = document.getElementById('theme-toggle');
            if (toggle) {
                toggle.textContent = theme === 'light' ? '🌙 Dark' : '☀️ Light';
            }
        }
        
        // Initialize theme toggle text on load
        window.addEventListener('DOMContentLoaded', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
            updateThemeToggleText(currentTheme);
        });
        
        // Initial load
        loadAllAgents();
        
        // Refresh every 30 seconds
        setInterval(loadAllAgents, 30000);
    </script>
</body>
</html>
        '''
        return web.Response(text=html, content_type='text/html')
    
    async def nodes_page(self, request):
        """Nodes page with table view"""
        html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Nodes - MeshyMcMapface</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        /* CSS Custom Properties for theming */
        :root {
            --bg-primary: #f5f5f5;
            --bg-secondary: white;
            --bg-tertiary: #f8f9fa;
            --text-primary: #333;
            --text-secondary: #666;
            --accent-color: #2196F3;
            --accent-hover: #e3f2fd;
            --border-color: #ddd;
            --shadow-color: rgba(0,0,0,0.1);
            --success-color: #4CAF50;
            --error-color: #f44336;
            --warning-color: #FF9800;
            --purple-color: #9C27B0;
            --gray-color: #607D8B;
            --muted-color: #9E9E9E;
        }
        
        [data-theme="dark"] {
            --bg-primary: #121212;
            --bg-secondary: #1e1e1e;
            --bg-tertiary: #2a2a2a;
            --text-primary: #e0e0e0;
            --text-secondary: #b0b0b0;
            --accent-color: #64b5f6;
            --accent-hover: #1a237e;
            --border-color: #404040;
            --shadow-color: rgba(0,0,0,0.3);
            --success-color: #81c784;
            --error-color: #e57373;
            --warning-color: #ffb74d;
            --purple-color: #ba68c8;
            --gray-color: #90a4ae;
            --muted-color: #bdbdbd;
        }

        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: var(--bg-primary); color: var(--text-primary); }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: var(--bg-secondary); padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px var(--shadow-color); }
        .section { background: var(--bg-secondary); padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px var(--shadow-color); }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 12px; text-align: left; border-bottom: 1px solid var(--border-color); color: var(--text-primary); }
        .table th { background: var(--bg-tertiary); }
        .status-active { color: var(--success-color); font-weight: bold; }
        .status-inactive { color: var(--error-color); }
        .nav { display: flex; gap: 20px; margin-bottom: 20px; align-items: center; }
        .nav a { color: var(--accent-color); text-decoration: none; padding: 10px 20px; background: var(--bg-secondary); border-radius: 4px; }
        .nav a:hover { background: var(--accent-hover); }
        .nav a.active { background: var(--accent-color); color: white; }
        .battery-high { color: var(--success-color); }
        .battery-medium { color: var(--warning-color); }
        .battery-low { color: var(--error-color); }
        .packet-details-table { margin-top: 15px; border: 1px solid var(--border-color); border-radius: 4px; }
        .packet-type { background: var(--accent-hover); padding: 2px 8px; border-radius: 12px; font-size: 0.8em; white-space: nowrap; color: var(--text-primary); }
        .clickable { cursor: pointer; color: var(--accent-color); text-decoration: underline; }
        .clickable:hover { color: #1976D2; }
        .packet-section { background: #f8f9fa; padding: 15px; border-radius: 4px; margin-top: 10px; }
        .filter-controls { display: flex; align-items: center; gap: 15px; margin-bottom: 15px; }
        .filter-controls label { font-weight: bold; }
        .filter-controls select, .filter-controls button { padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; }
        .role-router { background: #f44336; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }
        .role-router-client { background: #FF9800; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }
        .role-client { background: #2196F3; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }
        .role-client-mute { background: #4CAF50; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }
        .role-repeater { background: #9C27B0; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }
        .role-tracker { background: #607D8B; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }
        .role-unknown { background: #9E9E9E; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.8em; font-weight: bold; }
        .sortable { cursor: pointer; user-select: none; position: relative; }
        .sortable:hover { background: #e3f2fd; }
        .sortable::after { content: '⇅'; margin-left: 5px; color: #ccc; }
        .sortable.asc::after { content: '↑'; color: #2196F3; }
        .sortable.desc::after { content: '↓'; color: #2196F3; }
        .filter-section { background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #ddd; }
        .filter-buttons { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
        .filter-btn { padding: 6px 12px; border: 1px solid #ddd; background: white; border-radius: 20px; cursor: pointer; font-size: 0.85em; transition: all 0.2s; }
        .filter-btn:hover { background: #f0f0f0; }
        .filter-btn.active { background: #2196F3; color: white; border-color: #2196F3; }
        .filter-btn.active:hover { background: #1976D2; }
        .filter-counter { background: #666; color: white; padding: 2px 6px; border-radius: 10px; font-size: 0.75em; margin-left: 5px; }
        .clear-filters { background: #f44336; color: white; border: none; }
        .clear-filters:hover { background: #d32f2f; }
        
        /* Dark mode toggle */
        .theme-toggle {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-left: auto;
        }
        .theme-toggle:hover {
            background: var(--accent-hover);
        }
    </style>
    <script>
        // Theme initialization - must run before page renders to avoid flash
        (function() {
            const theme = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', theme);
        })();
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Network Nodes</h1>
            <p>All mesh nodes detected across the network</p>
        </div>
        
        <div class="nav">
            <a href="/">Dashboard</a>
            <a href="/agents">Agents</a>
            <a href="/packets">Packets</a>
            <a href="/nodes" class="active">Nodes</a>
            <a href="/map">Map</a>
            <button class="theme-toggle" onclick="toggleTheme()" id="theme-toggle">🌙 Dark</button>
        </div>
        
        <div class="section">
            <h2>All Network Nodes</h2>
            <div class="filter-controls">
                <label for="hours-filter">Show nodes active in last:</label>
                <select id="hours-filter" onchange="loadNodes()">
                    <option value="1">1 hour</option>
                    <option value="6">6 hours</option>
                    <option value="72" selected>72 hours</option>
                    <option value="168">7 days</option>
                </select>
                
                <button onclick="toggleView()" id="view-toggle">Show Packet Details</button>
                <button onclick="loadNodes()" style="background: #4CAF50; color: white; border: none;">Refresh</button>
            </div>
            
            <div class="filter-section">
                <strong>🔍 Quick Filters:</strong>
                <div class="filter-buttons">
                    <button class="filter-btn" data-filter="all" onclick="toggleFilter('all')">
                        All Nodes <span class="filter-counter" id="count-all">0</span>
                    </button>
                    <button class="filter-btn" data-filter="routers" onclick="toggleFilter('routers')">
                        Routers <span class="filter-counter" id="count-routers">0</span>
                    </button>
                    <button class="filter-btn" data-filter="routers-no-gps" onclick="toggleFilter('routers-no-gps')">
                        Routers w/o GPS <span class="filter-counter" id="count-routers-no-gps">0</span>
                    </button>
                    <button class="filter-btn" data-filter="clients" onclick="toggleFilter('clients')">
                        Clients <span class="filter-counter" id="count-clients">0</span>
                    </button>
                    <button class="filter-btn" data-filter="client-mute" onclick="toggleFilter('client-mute')">
                        Client Mute <span class="filter-counter" id="count-client-mute">0</span>
                    </button>
                    <button class="filter-btn" data-filter="has-gps" onclick="toggleFilter('has-gps')">
                        Has GPS <span class="filter-counter" id="count-has-gps">0</span>
                    </button>
                    <button class="filter-btn" data-filter="high-battery" onclick="toggleFilter('high-battery')">
                        High Battery (>70%) <span class="filter-counter" id="count-high-battery">0</span>
                    </button>
                    <button class="filter-btn" data-filter="low-battery" onclick="toggleFilter('low-battery')">
                        Low Battery (<30%) <span class="filter-counter" id="count-low-battery">0</span>
                    </button>
                    <button class="filter-btn clear-filters" onclick="clearAllFilters()">
                        Clear All
                    </button>
                </div>
            </div>
            
            <div id="filter-status" style="margin-bottom: 10px; font-weight: bold; color: #666;"></div>
            
            <table class="table" id="nodes-table">
                <thead>
                    <tr>
                        <th class="sortable" data-column="node_id">Node ID</th>
                        <th class="sortable" data-column="name">Names</th>
                        <th class="sortable" data-column="role">Role</th>
                        <th class="sortable" data-column="agent_count">Agents Seeing</th>
                        <th class="sortable" data-column="updated_at">Last Seen</th>
                        <th class="sortable" data-column="battery_level">Battery</th>
                        <th>Position</th>
                        <th class="sortable" data-column="rssi">Signal</th>
                        <th class="sortable" data-column="hops_away">Hops</th>
                        <th class="sortable" data-column="packet_count">Packets (24h)</th>
                        <th class="sortable" data-column="status">Status</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
            
            <div id="packet-details" style="display: none; margin-top: 20px;">
                <h3>Recent Packet Details</h3>
                <div id="packet-details-content"></div>
            </div>
        </div>
    </div>
    
    <script>
        console.log('Script tag loaded');
        
        let showPacketDetails = false;
        let currentNodes = [];
        
        async function loadNodes() {
            try {
                const hours = document.getElementById('hours-filter').value;
                console.log('Loading nodes for', hours, 'hours...');
                
                const response = await fetch(`/api/nodes/detailed?hours=${hours}&limit=50`);
                console.log('Nodes response status:', response.status);
                
                if (!response.ok) {
                    console.error('Failed to fetch nodes:', response.status, response.statusText);
                    return;
                }
                
                const data = await response.json();
                console.log('Raw API response:', data);
                console.log('Nodes array:', data.nodes);
                console.log('Number of nodes:', data.nodes ? data.nodes.length : 'undefined');
                
                allNodes = data.nodes || []; // Store original data
                console.log('allNodes set to:', allNodes);
                console.log('allNodes length:', allNodes.length);
                
                // Apply current filters to the new data
                applyFilters();
                
            } catch (error) {
                console.error('Error loading nodes:', error);
            }
        }
        
        function displayNodes() {
            console.log('displayNodes called with currentNodes.length:', currentNodes.length);
            const tbody = document.querySelector('#nodes-table tbody');
            console.log('tbody element found:', !!tbody);
            
            if (!tbody) {
                console.error('Could not find tbody element');
                return;
            }
            
            tbody.innerHTML = '';
            
            if (currentNodes.length === 0) {
                console.log('No nodes found, showing empty message');
                const row = tbody.insertRow();
                row.innerHTML = '<td colspan="11" style="text-align: center;">No nodes found</td>';
                return;
            }
            
            console.log('Processing', currentNodes.length, 'nodes...');
            
            currentNodes.forEach((node, index) => {
                console.log('Processing node', index, ':', node.node_id, node);
                const row = tbody.insertRow();
                const lastSeen = new Date(node.updated_at).toLocaleString();
                const isActive = new Date() - new Date(node.updated_at) < 60 * 60 * 1000;
                console.log('Node', node.node_id, 'processed, isActive:', isActive);
                
                // Format names
                let nameDisplay = node.node_id;
                if (node.short_name && node.long_name) {
                    nameDisplay = `${node.short_name} (${node.long_name})`;
                } else if (node.short_name) {
                    nameDisplay = node.short_name;
                } else if (node.long_name) {
                    nameDisplay = node.long_name;
                }
                
                // Format battery level with color coding
                let batteryDisplay = '-';
                let batteryClass = '';
                if (node.battery_level !== null) {
                    batteryDisplay = `${node.battery_level}%`;
                    if (node.battery_level > 50) batteryClass = 'battery-high';
                    else if (node.battery_level > 20) batteryClass = 'battery-medium';
                    else batteryClass = 'battery-low';
                }
                
                // Format position
                let positionDisplay = '-';
                if (node.position && node.position[0] && node.position[1]) {
                    positionDisplay = `${node.position[0].toFixed(4)}, ${node.position[1].toFixed(4)}`;
                }
                
                // Format signal info
                let signalDisplay = '';
                if (node.rssi) signalDisplay += `${node.rssi} dBm`;
                if (node.snr) signalDisplay += ` / ${node.snr} dB`;
                if (!signalDisplay) signalDisplay = '-';
                
                // Format agents seeing this node
                let agentsDisplay = node.seeing_agents.length > 0 ? 
                    `${node.agent_count} (${node.seeing_agents.join(', ')})` : '-';
                
                // Format role with color coding
                let roleDisplay = '-';
                if (node.role && node.role !== '' && node.role !== '0') {
                    let roleClass = 'role-unknown';
                    let roleName = node.role.toUpperCase();
                    
                    if (roleName.includes('ROUTER') && !roleName.includes('CLIENT')) {
                        roleClass = 'role-router';
                        roleName = 'ROUTER';
                    } else if (roleName.includes('ROUTER') && roleName.includes('CLIENT')) {
                        roleClass = 'role-router-client';  
                        roleName = 'ROUTER_CLIENT';
                    } else if (roleName.includes('CLIENT_MUTE') || roleName.includes('CLIENTMUTE')) {
                        roleClass = 'role-client-mute';
                        roleName = 'CLIENT_MUTE';
                    } else if (roleName.includes('CLIENT')) {
                        roleClass = 'role-client';
                        roleName = 'CLIENT';
                    } else if (roleName.includes('REPEATER')) {
                        roleClass = 'role-repeater';
                        roleName = 'REPEATER';
                    } else if (roleName.includes('TRACKER')) {
                        roleClass = 'role-tracker';
                        roleName = 'TRACKER';
                    }
                    
                    roleDisplay = `<span class="${roleClass}">${roleName}</span>`;
                }

                // Format hop count with color coding
                let hopDisplay = '-';
                let hopClass = '';
                if (node.hops_away !== null && node.hops_away !== undefined) {
                    hopDisplay = `${node.hops_away}`;
                    if (node.hops_away === 0) hopClass = 'style="color: #4CAF50; font-weight: bold;"'; // Direct
                    else if (node.hops_away <= 2) hopClass = 'style="color: #FF9800;"'; // Close
                    else if (node.hops_away <= 4) hopClass = 'style="color: #f44336;"'; // Far
                    else hopClass = 'style="color: #9E9E9E;"'; // Very far
                }
                
                row.innerHTML = `
                    <td><strong>${node.node_id}</strong></td>
                    <td>${nameDisplay}</td>
                    <td>${roleDisplay}</td>
                    <td>${agentsDisplay}</td>
                    <td>${lastSeen}</td>
                    <td class="${batteryClass}">${batteryDisplay}</td>
                    <td>${positionDisplay}</td>
                    <td>${signalDisplay}</td>
                    <td ${hopClass}>${hopDisplay}</td>
                    <td><span style="cursor: pointer; color: #2196F3;">${node.packet_count}</span></td>
                    <td class="${isActive ? 'status-active' : 'status-inactive'}">
                        ${isActive ? 'Active' : 'Inactive'}
                    </td>
                `;
                
                // Add click handler for packet count
                const packetSpan = row.querySelector('span');
                if (packetSpan) {
                    packetSpan.onclick = () => showPackets(index);
                }
            });
            
            // Setup sorting event listeners (re-attach after each load)
            setupSorting();
        }
        
        function setupSorting() {
            document.querySelectorAll('.sortable').forEach(th => {
                th.removeEventListener('click', handleSortClick); // Remove existing listeners
                th.addEventListener('click', handleSortClick);
            });
        }
        
        function handleSortClick() {
            const column = this.getAttribute('data-column');
            sortNodes(column);
        }
        
        function showPackets(nodeIndex) {
            const node = currentNodes[nodeIndex];
            const detailsDiv = document.getElementById('packet-details');
            const contentDiv = document.getElementById('packet-details-content');
            
            if (!node.recent_packets || node.recent_packets.length === 0) {
                contentDiv.innerHTML = `<p>No recent packets for ${node.node_id}</p>`;
            } else {
                let html = `<h4>Recent packets from ${node.node_id}</h4>`;
                html += '<table class="table" style="font-size: 0.9em;">';
                html += '<thead><tr><th>Timestamp</th><th>Type</th><th>Agent</th><th>Payload</th><th>Signal</th></tr></thead><tbody>';
                
                node.recent_packets.forEach(packet => {
                    const timestamp = new Date(packet.timestamp).toLocaleString();
                    let payloadDisplay = '';
                    
                    // Format payload based on type
                    if (packet.type === 'position' && packet.payload) {
                        const pos = packet.payload;
                        payloadDisplay = `Lat: ${pos.latitude?.toFixed(4) || 'N/A'}, Lon: ${pos.longitude?.toFixed(4) || 'N/A'}`;
                        if (pos.altitude) payloadDisplay += `, Alt: ${pos.altitude}m`;
                    } else if (packet.type === 'telemetry' && packet.payload) {
                        if (packet.payload.device_metrics) {
                            const dm = packet.payload.device_metrics;
                            payloadDisplay = `Battery: ${dm.battery_level || 'N/A'}%`;
                            if (dm.voltage) payloadDisplay += `, Voltage: ${dm.voltage}V`;
                            if (dm.channel_utilization) payloadDisplay += `, Ch.Util: ${dm.channel_utilization}%`;
                        }
                    } else if (packet.type === 'text_message' && packet.payload) {
                        payloadDisplay = packet.payload.length > 50 ? 
                            packet.payload.substring(0, 50) + '...' : packet.payload;
                    } else if (packet.type === 'user_info' && packet.payload) {
                        const ui = packet.payload;
                        payloadDisplay = `${ui.short_name || 'N/A'} (${ui.long_name || 'N/A'})`;
                    } else if (packet.payload) {
                        payloadDisplay = JSON.stringify(packet.payload).substring(0, 100);
                    } else {
                        payloadDisplay = '-';
                    }
                    
                    let signalInfo = '';
                    if (packet.rssi) signalInfo += `${packet.rssi} dBm`;
                    if (packet.snr) signalInfo += ` / ${packet.snr} dB`;
                    if (!signalInfo) signalInfo = '-';
                    
                    html += `
                        <tr>
                            <td>${timestamp}</td>
                            <td><span style="background: #e3f2fd; padding: 2px 6px; border-radius: 3px; font-size: 0.8em;">${packet.type}</span></td>
                            <td>${packet.agent_location}</td>
                            <td style="max-width: 300px; overflow: hidden;">${payloadDisplay}</td>
                            <td>${signalInfo}</td>
                        </tr>
                    `;
                });
                
                html += '</tbody></table>';
                contentDiv.innerHTML = html;
            }
            
            detailsDiv.style.display = 'block';
            detailsDiv.scrollIntoView({ behavior: 'smooth' });
        }
        
        function toggleView() {
            showPacketDetails = !showPacketDetails;
            const button = document.getElementById('view-toggle');
            const detailsDiv = document.getElementById('packet-details');
            
            if (showPacketDetails) {
                button.textContent = 'Hide Packet Details';
                detailsDiv.style.display = 'block';
                
                // Show a simple message if no nodes, otherwise show packets
                const contentDiv = document.getElementById('packet-details-content');
                if (currentNodes.length === 0) {
                    contentDiv.innerHTML = '<div class="packet-section"><h4>Packet Details View</h4><p>No nodes with packets currently available. This section will show detailed packet information when agents are sending data to the server.</p><p><strong>What you will see here:</strong></p><ul><li>Recent packets from all nodes</li><li>Packet types (position, telemetry, text messages, etc.)</li><li>Detailed payload information</li><li>Which agent received each packet</li><li>Signal strength data</li></ul></div>';
                } else {
                    showAllPackets();
                }
            } else {
                button.textContent = 'Show Packet Details';
                detailsDiv.style.display = 'none';
            }
        }
        
        function showAllPackets() {
            console.log('showAllPackets called, nodes:', currentNodes.length);
            const contentDiv = document.getElementById('packet-details-content');
            
            if (currentNodes.length === 0) {
                contentDiv.innerHTML = '<p>No nodes to show packets for</p>';
                console.log('No nodes available');
                return;
            }
            
            let html = '<h4>Recent Packets from All Nodes</h4>';
            
            try {
                // Collect all packets from all nodes
                let allPackets = [];
                currentNodes.forEach(node => {
                    if (node.recent_packets) {
                        node.recent_packets.forEach(packet => {
                            allPackets.push({
                                ...packet,
                                node_id: node.node_id,
                                node_name: node.short_name || node.long_name || node.node_id
                            });
                        });
                    }
                });
                
                console.log('Total packets collected:', allPackets.length);
                
                // Sort by timestamp
                allPackets.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
                
                if (allPackets.length === 0) {
                    contentDiv.innerHTML = html + '<p>No recent packets found</p>';
                    return;
                }
                
                html += '<table class="table" style="font-size: 0.9em;">';
                html += '<thead><tr><th>Timestamp</th><th>From Node</th><th>Type</th><th>Agent</th><th>Payload</th><th>Signal</th></tr></thead><tbody>';
                
                allPackets.slice(0, 50).forEach(packet => {  // Limit to 50 most recent
                    const timestamp = new Date(packet.timestamp).toLocaleString();
                    let payloadDisplay = formatPayload(packet.type, packet.payload);
                    
                    let signalInfo = '';
                    if (packet.rssi) signalInfo += `${packet.rssi} dBm`;
                    if (packet.snr) signalInfo += ` / ${packet.snr} dB`;
                    if (!signalInfo) signalInfo = '-';
                    
                    html += `
                        <tr>
                            <td>${timestamp}</td>
                            <td><strong>${packet.node_name}</strong></td>
                            <td><span style="background: #e3f2fd; padding: 2px 6px; border-radius: 3px; font-size: 0.8em;">${packet.type}</span></td>
                            <td>${packet.agent_location}</td>
                            <td style="max-width: 400px; overflow: hidden;">${payloadDisplay}</td>
                            <td>${signalInfo}</td>
                        </tr>
                    `;
                });
                
                html += '</tbody></table>';
                contentDiv.innerHTML = html;
                console.log('All packets table created successfully');
                
            } catch (error) {
                console.error('Error in showAllPackets:', error);
                contentDiv.innerHTML = html + '<p>Error loading packets: ' + error.message + '</p>';
            }
        }
        
        function formatPayload(type, payload) {
            if (!payload) return '-';
            
            if (type === 'position') {
                const pos = payload;
                let display = `Lat: ${pos.latitude?.toFixed(4) || 'N/A'}, Lon: ${pos.longitude?.toFixed(4) || 'N/A'}`;
                if (pos.altitude) display += `, Alt: ${pos.altitude}m`;
                return display;
            } else if (type === 'telemetry') {
                if (payload.device_metrics) {
                    const dm = payload.device_metrics;
                    let display = `Battery: ${dm.battery_level || 'N/A'}%`;
                    if (dm.voltage) display += `, Voltage: ${dm.voltage}V`;
                    if (dm.channel_utilization) display += `, Ch.Util: ${dm.channel_utilization}%`;
                    return display;
                }
                return JSON.stringify(payload).substring(0, 100);
            } else if (type === 'text_message') {
                return payload.length > 80 ? payload.substring(0, 80) + '...' : payload;
            } else if (type === 'user_info') {
                return `${payload.short_name || 'N/A'} (${payload.long_name || 'N/A'})`;
            } else {
                return JSON.stringify(payload).substring(0, 100);
            }
        }
        
        // Filtering functionality
        let activeFilters = new Set(['all']);
        let allNodes = []; // Keep original unfiltered data
        
        function toggleFilter(filterType) {
            console.log('Toggle filter:', filterType);
            
            if (filterType === 'all') {
                // "All" is exclusive - clear other filters
                activeFilters.clear();
                activeFilters.add('all');
            } else {
                // Remove "all" if adding specific filters
                activeFilters.delete('all');
                
                // Toggle the specific filter
                if (activeFilters.has(filterType)) {
                    activeFilters.delete(filterType);
                } else {
                    activeFilters.add(filterType);
                }
                
                // If no specific filters, default back to "all"
                if (activeFilters.size === 0) {
                    activeFilters.add('all');
                }
            }
            
            updateFilterUI();
            applyFilters();
        }
        
        function clearAllFilters() {
            activeFilters.clear();
            activeFilters.add('all');
            updateFilterUI();
            applyFilters();
        }
        
        function updateFilterUI() {
            // Update button states
            document.querySelectorAll('.filter-btn').forEach(btn => {
                const filter = btn.getAttribute('data-filter');
                if (filter && activeFilters.has(filter)) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
        }
        
        function applyFilters() {
            // Filter the nodes based on active filters
            if (activeFilters.has('all')) {
                currentNodes = [...allNodes]; // Show all nodes
            } else {
                currentNodes = allNodes.filter(node => {
                    return Array.from(activeFilters).some(filter => nodeMatchesFilter(node, filter));
                });
            }
            
            // Update filter counts
            updateFilterCounts();
            
            // Update filter status display
            updateFilterStatus();
            
            // Re-display the filtered nodes
            displayNodes();
        }
        
        function nodeMatchesFilter(node, filter) {
            const role = (node.role || '').toUpperCase();
            const hasGPS = node.position && node.position[0] && node.position[1];
            const battery = node.battery_level;
            
            switch (filter) {
                case 'routers':
                    return role.includes('ROUTER') && !role.includes('CLIENT');
                    
                case 'routers-no-gps':
                    return (role.includes('ROUTER') && !role.includes('CLIENT')) && !hasGPS;
                    
                case 'clients':
                    return role.includes('CLIENT') && !role.includes('MUTE');
                    
                case 'client-mute':
                    return role.includes('CLIENT_MUTE') || role.includes('CLIENTMUTE');
                    
                case 'has-gps':
                    return hasGPS;
                    
                case 'high-battery':
                    return battery && battery > 70;
                    
                case 'low-battery':
                    return battery && battery < 30;
                    
                default:
                    return false;
            }
        }
        
        function updateFilterCounts() {
            // Count nodes for each filter
            const counts = {
                'all': allNodes.length,
                'routers': 0,
                'routers-no-gps': 0,
                'clients': 0,
                'client-mute': 0,
                'has-gps': 0,
                'high-battery': 0,
                'low-battery': 0
            };
            
            allNodes.forEach(node => {
                if (nodeMatchesFilter(node, 'routers')) counts['routers']++;
                if (nodeMatchesFilter(node, 'routers-no-gps')) counts['routers-no-gps']++;
                if (nodeMatchesFilter(node, 'clients')) counts['clients']++;
                if (nodeMatchesFilter(node, 'client-mute')) counts['client-mute']++;
                if (nodeMatchesFilter(node, 'has-gps')) counts['has-gps']++;
                if (nodeMatchesFilter(node, 'high-battery')) counts['high-battery']++;
                if (nodeMatchesFilter(node, 'low-battery')) counts['low-battery']++;
            });
            
            // Update counter displays
            Object.entries(counts).forEach(([filter, count]) => {
                const counter = document.getElementById(`count-${filter}`);
                if (counter) {
                    counter.textContent = count;
                }
            });
        }
        
        function updateFilterStatus() {
            const statusDiv = document.getElementById('filter-status');
            if (!statusDiv) return;
            
            if (activeFilters.has('all')) {
                statusDiv.innerHTML = `📊 Showing all ${currentNodes.length} nodes`;
            } else {
                const filterNames = Array.from(activeFilters).map(f => {
                    switch(f) {
                        case 'routers': return 'Routers';
                        case 'routers-no-gps': return 'Routers w/o GPS';
                        case 'clients': return 'Clients';
                        case 'client-mute': return 'Client Mute';
                        case 'has-gps': return 'Has GPS';
                        case 'high-battery': return 'High Battery';
                        case 'low-battery': return 'Low Battery';
                        default: return f;
                    }
                }).join(', ');
                statusDiv.innerHTML = `🔍 Showing ${currentNodes.length} nodes filtered by: ${filterNames}`;
            }
        }
        
        // Sorting functionality
        let currentSortColumn = null;
        let currentSortDirection = 'asc';
        
        function sortNodes(column) {
            // Toggle direction if clicking the same column
            if (currentSortColumn === column) {
                currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                currentSortColumn = column;
                currentSortDirection = 'asc';
            }
            
            // Update header visual indicators
            document.querySelectorAll('.sortable').forEach(th => {
                th.classList.remove('asc', 'desc');
            });
            const activeHeader = document.querySelector(`.sortable[data-column="${column}"]`);
            if (activeHeader) {
                activeHeader.classList.add(currentSortDirection);
            }
            
            // Sort the nodes array
            currentNodes.sort((a, b) => {
                let valueA = getSortValue(a, column);
                let valueB = getSortValue(b, column);
                
                // Handle null/undefined values
                if (valueA === null || valueA === undefined) valueA = '';
                if (valueB === null || valueB === undefined) valueB = '';
                
                // Convert to comparable format
                if (typeof valueA === 'string') valueA = valueA.toLowerCase();
                if (typeof valueB === 'string') valueB = valueB.toLowerCase();
                
                let comparison = 0;
                if (valueA < valueB) comparison = -1;
                else if (valueA > valueB) comparison = 1;
                
                return currentSortDirection === 'desc' ? -comparison : comparison;
            });
            
            // Redraw the table
            displayNodes();
        }
        
        function getSortValue(node, column) {
            switch (column) {
                case 'node_id': return node.node_id;
                case 'name': 
                    if (node.short_name && node.long_name) return `${node.short_name} (${node.long_name})`;
                    else if (node.short_name) return node.short_name;
                    else if (node.long_name) return node.long_name;
                    else return node.node_id;
                case 'role': return node.role || '';
                case 'agent_count': return node.agent_count || 0;
                case 'updated_at': return new Date(node.updated_at).getTime();
                case 'battery_level': return node.battery_level || -1;
                case 'rssi': return node.rssi || -999;
                case 'hops_away': return node.hops_away || 999;
                case 'packet_count': return node.packet_count || 0;
                case 'status': 
                    const isActive = new Date() - new Date(node.updated_at) < 60 * 60 * 1000;
                    return isActive ? 1 : 0;
                default: return '';
            }
        }
        
        // Ensure initial load happens after DOM is ready
        document.addEventListener('DOMContentLoaded', function() {
            console.log('DOM loaded, initializing nodes page...');
            
            // Add visible indicator that JS is running
            const header = document.querySelector('.header h1');
            if (header) {
                header.innerHTML += ' <span style="color: green;">(JS Loaded)</span>';
            }
            
            // Run test to verify DOM access
            testJS();
            
            const button = document.getElementById('view-toggle');
            if (button) {
                button.onclick = toggleView;
            }
            
            // Initial sorting setup will be done after first load
            
            // Initialize filter UI
            updateFilterUI();
            
            // Initial load after DOM is ready
            setTimeout(loadNodes, 1000); // Add small delay
        });
        
        // Theme toggle functions
        function toggleTheme() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme') || 'light';
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeToggleText(newTheme);
        }
        
        function updateThemeToggleText(theme) {
            const toggle = document.getElementById('theme-toggle');
            if (toggle) {
                toggle.textContent = theme === 'light' ? '🌙 Dark' : '☀️ Light';
            }
        }
        
        // Initialize theme toggle text on load
        window.addEventListener('DOMContentLoaded', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
            updateThemeToggleText(currentTheme);
        });
        
        // Refresh every 30 seconds
        setInterval(loadNodes, 30000);
    </script>
</body>
</html>
        '''
        return web.Response(text=html, content_type='text/html')
    
    async def packets_page(self, request):
        """Packets page with filtering"""
        html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Packets - MeshyMcMapface</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        /* CSS Custom Properties for theming */
        :root {
            --bg-primary: #f5f5f5;
            --bg-secondary: white;
            --bg-tertiary: #f8f9fa;
            --text-primary: #333;
            --text-secondary: #666;
            --accent-color: #2196F3;
            --accent-hover: #e3f2fd;
            --border-color: #ddd;
            --shadow-color: rgba(0,0,0,0.1);
            --success-color: #4CAF50;
            --error-color: #f44336;
        }
        
        [data-theme="dark"] {
            --bg-primary: #121212;
            --bg-secondary: #1e1e1e;
            --bg-tertiary: #2a2a2a;
            --text-primary: #e0e0e0;
            --text-secondary: #b0b0b0;
            --accent-color: #64b5f6;
            --accent-hover: #1a237e;
            --border-color: #404040;
            --shadow-color: rgba(0,0,0,0.3);
            --success-color: #81c784;
            --error-color: #e57373;
        }

        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: var(--bg-primary); color: var(--text-primary); }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { background: var(--bg-secondary); padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px var(--shadow-color); }
        .section { background: var(--bg-secondary); padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px var(--shadow-color); }
        .table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
        .table th, .table td { padding: 8px; text-align: left; border-bottom: 1px solid var(--border-color); color: var(--text-primary); }
        .table th { background: var(--bg-tertiary); position: sticky; top: 0; }
        .nav { display: flex; gap: 20px; margin-bottom: 20px; align-items: center; }
        .nav a { color: var(--accent-color); text-decoration: none; padding: 10px 20px; background: var(--bg-secondary); border-radius: 4px; }
        .nav a:hover { background: var(--accent-hover); }
        .nav a.active { background: var(--accent-color); color: white; }
        .filter-controls { display: flex; align-items: center; gap: 15px; margin-bottom: 15px; flex-wrap: wrap; }
        .filter-controls label { font-weight: bold; color: var(--text-primary); }
        .filter-controls select, .filter-controls button { padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-secondary); color: var(--text-primary); }
        .packet-type { background: var(--accent-hover); padding: 2px 8px; border-radius: 12px; font-size: 0.8em; white-space: nowrap; color: var(--text-primary); }
        .packet-payload { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
        .clickable { cursor: pointer; color: var(--accent-color); }
        .clickable:hover { text-decoration: underline; }
        .table-container { max-height: 600px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 4px; }
        
        /* Dark mode toggle */
        .theme-toggle {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-left: auto;
        }
        .theme-toggle:hover {
            background: var(--accent-hover);
        }
    </style>
    <script>
        // Theme initialization - must run before page renders to avoid flash
        (function() {
            const theme = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', theme);
        })();
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Network Packets</h1>
            <p>All packets received across the mesh network</p>
        </div>
        
        <div class="nav">
            <a href="/">Dashboard</a>
            <a href="/agents">Agents</a>
            <a href="/packets" class="active">Packets</a>
            <a href="/nodes">Nodes</a>
            <a href="/map">Map</a>
            <button class="theme-toggle" onclick="toggleTheme()" id="theme-toggle">🌙 Dark</button>
        </div>
        
        <div class="section">
            <h2>Recent Packets</h2>
            <div class="filter-controls">
                <label for="hours-filter">Time range:</label>
                <select id="hours-filter" onchange="loadPackets()">
                    <option value="1">Last 1 hour</option>
                    <option value="6">Last 6 hours</option>
                    <option value="72" selected>Last 72 hours</option>
                    <option value="168">Last 7 days</option>
                </select>
                
                <label for="type-filter">Packet type:</label>
                <select id="type-filter" onchange="loadPackets()">
                    <option value="all">All types</option>
                    <option value="position">Position</option>
                    <option value="telemetry">Telemetry</option>
                    <option value="text">Text</option>
                    <option value="user_info">User Info</option>
                </select>
                
                <label for="agent-filter">Agent:</label>
                <select id="agent-filter" onchange="loadPackets()">
                    <option value="all">All agents</option>
                </select>
                
                <label for="limit-filter">Show:</label>
                <select id="limit-filter" onchange="loadPackets()">
                    <option value="50">50 packets</option>
                    <option value="100" selected>100 packets</option>
                    <option value="500">500 packets</option>
                    <option value="1000">1000 packets</option>
                </select>
                
                <button onclick="loadPackets()" style="background: #4CAF50; color: white; border: none;">Refresh</button>
            </div>
            
            <div class="table-container">
                <table class="table" id="packets-table">
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>From Node</th>
                            <th>To Node</th>
                            <th>Type</th>
                            <th>Agent</th>
                            <th>RSSI</th>
                            <th>SNR</th>
                            <th>Payload</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>
    </div>
    
    <script>
        console.log('Packets page script loaded');
        
        async function loadPackets() {
            console.log('loadPackets called');
            try {
                const hours = document.getElementById('hours-filter').value;
                const type = document.getElementById('type-filter').value;
                const agent = document.getElementById('agent-filter').value;
                const limit = document.getElementById('limit-filter').value;
                
                let url = `/api/packets?hours=${hours}&limit=${limit}`;
                if (type !== 'all') url += `&type=${type}`;
                if (agent !== 'all') url += `&agent_id=${agent}`;
                
                const response = await fetch(url);
                const data = await response.json();
                
                const tbody = document.querySelector('#packets-table tbody');
                tbody.innerHTML = '';
                
                if (!data.packets || data.packets.length === 0) {
                    const row = tbody.insertRow();
                    row.innerHTML = '<td colspan="8" style="text-align: center;">No packets found</td>';
                    return;
                }
                
                data.packets.forEach(packet => {
                    const row = tbody.insertRow();
                    const timestamp = new Date(packet.timestamp).toLocaleString();
                    
                    row.innerHTML = `
                        <td>${timestamp}</td>
                        <td><strong>${packet.from_node_display}</strong>${packet.from_hw_model ? `<br><small style="color: #666;">${packet.from_hw_model}</small>` : ''}${packet.from_role ? `<br><small style="color: #888; font-style: italic;">${packet.from_role}</small>` : ''}${packet.from_hops ? `<br><small style="color: #2196F3;">🛣️ ${packet.from_hops} hops</small>` : ''}</td>
                        <td>${packet.to_node_display}${packet.to_hw_model ? `<br><small style="color: #666;">${packet.to_hw_model}</small>` : ''}${packet.to_role ? `<br><small style="color: #888; font-style: italic;">${packet.to_role}</small>` : ''}${packet.to_hops ? `<br><small style="color: #2196F3;">🛣️ ${packet.to_hops} hops</small>` : ''}</td>
                        <td><span class="packet-type">${packet.type}</span></td>
                        <td>${packet.agent_location}</td>
                        <td>${packet.rssi || '-'}</td>
                        <td>${packet.snr || '-'}</td>
                        <td class="packet-payload">${formatPayload(packet.payload)}</td>
                    `;
                });
                
            } catch (error) {
                console.error('Error loading packets:', error);
            }
        }
        
        async function loadAgents() {
            try {
                const response = await fetch('/api/agents');
                const data = await response.json();
                
                const select = document.getElementById('agent-filter');
                select.innerHTML = '<option value="all">All agents</option>';
                
                if (data.agents) {
                    data.agents.forEach(agent => {
                        const option = document.createElement('option');
                        option.value = agent.agent_id;
                        option.textContent = agent.location_name;
                        select.appendChild(option);
                    });
                }
            } catch (error) {
                console.error('Error loading agents:', error);
            }
        }
        
        function formatPayload(payload) {
            if (!payload) return '-';
            if (typeof payload === 'object') {
                const keys = Object.keys(payload);
                if (keys.length === 0) return 'Empty';
                return keys.map(key => `${key}: ${JSON.stringify(payload[key])}`).join(', ');
            }
            return String(payload);
        }
        
        // Theme toggle functions
        function toggleTheme() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme') || 'light';
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeToggleText(newTheme);
        }
        
        function updateThemeToggleText(theme) {
            const toggle = document.getElementById('theme-toggle');
            if (toggle) {
                toggle.textContent = theme === 'light' ? '🌙 Dark' : '☀️ Light';
            }
        }
        
        // Initialize theme toggle text on load
        window.addEventListener('DOMContentLoaded', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
            updateThemeToggleText(currentTheme);
        });
        
        document.addEventListener('DOMContentLoaded', function() {
            loadAgents();
            loadPackets();
        });
        
        setInterval(loadPackets, 30000);
    </script>
</body>
</html>
        '''
        return web.Response(text=html, content_type='text/html')
    
    async def map_page(self, request):
        """Interactive map page showing nodes and agents"""
        html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Network Map - MeshyMcMapface</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        /* CSS Custom Properties for theming */
        :root {
            --bg-primary: #f5f5f5;
            --bg-secondary: white;
            --bg-tertiary: #f8f9fa;
            --text-primary: #333;
            --text-secondary: #666;
            --accent-color: #2196F3;
            --accent-hover: #e3f2fd;
            --border-color: #ddd;
            --shadow-color: rgba(0,0,0,0.1);
            --success-color: #4CAF50;
            --error-color: #f44336;
        }
        
        [data-theme="dark"] {
            --bg-primary: #121212;
            --bg-secondary: #1e1e1e;
            --bg-tertiary: #2a2a2a;
            --text-primary: #e0e0e0;
            --text-secondary: #b0b0b0;
            --accent-color: #64b5f6;
            --accent-hover: #1a237e;
            --border-color: #404040;
            --shadow-color: rgba(0,0,0,0.3);
            --success-color: #81c784;
            --error-color: #e57373;
        }

        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: var(--bg-primary); color: var(--text-primary); }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { background: var(--bg-secondary); padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px var(--shadow-color); }
        .section { background: var(--bg-secondary); padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px var(--shadow-color); }
        .nav { display: flex; gap: 20px; margin-bottom: 20px; align-items: center; }
        .nav a { color: var(--accent-color); text-decoration: none; padding: 10px 20px; background: var(--bg-secondary); border-radius: 4px; }
        .nav a:hover { background: var(--accent-hover); }
        .nav a.active { background: var(--accent-color); color: white; }
        .controls { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
        .control-group { display: flex; gap: 5px; align-items: center; }
        .control-group label { font-weight: bold; color: var(--text-primary); }
        .control-group select, .control-group input { padding: 5px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-secondary); color: var(--text-primary); }
        #map { height: 600px; width: 100%; border-radius: 8px; }
        .legend { background: var(--bg-secondary); padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px var(--shadow-color); margin-top: 20px; }
        .legend h3 { margin-top: 0; color: var(--text-primary); }
        .legend-item { display: flex; align-items: center; margin: 10px 0; color: var(--text-primary); }
        .legend-icon { width: 20px; height: 20px; border-radius: 50%; margin-right: 10px; border: 2px solid #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }
        .stats-bar { display: flex; gap: 20px; margin-bottom: 20px; }
        .stat { background: var(--bg-secondary); padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px var(--shadow-color); text-align: center; min-width: 120px; }
        .stat-number { font-size: 1.5em; font-weight: bold; color: var(--accent-color); }
        .stat-label { color: var(--text-secondary); font-size: 0.9em; }
        
        /* Route information styling for popups */
        .leaflet-popup-content { max-width: 350px !important; }
        .route-path { font-family: monospace; color: var(--text-secondary); font-size: 0.9em; }
        .route-discovery-time { color: var(--text-secondary); font-size: 0.8em; }
        
        /* Dark mode toggle */
        .theme-toggle {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-left: auto;
        }
        .theme-toggle:hover {
            background: var(--accent-hover);
        }
    </style>
    <script>
        // Theme initialization - must run before page renders to avoid flash
        (function() {
            const theme = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-theme', theme);
        })();
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>MeshyMcMapface Network Map</h1>
            <p>Real-time visualization of mesh network nodes and agents</p>
        </div>
        
        <div class="nav">
            <a href="/">Dashboard</a>
            <a href="/agents">Agents</a>
            <a href="/packets">Packets</a>
            <a href="/nodes">Nodes</a>
            <a href="/map" class="active">Map</a>
            <button class="theme-toggle" onclick="toggleTheme()" id="theme-toggle">🌙 Dark</button>
        </div>
        
        <div class="stats-bar">
            <div class="stat">
                <div class="stat-number" id="total-nodes">-</div>
                <div class="stat-label">Total Nodes</div>
            </div>
            <div class="stat">
                <div class="stat-number" id="active-nodes">-</div>
                <div class="stat-label">Active Nodes</div>
            </div>
            <div class="stat">
                <div class="stat-number" id="total-agents">-</div>
                <div class="stat-label">Agents</div>
            </div>
            <div class="stat">
                <div class="stat-number" id="coverage-area">-</div>
                <div class="stat-label">Coverage (km²)</div>
            </div>
        </div>
        
        <div class="section">
            <div class="controls">
                <div class="control-group">
                    <label>Show:</label>
                    <select id="filter-type">
                        <option value="all">All Nodes</option>
                        <option value="active">Active Only</option>
                        <option value="agents">Agents Only</option>
                    </select>
                </div>
                <div class="control-group">
                    <label>Agent:</label>
                    <select id="filter-agent">
                        <option value="all">All Agents</option>
                    </select>
                </div>
                <div class="control-group">
                    <label>Time Range:</label>
                    <select id="time-range">
                        <option value="1">Last 1 Hour</option>
                        <option value="6">Last 6 Hours</option>
                        <option value="24" selected>Last 24 Hours</option>
                        <option value="168">Last Week</option>
                    </select>
                </div>
                <div class="control-group">
                    <input type="checkbox" id="show-connections" checked>
                    <label for="show-connections">Show Connections</label>
                </div>
                <div class="control-group">
                    <button onclick="refreshMap()" style="padding: 5px 15px; background: #2196F3; color: white; border: none; border-radius: 4px; cursor: pointer;">Refresh</button>
                </div>
            </div>
            
            <div id="map"></div>
        </div>
        
        <div class="legend">
            <h3>Network Topology Map</h3>
            <div style="margin-bottom: 10px;"><strong>🛣️ Hop Distance from Agents:</strong></div>
            <div class="legend-item">
                <div class="legend-icon" style="background: #2E7D32;"></div>
                <span>Direct Connection (0 hops)</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="background: #4CAF50;"></div>
                <span>1 Hop Away</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="background: #FF9800;"></div>
                <span>2 Hops Away</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="background: #F57C00;"></div>
                <span>3 Hops Away</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="background: #f44336;"></div>
                <span>4 Hops Away</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="background: #9E9E9E;"></div>
                <span>5+ Hops or Unknown Distance</span>
            </div>
            <div class="legend-item" style="margin-top: 10px;">
                <div class="legend-icon" style="background: #2196F3; transform: scale(1.3);"></div>
                <span>MeshyMcMapface Agent</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="background: #D32F2F;"></div>
                <span>Critical Battery (<20%) - Override</span>
            </div>
            <div style="margin-top: 15px; border-top: 1px solid #ddd; padding-top: 10px;">
                <strong>📡 Network Connections:</strong><br>
                <div style="font-size: 0.9em; margin-top: 5px;">
                    <span style="color: #4CAF50;">●━━━━</span> Text Messages (solid green)<br>
                    <span style="color: #FF9800;">●┅┅┅┅</span> Position Data (dashed orange)<br>
                    <span style="color: #9C27B0;">●┅┅┅┅</span> Telemetry Data (dashed purple)<br>
                    <span style="color: #2196F3;">●┅┅┅┅</span> Other Packet Types (dashed blue)<br>
                    <small>Line thickness = packet volume</small>
                </div>
            </div>
        </div>
    </div>
    
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        let map;
        let markers = new Map();
        let connections = [];
        let nodeData = [];
        let agentData = [];
        let packetData = [];
        
        // Initialize map
        function initMap() {
            map = L.map('map').setView([39.8283, -98.5795], 4); // Center of US
            
            // Add tile layer
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors'
            }).addTo(map);
        }
        
        // Load and display data
        async function loadMapData() {
            try {
                // Load nodes
                const timeRange = document.getElementById('time-range').value;
                const agentFilter = document.getElementById('filter-agent').value;
                
                let nodesUrl = `/api/nodes/detailed?hours=${timeRange}&limit=500`;
                if (agentFilter !== 'all') {
                    nodesUrl += `&agent_id=${agentFilter}`;
                }
                
                const nodesResponse = await fetch(nodesUrl);
                const nodesData = await nodesResponse.json();
                nodeData = nodesData.nodes || [];
                
                // Load agents
                const agentsResponse = await fetch('/api/agents');
                const agentsData = await agentsResponse.json();
                agentData = agentsData.agents || [];
                
                // Load recent packets for connections
                const packetsResponse = await fetch(`/api/packets?limit=500&hours=${timeRange}`);
                const packetsData = await packetsResponse.json();
                packetData = packetsData.packets || [];
                
                displayNodes();
                displayAgents();
                displayConnections(packetData);
                updateStats();
                updateAgentFilter();
                
            } catch (error) {
                console.error('Error loading map data:', error);
            }
        }
        
        function displayNodes() {
            const filterType = document.getElementById('filter-type').value;
            const now = new Date();
            
            // Clear existing node markers
            markers.forEach((marker, key) => {
                if (key.startsWith('node_')) {
                    map.removeLayer(marker);
                    markers.delete(key);
                }
            });
            
            nodeData.forEach(node => {
                if (!node.position || node.position[0] === null || node.position[1] === null) return;
                
                const lastSeen = new Date(node.updated_at);
                const hoursOld = (now - lastSeen) / (1000 * 60 * 60);
                const isActive = hoursOld < 1;
                
                // Apply filter
                if (filterType === 'active' && !isActive) return;
                if (filterType === 'agents') return; // Skip nodes when showing agents only
                
                // Determine color based on hop count first, then status
                let color = '#4CAF50'; // Default active
                
                // Color by hop count (network topology priority)
                if (node.hops_away !== null && node.hops_away !== undefined) {
                    if (node.hops_away === 0) color = '#2E7D32'; // Dark green - Direct connection
                    else if (node.hops_away === 1) color = '#4CAF50'; // Green - 1 hop
                    else if (node.hops_away === 2) color = '#FF9800'; // Orange - 2 hops  
                    else if (node.hops_away === 3) color = '#F57C00'; // Dark orange - 3 hops
                    else if (node.hops_away === 4) color = '#f44336'; // Red - 4 hops
                    else color = '#9E9E9E'; // Gray - 5+ hops or very far
                } else {
                    // Fallback to activity status if no hop data
                    if (!isActive) color = '#FF9800'; // Inactive
                }
                
                // Override for critical battery (always red)
                if (node.battery_level && node.battery_level < 20) color = '#D32F2F';
                
                // Create marker
                const marker = L.circleMarker([node.position[0], node.position[1]], {
                    radius: 8,
                    fillColor: color,
                    color: '#fff',
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.8
                });
                
                // Create popup content with names and hardware info
                let nodeTitle = node.node_id;
                const hasShortName = node.short_name && node.short_name.trim() !== '';
                const hasLongName = node.long_name && node.long_name.trim() !== '';
                
                if (hasShortName && hasLongName) {
                    nodeTitle = `${node.short_name} (${node.long_name})`;
                } else if (hasShortName) {
                    nodeTitle = `${node.short_name} (${node.node_id})`;
                } else if (hasLongName) {
                    nodeTitle = `${node.long_name} (${node.node_id})`;
                }
                
                // Build route information display
                let routeInfo = '';
                if (node.agent_routes && Object.keys(node.agent_routes).length > 0) {
                    routeInfo = '<strong>🛣️ Network Routes:</strong><br>';
                    for (const [agentId, routeData] of Object.entries(node.agent_routes)) {
                        const agentName = routeData.location_name || routeData.agent_id;
                        const hopCount = routeData.hop_count;
                        
                        if (routeData.route_type === 'traceroute' && routeData.route_path && routeData.route_path.length > 0) {
                            // Show full traceroute path
                            const pathDisplay = routeData.route_path.join(' → ');
                            const discoveryTime = routeData.discovery_timestamp ? 
                                new Date(routeData.discovery_timestamp).toLocaleString() : 'Unknown';
                            routeInfo += `&nbsp;&nbsp;📍 <strong>${agentName}</strong>: ${hopCount} hops<br>`;
                            routeInfo += `&nbsp;&nbsp;&nbsp;&nbsp;<span class="route-path">${pathDisplay}</span><br>`;
                            routeInfo += `&nbsp;&nbsp;&nbsp;&nbsp;<span class="route-discovery-time">Discovered: ${discoveryTime}</span><br>`;
                        } else {
                            // Show basic hop count
                            routeInfo += `&nbsp;&nbsp;📍 <strong>${agentName}</strong>: ${hopCount !== null ? hopCount + ' hops' : 'Unknown hops'}<br>`;
                        }
                    }
                } else if (node.hops_away !== null) {
                    // Fallback to old format if no route data
                    routeInfo = `<strong>🛣️ Network Hops: ${node.hops_away}</strong><br>`;
                }

                const popupContent = `
                    <strong>📡 ${nodeTitle}</strong><br>
                    ${node.hw_model ? `Hardware: ${node.hw_model}<br>` : ''}
                    ${node.role ? `Role: ${node.role}<br>` : ''}
                    Last Seen: ${lastSeen.toLocaleString()}<br>
                    ${node.battery_level ? `Battery: ${node.battery_level}%<br>` : ''}
                    ${node.voltage ? `Voltage: ${node.voltage.toFixed(2)}V<br>` : ''}
                    ${routeInfo}
                    ${node.rssi ? `RSSI: ${node.rssi} dBm<br>` : ''}
                    ${node.snr ? `SNR: ${node.snr} dB` : ''}
                `;
                
                marker.bindPopup(popupContent);
                marker.addTo(map);
                markers.set(`node_${node.node_id}`, marker);
            });
        }
        
        function displayAgents() {
            const filterType = document.getElementById('filter-type').value;
            
            // Clear existing agent markers
            markers.forEach((marker, key) => {
                if (key.startsWith('agent_')) {
                    map.removeLayer(marker);
                    markers.delete(key);
                }
            });
            
            if (filterType === 'nodes') return; // Skip agents when showing nodes only
            
            agentData.forEach(agent => {
                if (!agent.coordinates || agent.coordinates.length !== 2) return;
                
                const lastSeen = new Date(agent.last_seen);
                const isActive = (new Date() - lastSeen) < (60 * 60 * 1000); // 1 hour
                
                // Create agent marker (larger, different style)
                const marker = L.circleMarker([agent.coordinates[0], agent.coordinates[1]], {
                    radius: 12,
                    fillColor: '#2196F3',
                    color: '#fff',
                    weight: 3,
                    opacity: 1,
                    fillOpacity: 0.9
                });
                
                const popupContent = `
                    <strong>🏢 Agent: ${agent.agent_id}</strong><br>
                    Location: ${agent.location_name}<br>
                    Last Seen: ${lastSeen.toLocaleString()}<br>
                    Status: ${isActive ? '✅ Active' : '❌ Inactive'}<br>
                    Total Packets: ${agent.packet_count}
                `;
                
                marker.bindPopup(popupContent);
                marker.addTo(map);
                markers.set(`agent_${agent.agent_id}`, marker);
            });
        }
        
        function displayConnections(packets) {
            const showConnections = document.getElementById('show-connections').checked;
            
            // Clear existing connections
            connections.forEach(line => map.removeLayer(line));
            connections = [];
            
            if (!showConnections) return;
            
            // Create connections from recent packets (all types, not just text)
            const connectionMap = new Map();
            
            packets.forEach(packet => {
                // Show connections for all packet types except broadcasts
                if (packet.from_node && packet.to_node && packet.to_node !== '^all' && packet.to_node !== 'Broadcast') {
                    const key = `${packet.from_node}-${packet.to_node}`;
                    if (!connectionMap.has(key)) {
                        connectionMap.set(key, { count: 0, latest: packet.timestamp, types: new Set() });
                    }
                    connectionMap.get(key).count++;
                    connectionMap.get(key).types.add(packet.type);
                    if (packet.timestamp > connectionMap.get(key).latest) {
                        connectionMap.get(key).latest = packet.timestamp;
                    }
                }
            });
            
            connectionMap.forEach((data, key) => {
                const [fromNode, toNode] = key.split('-');
                let fromMarker = markers.get(`node_${fromNode}`) || markers.get(`agent_${fromNode}`);
                let toMarker = markers.get(`node_${toNode}`) || markers.get(`agent_${toNode}`);
                
                // Show agent-to-node connections even if destination node isn't on map
                // This reveals the network reach from agents
                if (fromMarker && toMarker) {
                    // Style connections based on activity and type
                    let lineColor = '#2196F3'; // Default blue
                    let lineWeight = Math.max(2, Math.min(data.count / 5, 6));
                    let lineOpacity = 0.7;
                    
                    // Color code by packet types
                    if (data.types.has('text')) lineColor = '#4CAF50'; // Green for text
                    else if (data.types.has('position')) lineColor = '#FF9800'; // Orange for position
                    else if (data.types.has('telemetry')) lineColor = '#9C27B0'; // Purple for telemetry
                    
                    const line = L.polyline([
                        fromMarker.getLatLng(),
                        toMarker.getLatLng()
                    ], {
                        color: lineColor,
                        weight: lineWeight,
                        opacity: lineOpacity,
                        dashArray: data.types.has('text') ? null : '5, 5' // Solid for text, dashed for data
                    });
                    
                    // Enhanced popup with routing information
                    const typesArray = Array.from(data.types);
                    line.bindPopup(`
                        <strong>🔗 Mesh Connection</strong><br>
                        <strong>From:</strong> ${fromNode}<br>
                        <strong>To:</strong> ${toNode}<br>
                        <strong>Packets:</strong> ${data.count}<br>
                        <strong>Types:</strong> ${typesArray.join(', ')}<br>
                        <strong>Latest:</strong> ${new Date(data.latest).toLocaleString()}
                    `);
                    
                    line.addTo(map);
                    connections.push(line);
                }
            });
        }
        
        function updateStats() {
            const now = new Date();
            const activeNodes = nodeData.filter(node => {
                const lastSeen = new Date(node.updated_at);
                return (now - lastSeen) < (60 * 60 * 1000);
            }).length;
            
            document.getElementById('total-nodes').textContent = nodeData.length;
            document.getElementById('active-nodes').textContent = activeNodes;
            document.getElementById('total-agents').textContent = agentData.length;
            
            // Calculate rough coverage area
            const positions = [...nodeData, ...agentData].map(item => 
                item.position || item.coordinates
            ).filter(pos => pos && pos[0] && pos[1]);
            
            let area = 0;
            if (positions.length > 2) {
                const lats = positions.map(p => p[0]);
                const lons = positions.map(p => p[1]);
                const latRange = Math.max(...lats) - Math.min(...lats);
                const lonRange = Math.max(...lons) - Math.min(...lons);
                area = Math.round(latRange * lonRange * 111 * 111); // Rough km²
            }
            
            document.getElementById('coverage-area').textContent = area > 0 ? area : '-';
        }
        
        function updateAgentFilter() {
            const select = document.getElementById('filter-agent');
            const currentValue = select.value;
            
            // Clear existing options except "All Agents"
            select.innerHTML = '<option value="all">All Agents</option>';
            
            // Add agent options
            agentData.forEach(agent => {
                const option = document.createElement('option');
                option.value = agent.agent_id;
                option.textContent = `${agent.agent_id} (${agent.location_name})`;
                select.appendChild(option);
            });
            
            // Restore previous selection
            select.value = currentValue;
        }
        
        function refreshMap() {
            loadMapData();
        }
        
        // Auto-fit map to show all markers
        function fitMapToMarkers() {
            if (markers.size > 0) {
                const group = new L.featureGroup([...markers.values()]);
                map.fitBounds(group.getBounds().pad(0.1));
            }
        }
        
        // Event listeners
        document.getElementById('filter-type').addEventListener('change', () => {
            displayNodes();
            displayAgents();
        });
        
        document.getElementById('filter-agent').addEventListener('change', refreshMap);
        document.getElementById('time-range').addEventListener('change', refreshMap);
        document.getElementById('show-connections').addEventListener('change', () => {
            displayConnections(packetData); // Use actual packet data
        });
        
        // Theme toggle functions
        function toggleTheme() {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme') || 'light';
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeToggleText(newTheme);
        }
        
        function updateThemeToggleText(theme) {
            const toggle = document.getElementById('theme-toggle');
            if (toggle) {
                toggle.textContent = theme === 'light' ? '🌙 Dark' : '☀️ Light';
            }
        }
        
        // Initialize theme toggle text on load
        window.addEventListener('DOMContentLoaded', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
            updateThemeToggleText(currentTheme);
        });
        
        // Initialize
        initMap();
        loadMapData();
        
        // Auto-refresh every 30 seconds
        setInterval(loadMapData, 30000);
        
        // Fit map after initial load
        setTimeout(fitMapToMarkers, 2000);
    </script>
</body>
</html>
        '''
        return web.Response(text=html, content_type='text/html')
    
    async def start_server(self):
        """Start the web server"""
        await self.setup_database()
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, self.bind_host, self.bind_port)
        await site.start()
        
        self.logger.info(f"Server started at http://{self.bind_host}:{self.bind_port}")
        return site

def create_sample_config():
    """Create sample server configuration"""
    config = configparser.ConfigParser()
    
    config['server'] = {
        'host': 'localhost',
        'port': '8082'
    }
    
    config['database'] = {
        'path': 'distributed_meshview.db'
    }
    
    config['api_keys'] = {
        'agent_001': secrets.token_hex(16),
        'agent_002': secrets.token_hex(16)
    }
    
    with open('server_config.ini', 'w') as f:
        config.write(f)
    
    print("Created sample server config: server_config.ini")
    print("\nAPI Keys generated:")
    for agent, key in config.items('api_keys'):
        print(f"  {agent}: {key}")
    print("\nUpdate your agent configurations with these API keys.")

async def main():
    parser = argparse.ArgumentParser(description='MeshyMcMapface Server MVP')
    parser.add_argument('--config', default='server_config.ini',
                       help='Configuration file path')
    parser.add_argument('--create-config', action='store_true',
                       help='Create sample configuration file')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Logging level')
    parser.add_argument('--log-file', 
                       help='Log file path (optional)')
    
    args = parser.parse_args()
    
    if args.create_config:
        create_sample_config()
        return
    
    if not Path(args.config).exists():
        print(f"Configuration file {args.config} not found.")
        print("Use --create-config to generate a sample configuration.")
        return
    
    # Load syslog configuration if available
    syslog_configs = None
    try:
        from src.core.config import ConfigManager
        config_manager = ConfigManager(args.config)
        syslog_config_objects = config_manager.load_syslog_configs()
        if syslog_config_objects:
            syslog_configs = [
                {
                    'host': config.host,
                    'port': config.port,
                    'protocol': config.protocol,
                    'facility': config.facility
                }
                for config in syslog_config_objects
            ]
    except Exception as e:
        print(f"Warning: Could not load syslog configuration: {e}")
    
    # Setup logging with syslog support
    try:
        from src.utils.logging import setup_logging
        setup_logging(level=args.log_level, log_file=args.log_file, syslog_configs=syslog_configs)
    except ImportError:
        # Fallback to basic logging if modular logging not available
        logging.basicConfig(level=getattr(logging, args.log_level.upper()),
                          format='%(asctime)s - %(levelname)s - %(message)s')
        if args.log_file:
            file_handler = logging.FileHandler(args.log_file)
            logging.getLogger().addHandler(file_handler)
    
    server = DistributedMeshyMcMapfaceServer(args.config)
    
    try:
        await server.start_server()
        
        # Keep server running
        while True:
            await asyncio.sleep(3600)  # Sleep for 1 hour
            
    except KeyboardInterrupt:
        print("Server stopped by user")

if __name__ == "__main__":
    asyncio.run(main())