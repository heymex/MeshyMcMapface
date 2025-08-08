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
from typing import Dict, List, Optional

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
        
        # Setup logging
        logging.basicConfig(level=logging.INFO, 
                          format='%(asctime)s - %(levelname)s - %(message)s')
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
        
        # Create indexes for performance
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_packets_timestamp ON packets(timestamp)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_packets_agent ON packets(agent_id)')
        await self.db.execute('CREATE INDEX IF NOT EXISTS idx_nodes_agent ON nodes(agent_id)')
        
        await self.db.commit()
        self.logger.info("Database initialized")
    
    def setup_routes(self):
        """Setup web routes"""
        # API routes
        self.app.router.add_post('/api/agent/register', self.register_agent)
        self.app.router.add_post('/api/agent/data', self.receive_agent_data)
        self.app.router.add_get('/api/agents', self.list_agents)
        self.app.router.add_get('/api/agents/{agent_id}/status', self.agent_status)
        self.app.router.add_get('/api/packets', self.get_packets)
        self.app.router.add_get('/api/nodes', self.get_nodes)
        self.app.router.add_get('/api/stats', self.get_stats)
        self.app.router.add_get('/api/debug/agents', self.debug_agents)  # Debug endpoint
        
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
            
            # Insert packets
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
    
    async def get_packets(self, request):
        """Get recent packets with filtering options"""
        try:
            # Parse query parameters
            limit = int(request.query.get('limit', 100))
            agent_id = request.query.get('agent_id')
            packet_type = request.query.get('type')
            hours = int(request.query.get('hours', 24))
            
            # Build query
            query = '''
                SELECT p.*, a.location_name
                FROM packets p
                JOIN agents a ON p.agent_id = a.agent_id
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
                result.append({
                    'id': packet[0],
                    'agent_id': packet[1],
                    'agent_location': packet[12],
                    'timestamp': packet[2],
                    'from_node': packet[3],
                    'to_node': packet[4],
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
            hours = int(request.query.get('hours', 24))
            
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
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }
        .stat-number { font-size: 2em; font-weight: bold; color: #2196F3; }
        .stat-label { color: #666; margin-top: 5px; }
        .section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .section h2 { margin-top: 0; color: #333; }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        .table th { background: #f8f9fa; }
        .status-active { color: #4CAF50; font-weight: bold; }
        .status-inactive { color: #f44336; }
        .nav { display: flex; gap: 20px; margin-bottom: 20px; }
        .nav a { color: #2196F3; text-decoration: none; padding: 10px 20px; background: white; border-radius: 4px; }
        .nav a:hover { background: #e3f2fd; }
    </style>
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
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        .table th { background: #f8f9fa; }
        .status-active { color: #4CAF50; font-weight: bold; }
        .status-inactive { color: #f44336; }
        .nav { display: flex; gap: 20px; margin-bottom: 20px; }
        .nav a { color: #2196F3; text-decoration: none; padding: 10px 20px; background: white; border-radius: 4px; }
        .nav a:hover { background: #e3f2fd; }
        .nav a.active { background: #2196F3; color: white; }
    </style>
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
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        .table th { background: #f8f9fa; }
        .status-active { color: #4CAF50; font-weight: bold; }
        .status-inactive { color: #f44336; }
        .nav { display: flex; gap: 20px; margin-bottom: 20px; }
        .nav a { color: #2196F3; text-decoration: none; padding: 10px 20px; background: white; border-radius: 4px; }
        .nav a:hover { background: #e3f2fd; }
        .nav a.active { background: #2196F3; color: white; }
        .battery-high { color: #4CAF50; }
        .battery-medium { color: #FF9800; }
        .battery-low { color: #f44336; }
    </style>
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
        </div>
        
        <div class="section">
            <h2>All Network Nodes</h2>
            <table class="table" id="nodes-table">
                <thead>
                    <tr>
                        <th>Node ID</th>
                        <th>Agent</th>
                        <th>Last Seen</th>
                        <th>Battery</th>
                        <th>Position</th>
                        <th>Signal (RSSI)</th>
                        <th>SNR</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
    </div>
    
    <script>
        async function loadAllNodes() {
            try {
                console.log('Loading nodes...');
                const response = await fetch('/api/nodes');
                console.log('Nodes response status:', response.status);
                
                if (!response.ok) {
                    console.error('Failed to fetch nodes:', response.status, response.statusText);
                    return;
                }
                
                const data = await response.json();
                console.log('Nodes data:', data);
                
                const tbody = document.querySelector('#nodes-table tbody');
                tbody.innerHTML = '';
                
                if (!data.nodes || data.nodes.length === 0) {
                    console.log('No nodes found');
                    const row = tbody.insertRow();
                    row.innerHTML = '<td colspan="8" style="text-align: center;">No nodes found</td>';
                    return;
                }
                
                data.nodes.forEach(node => {
                    const row = tbody.insertRow();
                    const lastSeen = new Date(node.updated_at).toLocaleString();
                    const isActive = new Date() - new Date(node.updated_at) < 60 * 60 * 1000;
                    
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
                    
                    row.innerHTML = `
                        <td><strong>${node.node_id}</strong></td>
                        <td>${node.agent_location}</td>
                        <td>${lastSeen}</td>
                        <td class="${batteryClass}">${batteryDisplay}</td>
                        <td>${positionDisplay}</td>
                        <td>${node.rssi ? node.rssi + ' dBm' : '-'}</td>
                        <td>${node.snr ? node.snr + ' dB' : '-'}</td>
                        <td class="${isActive ? 'status-active' : 'status-inactive'}">
                            ${isActive ? 'Active' : 'Inactive'}
                        </td>
                    `;
                });
            } catch (error) {
                console.error('Error loading nodes:', error);
            }
        }
        
        // Initial load
        loadAllNodes();
        
        // Refresh every 30 seconds
        setInterval(loadAllNodes, 30000);
    </script>
</body>
</html>
        '''
        return web.Response(text=html, content_type='text/html')
    
    async def packets_page(self, request):
        """Packets page with filtering"""
        return web.Response(text="Packets page - Coming soon!", content_type='text/html')
    
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
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .nav { display: flex; gap: 20px; margin-bottom: 20px; }
        .nav a { color: #2196F3; text-decoration: none; padding: 10px 20px; background: white; border-radius: 4px; }
        .nav a:hover { background: #e3f2fd; }
        .nav a.active { background: #2196F3; color: white; }
        .controls { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
        .control-group { display: flex; gap: 5px; align-items: center; }
        .control-group label { font-weight: bold; }
        .control-group select, .control-group input { padding: 5px; border: 1px solid #ddd; border-radius: 4px; }
        #map { height: 600px; width: 100%; border-radius: 8px; }
        .legend { background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-top: 20px; }
        .legend h3 { margin-top: 0; }
        .legend-item { display: flex; align-items: center; margin: 10px 0; }
        .legend-icon { width: 20px; height: 20px; border-radius: 50%; margin-right: 10px; border: 2px solid #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }
        .stats-bar { display: flex; gap: 20px; margin-bottom: 20px; }
        .stat { background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; min-width: 120px; }
        .stat-number { font-size: 1.5em; font-weight: bold; color: #2196F3; }
        .stat-label { color: #666; font-size: 0.9em; }
    </style>
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
            <h3>Map Legend</h3>
            <div class="legend-item">
                <div class="legend-icon" style="background: #4CAF50;"></div>
                <span>Active Mesh Node (seen in last hour)</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="background: #FF9800;"></div>
                <span>Inactive Mesh Node (older than 1 hour)</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="background: #2196F3; transform: scale(1.3);"></div>
                <span>MeshyMcMapface Agent</span>
            </div>
            <div class="legend-item">
                <div class="legend-icon" style="background: #f44336;"></div>
                <span>Node with Low Battery (<20%)</span>
            </div>
            <div style="margin-top: 10px;">
                <strong>Lines:</strong> Recent packet transmissions between nodes
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
                
                let nodesUrl = `/api/nodes?hours=${timeRange}`;
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
                
                displayNodes();
                displayAgents();
                displayConnections(packetsData.packets || []);
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
                
                // Determine color based on status
                let color = '#4CAF50'; // Active
                if (!isActive) color = '#FF9800'; // Inactive
                if (node.battery_level && node.battery_level < 20) color = '#f44336'; // Low battery
                
                // Create marker
                const marker = L.circleMarker([node.position[0], node.position[1]], {
                    radius: 8,
                    fillColor: color,
                    color: '#fff',
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.8
                });
                
                // Create popup content
                const popupContent = `
                    <strong>Node: ${node.node_id}</strong><br>
                    Agent: ${node.agent_location}<br>
                    Last Seen: ${lastSeen.toLocaleString()}<br>
                    ${node.battery_level ? `Battery: ${node.battery_level}%<br>` : ''}
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
            
            // Create connections from recent packets
            const connectionMap = new Map();
            
            packets.forEach(packet => {
                if (packet.type === 'text_message' && packet.from_node && packet.to_node !== '^all') {
                    const key = `${packet.from_node}-${packet.to_node}`;
                    if (!connectionMap.has(key)) {
                        connectionMap.set(key, { count: 0, latest: packet.timestamp });
                    }
                    connectionMap.get(key).count++;
                    if (packet.timestamp > connectionMap.get(key).latest) {
                        connectionMap.get(key).latest = packet.timestamp;
                    }
                }
            });
            
            connectionMap.forEach((data, key) => {
                const [fromNode, toNode] = key.split('-');
                const fromMarker = markers.get(`node_${fromNode}`);
                const toMarker = markers.get(`node_${toNode}`);
                
                if (fromMarker && toMarker) {
                    const line = L.polyline([
                        fromMarker.getLatLng(),
                        toMarker.getLatLng()
                    ], {
                        color: '#666',
                        weight: Math.min(data.count, 5),
                        opacity: 0.6
                    });
                    
                    line.bindPopup(`
                        <strong>Connection</strong><br>
                        From: ${fromNode}<br>
                        To: ${toNode}<br>
                        Messages: ${data.count}<br>
                        Latest: ${new Date(data.latest).toLocaleString()}
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
            displayConnections([]); // Will reload connections based on current data
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
    
    args = parser.parse_args()
    
    if args.create_config:
        create_sample_config()
        return
    
    if not Path(args.config).exists():
        print(f"Configuration file {args.config} not found.")
        print("Use --create-config to generate a sample configuration.")
        return
    
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