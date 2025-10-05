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
        if not decoded:
            return False

        # Check for text message or TEXT_MESSAGE_APP portnum
        portnum = decoded.get('portnum')
        return 'text' in decoded or portnum == 'TEXT_MESSAGE_APP' or portnum == 1

    def process(self, packet: Dict) -> Dict:
        packet_data = self._create_base_packet_data(packet)
        packet_data['type'] = 'text_message'

        # Extract text from decoded section
        decoded = packet.get('decoded', {})
        packet_data['payload'] = decoded.get('text', '')

        self.logger.debug(f"Processed text message from {packet_data['from_node']}")
        return packet_data


class PositionHandler(PacketHandler):
    """Handler for position packets"""

    def can_handle(self, packet: Dict) -> bool:
        decoded = packet.get('decoded', {})
        if not decoded:
            return False

        # Check for position data or POSITION_APP portnum
        portnum = decoded.get('portnum')
        return 'position' in decoded or portnum == 'POSITION_APP' or portnum == 3

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
        if not decoded:
            return False

        # Check for telemetry data or TELEMETRY_APP portnum
        portnum = decoded.get('portnum')
        return 'telemetry' in decoded or portnum == 'TELEMETRY_APP' or portnum == 67

    def process(self, packet: Dict) -> Dict:
        packet_data = self._create_base_packet_data(packet)
        packet_data['type'] = 'telemetry'

        telemetry = packet['decoded']['telemetry']

        # Process different telemetry types
        telemetry_data = {}

        # Device metrics (battery, voltage, channel utilization, airtime, uptime)
        # Check for both snake_case and camelCase variants
        device_metrics = None
        if hasattr(telemetry, 'device_metrics') or 'device_metrics' in telemetry:
            device_metrics = getattr(telemetry, 'device_metrics', telemetry.get('device_metrics'))
        elif hasattr(telemetry, 'deviceMetrics') or 'deviceMetrics' in telemetry:
            device_metrics = getattr(telemetry, 'deviceMetrics', telemetry.get('deviceMetrics'))

        if device_metrics:
            telemetry_data['device_metrics'] = {
                'battery_level': getattr(device_metrics, 'battery_level', None) or getattr(device_metrics, 'batteryLevel', None) or device_metrics.get('battery_level') or device_metrics.get('batteryLevel'),
                'voltage': getattr(device_metrics, 'voltage', None) or device_metrics.get('voltage'),
                'channel_utilization': getattr(device_metrics, 'channel_utilization', None) or getattr(device_metrics, 'channelUtilization', None) or device_metrics.get('channel_utilization') or device_metrics.get('channelUtilization'),
                'air_util_tx': getattr(device_metrics, 'air_util_tx', None) or getattr(device_metrics, 'airUtilTx', None) or device_metrics.get('air_util_tx') or device_metrics.get('airUtilTx'),
                'uptime_seconds': getattr(device_metrics, 'uptime_seconds', None) or getattr(device_metrics, 'uptimeSeconds', None) or device_metrics.get('uptime_seconds') or device_metrics.get('uptimeSeconds')
            }

        # Environment metrics (temperature, humidity, pressure, sensors, etc.)
        # Check for both snake_case and camelCase variants
        env_metrics = None
        if hasattr(telemetry, 'environment_metrics') or 'environment_metrics' in telemetry:
            env_metrics = getattr(telemetry, 'environment_metrics', telemetry.get('environment_metrics'))
        elif hasattr(telemetry, 'environmentMetrics') or 'environmentMetrics' in telemetry:
            env_metrics = getattr(telemetry, 'environmentMetrics', telemetry.get('environmentMetrics'))

        if env_metrics:
            self.logger.debug(f"Environment metrics found for {packet_data['from_node']}: temp={env_metrics.get('temperature')}, humidity={env_metrics.get('relativeHumidity')}")
            telemetry_data['environment_metrics'] = {
                'temperature': getattr(env_metrics, 'temperature', None) or env_metrics.get('temperature'),
                'relative_humidity': getattr(env_metrics, 'relative_humidity', None) or getattr(env_metrics, 'relativeHumidity', None) or env_metrics.get('relative_humidity') or env_metrics.get('relativeHumidity'),
                'barometric_pressure': getattr(env_metrics, 'barometric_pressure', None) or getattr(env_metrics, 'barometricPressure', None) or env_metrics.get('barometric_pressure') or env_metrics.get('barometricPressure'),
                'gas_resistance': getattr(env_metrics, 'gas_resistance', None) or getattr(env_metrics, 'gasResistance', None) or env_metrics.get('gas_resistance') or env_metrics.get('gasResistance'),
                'voltage': getattr(env_metrics, 'voltage', None) or env_metrics.get('voltage'),
                'current': getattr(env_metrics, 'current', None) or env_metrics.get('current'),
                'iaq': getattr(env_metrics, 'iaq', None) or env_metrics.get('iaq'),
                'distance': getattr(env_metrics, 'distance', None) or env_metrics.get('distance'),
                'lux': getattr(env_metrics, 'lux', None) or env_metrics.get('lux'),
                'white_lux': getattr(env_metrics, 'white_lux', None) or getattr(env_metrics, 'whiteLux', None) or env_metrics.get('white_lux') or env_metrics.get('whiteLux'),
                'ir_lux': getattr(env_metrics, 'ir_lux', None) or getattr(env_metrics, 'irLux', None) or env_metrics.get('ir_lux') or env_metrics.get('irLux'),
                'uv_lux': getattr(env_metrics, 'uv_lux', None) or getattr(env_metrics, 'uvLux', None) or env_metrics.get('uv_lux') or env_metrics.get('uvLux'),
                'wind_direction': getattr(env_metrics, 'wind_direction', None) or getattr(env_metrics, 'windDirection', None) or env_metrics.get('wind_direction') or env_metrics.get('windDirection'),
                'wind_speed': getattr(env_metrics, 'wind_speed', None) or getattr(env_metrics, 'windSpeed', None) or env_metrics.get('wind_speed') or env_metrics.get('windSpeed'),
                'weight': getattr(env_metrics, 'weight', None) or env_metrics.get('weight'),
                'wind_gust': getattr(env_metrics, 'wind_gust', None) or getattr(env_metrics, 'windGust', None) or env_metrics.get('wind_gust') or env_metrics.get('windGust'),
                'wind_lull': getattr(env_metrics, 'wind_lull', None) or getattr(env_metrics, 'windLull', None) or env_metrics.get('wind_lull') or env_metrics.get('windLull'),
                'radiation': getattr(env_metrics, 'radiation', None) or env_metrics.get('radiation'),
                'rainfall_1h': getattr(env_metrics, 'rainfall_1h', None) or getattr(env_metrics, 'rainfall1h', None) or env_metrics.get('rainfall_1h') or env_metrics.get('rainfall1h'),
                'rainfall_24h': getattr(env_metrics, 'rainfall_24h', None) or getattr(env_metrics, 'rainfall24h', None) or env_metrics.get('rainfall_24h') or env_metrics.get('rainfall24h')
            }

        # Power metrics (multi-channel voltage/current monitoring)
        power_metrics = None
        if hasattr(telemetry, 'power_metrics') or 'power_metrics' in telemetry:
            power_metrics = getattr(telemetry, 'power_metrics', telemetry.get('power_metrics'))
        elif hasattr(telemetry, 'powerMetrics') or 'powerMetrics' in telemetry:
            power_metrics = getattr(telemetry, 'powerMetrics', telemetry.get('powerMetrics'))

        if power_metrics:
            telemetry_data['power_metrics'] = {
                'ch1_voltage': getattr(power_metrics, 'ch1_voltage', None) or getattr(power_metrics, 'ch1Voltage', None) or power_metrics.get('ch1_voltage') or power_metrics.get('ch1Voltage'),
                'ch1_current': getattr(power_metrics, 'ch1_current', None) or getattr(power_metrics, 'ch1Current', None) or power_metrics.get('ch1_current') or power_metrics.get('ch1Current'),
                'ch2_voltage': getattr(power_metrics, 'ch2_voltage', None) or getattr(power_metrics, 'ch2Voltage', None) or power_metrics.get('ch2_voltage') or power_metrics.get('ch2Voltage'),
                'ch2_current': getattr(power_metrics, 'ch2_current', None) or getattr(power_metrics, 'ch2Current', None) or power_metrics.get('ch2_current') or power_metrics.get('ch2Current'),
                'ch3_voltage': getattr(power_metrics, 'ch3_voltage', None) or getattr(power_metrics, 'ch3Voltage', None) or power_metrics.get('ch3_voltage') or power_metrics.get('ch3Voltage'),
                'ch3_current': getattr(power_metrics, 'ch3_current', None) or getattr(power_metrics, 'ch3Current', None) or power_metrics.get('ch3_current') or power_metrics.get('ch3Current')
            }

        # Air quality metrics (particulate matter and particle counts)
        aq_metrics = None
        if hasattr(telemetry, 'air_quality_metrics') or 'air_quality_metrics' in telemetry:
            aq_metrics = getattr(telemetry, 'air_quality_metrics', telemetry.get('air_quality_metrics'))
        elif hasattr(telemetry, 'airQualityMetrics') or 'airQualityMetrics' in telemetry:
            aq_metrics = getattr(telemetry, 'airQualityMetrics', telemetry.get('airQualityMetrics'))

        if aq_metrics:
            telemetry_data['air_quality_metrics'] = {
                'pm10_standard': getattr(aq_metrics, 'pm10_standard', None) or getattr(aq_metrics, 'pm10Standard', None) or aq_metrics.get('pm10_standard') or aq_metrics.get('pm10Standard'),
                'pm25_standard': getattr(aq_metrics, 'pm25_standard', None) or getattr(aq_metrics, 'pm25Standard', None) or aq_metrics.get('pm25_standard') or aq_metrics.get('pm25Standard'),
                'pm100_standard': getattr(aq_metrics, 'pm100_standard', None) or getattr(aq_metrics, 'pm100Standard', None) or aq_metrics.get('pm100_standard') or aq_metrics.get('pm100Standard'),
                'pm10_environmental': getattr(aq_metrics, 'pm10_environmental', None) or getattr(aq_metrics, 'pm10Environmental', None) or aq_metrics.get('pm10_environmental') or aq_metrics.get('pm10Environmental'),
                'pm25_environmental': getattr(aq_metrics, 'pm25_environmental', None) or getattr(aq_metrics, 'pm25Environmental', None) or aq_metrics.get('pm25_environmental') or aq_metrics.get('pm25Environmental'),
                'pm100_environmental': getattr(aq_metrics, 'pm100_environmental', None) or getattr(aq_metrics, 'pm100Environmental', None) or aq_metrics.get('pm100_environmental') or aq_metrics.get('pm100Environmental'),
                'particles_03um': getattr(aq_metrics, 'particles_03um', None) or getattr(aq_metrics, 'particles03um', None) or aq_metrics.get('particles_03um') or aq_metrics.get('particles03um'),
                'particles_05um': getattr(aq_metrics, 'particles_05um', None) or getattr(aq_metrics, 'particles05um', None) or aq_metrics.get('particles_05um') or aq_metrics.get('particles05um'),
                'particles_10um': getattr(aq_metrics, 'particles_10um', None) or getattr(aq_metrics, 'particles10um', None) or aq_metrics.get('particles_10um') or aq_metrics.get('particles10um'),
                'particles_25um': getattr(aq_metrics, 'particles_25um', None) or getattr(aq_metrics, 'particles25um', None) or aq_metrics.get('particles_25um') or aq_metrics.get('particles25um'),
                'particles_50um': getattr(aq_metrics, 'particles_50um', None) or getattr(aq_metrics, 'particles50um', None) or aq_metrics.get('particles_50um') or aq_metrics.get('particles50um'),
                'particles_100um': getattr(aq_metrics, 'particles_100um', None) or getattr(aq_metrics, 'particles100um', None) or aq_metrics.get('particles_100um') or aq_metrics.get('particles100um')
            }

        # Local stats (network statistics)
        local_stats = None
        if hasattr(telemetry, 'local_stats') or 'local_stats' in telemetry:
            local_stats = getattr(telemetry, 'local_stats', telemetry.get('local_stats'))
        elif hasattr(telemetry, 'localStats') or 'localStats' in telemetry:
            local_stats = getattr(telemetry, 'localStats', telemetry.get('localStats'))

        if local_stats:
            telemetry_data['local_stats'] = dict(local_stats) if isinstance(local_stats, dict) else str(local_stats)

        # Health metrics (heart rate, SpO2, body temperature)
        health_metrics = None
        if hasattr(telemetry, 'health_metrics') or 'health_metrics' in telemetry:
            health_metrics = getattr(telemetry, 'health_metrics', telemetry.get('health_metrics'))
        elif hasattr(telemetry, 'healthMetrics') or 'healthMetrics' in telemetry:
            health_metrics = getattr(telemetry, 'healthMetrics', telemetry.get('healthMetrics'))

        if health_metrics:
            telemetry_data['health_metrics'] = dict(health_metrics) if isinstance(health_metrics, dict) else str(health_metrics)

        packet_data['payload'] = telemetry_data

        self.logger.debug(f"Processed telemetry from {packet_data['from_node']}: {list(telemetry_data.keys())}")
        return packet_data


class UserInfoHandler(PacketHandler):
    """Handler for user info packets"""

    def can_handle(self, packet: Dict) -> bool:
        decoded = packet.get('decoded', {})
        if not decoded:
            return False

        # Check for user info or NODEINFO_APP portnum
        portnum = decoded.get('portnum')
        return 'user' in decoded or portnum == 'NODEINFO_APP' or portnum == 4

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
        if not decoded:
            return False

        # Check for routing data or ROUTING_APP portnum
        portnum = decoded.get('portnum')
        return 'routing' in decoded or portnum == 'ROUTING_APP' or portnum == 5

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
        if not decoded:
            return False

        # Check for traceroute data or TRACEROUTE_APP portnum
        portnum = decoded.get('portnum')
        return 'traceroute' in decoded or portnum == 'TRACEROUTE_APP' or portnum == 70

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
        # Check if packet has encrypted field or is missing decoded data
        if 'encrypted' in packet:
            return True

        decoded = packet.get('decoded')
        # If no decoded section or decoded is empty/None, it's likely encrypted
        if not decoded or (isinstance(decoded, dict) and not decoded):
            return True

        # Check if decoded has only portnum but no actual data (encrypted on non-default channel)
        if isinstance(decoded, dict):
            # If only has portnum and maybe request_id, but no actual payload data
            keys = set(decoded.keys()) - {'portnum', 'request_id', 'want_response'}
            if not keys:
                return True

        return False

    def process(self, packet: Dict) -> Dict:
        packet_data = self._create_base_packet_data(packet)
        packet_data['type'] = 'encrypted'

        # Try to extract portnum if available
        decoded = packet.get('decoded', {})
        if decoded and isinstance(decoded, dict):
            portnum = decoded.get('portnum')
            if portnum:
                packet_data['portnum'] = portnum

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