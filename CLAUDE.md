# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MeshyMcMapface is a distributed Meshtastic mesh network monitoring system with modular architecture. It provides real-time monitoring, route discovery, and network topology analysis for Meshtastic mesh networks.

## Key Commands

### Core Application
```bash
# Install dependencies
pip install -r requirements.txt

# Create configuration files
python3 mmm-agent-modular.py --create-config
python3 mmm-server.py --create-config

# Run modular agent (main application)
python3 mmm-agent-modular.py --config multi_agent_config.ini --log-level INFO --log-file agent.log

# Run server with logging options
python3 mmm-server.py --config server_config.ini --log-level INFO --log-file server.log
```

### SystemD Service Installation
```bash
# Install as system services
sudo ./install-service.sh

# Service management
sudo systemctl enable meshymcmapface-agent
sudo systemctl start meshymcmapface-agent
sudo systemctl enable meshymcmapface-server
sudo systemctl start meshymcmapface-server

# Check service status
sudo systemctl status meshymcmapface-agent
sudo systemctl status meshymcmapface-server

# View service logs
sudo journalctl -u meshymcmapface-agent -f
sudo journalctl -u meshymcmapface-server -f
```

### Development Tools (in _archive/)
```bash
# Legacy agent and development tools are archived in _archive/ directory
# Access them if needed for development or debugging:
python3 _archive/test_agent_nodedb.py
python3 _archive/db-inspektah.py
python3 _archive/simple_meshtastic_test.py
```

## Architecture

### Core Components

**Main Architecture**:
- `src/core/` - Configuration, database, exceptions, priority monitoring
- `src/agents/` - Base agent classes and multi-server agent implementation
- `src/mesh_integration/` - Meshtastic connections, packet parsing, node tracking
- `src/servers/` - Server communication clients, health monitoring, queue management
- `src/utils/` - Logging and helper utilities
- `mmm-server.py` - Server implementation with web dashboard
- `meshtastic_traceroute_integration.py` - Route discovery functionality

**Archived Components**:
- `_archive/` - Contains legacy agent, test scripts, and development utilities

### Key Classes and Patterns

**Configuration Management**: The `ConfigManager` class in `src/core/config.py` handles multi-server configurations with validation. Supports multiple server targets with different priorities, intervals, and packet filtering.

**Agent Pattern**: `BaseAgent` in `src/agents/base_agent.py` provides abstract base class for all agents. Implements Meshtastic connection management, packet processing, and route discovery integration.

**Repository Pattern**: Database access uses repository pattern in `src/core/database.py` with separate classes for different data types (agents, packets, nodes, routes).

**Plugin Architecture**: Packet handlers in `src/mesh_integration/packet_parser.py` can be extended with custom packet processors.

### Route Discovery System

The system includes comprehensive route discovery using Meshtastic's traceroute functionality:
- `meshtastic_traceroute_integration.py` - Core traceroute management
- `MeshtasticTracerouteManager` - Handles route discovery with caching
- Priority node monitoring for critical network infrastructure
- Route caching with TTL for performance optimization

### Database Schema

**Core Tables**:
- `agents` - Agent registration and status
- `packets` - All mesh packets with agent attribution
- `nodes` - Node information per agent
- `routes` - Discovered network routes from traceroute

**Route Discovery Tables**:
- `route_cache` - Cached route information with TTL
- `route_discoveries` - Historical route discovery results

### Multi-Server Support

Agents can report to multiple servers simultaneously with different configurations:
- Primary server for real-time monitoring
- Backup server for redundancy
- Analytics servers for specific data types
- Per-server filtering and retry logic

## Configuration Files

**Agent Config** (`multi_agent_config.ini`):
- Agent identification and location
- Meshtastic connection settings (auto, serial, TCP, BLE)
- Multiple server configurations with priorities
- Route discovery settings
- Priority node monitoring
- JSON TCP logging destinations for remote logging

**Server Config** (`server_config.ini`):
- Server binding and database settings
- Agent API keys for authentication
- Web dashboard configuration
- JSON TCP logging destinations for remote logging

### JSON TCP Logging Configuration

Both agent and server support structured JSON logging to remote log collectors over TCP:

```ini
# Example JSON TCP logging configurations in config files
[json_tcp_log_primary]
host = logs.example.com
port = 5140
application = meshymcmapface-agent
environment = production

[json_tcp_log_backup]
host = backup-logs.example.com
port = 5141
application = meshymcmapface-agent
environment = production
```

**Supported Options:**
- **Host**: Target log collector hostname or IP
- **Port**: TCP port for log collector (default: 5140)
- **Application**: Application identifier in logs (default: meshymcmapface)
- **Environment**: Environment tag (default: production)

**Log Format**: Each log entry is sent as a JSON object with newline delimiter containing:
- `timestamp`: Unix timestamp
- `iso_timestamp`: ISO 8601 formatted timestamp
- `level`: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `logger`: Logger name
- `message`: Log message
- `application`: Application identifier
- `environment`: Environment tag
- `host`: Hostname of the logging system
- `module`, `function`, `line`: Code location information
- `thread`, `process`: Execution context

## Web Dashboard

Accessible at `http://localhost:8082` (configurable):
- Main dashboard with real-time statistics
- Agent status and locations (`/agents`)
- Packet viewer with filtering (`/packets`)
- Node information with role-based filtering (`/nodes`)
- Interactive network map (`/map`)

## API Endpoints

**Agent Data Submission**:
- `POST /api/agent/register` - Agent registration
- `POST /api/agent/data` - General packet data
- `POST /api/agent/nodedb` - Node database information
- `POST /api/agent/routes` - Route discovery results

**Data Retrieval**:
- `GET /api/agents` - List all agents
- `GET /api/nodes/detailed` - Detailed node information (main nodes page endpoint)
- `GET /api/packets` - Filtered packet data
- `GET /api/routes` - Network route data for graph visualization
- `GET /api/stats` - System statistics

## Development Guidelines

**Adding New Features**:
1. Use modular architecture in `src/` directory
2. Follow repository pattern for database access
3. Implement packet handlers for new data types
4. Add server clients for new protocols
5. Extend base agent for custom behaviors

**Database Changes**:
- Use `_archive/migrate_db.py` for schema changes
- Test with `_archive/db-inspektah.py` for data integrity
- Run database utilities from _archive/ for maintenance

**Testing**:
- Test individual components with scripts in `_archive/`
- Use `_archive/simple_meshtastic_test.py` for connection testing
- Verify multi-server configurations before deployment

## Important Implementation Notes

**Connection Management**: The system supports automatic Meshtastic device detection and multiple connection types (Serial, TCP, BLE). Connection failures are handled gracefully with retry logic.

**Data Buffering**: Local SQLite databases buffer data when servers are unreachable, ensuring no data loss during network interruptions.

**Route Discovery**: Implements intelligent route caching with priority node monitoring. Routes to priority nodes (gateways, repeaters) are refreshed more frequently.

**Error Handling**: Custom exception hierarchy in `src/core/exceptions.py` provides specific error types for different failure scenarios.

**Logging**: Centralized logging configuration supports file output, different log levels, and structured logging for debugging.

The modular architecture enables easy extension for additional mesh technologies, server protocols, and analysis features. Legacy tools and the original agent implementation are preserved in the `_archive/` directory for reference and specialized use cases.

## File Organization

**Active Files (Production)**:
- `mmm-agent-modular.py` - Main agent application
- `mmm-server.py` - Server application  
- `meshtastic_traceroute_integration.py` - Route discovery
- `src/` - Complete modular architecture
- Configuration and documentation files

**Archived Files** (`_archive/`):
- `mmm-agent.py` - Legacy single-file agent
- Database utilities, test scripts, debug tools
- Development and research code
- Design documents and schemas

**SystemD Service Files**:
- `systemd/` - Service definition files for system installation
- `install-service.sh` - Automated installation script

## SystemD Service Deployment

The system includes full systemd integration for production deployment:

### Installation Process
1. Run `sudo ./install-service.sh` to install services
2. Configure settings in `/etc/meshymcmapface/`
3. Enable and start services
4. Monitor via journalctl

### Service Features
- **Security hardening**: Restricted permissions, private temp, read-only system
- **Resource limits**: Memory and CPU quotas
- **Auto-restart**: Automatic restart on failure with backoff
- **Logging integration**: Full journalctl support + optional JSON TCP logging
- **Network security**: IP restrictions for server service