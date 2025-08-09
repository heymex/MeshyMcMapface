#!/usr/bin/env python3
"""
Enhanced MeshyMcMapface Agent with Multi-Server Support
Supports reporting to multiple servers with different configurations
"""

import asyncio
import aiohttp
import json
import logging
import sqlite3
import time
import queue
import threading
import base64
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import configparser
import argparse
import sys
from pathlib import Path

# Meshtastic imports
try:
    import meshtastic
    import meshtastic.serial_interface
    import meshtastic.tcp_interface
    import meshtastic.ble_interface
    from pubsub import pub
except ImportError:
    print("Error: Meshtastic library not installed. Run: pip install meshtastic")
    sys.exit(1)

class ServerConfig:
    """Configuration for a single server"""
    def __init__(self, name: str, config_section: Dict):
        self.name = name
        self.url = config_section['url']
        self.api_key = config_section['api_key']
        self.enabled = config_section.get('enabled', 'true').lower() == 'true'
        self.report_interval = int(config_section.get('report_interval', 30))
        self.packet_types = config_section.get('packet_types', 'all').split(',')
        self.priority = int(config_section.get('priority', 1))
        self.max_retries = int(config_section.get('max_retries', 3))
        self.timeout = int(config_section.get('timeout', 10))
        
        # Server-specific filtering
        self.filter_nodes = config_section.get('filter_nodes', '').split(',') if config_section.get('filter_nodes') else []
        self.exclude_nodes = config_section.get('exclude_nodes', '').split(',') if config_section.get('exclude_nodes') else []
        
        # Status tracking
        self.last_success = None
        self.consecutive_failures = 0
        self.is_healthy = True

class MultiServerMeshyMcMapfaceAgent:
    def __init__(self, config_file: str):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        
        # Agent configuration
        self.agent_id = self.config.get('agent', 'id')
        self.location_name = self.config.get('agent', 'location_name')
        self.location_lat = self.config.getfloat('agent', 'location_lat')
        self.location_lon = self.config.getfloat('agent', 'location_lon')
        
        # Meshtastic configuration
        self.connection_type = self.config.get('meshtastic', 'connection_type', fallback='auto')
        self.device_path = self.config.get('meshtastic', 'device_path', fallback=None)
        self.tcp_host = self.config.get('meshtastic', 'tcp_host', fallback=None)
        self.ble_address = self.config.get('meshtastic', 'ble_address', fallback=None)
        
        # Load server configurations
        self.servers = {}
        self.load_server_configs()
        
        # State
        self.interface = None
        self.packet_buffer = []
        self.node_status = {}
        self.running = True
        
        # Thread-safe packet queue
        self.packet_queue = queue.Queue()
        self.node_queue = queue.Queue()
        
        # Server-specific queues (for different reporting intervals)
        self.server_queues = {name: queue.Queue() for name in self.servers.keys()}
        
        # Setup logging
        logging.basicConfig(level=logging.INFO, 
                          format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Setup local database
        self.setup_database()
        
        self.logger.info(f"Loaded {len(self.servers)} server configurations")
        for name, server in self.servers.items():
            if server.enabled:
                self.logger.info(f"  - {name}: {server.url} (interval: {server.report_interval}s, priority: {server.priority})")
            else:
                self.logger.info(f"  - {name}: DISABLED")
    
    def load_server_configs(self):
        """Load multiple server configurations"""
        for section_name in self.config.sections():
            if section_name.startswith('server_'):
                server_name = section_name[7:]  # Remove 'server_' prefix
                server_config = dict(self.config.items(section_name))
                self.servers[server_name] = ServerConfig(server_name, server_config)
    
    def setup_database(self):
        """Initialize local SQLite database for buffering"""
        self.db_path = f"{self.agent_id}_buffer.db"
    
    def get_db_connection(self):
        """Get a database connection for the current thread"""
        conn = sqlite3.connect(self.db_path)
        
        # Create tables if they don't exist
        conn.execute('''
            CREATE TABLE IF NOT EXISTS packet_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                packet_data TEXT,
                server_status TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
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
                PRIMARY KEY (node_id, agent_id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS server_health (
                server_name TEXT PRIMARY KEY,
                last_success TEXT,
                last_failure TEXT,
                consecutive_failures INTEGER DEFAULT 0,
                total_packets_sent INTEGER DEFAULT 0,
                is_healthy BOOLEAN DEFAULT 1
            )
        ''')
        
        conn.commit()
        return conn
    
    def connect_to_node(self):
        """Connect to Meshtastic node based on configuration"""
        try:
            if self.connection_type == 'serial' or (self.connection_type == 'auto' and self.device_path):
                self.logger.info(f"Connecting via serial to {self.device_path}")
                self.interface = meshtastic.serial_interface.SerialInterface(devPath=self.device_path)
                
            elif self.connection_type == 'tcp' or (self.connection_type == 'auto' and self.tcp_host):
                self.logger.info(f"Connecting via TCP to {self.tcp_host}")
                self.interface = meshtastic.tcp_interface.TCPInterface(hostname=self.tcp_host)
                
            elif self.connection_type == 'ble' or (self.connection_type == 'auto' and self.ble_address):
                self.logger.info(f"Connecting via BLE to {self.ble_address}")
                self.interface = meshtastic.ble_interface.BLEInterface(address=self.ble_address)
                
            else:
                # Auto-detect
                self.logger.info("Auto-detecting Meshtastic device...")
                self.interface = meshtastic.serial_interface.SerialInterface()
            
            # Subscribe to events
            pub.subscribe(self.on_receive, "meshtastic.receive")
            pub.subscribe(self.on_connection, "meshtastic.connection.established")
            pub.subscribe(self.on_node_updated, "meshtastic.node.updated")
            
            self.logger.info("Successfully connected to Meshtastic node")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Meshtastic node: {e}")
            return False
    
    def should_send_to_server(self, server: ServerConfig, packet_data: Dict, node_id: str) -> bool:
        """Determine if packet should be sent to specific server"""
        if not server.enabled:
            return False
        
        # Check packet type filtering
        if server.packet_types != ['all'] and packet_data['type'] not in server.packet_types:
            return False
        
        # Check node filtering
        if server.filter_nodes and node_id not in server.filter_nodes:
            return False
        
        if server.exclude_nodes and node_id in server.exclude_nodes:
            return False
        
        return True
    
    def on_receive(self, packet, interface):
        """Handle received packets"""
        try:
            self.logger.info(f"Received packet from: {packet.get('fromId', 'unknown')}")
            
            # Convert packet to JSON-serializable format
            packet_data = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'from_node': packet.get('fromId', ''),
                'to_node': packet.get('toId', ''),
                'packet_id': packet.get('id', 0),
                'channel': packet.get('channel', 0),
                'hop_limit': packet.get('hopLimit', 0),
                'want_ack': packet.get('wantAck', False),
                'rssi': packet.get('rssi', None),
                'snr': packet.get('snr', None),
                'type': 'unknown',
                'payload': None
            }
            
            # Process packet types (similar to original agent)
            if 'decoded' in packet and packet['decoded']:
                decoded = packet['decoded']
                
                if 'text' in decoded:
                    packet_data['type'] = 'text_message'
                    packet_data['payload'] = decoded['text']
                elif 'position' in decoded:
                    packet_data['type'] = 'position'
                    pos = decoded['position']
                    position_data = {
                        'latitude': getattr(pos, 'latitude', 0) if hasattr(pos, 'latitude') else pos.get('latitude', 0),
                        'longitude': getattr(pos, 'longitude', 0) if hasattr(pos, 'longitude') else pos.get('longitude', 0),
                        'altitude': getattr(pos, 'altitude', 0) if hasattr(pos, 'altitude') else pos.get('altitude', 0),
                        'time': getattr(pos, 'time', 0) if hasattr(pos, 'time') else pos.get('time', 0)
                    }
                    packet_data['payload'] = position_data
                    
                    if packet_data['from_node'] and position_data['latitude'] and position_data['longitude']:
                        self.update_node_position(packet_data['from_node'], position_data)
                elif 'telemetry' in decoded:
                    packet_data['type'] = 'telemetry'
                    # Process telemetry data...
                elif 'user' in decoded:
                    packet_data['type'] = 'user_info'
                    # Process user info...
                else:
                    packet_data['type'] = 'other'
            else:
                packet_data['type'] = 'encrypted'
            
            # Update node tracking
            if packet_data['from_node'] and packet_data['from_node'] not in ['^all', '^local', 'null', '']:
                self.update_node_from_packet(packet_data['from_node'], packet_data)
            
            # Buffer packet for all relevant servers
            self.buffer_packet_for_servers(packet_data)
            
        except Exception as e:
            self.logger.error(f"Error processing packet: {e}")
    
    def buffer_packet_for_servers(self, packet_data: Dict):
        """Buffer packet with server-specific routing information"""
        try:
            # Determine which servers should receive this packet
            server_routing = {}
            node_id = packet_data['from_node']
            
            for server_name, server in self.servers.items():
                if self.should_send_to_server(server, packet_data, node_id):
                    server_routing[server_name] = {
                        'queued': False,
                        'sent': False,
                        'last_attempt': None,
                        'retry_count': 0
                    }
            
            if server_routing:
                conn = self.get_db_connection()
                conn.execute('''
                    INSERT INTO packet_buffer (timestamp, packet_data, server_status)
                    VALUES (?, ?, ?)
                ''', (packet_data['timestamp'], json.dumps(packet_data), json.dumps(server_routing)))
                conn.commit()
                conn.close()
                
                self.logger.debug(f"Buffered packet for servers: {list(server_routing.keys())}")
            
        except Exception as e:
            self.logger.error(f"Error buffering packet for servers: {e}")
    
    def update_node_from_packet(self, node_id, packet_data):
        """Update node information from any packet"""
        if not node_id or node_id in ['^all', '^local']:
            return
            
        status = {
            'node_id': node_id,
            'last_seen': packet_data['timestamp'],
            'battery_level': None,
            'position_lat': None,
            'position_lon': None,
            'rssi': packet_data.get('rssi'),
            'snr': packet_data.get('snr'),
            'updated_at': packet_data['timestamp']
        }
        
        self.node_status[node_id] = status
        self.node_queue.put(status)
    
    def update_node_position(self, node_id, position_data):
        """Update node position"""
        if node_id in self.node_status:
            self.node_status[node_id]['position_lat'] = position_data['latitude']
            self.node_status[node_id]['position_lon'] = position_data['longitude']
            self.node_status[node_id]['updated_at'] = datetime.now(timezone.utc).isoformat()
            self.node_queue.put(self.node_status[node_id])
    
    def on_connection(self, interface, topic=None):
        """Handle connection established"""
        self.logger.info("Meshtastic connection established")
    
    def on_node_updated(self, node):
        """Handle node updates"""
        pass  # Simplified for brevity
    
    async def register_with_server(self, server: ServerConfig) -> bool:
        """Register this agent with a specific server"""
        try:
            payload = {
                'agent_id': self.agent_id,
                'location': {
                    'name': self.location_name,
                    'coordinates': [self.location_lat, self.location_lon]
                }
            }
            
            headers = {
                'Content-Type': 'application/json',
                'X-API-Key': server.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{server.url}/api/agent/register",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=server.timeout)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.logger.info(f"Successfully registered with {server.name}: {result.get('agent_id')}")
                        self.update_server_health(server.name, success=True)
                        return True
                    else:
                        self.logger.error(f"Failed to register with {server.name}: {response.status}")
                        self.update_server_health(server.name, success=False)
                        return False
                        
        except Exception as e:
            self.logger.error(f"Error registering with {server.name}: {e}")
            self.update_server_health(server.name, success=False)
            return False
    
    async def send_data_to_server(self, server: ServerConfig):
        """Send buffered data to a specific server"""
        try:
            # Get unsent packets for this server
            conn = self.get_db_connection()
            cursor = conn.execute('''
                SELECT id, packet_data, server_status FROM packet_buffer 
                WHERE created_at > datetime('now', '-1 hour')
                ORDER BY timestamp 
                LIMIT 100
            ''')
            packets = cursor.fetchall()
            
            if not packets:
                conn.close()
                return
            
            # Filter packets that need to be sent to this server
            packets_to_send = []
            packet_ids_to_update = []
            
            for packet_row in packets:
                packet_id, packet_data_str, server_status_str = packet_row
                server_status = json.loads(server_status_str)
                
                if (server.name in server_status and 
                    not server_status[server.name]['sent'] and
                    server_status[server.name]['retry_count'] < server.max_retries):
                    
                    packets_to_send.append(json.loads(packet_data_str))
                    packet_ids_to_update.append(packet_id)
            
            if not packets_to_send:
                conn.close()
                return
            
            # Get current node status - FIXED: Query the correct table with correct structure
            cursor = conn.execute('''
                SELECT node_id, last_seen, battery_level, position_lat, position_lon, rssi, snr
                FROM nodes 
                WHERE agent_id = ? AND datetime(updated_at) > datetime('now', '-24 hours')
            ''', (self.agent_id,))
            nodes = cursor.fetchall()
            conn.close()
            
            # Prepare payload
            payload = {
                'agent_id': self.agent_id,
                'location': {
                    'name': self.location_name,
                    'coordinates': [self.location_lat, self.location_lon]
                },
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'packets': packets_to_send,
                'node_status': [
                    {
                        'node_id': n[0],           # node_id
                        'last_seen': n[1],         # last_seen
                        'battery_level': n[2],     # battery_level
                        'position': [n[3], n[4]] if n[3] and n[4] else None,  # position_lat, position_lon
                        'rssi': n[5],              # rssi
                        'snr': n[6]                # snr
                    } for n in nodes
                ]
            }
            
            # Send to server
            headers = {
                'Content-Type': 'application/json',
                'X-API-Key': server.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{server.url}/api/agent/data",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=server.timeout)
                ) as response:
                    if response.status == 200:
                        # Mark packets as sent for this server
                        self.mark_packets_sent(packet_ids_to_update, server.name)
                        self.update_server_health(server.name, success=True)
                        
                        self.logger.info(f"Successfully sent {len(packets_to_send)} packets to {server.name}")
                    else:
                        self.logger.error(f"Server {server.name} returned status {response.status}")
                        self.update_server_health(server.name, success=False)
                        
        except Exception as e:
            self.logger.error(f"Error sending data to {server.name}: {e}")
            self.update_server_health(server.name, success=False)
    
    def mark_packets_sent(self, packet_ids: List[int], server_name: str):
        """Mark packets as sent to a specific server"""
        try:
            conn = self.get_db_connection()
            
            for packet_id in packet_ids:
                cursor = conn.execute('SELECT server_status FROM packet_buffer WHERE id = ?', (packet_id,))
                row = cursor.fetchone()
                if row:
                    server_status = json.loads(row[0])
                    if server_name in server_status:
                        server_status[server_name]['sent'] = True
                        server_status[server_name]['last_attempt'] = datetime.now(timezone.utc).isoformat()
                    
                    conn.execute('UPDATE packet_buffer SET server_status = ? WHERE id = ?',
                               (json.dumps(server_status), packet_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error marking packets sent for {server_name}: {e}")
    
    def update_server_health(self, server_name: str, success: bool):
        """Update server health status"""
        try:
            conn = self.get_db_connection()
            now = datetime.now(timezone.utc).isoformat()
            
            if success:
                conn.execute('''
                    INSERT OR REPLACE INTO server_health 
                    (server_name, last_success, consecutive_failures, total_packets_sent, is_healthy)
                    VALUES (?, ?, 0, COALESCE((SELECT total_packets_sent FROM server_health WHERE server_name = ?), 0) + 1, 1)
                ''', (server_name, now, server_name))
                
                if server_name in self.servers:
                    self.servers[server_name].consecutive_failures = 0
                    self.servers[server_name].is_healthy = True
                    self.servers[server_name].last_success = now
            else:
                conn.execute('''
                    INSERT OR REPLACE INTO server_health 
                    (server_name, last_failure, consecutive_failures, total_packets_sent, is_healthy)
                    VALUES (?, ?, COALESCE((SELECT consecutive_failures FROM server_health WHERE server_name = ?), 0) + 1, 
                            COALESCE((SELECT total_packets_sent FROM server_health WHERE server_name = ?), 0), 0)
                ''', (server_name, now, server_name, server_name))
                
                if server_name in self.servers:
                    self.servers[server_name].consecutive_failures += 1
                    self.servers[server_name].is_healthy = False
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error updating server health for {server_name}: {e}")
    
    def process_queued_data(self):
        """Process queued packets and node updates from main thread"""
        # Process node updates
        node_count = 0
        while not self.node_queue.empty():
            try:
                status = self.node_queue.get_nowait()
                self.update_node_status(status)
                node_count += 1
            except queue.Empty:
                break
            except Exception as e:
                self.logger.error(f"Error processing queued node status: {e}")
        
        if node_count > 0:
            self.logger.info(f"Processed {node_count} queued node updates")
    
    def update_node_status(self, status):
        """Update node status in local database"""
        try:
            self.logger.info(f"Writing node {status['node_id']} to database: lat={status['position_lat']}, lon={status['position_lon']}, battery={status['battery_level']}")
            
            conn = self.get_db_connection()
            conn.execute('''
                INSERT OR REPLACE INTO nodes 
                (node_id, agent_id, last_seen, battery_level, position_lat, position_lon, rssi, snr, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                status['node_id'], self.agent_id, status['last_seen'], status['battery_level'],
                status['position_lat'], status['position_lon'], 
                status['rssi'], status['snr'], status['updated_at']
            ))
            conn.commit()
            conn.close()
            
            self.logger.info(f"Successfully wrote node {status['node_id']} to database")
            
        except Exception as e:
            self.logger.error(f"Error updating node status: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def run(self):
        """Main agent loop with multi-server support"""
        self.logger.info(f"Starting Multi-Server MeshyMcMapface Agent {self.agent_id}")
        
        # Connect to Meshtastic node
        if not self.connect_to_node():
            self.logger.error("Failed to connect to Meshtastic node, exiting")
            return
        
        # Register with all enabled servers
        self.logger.info("Registering with servers...")
        for server in self.servers.values():
            if server.enabled:
                success = await self.register_with_server(server)
                if success:
                    self.logger.info(f"Registration with {server.name} successful")
                else:
                    self.logger.warning(f"Registration with {server.name} failed")
        
        # Create per-server tasks with different intervals
        server_tasks = []
        for server in self.servers.values():
            if server.enabled:
                task = asyncio.create_task(self.server_loop(server))
                server_tasks.append(task)
        
        # Main processing loop
        try:
            while self.running:
                # Process queued data
                self.process_queued_data()
                
                # Cleanup old data
                await self.cleanup_old_data()
                
                # Wait before next cycle
                await asyncio.sleep(5)  # Fast processing loop
                
        except KeyboardInterrupt:
            self.logger.info("Received interrupt, shutting down...")
            self.running = False
        
        # Cancel server tasks
        for task in server_tasks:
            task.cancel()
        
        # Cleanup
        if self.interface:
            self.interface.close()
        self.logger.info("Multi-Server MeshyMcMapface Agent stopped")
    
    async def server_loop(self, server: ServerConfig):
        """Individual server reporting loop"""
        self.logger.info(f"Started reporting loop for {server.name} (interval: {server.report_interval}s)")
        
        while self.running:
            try:
                if server.enabled and server.is_healthy:
                    await self.send_data_to_server(server)
                
                await asyncio.sleep(server.report_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in server loop for {server.name}: {e}")
                await asyncio.sleep(server.report_interval)
    
    async def cleanup_old_data(self):
        """Clean up old buffered data"""
        try:
            # Remove old packets (keep for 24 hours)
            cutoff = datetime.now(timezone.utc).timestamp() - (24 * 60 * 60)
            cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
            
            conn = self.get_db_connection()
            conn.execute('''
                DELETE FROM packet_buffer 
                WHERE created_at < ?
            ''', (cutoff_iso,))
            
            # Also clean up old nodes (keep for 7 days)
            node_cutoff = datetime.now(timezone.utc).timestamp() - (7 * 24 * 60 * 60)
            node_cutoff_iso = datetime.fromtimestamp(node_cutoff, timezone.utc).isoformat()
            
            conn.execute('''
                DELETE FROM nodes 
                WHERE updated_at < ?
            ''', (node_cutoff_iso,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old data: {e}")

def create_sample_multi_config():
    """Create sample configuration file for multi-server setup"""
    config = configparser.ConfigParser()
    
    config['agent'] = {
        'id': 'agent_001',
        'location_name': 'Test Location',
        'location_lat': '37.7749',
        'location_lon': '-122.4194'
    }
    
    config['meshtastic'] = {
        'connection_type': 'auto',
        '# device_path': '/dev/ttyUSB0',
        '# tcp_host': '192.168.1.100',
        '# ble_address': 'AA:BB:CC:DD:EE:FF'
    }
    
    # Primary server
    config['server_primary'] = {
        'url': 'http://localhost:8082',
        'api_key': 'primary-server-key',
        'enabled': 'true',
        'report_interval': '30',
        'packet_types': 'all',
        'priority': '1',
        'max_retries': '3',
        'timeout': '10'
    }
    
    # Backup server
    config['server_backup'] = {
        'url': 'http://backup.example.com:8082',
        'api_key': 'backup-server-key',
        'enabled': 'true',
        'report_interval': '60',
        'packet_types': 'all',
        'priority': '2',
        'max_retries': '5',
        'timeout': '15'
    }
    
    # Analytics server (only specific data)
    config['server_analytics'] = {
        'url': 'http://analytics.example.com:8083',
        'api_key': 'analytics-server-key',
        'enabled': 'true',
        'report_interval': '300',
        'packet_types': 'position,telemetry',
        'priority': '3',
        'max_retries': '2',
        'timeout': '30',
        '# filter_nodes': '!node1,!node2',
        '# exclude_nodes': '!private_node'
    }
    
    with open('multi_agent_config.ini', 'w') as f:
        config.write(f)
    
    print("Created sample multi-server config file: multi_agent_config.ini")
    print("\nServer configurations:")
    print("  - Primary: Real-time reporting every 30s")
    print("  - Backup: Redundant reporting every 60s") 
    print("  - Analytics: Position/telemetry only every 5min")

def main():
    parser = argparse.ArgumentParser(description='Multi-Server MeshyMcMapface Agent')
    parser.add_argument('--config', default='multi_agent_config.ini',
                       help='Configuration file path')
    parser.add_argument('--create-config', action='store_true',
                       help='Create sample multi-server configuration file')
    
    args = parser.parse_args()
    
    if args.create_config:
        create_sample_multi_config()
        return
    
    if not Path(args.config).exists():
        print(f"Configuration file {args.config} not found.")
        print("Use --create-config to generate a sample configuration.")
        return
    
    agent = MultiServerMeshyMcMapfaceAgent(args.config)
    
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("Agent stopped by user")

if __name__ == "__main__":
    main()