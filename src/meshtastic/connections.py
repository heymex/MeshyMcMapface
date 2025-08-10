"""
Meshtastic connection management
"""
import logging
import sys
from typing import Optional

from ..core.config import MeshtasticConfig
from ..core.exceptions import MeshtasticConnectionError

# Meshtastic imports - delay import until needed
meshtastic = None
pub = None

def _ensure_meshtastic_imports():
    """Ensure meshtastic modules are imported"""
    global meshtastic, pub
    if meshtastic is None:
        try:
            import meshtastic
            import meshtastic.serial_interface
            import meshtastic.tcp_interface
            import meshtastic.ble_interface
            from pubsub import pub
        except ImportError:
            raise MeshtasticConnectionError("Meshtastic library not installed. Run: pip install meshtastic")


class MeshtasticConnection:
    """Manages connection to Meshtastic devices"""
    
    def __init__(self, config: MeshtasticConfig):
        self.config = config
        self.interface = None
        self.logger = logging.getLogger(__name__)
    
    def connect(self) -> bool:
        """Connect to Meshtastic node based on configuration"""
        try:
            _ensure_meshtastic_imports()
            if self.config.connection_type == 'serial' or (self.config.connection_type == 'auto' and self.config.device_path):
                self.logger.info(f"Connecting via serial to {self.config.device_path}")
                self.interface = meshtastic.serial_interface.SerialInterface(devPath=self.config.device_path)
                
            elif self.config.connection_type == 'tcp' or (self.config.connection_type == 'auto' and self.config.tcp_host):
                self.logger.info(f"Connecting via TCP to {self.config.tcp_host}")
                self.interface = meshtastic.tcp_interface.TCPInterface(hostname=self.config.tcp_host)
                
            elif self.config.connection_type == 'ble' or (self.config.connection_type == 'auto' and self.config.ble_address):
                self.logger.info(f"Connecting via BLE to {self.config.ble_address}")
                self.interface = meshtastic.ble_interface.BLEInterface(address=self.config.ble_address)
                
            else:
                # Auto-detect
                self.logger.info("Auto-detecting Meshtastic device...")
                self.interface = meshtastic.serial_interface.SerialInterface()
            
            self.logger.info("Successfully connected to Meshtastic node")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Meshtastic node: {e}")
            raise MeshtasticConnectionError(f"Connection failed: {e}")
    
    def subscribe_to_events(self, on_receive_callback, on_connection_callback=None, on_node_updated_callback=None):
        """Subscribe to Meshtastic events"""
        try:
            _ensure_meshtastic_imports()
            pub.subscribe(on_receive_callback, "meshtastic.receive")
            
            if on_connection_callback:
                pub.subscribe(on_connection_callback, "meshtastic.connection.established")
            
            if on_node_updated_callback:
                pub.subscribe(on_node_updated_callback, "meshtastic.node.updated")
                
            self.logger.info("Subscribed to Meshtastic events")
            
        except Exception as e:
            self.logger.error(f"Error subscribing to events: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from Meshtastic node"""
        if self.interface:
            try:
                self.interface.close()
                self.logger.info("Disconnected from Meshtastic node")
            except Exception as e:
                self.logger.error(f"Error disconnecting: {e}")
            finally:
                self.interface = None
    
    def is_connected(self) -> bool:
        """Check if connected to Meshtastic node"""
        return self.interface is not None
    
    def get_interface(self):
        """Get the Meshtastic interface object"""
        return self.interface
    
    def get_node_info(self) -> Optional[dict]:
        """Get information about the connected node"""
        if not self.interface:
            return None
        
        try:
            # Get node info if available
            if hasattr(self.interface, 'nodesByNum') and self.interface.nodesByNum:
                # Get our own node info
                our_node = None
                for node in self.interface.nodesByNum.values():
                    if hasattr(node, 'isOurs') and node.isOurs:
                        our_node = node
                        break
                
                if our_node:
                    return {
                        'id': getattr(our_node, 'num', 'unknown'),
                        'user': {
                            'id': getattr(our_node.user, 'id', '') if hasattr(our_node, 'user') and our_node.user else '',
                            'long_name': getattr(our_node.user, 'longName', '') if hasattr(our_node, 'user') and our_node.user else '',
                            'short_name': getattr(our_node.user, 'shortName', '') if hasattr(our_node, 'user') and our_node.user else ''
                        }
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting node info: {e}")
            return None


class ConnectionManager:
    """Manages the lifecycle of Meshtastic connections"""
    
    def __init__(self):
        self.connection: Optional[MeshtasticConnection] = None
        self.logger = logging.getLogger(__name__)
    
    def create_connection(self, config: MeshtasticConfig) -> MeshtasticConnection:
        """Create a new Meshtastic connection"""
        if self.connection and self.connection.is_connected():
            self.logger.warning("Closing existing connection before creating new one")
            self.connection.disconnect()
        
        self.connection = MeshtasticConnection(config)
        return self.connection
    
    def get_connection(self) -> Optional[MeshtasticConnection]:
        """Get the current connection"""
        return self.connection
    
    def close_connection(self):
        """Close the current connection"""
        if self.connection:
            self.connection.disconnect()
            self.connection = None
    
    def reconnect(self) -> bool:
        """Attempt to reconnect using the same configuration"""
        if not self.connection:
            self.logger.error("No connection to reconnect")
            return False
        
        config = self.connection.config
        try:
            self.connection.disconnect()
            return self.connection.connect()
        except Exception as e:
            self.logger.error(f"Reconnection failed: {e}")
            return False