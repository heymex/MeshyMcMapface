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
        
        # Web UI routes
        self.app.router.add_get('/', self.dashboard)
        self.app.router.add_get('/agents', self.agents_page)
        self.app.router.add_get('/packets', self.packets_page)
        self.app.router.add_get('/nodes', self.nodes_page)
        
        # Static files (CSS, JS)
        self.app.router.add_static('/', path='static/', name='static')
    
    @web_middlewares.middleware
    async def auth_middleware(self, request, handler):
        """Authentication middleware for API endpoints"""
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
                (agent_id, location_name, location_lat, location_lon, last_seen)
                VALUES (?, ?, ?, ?, ?)
            ''', (agent_id, location_name, location_lat, location_lon, 
                  datetime.now(timezone.utc).isoformat()))
            
            await self.db.commit()
            
            self.logger.info(f"Registered agent: {agent_id}")
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
    
    async def get_packets(self, request):
        """Get recent packets with filtering options"""
        try:
            # Parse query parameters
            limit = int(request.query.get('limit', 100))
            agent_id = request.query.get('agent_id')
            packet_type = request.query.get('type')
            
            # Build query
            query = '''
                SELECT p.*, a.location_name
                FROM packets p
                JOIN agents a ON p.agent_id = a.agent_id
                WHERE 1=1
            '''
            params = []
            
            if agent_id:
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
            
            # Build query
            query = '''
                SELECT n.node_id, n.agent_id, a.location_name, n.last_seen,
                       n.battery_level, n.position_lat, n.position_lon,
                       n.rssi, n.snr, n.updated_at
                FROM nodes n
                JOIN agents a ON n.agent_id = a.agent_id
                WHERE datetime(n.updated_at) > datetime('now', '-24 hours')
            '''
            params = []
            
            if agent_id:
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
                const response = await fetch('/api/agents');
                const data = await response.json();
                
                const tbody = document.querySelector('#agents-table tbody');
                tbody.innerHTML = '';
                
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
                console.error('Error loading agents:', error);
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
                const response = await fetch('/api/agents');
                const data = await response.json();
                
                const tbody = document.querySelector('#agents-table tbody');
                tbody.innerHTML = '';
                
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
    
    async def packets_page(self, request):
        """Packets page with filtering"""
        return web.Response(text="Packets page - TODO", content_type='text/html')
    
    async def nodes_page(self, request):
        """Nodes page with map"""
        return web.Response(text="Nodes page - TODO", content_type='text/html')
    
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