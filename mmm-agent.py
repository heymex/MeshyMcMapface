#!/usr/bin/env python3
"""
MeshyMcMapface Agent MVP - Connects to local Meshtastic node and reports to central server
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
from typing import Dict, List, Optional
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

class MeshyMcMapfaceAgent:
    def __init__(self, config_file: str):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        
        # Configuration
        self.agent_id = self.config.get('agent', 'id')
        self.location_name = self.config.get('agent', 'location_name')
        self.location_lat = self.config.getfloat('agent', 'location_lat')
        self.location_lon = self.config.getfloat('agent', 'location_lon')
        
        self.server_url = self.config.get('server', 'url')
        self.api_key = self.config.get('server', 'api_key')
        self.report_interval = self.config.getint('server', 'report_interval', fallback=30)
        
        self.connection_type = self.config.get('meshtastic', 'connection_type', fallback='auto')
        self.device_path = self.config.get('meshtastic', 'device_path', fallback=None)
        self.tcp_host = self.config.get('meshtastic', 'tcp_host', fallback=None)
        self.ble_address = self.config.get('meshtastic', 'ble_address', fallback=None)
        
        # State
        self.interface = None
        self.packet_buffer = []
        self.node_status = {}
        self.running = True
        
        # Thread-safe packet queue
        self.packet_queue = queue.Queue()
        self.node_queue = queue.Queue()
        
        # Setup logging
        logging.basicConfig(level=logging.INFO, 
                          format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # Setup local database
        self.setup_database()
        
    def setup_database(self):
        """Initialize local SQLite database for buffering"""
        self.db_path = f"{self.agent_id}_buffer.db"
        # Note: We'll create connections in the specific threads that need them
    
    def get_db_connection(self):
        """Get a database connection for the current thread"""
        conn = sqlite3.connect(self.db_path)
        
        # Create tables if they don't exist
        conn.execute('''
            CREATE TABLE IF NOT EXISTS packet_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                packet_data TEXT,
                sent INTEGER DEFAULT 0
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS node_status (
                node_id TEXT PRIMARY KEY,
                last_seen TEXT,
                battery_level INTEGER,
                position_lat REAL,
                position_lon REAL,
                rssi INTEGER,
                snr REAL,
                updated_at TEXT
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
    
    def _safe_convert(self, value):
        """Safely convert values to JSON-serializable types"""
        if isinstance(value, bytes):
            # Convert bytes to base64 string
            return base64.b64encode(value).decode('ascii')
        elif hasattr(value, '__dict__'):
            # Convert objects with __dict__ to dict
            return {k: self._safe_convert(v) for k, v in value.__dict__.items()}
        elif isinstance(value, (list, tuple)):
            return [self._safe_convert(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._safe_convert(v) for k, v in value.items()}
        else:
            return value
    
    def _convert_protobuf_to_dict(self, obj):
        """Convert protobuf objects to dictionaries recursively"""
        if hasattr(obj, 'ListFields'):
            # This is a protobuf message
            result = {}
            for field, value in obj.ListFields():
                if hasattr(value, 'ListFields'):
                    result[field.name] = self._convert_protobuf_to_dict(value)
                elif isinstance(value, (list, tuple)):
                    result[field.name] = [self._convert_protobuf_to_dict(item) if hasattr(item, 'ListFields') else self._safe_convert(item) for item in value]
                else:
                    result[field.name] = self._safe_convert(value)
            return result
        elif isinstance(obj, dict):
            # Already a dict, process recursively
            result = {}
            for key, value in obj.items():
                if hasattr(value, 'ListFields'):
                    result[key] = self._convert_protobuf_to_dict(value)
                elif isinstance(value, (list, tuple)):
                    result[key] = [self._convert_protobuf_to_dict(item) if hasattr(item, 'ListFields') else self._safe_convert(item) for item in value]
                else:
                    result[key] = self._safe_convert(value)
            return result
        else:
            return self._safe_convert(obj)
    
    def on_receive(self, packet, interface):
        """Handle received packets"""
        try:
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
                'snr': packet.get('snr', None)
            }
            
            # Handle different payload types
            if 'decoded' in packet:
                decoded = packet['decoded']
                packet_data['port_num'] = decoded.get('portnum', '')
                
                if 'text' in decoded:
                    packet_data['type'] = 'text_message'
                    packet_data['payload'] = decoded['text']
                    
                elif 'position' in decoded:
                    packet_data['type'] = 'position'
                    pos = decoded['position']
                    # Convert protobuf position to dict
                    packet_data['payload'] = {
                        'latitude': getattr(pos, 'latitude', 0) if hasattr(pos, 'latitude') else pos.get('latitude', 0),
                        'longitude': getattr(pos, 'longitude', 0) if hasattr(pos, 'longitude') else pos.get('longitude', 0),
                        'altitude': getattr(pos, 'altitude', 0) if hasattr(pos, 'altitude') else pos.get('altitude', 0),
                        'time': getattr(pos, 'time', 0) if hasattr(pos, 'time') else pos.get('time', 0)
                    }
                    
                elif 'telemetry' in decoded:
                    packet_data['type'] = 'telemetry'
                    tel = decoded['telemetry']
                    # Convert protobuf telemetry to dict
                    telemetry_data = {}
                    
                    # Handle device metrics
                    if hasattr(tel, 'device_metrics') or 'device_metrics' in tel:
                        device_metrics = getattr(tel, 'device_metrics', None) or tel.get('device_metrics')
                        if device_metrics:
                            telemetry_data['device_metrics'] = {
                                'battery_level': getattr(device_metrics, 'battery_level', None) if hasattr(device_metrics, 'battery_level') else device_metrics.get('battery_level'),
                                'voltage': getattr(device_metrics, 'voltage', None) if hasattr(device_metrics, 'voltage') else device_metrics.get('voltage'),
                                'channel_utilization': getattr(device_metrics, 'channel_utilization', None) if hasattr(device_metrics, 'channel_utilization') else device_metrics.get('channel_utilization'),
                                'air_util_tx': getattr(device_metrics, 'air_util_tx', None) if hasattr(device_metrics, 'air_util_tx') else device_metrics.get('air_util_tx')
                            }
                    
                    # Handle environment metrics
                    if hasattr(tel, 'environment_metrics') or 'environment_metrics' in tel:
                        env_metrics = getattr(tel, 'environment_metrics', None) or tel.get('environment_metrics')
                        if env_metrics:
                            telemetry_data['environment_metrics'] = {
                                'temperature': getattr(env_metrics, 'temperature', None) if hasattr(env_metrics, 'temperature') else env_metrics.get('temperature'),
                                'relative_humidity': getattr(env_metrics, 'relative_humidity', None) if hasattr(env_metrics, 'relative_humidity') else env_metrics.get('relative_humidity'),
                                'barometric_pressure': getattr(env_metrics, 'barometric_pressure', None) if hasattr(env_metrics, 'barometric_pressure') else env_metrics.get('barometric_pressure')
                            }
                    
                    packet_data['payload'] = telemetry_data
                    
                elif 'user' in decoded:
                    packet_data['type'] = 'user_info'
                    user = decoded['user']
                    # Convert protobuf user to dict
                    packet_data['payload'] = {
                        'id': getattr(user, 'id', '') if hasattr(user, 'id') else user.get('id', ''),
                        'long_name': getattr(user, 'long_name', '') if hasattr(user, 'long_name') else user.get('long_name', ''),
                        'short_name': getattr(user, 'short_name', '') if hasattr(user, 'short_name') else user.get('short_name', ''),
                        'hw_model': getattr(user, 'hw_model', 0) if hasattr(user, 'hw_model') else user.get('hw_model', 0)
                    }
                    
                else:
                    packet_data['type'] = 'other'
                    # Try to convert any protobuf objects to strings
                    try:
                        packet_data['payload'] = self._convert_protobuf_to_dict(decoded)
                    except:
                        packet_data['payload'] = self._safe_convert(decoded)
            
            # Buffer packet locally (thread-safe)
            self.packet_queue.put(packet_data)
            self.logger.debug(f"Queued packet: {packet_data['type']} from {packet_data['from_node']}")
            
        except Exception as e:
            self.logger.error(f"Error processing packet: {e}")
            # Log the problematic packet for debugging
            self.logger.debug(f"Problematic packet: {packet}")
    
    def on_connection(self, interface, topic=None):
        """Handle connection established"""
        self.logger.info("Meshtastic connection established")
    
    def on_node_updated(self, node):
        """Handle node updates"""
        try:
            node_id = node.get('user', {}).get('id', '')
            if not node_id:
                return
                
            status = {
                'node_id': node_id,
                'last_seen': datetime.now(timezone.utc).isoformat(),
                'battery_level': node.get('deviceMetrics', {}).get('batteryLevel', None),
                'position_lat': node.get('position', {}).get('latitude', None),
                'position_lon': node.get('position', {}).get('longitude', None),
                'rssi': None,  # Will be updated from packets
                'snr': None,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            self.node_status[node_id] = status
            self.node_queue.put(status)
            
        except Exception as e:
            self.logger.error(f"Error updating node status: {e}")
    
    def buffer_packet(self, packet_data):
        """Store packet in local buffer - called from main thread"""
        try:
            conn = self.get_db_connection()
            conn.execute('''
                INSERT INTO packet_buffer (timestamp, packet_data)
                VALUES (?, ?)
            ''', (packet_data['timestamp'], json.dumps(packet_data)))
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Error buffering packet: {e}")
    
    def update_node_status(self, status):
        """Update node status in local database - called from main thread"""
        try:
            conn = self.get_db_connection()
            conn.execute('''
                INSERT OR REPLACE INTO node_status 
                (node_id, last_seen, battery_level, position_lat, position_lon, rssi, snr, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                status['node_id'], status['last_seen'], status['battery_level'],
                status['position_lat'], status['position_lon'], 
                status['rssi'], status['snr'], status['updated_at']
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Error updating node status: {e}")
    
    def process_queued_data(self):
        """Process queued packets and node updates from main thread"""
        # Process packets
        while not self.packet_queue.empty():
            try:
                packet_data = self.packet_queue.get_nowait()
                self.buffer_packet(packet_data)
            except queue.Empty:
                break
            except Exception as e:
                self.logger.error(f"Error processing queued packet: {e}")
        
        # Process node updates
        while not self.node_queue.empty():
            try:
                status = self.node_queue.get_nowait()
                self.update_node_status(status)
            except queue.Empty:
                break
            except Exception as e:
                self.logger.error(f"Error processing queued node status: {e}")
    
    async def register_with_server(self):
        """Register this agent with the central server"""
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
                'X-API-Key': self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.server_url}/api/agent/register",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.logger.info(f"Successfully registered with server: {result.get('agent_id')}")
                        return True
                    else:
                        self.logger.error(f"Failed to register with server: {response.status}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"Error registering with server: {e}")
            return False
    
    async def send_data_to_server(self):
        """Send buffered data to central server"""
        try:
            # Get unsent packets
            conn = self.get_db_connection()
            cursor = conn.execute('''
                SELECT id, packet_data FROM packet_buffer 
                WHERE sent = 0 
                ORDER BY timestamp 
                LIMIT 100
            ''')
            packets = cursor.fetchall()
            
            if not packets:
                conn.close()
                return
            
            # Get current node status
            cursor = conn.execute('SELECT * FROM node_status')
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
                'packets': [json.loads(p[1]) for p in packets],
                'node_status': [
                    {
                        'node_id': n[0],
                        'last_seen': n[1],
                        'battery_level': n[2],
                        'position': [n[3], n[4]] if n[3] and n[4] else None,
                        'rssi': n[5],
                        'snr': n[6]
                    } for n in nodes
                ]
            }
            
            # Send to server
            headers = {
                'Content-Type': 'application/json',
                'X-API-Key': self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.server_url}/api/agent/data",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        # Mark packets as sent
                        conn = self.get_db_connection()
                        packet_ids = [p[0] for p in packets]
                        placeholders = ','.join('?' * len(packet_ids))
                        conn.execute(f'''
                            UPDATE packet_buffer 
                            SET sent = 1 
                            WHERE id IN ({placeholders})
                        ''', packet_ids)
                        conn.commit()
                        conn.close()
                        
                        self.logger.info(f"Successfully sent {len(packets)} packets to server")
                    else:
                        self.logger.error(f"Server returned status {response.status}")
                        
        except Exception as e:
            self.logger.error(f"Error sending data to server: {e}")
    
    async def cleanup_old_data(self):
        """Clean up old buffered data"""
        try:
            # Remove sent packets older than 1 day
            cutoff = datetime.now(timezone.utc).timestamp() - (24 * 60 * 60)
            cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
            
            conn = self.get_db_connection()
            conn.execute('''
                DELETE FROM packet_buffer 
                WHERE sent = 1 AND timestamp < ?
            ''', (cutoff_iso,))
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old data: {e}")
    
    async def run(self):
        """Main agent loop"""
        self.logger.info(f"Starting MeshyMcMapface Agent {self.agent_id}")
        
        # Connect to Meshtastic node
        if not self.connect_to_node():
            self.logger.error("Failed to connect to Meshtastic node, exiting")
            return
        
        # Register with server
        self.logger.info("Registering with server...")
        if await self.register_with_server():
            self.logger.info("Registration successful")
        else:
            self.logger.warning("Registration failed, but continuing anyway")
        
        # Main loop
        while self.running:
            try:
                # Process any queued data from callback threads
                self.process_queued_data()
                
                # Send data to server
                await self.send_data_to_server()
                
                # Clean up old data
                await self.cleanup_old_data()
                
                # Wait for next interval
                await asyncio.sleep(self.report_interval)
                
            except KeyboardInterrupt:
                self.logger.info("Received interrupt, shutting down...")
                self.running = False
                break
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)  # Brief pause before retry
        
        # Cleanup
        if self.interface:
            self.interface.close()
        self.logger.info("MeshyMcMapface Agent stopped")

def create_sample_config():
    """Create sample configuration file"""
    config = configparser.ConfigParser()
    
    config['agent'] = {
        'id': 'agent_001',
        'location_name': 'Test Location',
        'location_lat': '37.7749',
        'location_lon': '-122.4194'
    }
    
    config['server'] = {
        'url': 'http://localhost:8082',
        'api_key': 'your-api-key-here',
        'report_interval': '30'
    }
    
    config['meshtastic'] = {
        'connection_type': 'auto',
        '# device_path': '/dev/ttyUSB0',
        '# tcp_host': '192.168.1.100',
        '# ble_address': 'AA:BB:CC:DD:EE:FF'
    }
    
    with open('agent_config.ini', 'w') as f:
        config.write(f)
    
    print("Created sample config file: agent_config.ini")
    print("Please edit the configuration before running the agent.")

def main():
    parser = argparse.ArgumentParser(description='MeshyMcMapface Agent MVP')
    parser.add_argument('--config', default='agent_config.ini', 
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
    
    agent = MeshyMcMapfaceAgent(args.config)
    
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        print("Agent stopped by user")

if __name__ == "__main__":
    main()