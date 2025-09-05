# MeshyMcMapface
A distributed Meshtastic mesh network monitoring system with modular, extensible architecture.

## Architecture Overview

MeshyMcMapface provides a distributed monitoring system for Meshtastic mesh networks with:
- **Modular Agent System**: Connects to local Meshtastic nodes and collects data
- **Multi-Server Support**: Route data to multiple servers with different configurations
- **Central Server**: Aggregates data from multiple agents with web dashboard
- **Plugin Architecture**: Easily extensible for new packet types, server protocols, and features

### New Modular Structure

```
src/
├── core/                   # Core system components
│   ├── config.py          # Configuration management
│   ├── database.py        # Database abstraction layer
│   └── exceptions.py      # Custom exceptions
├── mesh_integration/      # Meshtastic integration
│   ├── connections.py     # Connection handling
│   ├── packet_parser.py   # Pluggable packet processors
│   └── node_tracker.py    # Node status tracking
├── servers/               # Server communication
│   ├── client.py          # Multi-server communication
│   ├── health.py          # Health monitoring
│   └── queue_manager.py   # Smart queuing system
├── agents/                # Agent implementations
│   ├── base_agent.py      # Extensible base class
│   └── multi_server_agent.py  # Multi-server agent
└── utils/                 # Utility functions
    ├── logging.py         # Centralized logging
    └── helpers.py         # Helper functions
```

## Requirements

### Python Dependencies
```bash
pip install meshtastic aiohttp aiosqlite configparser pubsub-api
```

### Hardware Requirements
- **Agent**: Raspberry Pi or small computer near Meshtastic node
- **Server**: VPS or dedicated server (2GB RAM minimum)
- **Meshtastic Node**: Compatible device with Serial/TCP/BLE connectivity

## Quick Start

### Two Agent Options Available

**🚀 Recommended: New Modular Agent**
- Better architecture and extensibility
- Multi-server support built-in
- Enhanced error handling and logging

**📦 Legacy Agent**
- Original implementation
- Single/multi-server support
- Maintained for compatibility

### 1. Setup Central Server

```bash
# Create server configuration
python mmm-server.py --create-config

# Start server
python mmm-server.py --config server_config.ini
```

The server will start at `http://localhost:8082` with a web dashboard and auto-generated API keys for agents.

### 2. Setup MeshyMcMapface Agent

#### Option A: New Modular Agent (Recommended)

```bash
# Create multi-server configuration
python mmm-agent-modular.py --create-config

# Edit multi_agent_config.ini with your settings
nano multi_agent_config.ini

# Start modular agent with advanced logging
python mmm-agent-modular.py --config multi_agent_config.ini --log-level INFO --log-file agent.log
```

#### Option B: Legacy Agent

```bash
# Create agent configuration
python mmm-agent.py --create-config

# Start legacy agent
python mmm-agent.py --config multi_agent_config.ini
```

## Configuration

### Server Configuration (`server_config.ini`)
```ini
[server]
host = localhost
port = 8082

[database]
path = distributed_meshview.db

[api_keys]
agent_001 = <generated-api-key>
agent_002 = <generated-api-key>
```

### Multi-Server Agent Configuration (`multi_agent_config.ini`)
```ini
[agent]
id = agent_sf_bay_001
location_name = San Francisco Bay Area
location_lat = 37.7749
location_lon = -122.4194

[meshtastic]
connection_type = auto
# device_path = /dev/ttyUSB0        # For USB/Serial
# tcp_host = 192.168.1.100         # For WiFi nodes
# ble_address = AA:BB:CC:DD:EE:FF  # For Bluetooth

# Primary server - real-time monitoring
[server_primary]
url = http://localhost:8082
api_key = primary-server-key
enabled = true
report_interval = 30
packet_types = all
priority = 1
max_retries = 3
timeout = 10

# Backup server - redundant reporting
[server_backup]
url = http://backup.example.com:8082
api_key = backup-server-key
enabled = true
report_interval = 60
packet_types = all
priority = 2
max_retries = 5
timeout = 15

# Analytics server - specific data only
[server_analytics]
url = http://analytics.example.com:8083
api_key = analytics-server-key
enabled = true
report_interval = 300
packet_types = position,telemetry
priority = 3
max_retries = 2
timeout = 30
# filter_nodes = node1,node2        # Only these nodes
# exclude_nodes = private_node      # Exclude these nodes
```

## Connection Types

### USB/Serial Connection
```ini
[meshtastic]
connection_type = serial
device_path = /dev/ttyUSB0  # Linux/Mac
# device_path = COM4        # Windows
```

### WiFi/TCP Connection
```ini
[meshtastic]
connection_type = tcp
tcp_host = 192.168.1.100
```

### Bluetooth Low Energy
```ini
[meshtastic]
connection_type = ble
ble_address = AA:BB:CC:DD:EE:FF
```

### Auto-detection
```ini
[meshtastic]
connection_type = auto
# Will try to auto-detect available Meshtastic devices
```

## Deployment Scenarios

### Single Region Monitoring
1. Deploy server on VPS or local server
2. Install agents on 2-5 Raspberry Pis in different locations
3. Each agent connects to local Meshtastic node
4. Monitor entire regional network from central dashboard

### Multi-Region Network
1. Central server aggregates data from multiple regions
2. Each region has 3-8 agents for coverage
3. Compare network health across regions
4. Coordinate with other mesh operators

### Emergency Response
1. Quickly deploy agents at key communication points
2. Real-time monitoring of mesh network health
3. Identify coverage gaps and connectivity issues
4. Share network status with response teams

## Web Dashboard Features

### 🎯 **Comprehensive Web Interface with Dark Mode Support**

#### **Main Dashboard (`/`)**
- Real-time system statistics (agents, packets, nodes)
- Live agent status and connectivity
- Recent packet activity stream
- Network health overview with metrics

#### **Agents Management (`/agents`)**
- All registered agents with locations
- Connection status and last seen
- Packet throughput statistics
- Agent health monitoring

#### **📊 Advanced Nodes Page (`/nodes`)**
- **Performance Optimized**: 3000x faster loading (60s → 20ms for large networks)
- **Advanced Filtering**: Quick filters by role, GPS, battery level
- **Real-time Search**: Find nodes by ID or name instantly
- **Role Classification**: Proper CLIENT/ROUTER/ROUTER_CLIENT/ROUTER_LATE distinction
- **Clickable Node Details**: Comprehensive popup modals with:
  - Basic node information (ID, names, hardware, firmware)
  - Status metrics (battery, voltage, uptime, signal quality)
  - **Enhanced Telemetry Charts**: Current metrics visualization when historical data unavailable
  - **Interactive Neighbor Graph**: Clickable neighbor navigation
  - Packet statistics and agent connectivity

#### **📦 Enhanced Packets Page (`/packets`)**
- Real-time packet stream with filtering
- Packet type classification (text, position, telemetry, user_info)
- Agent source tracking
- Payload inspection and formatting
- Timeline view with timestamps

#### **🗺️ Interactive Map Page (`/map`)**
- **Real-time Network Topology Visualization**
- **Clickable Node Markers**: Same detailed popups as Nodes page
- **Connection Visualization**: 
  - Color-coded lines by packet type
  - Line thickness indicates packet volume
- **Network Distance Indicators**: Color-coded by hop count from agents
- **Smart Filtering**: Show all nodes, active only, or agents only
- **Agent Tracking**: Special markers for MeshyMcMapface agents

#### **🌙 Universal Dark Mode**
- Complete dark/light mode toggle across all pages
- CSS custom properties for consistent theming
- localStorage persistence across sessions
- Proper contrast and accessibility

### 🔌 **API Endpoints**
- `POST /api/agent/register` - Register new agent
- `POST /api/agent/data` - Receive agent data
- `GET /api/agents` - List all agents
- `GET /api/packets?type=X&hours=Y&limit=Z` - Get packets with advanced filtering
- `GET /api/nodes/detailed?hours=X&limit=Y` - Optimized nodes with routes/topology
- `GET /api/nodes/{node_id}/details` - **Comprehensive node details** with telemetry and neighbors
- `GET /api/stats` - System statistics

## Monitoring Features

### Data Collection
- **Text Messages**: All mesh text communications
- **Position Data**: GPS coordinates and movement
- **Telemetry**: Battery levels, signal strength
- **Node Information**: Device details and status
- **Network Topology**: Routing and connectivity

### Health Monitoring
- Agent connectivity status
- Packet delivery rates
- Node availability
- Signal quality metrics
- Battery level tracking

### Alerting (Future Enhancement)
- Offline agent detection
- Low battery warnings
- Network congestion alerts
- Coverage gap identification

## Troubleshooting

### Agent Connection Issues
```bash
# Check Meshtastic device detection
meshtastic --info

# Test manual connection
python -c "import meshtastic; print(meshtastic.serial_interface.SerialInterface())"

# Check logs
tail -f agent_*.log
```

### Server Issues
```bash
# Create database
sqlite3 distributed_meshymcmapface.db ".tables"

# Test API
curl -H "X-API-Key: your-key" http://localhost:8082/api/stats

# Check server logs
python mmm-server.py --config server_config.ini
```

### Date and Telemetry Issues
If you encounter "Invalid Date" displays or missing telemetry charts:
- The system now handles multiple timestamp formats automatically
- Historical telemetry data with empty payloads will show current node metrics instead
- All date parsing is timezone-aware and robust

### Network Connectivity
```bash
# Test agent to server communication
curl -X POST -H "Content-Type: application/json" \
     -H "X-API-Key: your-key" \
     -d '{"agent_id":"test","location":{"name":"test","coordinates":[0,0]},"timestamp":"2025-01-01T00:00:00Z","packets":[],"node_status":[]}' \
     http://your-server:8082/api/agent/data
```

## Performance Optimization

### Agent Optimization
- Adjust `report_interval` based on network activity
- Use local database buffering for reliability
- Implement data compression for bandwidth savings

### Server Optimization
- Add database indexes for large datasets
- Implement data retention policies
- Use connection pooling for multiple agents

### Scaling Considerations
- Load balancer for multiple server instances
- Database clustering for high availability
- Regional server deployment for global networks

## Security Considerations

### API Security
- Use strong API keys for agent authentication
- Implement HTTPS in production
- Rate limiting for API endpoints

### Network Security
- VPN connections for sensitive deployments
- Firewall rules for server access
- Encrypted data transmission

### Data Privacy
- Anonymize location data if required
- Implement data retention policies
- User consent for data collection

## Next Steps

### Completed Features ✅
- ✅ Interactive map visualization for nodes with real-time topology
- ✅ Advanced packet filtering and search in web UI  
- ✅ Comprehensive node details with telemetry visualization
- ✅ Performance optimizations (3000x faster node loading)
- ✅ Dark mode support across all pages
- ✅ Robust date parsing and timezone handling
- ✅ Enhanced telemetry charts with current metrics fallback

### Immediate Enhancements
1. Add export functionality for data analysis (CSV/JSON)
2. Create alerting system for network issues
3. Implement data retention policies
4. Add bulk operations for node management

### Advanced Features
1. Machine learning for network optimization
2. Predictive analytics for coverage planning
3. Integration with emergency services
4. Mobile app for field monitoring

### Production Deployment
1. Docker containerization
2. Kubernetes orchestration
3. Database clustering
4. Monitoring and logging infrastructure

## Modular Architecture Benefits

### Easy Feature Extension
The new modular architecture makes adding features straightforward:

#### Adding New Packet Types
```python
# Create custom packet handler
class MyCustomHandler(PacketHandler):
    def can_handle(self, packet: Dict) -> bool:
        return 'my_data' in packet.get('decoded', {})
    
    def process(self, packet: Dict) -> Dict:
        # Custom processing logic
        return processed_packet_data

# Add to processor
packet_processor.add_handler(MyCustomHandler())
```

#### Adding New Server Types
```python
# Extend server client for custom protocols
class MyCustomServerClient(ServerClient):
    async def send_data(self, agent_config, packets, node_status):
        # Custom server communication
        pass
```

#### Adding New Agent Behaviors
```python
# Extend base agent
class MyCustomAgent(BaseAgent):
    def _handle_processed_packet(self, packet_data: Dict):
        # Custom packet handling
        pass
```

### Migration Path

**From Legacy → Modular:**
1. Both agents use same configuration format
2. Same database schema
3. Gradual migration possible
4. No server changes required

**Benefits of Modular Version:**
- ✅ Better error handling and recovery
- ✅ Pluggable packet processors  
- ✅ Multi-server health monitoring
- ✅ Repository pattern for data access
- ✅ Centralized logging and configuration
- ✅ Easy to add new features
- ✅ Better testing and maintainability

## Future Enhancements Made Easy

With the modular structure, these features can be added as separate modules:

1. **Web Dashboard**: `src/web/` module
2. **Metrics/Monitoring**: `src/metrics/` module  
3. **Alerting System**: `src/alerts/` module
4. **API Server**: `src/api/` module
5. **Plugin System**: Extend handler architecture
6. **Cloud Integration**: Cloud-specific clients
7. **Mobile Apps**: Mobile API endpoints
8. **Machine Learning**: ML-based analysis modules

## Support and Contributing

MeshyMcMapface provides a solid foundation for distributed mesh monitoring with a **modular, extensible architecture**. The plugin-based system allows for easy customization and feature addition.

Key areas for contribution:
- ✅ Enhanced web UI with interactive maps (completed)
- ✅ Performance optimizations (completed - 3000x faster)
- Advanced analytics and reporting  
- Mobile applications
- Integration with other mesh technologies
- Custom packet handlers
- Additional server protocols
- Monitoring and alerting systems
- Data export and backup systems
- Real-time notifications and alerts

The system is designed to be lightweight, reliable, and easy to deploy while providing comprehensive monitoring capabilities for Meshtastic mesh networks.