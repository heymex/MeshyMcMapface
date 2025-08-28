"""
Packet processing handlers for different Meshtastic packet types
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Optional, Any


class PacketHandler(ABC):
    """Base class for packet handlers"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    @abstractmethod
    def can_handle(self, packet: Dict) -> bool:
        """Check if this handler can process the given packet"""
        pass
    
    @abstractmethod
    def process(self, packet: Dict) -> Dict:
        """Process the packet and return standardized packet data"""
        pass
    
    def _create_base_packet_data(self, packet: Dict) -> Dict:
        """Create base packet data structure"""
        return {
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


class TextMessageHandler(PacketHandler):
    """Handler for text messages"""
    
    def can_handle(self, packet: Dict) -> bool:
        decoded = packet.get('decoded', {})
        return 'text' in decoded if decoded else False
    
    def process(self, packet: Dict) -> Dict:
        packet_data = self._create_base_packet_data(packet)
        packet_data['type'] = 'text_message'
        packet_data['payload'] = packet['decoded']['text']
        
        self.logger.debug(f"Processed text message from {packet_data['from_node']}")
        return packet_data


class PositionHandler(PacketHandler):
    """Handler for position packets"""
    
    def can_handle(self, packet: Dict) -> bool:
        decoded = packet.get('decoded', {})
        return 'position' in decoded if decoded else False
    
    def process(self, packet: Dict) -> Dict:
        packet_data = self._create_base_packet_data(packet)
        packet_data['type'] = 'position'
        
        pos = packet['decoded']['position']
        position_data = {
            'latitude': getattr(pos, 'latitude', 0) if hasattr(pos, 'latitude') else pos.get('latitude', 0),
            'longitude': getattr(pos, 'longitude', 0) if hasattr(pos, 'longitude') else pos.get('longitude', 0),
            'altitude': getattr(pos, 'altitude', 0) if hasattr(pos, 'altitude') else pos.get('altitude', 0),
            'time': getattr(pos, 'time', 0) if hasattr(pos, 'time') else pos.get('time', 0)
        }
        packet_data['payload'] = position_data
        
        self.logger.debug(f"Processed position data from {packet_data['from_node']}: "
                         f"lat={position_data['latitude']}, lon={position_data['longitude']}")
        return packet_data


class TelemetryHandler(PacketHandler):
    """Handler for telemetry packets"""
    
    def can_handle(self, packet: Dict) -> bool:
        decoded = packet.get('decoded', {})
        return 'telemetry' in decoded if decoded else False
    
    def process(self, packet: Dict) -> Dict:
        packet_data = self._create_base_packet_data(packet)
        packet_data['type'] = 'telemetry'
        
        telemetry = packet['decoded']['telemetry']
        
        # Process different telemetry types
        telemetry_data = {}
        
        # Device metrics (battery, voltage, etc.)
        if hasattr(telemetry, 'device_metrics') or 'device_metrics' in telemetry:
            device_metrics = getattr(telemetry, 'device_metrics', telemetry.get('device_metrics', {}))
            if device_metrics:
                telemetry_data['device_metrics'] = {
                    'battery_level': getattr(device_metrics, 'battery_level', device_metrics.get('battery_level')),
                    'voltage': getattr(device_metrics, 'voltage', device_metrics.get('voltage')),
                    'channel_utilization': getattr(device_metrics, 'channel_utilization', device_metrics.get('channel_utilization')),
                    'air_util_tx': getattr(device_metrics, 'air_util_tx', device_metrics.get('air_util_tx'))
                }
        
        # Environment metrics (temperature, humidity, etc.)
        if hasattr(telemetry, 'environment_metrics') or 'environment_metrics' in telemetry:
            env_metrics = getattr(telemetry, 'environment_metrics', telemetry.get('environment_metrics', {}))
            if env_metrics:
                telemetry_data['environment_metrics'] = {
                    'temperature': getattr(env_metrics, 'temperature', env_metrics.get('temperature')),
                    'relative_humidity': getattr(env_metrics, 'relative_humidity', env_metrics.get('relative_humidity')),
                    'barometric_pressure': getattr(env_metrics, 'barometric_pressure', env_metrics.get('barometric_pressure'))
                }
        
        packet_data['payload'] = telemetry_data
        
        self.logger.debug(f"Processed telemetry data from {packet_data['from_node']}")
        return packet_data


class UserInfoHandler(PacketHandler):
    """Handler for user info packets"""
    
    def can_handle(self, packet: Dict) -> bool:
        decoded = packet.get('decoded', {})
        return 'user' in decoded if decoded else False
    
    def process(self, packet: Dict) -> Dict:
        packet_data = self._create_base_packet_data(packet)
        packet_data['type'] = 'user_info'
        
        user_info = packet['decoded']['user']
        user_data = {
            'id': getattr(user_info, 'id', user_info.get('id')),
            'long_name': getattr(user_info, 'long_name', user_info.get('long_name')),
            'short_name': getattr(user_info, 'short_name', user_info.get('short_name')),
            'macaddr': getattr(user_info, 'macaddr', user_info.get('macaddr'))
        }
        packet_data['payload'] = user_data
        
        self.logger.debug(f"Processed user info from {packet_data['from_node']}")
        return packet_data


class RoutingHandler(PacketHandler):
    """Handler for routing packets"""
    
    def can_handle(self, packet: Dict) -> bool:
        decoded = packet.get('decoded', {})
        return 'routing' in decoded if decoded else False
    
    def process(self, packet: Dict) -> Dict:
        packet_data = self._create_base_packet_data(packet)
        packet_data['type'] = 'routing'
        
        routing = packet['decoded']['routing']
        routing_data = {
            'error_reason': getattr(routing, 'error_reason', routing.get('error_reason')),
        }
        packet_data['payload'] = routing_data
        
        self.logger.debug(f"Processed routing packet from {packet_data['from_node']}")
        return packet_data


class TracerouteHandler(PacketHandler):
    """Handler for traceroute packets"""
    
    def can_handle(self, packet: Dict) -> bool:
        decoded = packet.get('decoded', {})
        return 'traceroute' in decoded if decoded else False
    
    def process(self, packet: Dict) -> Dict:
        packet_data = self._create_base_packet_data(packet)
        packet_data['type'] = 'traceroute'
        
        traceroute = packet['decoded']['traceroute']
        
        # Safely extract traceroute data, avoiding binary data
        traceroute_data = {}
        
        # Handle route field - may contain binary data
        if hasattr(traceroute, 'route') or 'route' in traceroute:
            route = getattr(traceroute, 'route', traceroute.get('route', []))
            # Convert any binary data to hex strings
            if isinstance(route, (list, tuple)):
                traceroute_data['route'] = []
                for hop in route:
                    if isinstance(hop, bytes):
                        traceroute_data['route'].append(hop.hex())
                    elif isinstance(hop, int):
                        traceroute_data['route'].append(f"!{hop:08x}")
                    else:
                        traceroute_data['route'].append(str(hop))
            elif isinstance(route, bytes):
                traceroute_data['route'] = route.hex()
            else:
                traceroute_data['route'] = str(route) if route is not None else None
        
        # Handle back field - may contain binary data
        if hasattr(traceroute, 'back') or 'back' in traceroute:
            back = getattr(traceroute, 'back', traceroute.get('back'))
            if isinstance(back, bytes):
                traceroute_data['back'] = back.hex()
            elif back is not None:
                traceroute_data['back'] = str(back)
            else:
                traceroute_data['back'] = None
        
        packet_data['payload'] = traceroute_data
        
        self.logger.debug(f"Processed traceroute packet from {packet_data['from_node']}")
        return packet_data


class EncryptedHandler(PacketHandler):
    """Handler for encrypted packets"""
    
    def can_handle(self, packet: Dict) -> bool:
        # If no decoded section or decoded is empty/None, it's likely encrypted
        decoded = packet.get('decoded')
        return not decoded or (isinstance(decoded, dict) and not decoded)
    
    def process(self, packet: Dict) -> Dict:
        packet_data = self._create_base_packet_data(packet)
        packet_data['type'] = 'encrypted'
        packet_data['payload'] = None
        
        self.logger.debug(f"Processed encrypted packet from {packet_data['from_node']}")
        return packet_data


class UnknownHandler(PacketHandler):
    """Handler for unknown/other packet types"""
    
    def can_handle(self, packet: Dict) -> bool:
        # This handler can handle any packet (fallback)
        return True
    
    def process(self, packet: Dict) -> Dict:
        packet_data = self._create_base_packet_data(packet)
        packet_data['type'] = 'other'
        packet_data['payload'] = packet.get('decoded', {})
        
        self.logger.debug(f"Processed unknown packet type from {packet_data['from_node']}")
        return packet_data


class PacketProcessor:
    """Main packet processor that routes packets to appropriate handlers"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.handlers = [
            TextMessageHandler(),
            PositionHandler(),
            TelemetryHandler(),
            UserInfoHandler(),
            RoutingHandler(),
            TracerouteHandler(),
            EncryptedHandler(),
            UnknownHandler()  # Always last as fallback
        ]
    
    def process_packet(self, packet: Dict) -> Dict:
        """Process a packet using the first matching handler"""
        try:
            for handler in self.handlers:
                if handler.can_handle(packet):
                    return handler.process(packet)
            
            # This should never happen since UnknownHandler accepts all packets
            self.logger.error(f"No handler found for packet: {packet}")
            return self.handlers[-1].process(packet)  # Use UnknownHandler as fallback
            
        except Exception as e:
            self.logger.error(f"Error processing packet: {e}")
            # Return a basic packet structure
            base_handler = PacketHandler()
            base_data = base_handler._create_base_packet_data(packet)
            base_data['type'] = 'error'
            base_data['error'] = str(e)
            return base_data
    
    def add_handler(self, handler: PacketHandler, priority: int = -1):
        """Add a custom handler at specified priority (default: before UnknownHandler)"""
        if priority == -1:
            # Insert before the last handler (UnknownHandler)
            self.handlers.insert(-1, handler)
        else:
            self.handlers.insert(priority, handler)
        
        self.logger.info(f"Added custom packet handler: {handler.__class__.__name__}")
    
    def remove_handler(self, handler_class: type):
        """Remove a handler by class type"""
        self.handlers = [h for h in self.handlers if not isinstance(h, handler_class)]
        self.logger.info(f"Removed packet handler: {handler_class.__name__}")