"""
Database abstraction layer for MeshyMcMapface
Provides repository pattern for data access
"""
import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from abc import ABC, abstractmethod


class DatabaseConnection:
    """Manages database connections and schema setup"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
    
    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection for the current thread"""
        conn = sqlite3.connect(self.db_path)
        self._ensure_schema(conn)
        return conn
    
    def _ensure_schema(self, conn: sqlite3.Connection):
        """Create tables if they don't exist"""
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


class BaseRepository(ABC):
    """Base repository class with common functionality"""
    
    def __init__(self, db_connection: DatabaseConnection):
        self.db_connection = db_connection
        self.logger = logging.getLogger(__name__)


class PacketRepository(BaseRepository):
    """Repository for packet data operations"""
    
    def store_packet(self, packet_data: Dict, server_routing: Dict) -> int:
        """Store a packet with server routing information"""
        try:
            conn = self.db_connection.get_connection()
            cursor = conn.execute('''
                INSERT INTO packet_buffer (timestamp, packet_data, server_status)
                VALUES (?, ?, ?)
            ''', (packet_data['timestamp'], json.dumps(packet_data), json.dumps(server_routing)))
            
            packet_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            self.logger.debug(f"Stored packet {packet_id} for servers: {list(server_routing.keys())}")
            return packet_id
            
        except Exception as e:
            self.logger.error(f"Error storing packet: {e}")
            raise
    
    def get_unsent_packets(self, server_name: str, limit: int = 100) -> List[Tuple]:
        """Get packets that need to be sent to a specific server"""
        try:
            conn = self.db_connection.get_connection()
            cursor = conn.execute('''
                SELECT id, packet_data, server_status FROM packet_buffer 
                WHERE created_at > datetime('now', '-1 hour')
                ORDER BY timestamp 
                LIMIT ?
            ''', (limit,))
            
            packets = cursor.fetchall()
            conn.close()
            
            # Filter for this specific server
            filtered_packets = []
            for packet_row in packets:
                packet_id, packet_data_str, server_status_str = packet_row
                server_status = json.loads(server_status_str)
                
                if (server_name in server_status and 
                    not server_status[server_name]['sent'] and
                    server_status[server_name]['retry_count'] < 3):  # Default max_retries
                    
                    filtered_packets.append((packet_id, json.loads(packet_data_str), server_status))
            
            return filtered_packets
            
        except Exception as e:
            self.logger.error(f"Error getting unsent packets for {server_name}: {e}")
            raise
    
    def mark_packets_sent(self, packet_ids: List[int], server_name: str):
        """Mark packets as sent to a specific server"""
        try:
            conn = self.db_connection.get_connection()
            
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
            raise
    
    def cleanup_old_packets(self, hours_to_keep: int = 24):
        """Remove old packets from buffer"""
        try:
            cutoff = datetime.now(timezone.utc).timestamp() - (hours_to_keep * 60 * 60)
            cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
            
            conn = self.db_connection.get_connection()
            conn.execute('DELETE FROM packet_buffer WHERE created_at < ?', (cutoff_iso,))
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old packets: {e}")
            raise


class NodeRepository(BaseRepository):
    """Repository for node data operations"""
    
    def update_node_status(self, node_status: Dict, agent_id: str):
        """Update node status in database"""
        try:
            node_id = node_status['node_id']
            lat = node_status.get('position_lat')
            lon = node_status.get('position_lon')
            
            self.logger.info(f"Writing node {node_id} to database: lat={lat}, lon={lon}, battery={node_status.get('battery_level')}")
            
            conn = self.db_connection.get_connection()
            
            # Use INSERT OR REPLACE to handle updates properly
            conn.execute('''
                INSERT OR REPLACE INTO nodes 
                (node_id, agent_id, last_seen, battery_level, position_lat, position_lon, rssi, snr, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                node_id, 
                agent_id, 
                node_status['last_seen'], 
                node_status.get('battery_level'),
                lat,
                lon,
                node_status.get('rssi'), 
                node_status.get('snr'), 
                node_status['updated_at']
            ))
            
            conn.commit()
            conn.close()
            
            if lat and lon:
                self.logger.info(f"Successfully wrote GPS data for node {node_id}: {lat:.6f}, {lon:.6f}")
            else:
                self.logger.debug(f"Node {node_id} written without GPS data")
                
        except Exception as e:
            self.logger.error(f"Error updating node status for {node_status.get('node_id', 'unknown')}: {e}")
            raise
    
    def get_nodes_for_agent(self, agent_id: str, hours_active: int = 24) -> List[Tuple]:
        """Get recent nodes for an agent"""
        try:
            conn = self.db_connection.get_connection()
            cursor = conn.execute('''
                SELECT node_id, last_seen, battery_level, position_lat, position_lon, rssi, snr
                FROM nodes 
                WHERE agent_id = ? AND datetime(updated_at) > datetime('now', '-{} hours')
            '''.format(hours_active), (agent_id,))
            
            nodes = cursor.fetchall()
            conn.close()
            
            self.logger.info(f"Found {len(nodes)} nodes in database for {agent_id}")
            return nodes
            
        except Exception as e:
            self.logger.error(f"Error getting nodes for agent {agent_id}: {e}")
            raise
    
    def cleanup_old_nodes(self, days_to_keep: int = 7):
        """Remove old node data"""
        try:
            cutoff = datetime.now(timezone.utc).timestamp() - (days_to_keep * 24 * 60 * 60)
            cutoff_iso = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
            
            conn = self.db_connection.get_connection()
            conn.execute('DELETE FROM nodes WHERE updated_at < ?', (cutoff_iso,))
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old nodes: {e}")
            raise


class ServerHealthRepository(BaseRepository):
    """Repository for server health tracking"""
    
    def update_server_health(self, server_name: str, success: bool):
        """Update server health status"""
        try:
            conn = self.db_connection.get_connection()
            now = datetime.now(timezone.utc).isoformat()
            
            if success:
                conn.execute('''
                    INSERT OR REPLACE INTO server_health 
                    (server_name, last_success, consecutive_failures, total_packets_sent, is_healthy)
                    VALUES (?, ?, 0, COALESCE((SELECT total_packets_sent FROM server_health WHERE server_name = ?), 0) + 1, 1)
                ''', (server_name, now, server_name))
            else:
                conn.execute('''
                    INSERT OR REPLACE INTO server_health 
                    (server_name, last_failure, consecutive_failures, total_packets_sent, is_healthy)
                    VALUES (?, ?, COALESCE((SELECT consecutive_failures FROM server_health WHERE server_name = ?), 0) + 1, 
                            COALESCE((SELECT total_packets_sent FROM server_health WHERE server_name = ?), 0), 0)
                ''', (server_name, now, server_name, server_name))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Error updating server health for {server_name}: {e}")
            raise
    
    def get_server_health(self, server_name: str) -> Optional[Dict]:
        """Get health status for a specific server"""
        try:
            conn = self.db_connection.get_connection()
            cursor = conn.execute('''
                SELECT last_success, last_failure, consecutive_failures, total_packets_sent, is_healthy
                FROM server_health WHERE server_name = ?
            ''', (server_name,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'last_success': row[0],
                    'last_failure': row[1],
                    'consecutive_failures': row[2],
                    'total_packets_sent': row[3],
                    'is_healthy': bool(row[4])
                }
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting server health for {server_name}: {e}")
            raise