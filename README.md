# MeshyMcMapface
My attempt to "vibe code" a Meshtastic mapping utility based on agent-collector architecture

# MeshyMcMapface MVP Setup Guide

## Overview
This MVP provides a distributed monitoring system for Meshtastic mesh networks with:
- **MeshyMcMapface Agent**: Connects to local Meshtastic nodes and collects data
- **Central Server**: Aggregates data from multiple agents with web dashboard

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

### 1. Setup Central Server

```bash
# Create server configuration
python enhanced_server_mvp.py --create-config

# Start server
python enhanced_server_mvp.py --config server_config.ini
```

The server will start at `http://localhost:8082` with a web dashboard and auto-generated API keys for agents.

### 2. Setup MeshyMcMapface Agent

```bash
# Create agent configuration
python mesh_agent_mvp.py --create-config

# Edit agent_config.ini with your settings
nano agent_config.ini

# Start agent
python mesh_agent_mvp.py --config agent_config.ini
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

### Agent Configuration (`agent_config.ini`)
```ini
[agent]
id = agent_sf_bay_001
location_name = San Francisco Bay Area
location_lat = 37.7749
location_lon = -122.4194

[server]
url = http://your-server:8082
api_key = <your-api-key-from-server>
report_interval = 30

[meshtastic]
connection_type = auto
# device_path = /dev/ttyUSB0        # For USB/Serial
# tcp_host = 192.168.1.100         # For WiFi nodes
# ble_address = AA:BB:CC:DD:EE:FF  # For Bluetooth
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

### Main Dashboard (`/`)
- Real-time statistics (agents, packets, nodes)
- Recent agent activity
- Latest packet stream
- Network health overview

### Agents Page (`/agents`)
- All registered agents
- Location information
- Connection status
- Packet counts

### API Endpoints
- `POST /api/agent/register` - Register new agent
- `POST /api/agent/data` - Receive agent data
- `GET /api/agents` - List all agents
- `GET /api/packets` - Get packets with filtering
- `GET /api/nodes` - Get node information
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
python enhanced_server_mvp.py --config server_config.ini
```

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

### Immediate Enhancements
1. Add map visualization for nodes
2. Implement packet filtering in web UI
3. Add export functionality for data analysis
4. Create alerting system for network issues

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

## Support and Contributing

This MVP provides a solid foundation for distributed mesh monitoring called **MeshyMcMapface**. The modular architecture allows for easy extension and customization based on specific deployment needs.

Key areas for contribution:
- Enhanced web UI with interactive maps
- Advanced analytics and reporting
- Mobile applications
- Integration with other mesh technologies
- Performance optimizations

The system is designed to be lightweight, reliable, and easy to deploy while providing comprehensive monitoring capabilities for Meshtastic mesh networks through **MeshyMcMapface**.