"""
Node tracking and status management
"""
import logging
import queue
from datetime import datetime, timezone
from typing import Dict, Optional


class NodeStatus:
    """Represents the status of a single node"""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.last_seen: Optional[str] = None
        self.battery_level: Optional[int] = None
        self.position_lat: Optional[float] = None
        self.position_lon: Optional[float] = None
        self.rssi: Optional[int] = None
        self.snr: Optional[float] = None
        self.updated_at: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary representation"""
        return {
            'node_id': self.node_id,
            'last_seen': self.last_seen,
            'battery_level': self.battery_level,
            'position_lat': self.position_lat,
            'position_lon': self.position_lon,
            'rssi': self.rssi,
            'snr': self.snr,
            'updated_at': self.updated_at
        }
    
    def update_from_packet(self, packet_data: Dict):
        """Update node status from packet data"""
        now = datetime.now(timezone.utc).isoformat()
        
        # Update basic info
        self.last_seen = packet_data['timestamp']
        self.updated_at = now
        
        # Update signal info
        if packet_data.get('rssi') is not None:
            self.rssi = packet_data['rssi']
        if packet_data.get('snr') is not None:
            self.snr = packet_data['snr']
        
        # Update position from position packets
        if packet_data['type'] == 'position' and packet_data.get('payload'):
            payload = packet_data['payload']
            if isinstance(payload, dict):
                lat = payload.get('latitude')
                lon = payload.get('longitude')
                if lat and lon and lat != 0 and lon != 0:
                    self.position_lat = lat
                    self.position_lon = lon
        
        # Update battery from telemetry packets
        if packet_data['type'] == 'telemetry' and packet_data.get('payload'):
            payload = packet_data['payload']
            if isinstance(payload, dict):
                # Handle different telemetry formats
                if 'device_metrics' in payload:
                    battery = payload['device_metrics'].get('battery_level')
                    if battery is not None:
                        self.battery_level = battery
                elif 'battery_level' in payload:
                    self.battery_level = payload['battery_level']
    
    def merge_with(self, other_status: Dict):
        """Merge with another status dict, preserving existing non-None values"""
        if other_status.get('position_lat') and not self.position_lat:
            self.position_lat = other_status['position_lat']
            self.position_lon = other_status['position_lon']
        
        if other_status.get('battery_level') and not self.battery_level:
            self.battery_level = other_status['battery_level']
        
        # Always update signal info if available
        if other_status.get('rssi') is not None:
            self.rssi = other_status['rssi']
        if other_status.get('snr') is not None:
            self.snr = other_status['snr']


class NodeTracker:
    """Manages tracking of multiple nodes and their status"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.nodes: Dict[str, NodeStatus] = {}
        self.update_queue = queue.Queue()
    
    def update_from_packet(self, packet_data: Dict):
        """Update node status from a packet"""
        node_id = packet_data.get('from_node')
        
        # Skip invalid or system node IDs
        if not node_id or node_id in ['^all', '^local', 'null', '']:
            return
        
        # Create or get existing node status
        if node_id not in self.nodes:
            self.nodes[node_id] = NodeStatus(node_id)
        
        # Update the node status
        self.nodes[node_id].update_from_packet(packet_data)
        
        # Queue for database update
        self.update_queue.put(self.nodes[node_id].to_dict())
        
        self.logger.debug(f"Updated node {node_id} from {packet_data['type']} packet")
    
    def update_position(self, node_id: str, position_data: Dict):
        """Update node position directly"""
        if not node_id or node_id in ['^all', '^local']:
            return
        
        # Create node if doesn't exist
        if node_id not in self.nodes:
            self.nodes[node_id] = NodeStatus(node_id)
        
        node = self.nodes[node_id]
        now = datetime.now(timezone.utc).isoformat()
        
        # Update position
        lat = position_data.get('latitude')
        lon = position_data.get('longitude')
        
        if lat and lon and lat != 0 and lon != 0:
            node.position_lat = lat
            node.position_lon = lon
            node.updated_at = now
            
            self.logger.info(f"Updated position for {node_id}: lat={lat}, lon={lon}")
            self.update_queue.put(node.to_dict())
        else:
            self.logger.warning(f"Invalid position data for {node_id}: lat={lat}, lon={lon}")
    
    def get_node(self, node_id: str) -> Optional[NodeStatus]:
        """Get a specific node's status"""
        return self.nodes.get(node_id)
    
    def get_all_nodes(self) -> Dict[str, NodeStatus]:
        """Get all tracked nodes"""
        return self.nodes.copy()
    
    def get_nodes_dict(self) -> Dict[str, Dict]:
        """Get all nodes as dictionaries"""
        return {node_id: node.to_dict() for node_id, node in self.nodes.items()}
    
    def has_updates(self) -> bool:
        """Check if there are pending updates in the queue"""
        return not self.update_queue.empty()
    
    def get_next_update(self) -> Optional[Dict]:
        """Get the next queued update"""
        try:
            return self.update_queue.get_nowait()
        except queue.Empty:
            return None
    
    def get_all_updates(self) -> list:
        """Get all queued updates and clear the queue"""
        updates = []
        while not self.update_queue.empty():
            try:
                updates.append(self.update_queue.get_nowait())
            except queue.Empty:
                break
        return updates
    
    def cleanup_stale_nodes(self, max_age_hours: int = 24):
        """Remove nodes that haven't been seen recently"""
        if not self.nodes:
            return
        
        current_time = datetime.now(timezone.utc).timestamp()
        cutoff = current_time - (max_age_hours * 60 * 60)
        
        stale_nodes = []
        for node_id, node in self.nodes.items():
            if node.last_seen:
                try:
                    last_seen_time = datetime.fromisoformat(node.last_seen.replace('Z', '+00:00')).timestamp()
                    if last_seen_time < cutoff:
                        stale_nodes.append(node_id)
                except Exception as e:
                    self.logger.warning(f"Error parsing last_seen time for {node_id}: {e}")
                    stale_nodes.append(node_id)
        
        for node_id in stale_nodes:
            del self.nodes[node_id]
            self.logger.info(f"Removed stale node: {node_id}")
    
    def get_stats(self) -> Dict:
        """Get statistics about tracked nodes"""
        total_nodes = len(self.nodes)
        nodes_with_position = sum(1 for node in self.nodes.values() 
                                if node.position_lat and node.position_lon)
        nodes_with_battery = sum(1 for node in self.nodes.values() 
                               if node.battery_level is not None)
        
        return {
            'total_nodes': total_nodes,
            'nodes_with_position': nodes_with_position,
            'nodes_with_battery': nodes_with_battery,
            'position_coverage': nodes_with_position / total_nodes if total_nodes > 0 else 0,
            'battery_coverage': nodes_with_battery / total_nodes if total_nodes > 0 else 0
        }