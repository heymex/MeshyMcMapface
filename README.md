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
pip install -r requirements.txt
```

### System Dependencies (Debian/Ubuntu)
```bash
sudo apt install python3 python3-venv python3-pip rsync
```

### Hardware Requirements
- **Agent**: Raspberry Pi or small computer near Meshtastic node
- **Server**: VPS or dedicated server (2GB RAM minimum)
- **Meshtastic Node**: Compatible device with Serial/TCP/BLE connectivity

## Quick Start

### SystemD Service Installation (Recommended for Production)

**Install Agent on Edge Node**
```bash
# Clone repository
git clone https://github.com/yourusername/MeshyMcMapface.git
cd MeshyMcMapface

# Install as systemd service (agent only - default)
sudo ./install-service.sh

# Edit configuration
sudo nano /etc/meshymcmapface/agent.ini

# Enable and start service
sudo systemctl enable meshymcmapface-agent
sudo systemctl start meshymcmapface-agent

# View logs
sudo journalctl -u meshymcmapface-agent -f
```

**Install Server on Central Node**
```bash
# Install server only
sudo ./install-service.sh --server

# Edit configuration
sudo nano /etc/meshymcmapface/server.ini

# Enable and start service
sudo systemctl enable meshymcmapface-server
sudo systemctl start meshymcmapface-server

# View logs
sudo journalctl -u meshymcmapface-server -f
```

**Installation Options**
- `./install-service.sh` or `./install-service.sh --agent` - Install agent only (default)
- `./install-service.sh --server` - Install server only
- `./install-service.sh --both` - Install both agent and server

**Uninstall**
```bash
# Remove services (keep data and config)
sudo ./uninstall-service.sh

# Complete removal including data and config
sudo ./uninstall-service.sh --purge
```

### Manual Setup (Development)

**1. Setup Central Server**

```bash
# Create server configuration
python3 mmm-server.py --create-config

# Start server
python3 mmm-server.py --config server_config.ini
```

The server will start at `http://localhost:8082` with a web dashboard and auto-generated API keys for agents.

**2. Setup MeshyMcMapface Agent**

```bash
# Create agent configuration
python3 mmm-agent-modular.py --create-config

# Edit agent.ini with your settings
nano multi_agent_config.ini

# Start agent with logging
python3 mmm-agent-modular.py --config multi_agent_config.ini --log-level INFO --log-file agent.log
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

### Agent Configuration (`agent.ini` or `multi_agent_config.ini`)
```ini
[agent]
id = agent_001
location_name = Test Location
location_lat = 37.7749
location_lon = -122.4194
database_dir = /var/lib/meshymcmapface  # Required for systemd service
# priority_nodes = !12345678,!87654321  # Optional: priority node monitoring
# priority_check_interval = 300         # Check every 5 minutes
# priority_cache_duration = 12          # Cache for 12 hours vs 24 for regular

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
```bash
# Central server
server_host:~$ sudo ./install-service.sh --server

# Edge nodes (3-5 Raspberry Pis)
edge01:~$ sudo ./install-service.sh --agent
edge02:~$ sudo ./install-service.sh --agent
edge03:~$ sudo ./install-service.sh --agent
```

Each agent connects to local Meshtastic node and reports to central server. Monitor entire regional network from central dashboard at `http://server_host:8082`.

### Multi-Region Network
```bash
# Central aggregation server
central:~$ sudo ./install-service.sh --server

# Region 1 (West Coast)
west01:~$ sudo ./install-service.sh --agent  # Configure to point to central server
west02:~$ sudo ./install-service.sh --agent

# Region 2 (East Coast)
east01:~$ sudo ./install-service.sh --agent  # Configure to point to central server
east02:~$ sudo ./install-service.sh --agent
```

Compare network health across regions and coordinate with other mesh operators.

### Emergency Response
```bash
# Mobile command center with server
command:~$ sudo ./install-service.sh --server

# Tactical deployment at key points
checkpoint1:~$ sudo ./install-service.sh --agent
checkpoint2:~$ sudo ./install-service.sh --agent
checkpoint3:~$ sudo ./install-service.sh --agent
```

Real-time monitoring of mesh network health, identify coverage gaps, and share network status with response teams.

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

### SystemD Service Issues

**Check Service Status**
```bash
# Check agent status
sudo systemctl status meshymcmapface-agent

# Check server status
sudo systemctl status meshymcmapface-server

# View recent logs
sudo journalctl -u meshymcmapface-agent -n 100
sudo journalctl -u meshymcmapface-server -n 100

# Follow logs in real-time
sudo journalctl -u meshymcmapface-agent -f
```

**Common Issues**
```bash
# Database permission error: "unable to open database file"
# Fix: Ensure database_dir is set in agent.ini
sudo nano /etc/meshymcmapface/agent.ini
# Add: database_dir = /var/lib/meshymcmapface

# Config file not found
# Fix: Create config if missing
cd /opt/meshymcmapface
sudo /opt/meshymcmapface/venv/bin/python3 mmm-agent-modular.py --create-config --config /etc/meshymcmapface/agent.ini

# Serial port permission denied
# Fix: Ensure user is in dialout group (install script does this)
sudo usermod -a -G dialout meshyuser
sudo systemctl restart meshymcmapface-agent

# Service restart loops
# Check for configuration errors in logs
sudo journalctl -u meshymcmapface-agent -n 50 --no-pager
```

### Agent Connection Issues
```bash
# Check Meshtastic device detection
meshtastic --info

# Test manual connection
python3 -c "import meshtastic; print(meshtastic.serial_interface.SerialInterface())"

# Check logs (systemd)
sudo journalctl -u meshymcmapface-agent -f

# Check logs (manual)
tail -f agent_*.log
```

### Server Issues
```bash
# Test API
curl -H "X-API-Key: your-key" http://localhost:8082/api/stats

# Check database
sudo sqlite3 /var/lib/meshymcmapface/distributed_meshview.db ".tables"

# Check server logs (systemd)
sudo journalctl -u meshymcmapface-server -f

# Check server logs (manual)
python3 mmm-server.py --config server_config.ini
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

### SystemD Service Security
The systemd service files include multiple security hardening features:
- `NoNewPrivileges=yes` - Prevents privilege escalation
- `ProtectSystem=strict` - Read-only system directories
- `ProtectHome=yes` - Blocks access to home directories
- `PrivateTmp=yes` - Isolated /tmp directory
- `DevicePolicy=closed` - Restricted device access
- Limited memory and CPU quotas

### API Security
- Use strong API keys for agent authentication (auto-generated during setup)
- Implement HTTPS in production with reverse proxy
- Rate limiting for API endpoints
- Server network restrictions via `IPAddressAllow` in systemd

### Network Security
- VPN connections for sensitive deployments
- Firewall rules for server access
- Encrypted data transmission (configure HTTPS/TLS)
- JSON TCP logging with TLS/SSL support

### Data Privacy
- Anonymize location data if required
- Implement data retention policies
- User consent for data collection
- Secure database storage in `/var/lib/meshymcmapface` with restricted permissions

## Next Steps

### Completed Features ✅
- ✅ Production-ready systemd service installation
- ✅ Selective agent/server installation with uninstall support
- ✅ Secure service configuration with hardened permissions
- ✅ Virtual environment isolation for dependencies
- ✅ Automatic database directory management
- ✅ Serial device access configuration (dialout group)
- ✅ JSON TCP logging with TLS/SSL support
- ✅ Interactive map visualization for nodes with real-time topology
- ✅ Advanced packet filtering and search in web UI
- ✅ Comprehensive node details with telemetry visualization
- ✅ Performance optimizations (3000x faster node loading)
- ✅ Dark mode support across all pages
- ✅ Robust date parsing and timezone handling
- ✅ Enhanced telemetry charts with current metrics fallback
- ✅ Multi-server support with priority and failover

### Immediate Enhancements
1. Add export functionality for data analysis (CSV/JSON)
2. Create alerting system for network issues
3. Implement data retention policies
4. Add bulk operations for node management
5. Monitoring integration (Monit, Prometheus, Grafana)

### Advanced Features
1. Machine learning for network optimization
2. Predictive analytics for coverage planning
3. Integration with emergency services
4. Mobile app for field monitoring
5. Docker containerization
6. Kubernetes orchestration for scale

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

### Production Deployment Architecture

**Files and Directories:**
- `/opt/meshymcmapface/` - Application code and virtual environment
- `/etc/meshymcmapface/` - Configuration files (agent.ini, server.ini)
- `/var/lib/meshymcmapface/` - Database files and persistent data
- `/var/log/meshymcmapface/` - Log files
- `/etc/systemd/system/meshymcmapface-*.service` - SystemD service definitions

**Service Management:**
```bash
# Start/stop services
sudo systemctl start meshymcmapface-agent
sudo systemctl stop meshymcmapface-agent

# Enable/disable auto-start on boot
sudo systemctl enable meshymcmapface-agent
sudo systemctl disable meshymcmapface-agent

# Restart after config changes
sudo systemctl restart meshymcmapface-agent

# View service status and recent logs
sudo systemctl status meshymcmapface-agent

# Follow live logs
sudo journalctl -u meshymcmapface-agent -f
```

**Benefits of SystemD Deployment:**
- ✅ Automatic service restart on failure
- ✅ Proper resource limits and security hardening
- ✅ Centralized logging with journald
- ✅ Easy monitoring with standard tools
- ✅ Consistent deployment across nodes
- ✅ Virtual environment isolation
- ✅ Proper permissions and user separation

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