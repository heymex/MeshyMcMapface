"""
Multi-server agent implementation for MeshyMcMapface
"""
import asyncio
from typing import Dict

from .base_agent import BaseAgent
from ..core.database import PacketRepository, NodeRepository, ServerHealthRepository
from ..servers.client import MultiServerClient
from ..servers.health import MultiServerHealthMonitor
from ..servers.queue_manager import MultiServerQueueManager, ServerTaskManager


class MultiServerAgent(BaseAgent):
    """Agent that can report to multiple servers with different configurations"""
    
    def __init__(self, config_file: str):
        super().__init__(config_file)
        
        # Load server configurations
        self.server_configs = self.config_manager.load_server_configs()
        
        # Initialize repositories
        self.packet_repo = PacketRepository(self.db_connection)
        self.node_repo = NodeRepository(self.db_connection)
        self.health_repo = ServerHealthRepository(self.db_connection)
        
        # Initialize server components
        self.server_client = MultiServerClient(self.server_configs)
        self.health_monitor = MultiServerHealthMonitor(self.server_configs, self.health_repo)
        self.queue_manager = MultiServerQueueManager(self.server_configs, self.packet_repo, self.node_repo)
        self.task_manager = ServerTaskManager(self.queue_manager)
        
        self.logger.info(f"Initialized multi-server agent with {len(self.server_configs)} servers")
        for name, config in self.server_configs.items():
            if config.enabled:
                self.logger.info(f"  - {name}: {config.url} (interval: {config.report_interval}s, priority: {config.priority})")
            else:
                self.logger.info(f"  - {name}: DISABLED")
    
    def _handle_processed_packet(self, packet_data: Dict):
        """Handle a processed packet by queuing it for appropriate servers"""
        try:
            packet_id = self.queue_manager.queue_packet(packet_data)
            if packet_id > 0:
                self.logger.debug(f"Queued packet {packet_id} from {packet_data.get('from_node')}")
        except Exception as e:
            self.logger.error(f"Error queuing packet: {e}")
    
    def _handle_connection_established(self):
        """Handle Meshtastic connection establishment"""
        self.logger.info("Meshtastic connection established, starting server registrations")
    
    async def register_with_servers(self):
        """Register this agent with all enabled servers"""
        self.logger.info("Registering with servers...")
        
        try:
            results = await self.server_client.register_all(self.agent_config)
            
            for server_name, success in results.items():
                if success:
                    self.logger.info(f"Registration with {server_name} successful")
                    self.health_monitor.record_success(server_name)
                else:
                    self.logger.warning(f"Registration with {server_name} failed")
                    self.health_monitor.record_failure(server_name)
        
        except Exception as e:
            self.logger.error(f"Error during server registrations: {e}")
    
    def start_server_tasks(self):
        """Start individual server reporting tasks"""
        self.logger.info("Starting server reporting tasks...")
        
        for server_name, config in self.server_configs.items():
            if config.enabled:
                self.task_manager.start_server_task(
                    server_name, 
                    self.server_client, 
                    self.agent_config, 
                    self.health_monitor
                )
        
        self.logger.info(f"Started {len(self.task_manager.get_active_tasks())} server reporting tasks")
    
    def stop_server_tasks(self):
        """Stop all server reporting tasks"""
        self.logger.info("Stopping server reporting tasks...")
        self.task_manager.stop_all_tasks()
    
    def process_node_updates(self):
        """Process queued node updates from tracker"""
        try:
            updates = self.node_tracker.get_all_updates()
            
            for update in updates:
                try:
                    self.node_repo.update_node_status(update, self.agent_config.id)
                except Exception as e:
                    self.logger.error(f"Error updating node status: {e}")
            
            if updates:
                self.logger.debug(f"Processed {len(updates)} node updates")
                
        except Exception as e:
            self.logger.error(f"Error processing node updates: {e}")
    
    async def cleanup_old_data(self):
        """Clean up old data from all repositories"""
        try:
            await super().cleanup_old_data()
            self.queue_manager.cleanup_old_data()
            self.logger.debug("Completed data cleanup")
        except Exception as e:
            self.logger.error(f"Error during data cleanup: {e}")
    
    async def run(self):
        """Main agent execution loop"""
        self.logger.info(f"Starting Multi-Server MeshyMcMapface Agent {self.agent_config.id}")
        
        # Connect to Meshtastic device
        if not self.connect_to_meshtastic():
            self.logger.error("Failed to connect to Meshtastic device, exiting")
            return
        
        # Register with all servers
        await self.register_with_servers()
        
        # Start server reporting tasks
        self.start_server_tasks()
        
        # Main processing loop
        try:
            cleanup_counter = 0
            nodedb_counter = 0
            while self.running:
                # Process queued node updates
                self.process_node_updates()
                
                # Send extended node data periodically (every ~2 minutes for testing)
                nodedb_counter += 1
                if nodedb_counter >= 24:  # 24 * 5 seconds = 2 minutes
                    self.logger.info("Starting nodedb data collection and sending...")
                    await self.send_nodedb_to_all_servers()
                    nodedb_counter = 0
                
                # Periodic cleanup (every ~10 minutes)
                cleanup_counter += 1
                if cleanup_counter >= 120:  # 120 * 5 seconds = 10 minutes
                    await self.cleanup_old_data()
                    cleanup_counter = 0
                
                # Wait before next cycle
                await asyncio.sleep(5)  # Fast processing loop
                
        except KeyboardInterrupt:
            self.logger.info("Received interrupt, shutting down...")
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}")
            raise
        finally:
            # Cleanup
            self.stop_server_tasks()
            self.logger.info("Multi-Server MeshyMcMapface Agent stopped")
    
    def get_agent_info(self) -> Dict:
        """Get comprehensive information about this agent"""
        base_info = super().get_agent_info()
        
        # Add multi-server specific info
        base_info.update({
            'servers': {
                'configured': len(self.server_configs),
                'enabled': len([c for c in self.server_configs.values() if c.enabled]),
                'health': self.health_monitor.get_all_health_info(),
                'queue_stats': self.queue_manager.get_queue_stats()
            },
            'active_tasks': self.task_manager.get_active_tasks()
        })
        
        return base_info
    
    def get_server_health_summary(self) -> Dict:
        """Get a summary of server health status"""
        healthy_servers = self.health_monitor.get_healthy_servers()
        unhealthy_servers = self.health_monitor.get_unhealthy_servers()
        
        return {
            'healthy_count': len(healthy_servers),
            'unhealthy_count': len(unhealthy_servers),
            'healthy_servers': list(healthy_servers.keys()),
            'unhealthy_servers': list(unhealthy_servers.keys()),
            'priority_order': self.health_monitor.get_server_priority_order()
        }
    
    def get_queue_summary(self) -> Dict:
        """Get a summary of queue status"""
        return self.queue_manager.get_queue_stats()
    
    async def send_nodedb_to_all_servers(self):
        """Send extended node data to all servers"""
        try:
            self.logger.info("Collecting extended node data from Meshtastic interface...")
            # Get extended node data from the Meshtastic interface
            nodes_data = self.get_extended_node_data()
            
            self.logger.info(f"Collected extended data for {len(nodes_data)} nodes")
            
            if not nodes_data:
                self.logger.warning("No extended node data available to send")
                return
            
            # Count nodes with actual metrics
            nodes_with_metrics = sum(1 for node_data in nodes_data.values() 
                                   if node_data.get('deviceMetrics') and 
                                   any(v is not None for v in node_data['deviceMetrics'].values()))
            
            self.logger.info(f"Found {nodes_with_metrics} nodes with device metrics to send")
            
            # Send to all enabled servers
            results = await self.server_client.send_nodedb_to_all(self.agent_config, nodes_data)
            
            # Record results in health monitor
            for server_name, success in results.items():
                if success:
                    self.health_monitor.record_success(server_name)
                    self.logger.debug(f"Successfully sent nodedb to {server_name}")
                else:
                    self.health_monitor.record_failure(server_name)
                    self.logger.warning(f"Failed to send nodedb to {server_name}")
            
            self.logger.info(f"Sent extended node data for {len(nodes_data)} nodes to {len(results)} servers")
            
        except Exception as e:
            self.logger.error(f"Error sending nodedb to servers: {e}")

    async def force_send_to_all_servers(self):
        """Force sending queued data to all servers (useful for testing)"""
        self.logger.info("Force sending data to all servers...")
        
        for server_name in self.server_configs.keys():
            if self.server_configs[server_name].enabled:
                try:
                    # Get data for this server
                    packet_ids, packets = self.queue_manager.get_packets_for_server(server_name)
                    node_status = self.queue_manager.get_node_status_for_server(
                        self.agent_config.id, server_name
                    )
                    
                    if packets or node_status:
                        # Send to server
                        success = await self.server_client.send_to_server(
                            server_name, self.agent_config, packets, node_status
                        )
                        
                        if success:
                            self.queue_manager.mark_packets_sent(packet_ids, server_name)
                            self.health_monitor.record_success(server_name)
                            self.logger.info(f"Force sent data to {server_name}: {len(packets)} packets, {len(node_status)} nodes")
                        else:
                            self.health_monitor.record_failure(server_name)
                            self.logger.warning(f"Force send to {server_name} failed")
                    else:
                        self.logger.info(f"No data to send to {server_name}")
                        
                except Exception as e:
                    self.logger.error(f"Error force sending to {server_name}: {e}")
                    self.health_monitor.record_failure(server_name)