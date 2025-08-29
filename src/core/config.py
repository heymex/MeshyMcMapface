"""
Configuration management for MeshyMcMapface
Handles loading and validation of agent and server configurations
"""
import configparser
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone


@dataclass
class ServerConfig:
    """Configuration for a single server"""
    name: str
    url: str
    api_key: str
    enabled: bool = True
    report_interval: int = 30
    packet_types: List[str] = None
    priority: int = 1
    max_retries: int = 3
    timeout: int = 10
    filter_nodes: List[str] = None
    exclude_nodes: List[str] = None
    
    # Runtime status tracking
    last_success: Optional[str] = None
    consecutive_failures: int = 0
    is_healthy: bool = True
    
    def __post_init__(self):
        if self.packet_types is None:
            self.packet_types = ['all']
        if self.filter_nodes is None:
            self.filter_nodes = []
        if self.exclude_nodes is None:
            self.exclude_nodes = []


@dataclass
class AgentConfig:
    """Configuration for the agent"""
    id: str
    location_name: str
    location_lat: float
    location_lon: float
    route_discovery: Optional[Dict] = None
    priority_nodes: List[str] = None
    priority_check_interval: int = 300  # 5 minutes for priority node checks
    priority_cache_duration: int = 12   # 12 hours cache for priority nodes vs 24 for regular
    
    def __post_init__(self):
        if self.priority_nodes is None:
            self.priority_nodes = []


@dataclass
class MeshtasticConfig:
    """Configuration for Meshtastic connection"""
    connection_type: str = 'auto'
    device_path: Optional[str] = None
    tcp_host: Optional[str] = None
    ble_address: Optional[str] = None


class ConfigManager:
    """Manages loading and validation of all configurations"""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.logger = logging.getLogger(__name__)
        
        if not Path(config_file).exists():
            raise FileNotFoundError(f"Configuration file {config_file} not found")
        
        self.config.read(config_file)
        self._validate_config()
    
    def _validate_config(self):
        """Validate required configuration sections exist"""
        required_sections = ['agent', 'meshtastic']
        missing_sections = [section for section in required_sections if section not in self.config.sections()]
        
        if missing_sections:
            raise ValueError(f"Missing required configuration sections: {missing_sections}")
        
        # Validate at least one server is configured
        server_sections = [s for s in self.config.sections() if s.startswith('server_')]
        if not server_sections:
            raise ValueError("No server configurations found. At least one [server_*] section is required")
    
    def load_agent_config(self) -> AgentConfig:
        """Load agent configuration"""
        try:
            agent_section = self.config['agent']
            
            # Load route discovery config if present
            route_discovery = None
            if 'route_discovery' in self.config.sections():
                route_discovery_section = dict(self.config.items('route_discovery'))
                route_discovery = {
                    'enabled': route_discovery_section.get('enabled', 'true').lower() == 'true',
                    'interval_minutes': int(route_discovery_section.get('interval_minutes', 60)),
                    'hop_limit': int(route_discovery_section.get('hop_limit', 7)),
                    'delay_between_traces': float(route_discovery_section.get('delay_between_traces', 3.0))
                }
            
            # Parse priority nodes
            priority_nodes = []
            if agent_section.get('priority_nodes'):
                priority_nodes = [node.strip() for node in agent_section['priority_nodes'].split(',') if node.strip()]
            
            return AgentConfig(
                id=agent_section['id'],
                location_name=agent_section['location_name'],
                location_lat=float(agent_section['location_lat']),
                location_lon=float(agent_section['location_lon']),
                route_discovery=route_discovery,
                priority_nodes=priority_nodes,
                priority_check_interval=int(agent_section.get('priority_check_interval', 300)),
                priority_cache_duration=int(agent_section.get('priority_cache_duration', 12))
            )
        except Exception as e:
            raise ValueError(f"Error loading agent configuration: {e}")
    
    def load_meshtastic_config(self) -> MeshtasticConfig:
        """Load Meshtastic connection configuration"""
        try:
            meshtastic_section = self.config['meshtastic']
            return MeshtasticConfig(
                connection_type=meshtastic_section.get('connection_type', 'auto'),
                device_path=meshtastic_section.get('device_path'),
                tcp_host=meshtastic_section.get('tcp_host'),
                ble_address=meshtastic_section.get('ble_address')
            )
        except Exception as e:
            raise ValueError(f"Error loading Meshtastic configuration: {e}")
    
    def load_server_configs(self) -> Dict[str, ServerConfig]:
        """Load all server configurations"""
        servers = {}
        
        for section_name in self.config.sections():
            if section_name.startswith('server_'):
                server_name = section_name[7:]  # Remove 'server_' prefix
                try:
                    servers[server_name] = self._load_single_server_config(server_name, section_name)
                except Exception as e:
                    self.logger.error(f"Error loading server config for {server_name}: {e}")
                    continue
        
        if not servers:
            raise ValueError("No valid server configurations found")
        
        return servers
    
    def _load_single_server_config(self, server_name: str, section_name: str) -> ServerConfig:
        """Load configuration for a single server"""
        section = dict(self.config.items(section_name))
        
        # Parse packet types
        packet_types = section.get('packet_types', 'all').split(',') if section.get('packet_types') != 'all' else ['all']
        packet_types = [pt.strip() for pt in packet_types if pt.strip()]
        
        # Parse node filters
        filter_nodes = []
        if section.get('filter_nodes'):
            filter_nodes = [node.strip() for node in section['filter_nodes'].split(',') if node.strip()]
        
        exclude_nodes = []
        if section.get('exclude_nodes'):
            exclude_nodes = [node.strip() for node in section['exclude_nodes'].split(',') if node.strip()]
        
        return ServerConfig(
            name=server_name,
            url=section['url'],
            api_key=section['api_key'],
            enabled=section.get('enabled', 'true').lower() == 'true',
            report_interval=int(section.get('report_interval', 30)),
            packet_types=packet_types,
            priority=int(section.get('priority', 1)),
            max_retries=int(section.get('max_retries', 3)),
            timeout=int(section.get('timeout', 10)),
            filter_nodes=filter_nodes,
            exclude_nodes=exclude_nodes
        )
    
    def get_database_path(self, agent_id: str) -> str:
        """Get database path for agent"""
        return f"{agent_id}_buffer.db"
    
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


def create_sample_multi_config(filename: str = 'multi_agent_config.ini'):
    """Create sample configuration file for multi-server setup"""
    config = configparser.ConfigParser()
    
    config['agent'] = {
        'id': 'agent_001',
        'location_name': 'Test Location',
        'location_lat': '37.7749',
        'location_lon': '-122.4194',
        '# priority_nodes': '!12345678,!87654321,!abcdef01',
        '# priority_check_interval': '300',
        '# priority_cache_duration': '12'
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
    
    # Route discovery configuration
    config['route_discovery'] = {
        'enabled': 'true',
        'interval_minutes': '60',
        'hop_limit': '7',
        'delay_between_traces': '3.0'
    }
    
    with open(filename, 'w') as f:
        config.write(f)
    
    print(f"Created sample multi-server config file: {filename}")
    print("\nServer configurations:")
    print("  - Primary: Real-time reporting every 30s")
    print("  - Backup: Redundant reporting every 60s") 
    print("  - Analytics: Position/telemetry only every 5min")
    print("\nRoute discovery:")
    print("  - Enabled: Automatic traceroute-based topology mapping")
    print("  - Interval: Every 60 minutes")
    print("  - Creates link-by-link network topology data")
    print("\nPriority node monitoring (optional):")
    print("  - Uncomment priority_nodes to enable priority monitoring")
    print("  - Priority nodes get fresher route data (6h cache vs 24h)")
    print("  - Proactive refresh every 2 hours")
    print("  - Example nodes: gateways, repeaters, critical infrastructure")