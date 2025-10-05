"""
Multi-server queue management for different reporting intervals
"""
import asyncio
import logging
from typing import Dict, List, Tuple

from ..core.config import ServerConfig
from ..core.database import PacketRepository, NodeRepository


class ServerQueue:
    """Queue for a specific server with its own reporting interval"""
    
    def __init__(self, server_name: str, server_config: ServerConfig):
        self.server_name = server_name
        self.config = server_config
        self.logger = logging.getLogger(__name__)
    
    def should_process_packet(self, packet_data: Dict, node_id: str) -> bool:
        """Check if this packet should be queued for this server"""
        if not self.config.enabled:
            return False
        
        # Check packet type filtering
        if self.config.packet_types != ['all'] and packet_data['type'] not in self.config.packet_types:
            return False
        
        # Check node filtering
        if self.config.filter_nodes and node_id not in self.config.filter_nodes:
            return False
        
        if self.config.exclude_nodes and node_id in self.config.exclude_nodes:
            return False
        
        return True


class MultiServerQueueManager:
    """Manages packet queuing and routing for multiple servers"""
    
    def __init__(self, server_configs: Dict[str, ServerConfig], 
                 packet_repo: PacketRepository, node_repo: NodeRepository):
        self.server_configs = server_configs
        self.packet_repo = packet_repo
        self.node_repo = node_repo
        self.server_queues = {}
        self.logger = logging.getLogger(__name__)
        
        # Create queues for each server
        for name, config in server_configs.items():
            self.server_queues[name] = ServerQueue(name, config)
    
    def queue_packet(self, packet_data: Dict) -> int:
        """Queue a packet for appropriate servers and return packet ID"""
        node_id = packet_data.get('from_node', '')
        
        # Determine which servers should receive this packet
        server_routing = {}
        
        for server_name, server_queue in self.server_queues.items():
            if server_queue.should_process_packet(packet_data, node_id):
                server_routing[server_name] = {
                    'queued': True,
                    'sent': False,
                    'last_attempt': None,
                    'retry_count': 0
                }
        
        if server_routing:
            # Store in database with routing information
            packet_id = self.packet_repo.store_packet(packet_data, server_routing)
            self.logger.debug(f"Queued packet {packet_id} for servers: {list(server_routing.keys())}")
            return packet_id
        else:
            self.logger.debug(f"No servers configured for packet from {node_id}")
            return -1
    
    def get_packets_for_server(self, server_name: str, limit: int = 100) -> Tuple[List[int], List[Dict]]:
        """Get queued packets for a specific server"""
        try:
            packets = self.packet_repo.get_unsent_packets(server_name, limit)
            
            packet_ids = []
            packet_data_list = []
            
            for packet_id, packet_data, server_status in packets:
                packet_ids.append(packet_id)
                packet_data_list.append(packet_data)
            
            self.logger.debug(f"Retrieved {len(packet_data_list)} packets for server {server_name}")
            return packet_ids, packet_data_list
            
        except Exception as e:
            self.logger.error(f"Error getting packets for server {server_name}: {e}")
            return [], []
    
    def mark_packets_sent(self, packet_ids: List[int], server_name: str):
        """Mark packets as successfully sent to a server"""
        try:
            self.packet_repo.mark_packets_sent(packet_ids, server_name)
            self.logger.debug(f"Marked {len(packet_ids)} packets as sent for server {server_name}")
        except Exception as e:
            self.logger.error(f"Error marking packets sent for {server_name}: {e}")
    
    def get_node_status_for_server(self, agent_id: str, server_name: str) -> List[Dict]:
        """Get formatted node status for a specific server"""
        try:
            # Get raw node data
            nodes = self.node_repo.get_nodes_for_agent(agent_id)
            
            # Format for server transmission
            node_status_list = []
            for node in nodes:
                node_status = {
                    'node_id': node[0],           # node_id
                    'last_seen': node[1],         # last_seen
                    'battery_level': node[2],     # battery_level
                    'position': [node[3], node[4]] if node[3] and node[4] else None,  # position_lat, position_lon
                    'rssi': node[5],              # rssi
                    'snr': node[6]                # snr
                }
                node_status_list.append(node_status)
            
            self.logger.debug(f"Prepared {len(node_status_list)} node statuses for server {server_name}")
            return node_status_list
            
        except Exception as e:
            self.logger.error(f"Error getting node status for server {server_name}: {e}")
            return []
    
    def cleanup_old_data(self, packet_hours: int = 24, node_days: int = 7):
        """Clean up old data from queues"""
        try:
            # Clean up old packets
            self.packet_repo.cleanup_old_packets(packet_hours)
            
            # Clean up old nodes
            self.node_repo.cleanup_old_nodes(node_days)
            
            self.logger.info(f"Cleaned up data older than {packet_hours}h (packets) and {node_days}d (nodes)")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old data: {e}")
    
    def get_queue_stats(self) -> Dict[str, Dict]:
        """Get statistics about queue status for each server"""
        stats = {}
        
        for server_name in self.server_queues.keys():
            try:
                # Get unsent packet count
                packet_ids, _ = self.get_packets_for_server(server_name, limit=1000)  # High limit for counting
                unsent_count = len(packet_ids)
                
                stats[server_name] = {
                    'unsent_packets': unsent_count,
                    'enabled': self.server_configs[server_name].enabled,
                    'report_interval': self.server_configs[server_name].report_interval
                }
                
            except Exception as e:
                self.logger.error(f"Error getting queue stats for {server_name}: {e}")
                stats[server_name] = {
                    'unsent_packets': 0,
                    'enabled': False,
                    'report_interval': 0,
                    'error': str(e)
                }
        
        return stats
    
    def add_server_queue(self, server_name: str, server_config: ServerConfig):
        """Add a new server queue"""
        self.server_queues[server_name] = ServerQueue(server_name, server_config)
        self.server_configs[server_name] = server_config
        self.logger.info(f"Added queue for server: {server_name}")
    
    def remove_server_queue(self, server_name: str):
        """Remove a server queue"""
        if server_name in self.server_queues:
            del self.server_queues[server_name]
        if server_name in self.server_configs:
            del self.server_configs[server_name]
        self.logger.info(f"Removed queue for server: {server_name}")
    
    def update_server_config(self, server_name: str, server_config: ServerConfig):
        """Update configuration for a server queue"""
        if server_name in self.server_queues:
            self.server_queues[server_name].config = server_config
            self.server_configs[server_name] = server_config
            self.logger.info(f"Updated configuration for server queue: {server_name}")


class ServerTaskManager:
    """Manages individual server reporting tasks"""
    
    def __init__(self, queue_manager: MultiServerQueueManager):
        self.queue_manager = queue_manager
        self.tasks: Dict[str, asyncio.Task] = {}
        self.logger = logging.getLogger(__name__)
    
    async def server_reporting_loop(self, server_name: str, server_client, agent_config, health_monitor):
        """Individual server reporting loop"""
        config = self.queue_manager.server_configs[server_name]
        self.logger.info(f"Started reporting loop for {server_name} (interval: {config.report_interval}s)")
        
        while True:
            try:
                if config.enabled and health_monitor.is_server_healthy(server_name):
                    # Get packets and node status for this server
                    packet_ids, packets = self.queue_manager.get_packets_for_server(server_name)
                    node_status = self.queue_manager.get_node_status_for_server(agent_config.id, server_name)
                    
                    if packets or node_status:
                        # Send data to server
                        success = await server_client.send_to_server(
                            server_name, agent_config, packets, node_status
                        )
                        
                        if success:
                            # Mark packets as sent
                            if packet_ids:
                                self.queue_manager.mark_packets_sent(packet_ids, server_name)
                            health_monitor.record_success(server_name)
                        else:
                            health_monitor.record_failure(server_name)
                    else:
                        self.logger.debug(f"No data to send to {server_name}")
                
                await asyncio.sleep(config.report_interval)
                
            except asyncio.CancelledError:
                self.logger.info(f"Reporting loop for {server_name} cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in server loop for {server_name}: {e}")
                health_monitor.record_failure(server_name)
                await asyncio.sleep(config.report_interval)
    
    def start_server_task(self, server_name: str, server_client, agent_config, health_monitor):
        """Start a reporting task for a server"""
        if server_name in self.tasks:
            self.logger.warning(f"Task for server {server_name} already running, stopping old task")
            self.stop_server_task(server_name)
        
        task = asyncio.create_task(
            self.server_reporting_loop(server_name, server_client, agent_config, health_monitor)
        )
        self.tasks[server_name] = task
        self.logger.info(f"Started reporting task for server: {server_name}")
    
    def stop_server_task(self, server_name: str):
        """Stop a reporting task for a server"""
        if server_name in self.tasks:
            self.tasks[server_name].cancel()
            del self.tasks[server_name]
            self.logger.info(f"Stopped reporting task for server: {server_name}")
    
    def stop_all_tasks(self):
        """Stop all server reporting tasks"""
        for server_name in list(self.tasks.keys()):
            self.stop_server_task(server_name)
        self.logger.info("Stopped all server reporting tasks")
    
    def get_active_tasks(self) -> List[str]:
        """Get list of servers with active tasks"""
        return list(self.tasks.keys())