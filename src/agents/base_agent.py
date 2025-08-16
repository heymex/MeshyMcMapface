"""
Base agent class for MeshyMcMapface
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional

from ..core.config import ConfigManager, AgentConfig, MeshtasticConfig
from ..core.database import DatabaseConnection
from ..core.exceptions import MeshyMcMapfaceError, ConfigurationError
from ..mesh_integration.connections import ConnectionManager
from ..mesh_integration.packet_parser import PacketProcessor
from ..mesh_integration.node_tracker import NodeTracker
from ..utils.logging import LoggerMixin


class BaseAgent(ABC, LoggerMixin):
    """Base class for all MeshyMcMapface agents"""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.running = False
        
        # Initialize components
        self.config_manager: Optional[ConfigManager] = None
        self.agent_config: Optional[AgentConfig] = None
        self.meshtastic_config: Optional[MeshtasticConfig] = None
        
        self.db_connection: Optional[DatabaseConnection] = None
        self.connection_manager: Optional[ConnectionManager] = None
        self.packet_processor: Optional[PacketProcessor] = None
        self.node_tracker: Optional[NodeTracker] = None
        
        self._initialize_components()
    
    def _initialize_components(self):
        """Initialize all agent components"""
        try:
            # Load configuration
            self.config_manager = ConfigManager(self.config_file)
            self.agent_config = self.config_manager.load_agent_config()
            self.meshtastic_config = self.config_manager.load_meshtastic_config()
            
            # Initialize database
            db_path = self.config_manager.get_database_path(self.agent_config.id)
            self.db_connection = DatabaseConnection(db_path)
            
            # Initialize Meshtastic components
            self.connection_manager = ConnectionManager()
            self.packet_processor = PacketProcessor()
            self.node_tracker = NodeTracker()
            
            self.logger.info(f"Initialized agent {self.agent_config.id} with config from {self.config_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize agent components: {e}")
            raise ConfigurationError(f"Agent initialization failed: {e}")
    
    @abstractmethod
    async def run(self):
        """Main agent execution loop - must be implemented by subclasses"""
        pass
    
    def connect_to_meshtastic(self) -> bool:
        """Connect to Meshtastic device"""
        try:
            connection = self.connection_manager.create_connection(self.meshtastic_config)
            
            if connection.connect():
                # Subscribe to events
                connection.subscribe_to_events(
                    on_receive_callback=self.on_receive,
                    on_connection_callback=self.on_connection,
                    on_node_updated_callback=self.on_node_updated
                )
                
                self.logger.info("Successfully connected to Meshtastic device")
                return True
            else:
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to connect to Meshtastic device: {e}")
            return False
    
    def disconnect_from_meshtastic(self):
        """Disconnect from Meshtastic device"""
        if self.connection_manager:
            self.connection_manager.close_connection()
            self.logger.info("Disconnected from Meshtastic device")
    
    def on_receive(self, packet, interface):
        """Handle received packets from Meshtastic"""
        try:
            self.logger.debug(f"Received packet from: {packet.get('fromId', 'unknown')}")
            
            # Process packet using packet processor
            packet_data = self.packet_processor.process_packet(packet)
            
            # Update node tracking
            self.node_tracker.update_from_packet(packet_data)
            
            # Let subclasses handle the processed packet
            self._handle_processed_packet(packet_data)
            
        except Exception as e:
            self.logger.error(f"Error processing received packet: {e}")
    
    def on_connection(self, interface, topic=None):
        """Handle Meshtastic connection established"""
        self.logger.info("Meshtastic connection established")
        self._handle_connection_established()
    
    def on_node_updated(self, node):
        """Handle Meshtastic node updates"""
        self.logger.debug(f"Node updated: {getattr(node, 'num', 'unknown')}")
        self._handle_node_updated(node)
    
    @abstractmethod
    def _handle_processed_packet(self, packet_data: Dict):
        """Handle a processed packet - must be implemented by subclasses"""
        pass
    
    def _handle_connection_established(self):
        """Handle connection establishment - can be overridden by subclasses"""
        pass
    
    def _handle_node_updated(self, node):
        """Handle node updates - can be overridden by subclasses"""
        pass
    
    async def cleanup_old_data(self):
        """Clean up old data - can be overridden by subclasses"""
        try:
            # Clean up old nodes in tracker
            self.node_tracker.cleanup_stale_nodes()
            self.logger.debug("Cleaned up stale nodes")
        except Exception as e:
            self.logger.error(f"Error during data cleanup: {e}")
    
    def get_extended_node_data(self) -> Dict:
        """Get extended node information from Meshtastic interface"""
        try:
            connection = self.connection_manager.get_connection()
            if not connection or not connection.is_connected():
                return {}
            
            interface = connection.interface
            if not interface or not hasattr(interface, 'nodesByNum') or not interface.nodesByNum:
                return {}
            
            nodes_data = {}
            
            for node_num, node in interface.nodesByNum.items():
                try:
                    # Convert node number to hex ID format
                    node_id = f"!{node_num:08x}"
                    
                    node_data = {
                        'user': {},
                        'position': {},
                        'deviceMetrics': {}
                    }
                    
                    # Extract user information
                    if hasattr(node, 'user') and node.user:
                        user = node.user
                        node_data['user'] = {
                            'id': getattr(user, 'id', '') or node_id,
                            'longName': getattr(user, 'longName', ''),
                            'shortName': getattr(user, 'shortName', ''),
                            'macaddr': getattr(user, 'macaddr', ''),
                            'hwModel': getattr(user, 'hwModel', 0),
                            'role': getattr(user, 'role', 0),
                            'isLicensed': getattr(user, 'isLicensed', False)
                        }
                    
                    # Extract position information
                    if hasattr(node, 'position') and node.position:
                        pos = node.position
                        node_data['position'] = {
                            'latitude': getattr(pos, 'latitude', 0),
                            'longitude': getattr(pos, 'longitude', 0),
                            'altitude': getattr(pos, 'altitude', 0),
                            'time': getattr(pos, 'time', 0)
                        }
                    
                    # Extract device metrics
                    if hasattr(node, 'deviceMetrics') and node.deviceMetrics:
                        metrics = node.deviceMetrics
                        node_data['deviceMetrics'] = {
                            'batteryLevel': getattr(metrics, 'batteryLevel', None),
                            'voltage': getattr(metrics, 'voltage', None),
                            'channelUtilization': getattr(metrics, 'channelUtilization', None),
                            'airUtilTx': getattr(metrics, 'airUtilTx', None),
                            'uptimeSeconds': getattr(metrics, 'uptimeSeconds', None)
                        }
                    
                    # Add other node-level fields
                    node_data['hopsAway'] = getattr(node, 'hopsAway', None)
                    node_data['lastHeard'] = getattr(node, 'lastHeard', None)
                    node_data['isFavorite'] = getattr(node, 'isFavorite', False)
                    
                    nodes_data[node_id] = node_data
                    
                except Exception as e:
                    self.logger.warning(f"Error processing node {node_num}: {e}")
                    continue
            
            return nodes_data
            
        except Exception as e:
            self.logger.error(f"Error getting extended node data: {e}")
            return {}

    def get_agent_info(self) -> Dict:
        """Get information about this agent"""
        connection = self.connection_manager.get_connection()
        meshtastic_info = connection.get_node_info() if connection else None
        
        return {
            'agent_id': self.agent_config.id,
            'location_name': self.agent_config.location_name,
            'coordinates': [self.agent_config.location_lat, self.agent_config.location_lon],
            'meshtastic_connection': {
                'connected': connection.is_connected() if connection else False,
                'node_info': meshtastic_info
            },
            'node_tracker': self.node_tracker.get_stats()
        }
    
    def start(self):
        """Start the agent"""
        self.running = True
        self.logger.info(f"Starting agent {self.agent_config.id}")
    
    def stop(self):
        """Stop the agent"""
        self.running = False
        self.disconnect_from_meshtastic()
        self.logger.info(f"Stopped agent {self.agent_config.id}")
    
    async def run_with_cleanup(self):
        """Run the agent with proper cleanup on exit"""
        try:
            self.start()
            await self.run()
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        except Exception as e:
            self.logger.error(f"Agent error: {e}")
            raise
        finally:
            self.stop()


class AgentFactory:
    """Factory for creating different types of agents"""
    
    @staticmethod
    def create_agent(agent_type: str, config_file: str) -> BaseAgent:
        """Create an agent of the specified type"""
        if agent_type == 'multi_server':
            from .multi_server_agent import MultiServerAgent
            return MultiServerAgent(config_file)
        elif agent_type == 'single_server':
            # Could add single server agent here
            raise NotImplementedError("Single server agent not yet implemented")
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")
    
    @staticmethod
    def get_available_agent_types() -> list:
        """Get list of available agent types"""
        return ['multi_server']