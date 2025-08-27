# MeshyMcMapface API Endpoints Reference

Complete documentation of all available API endpoints in the MeshyMcMapface system.

## 📡 Agent Management (POST endpoints)

### Register Agent
```
POST /api/agent/register
```
Register a new agent with the system.

**Request Body:**
```json
{
  "agent_id": "string",
  "location_name": "string",
  "coordinates": [lat, lon]
}
```

### Receive Agent Data
```
POST /api/agent/data
```
Receive general data from agents.

### Receive NodeDB Data
```
POST /api/agent/nodedb
```
Receive nodedb data from meshtastic command output.

### Receive Route Data
```
POST /api/agent/routes
```
Receive route discovery data from agents (traceroute data).

**Request Body:**
```json
{
  "agent_id": "string",
  "timestamp": "ISO-8601 timestamp",
  "routes": [
    {
      "discovery_id": "uuid",
      "source_node_id": "!12345678",
      "target_node_id": "!87654321",
      "route_path": ["!12345678", "!11111111", "!87654321"],
      "hop_count": 2,
      "total_time_ms": 850,
      "success": true
    }
  ]
}
```

## 🔍 Data Retrieval (GET endpoints)

### Agent Information

#### List All Agents
```
GET /api/agents
```
List all registered agents with their status and location information.

**Response:**
```json
{
  "agents": [
    {
      "agent_id": "agent_001",
      "location_name": "Seattle Hub",
      "coordinates": [47.6062, -122.3321],
      "last_seen": "2025-08-27T20:00:00Z",
      "packet_count": 150
    }
  ]
}
```

#### Agent Status
```
GET /api/agents/{agent_id}/status
```
Get specific agent status and health information.

### Network Data

#### Get Packets
```
GET /api/packets
```
Get recent packets with filtering options.

**Query Parameters:**
- `hours` - Hours back to search (default: 24)
- `limit` - Maximum number of packets (default: 100)
- `type` - Packet type filter (position, telemetry, text_message, etc.)
- `agent_id` - Filter by specific agent
- `from_node` - Filter by source node
- `to_node` - Filter by destination node

**Example:**
```
GET /api/packets?hours=6&limit=50&type=position&agent_id=agent_001
```

**Response:**
```json
{
  "packets": [
    {
      "from_node": "!12345678",
      "to_node": "!87654321",
      "type": "position",
      "timestamp": "2025-08-27T20:00:00Z",
      "payload": {...},
      "rssi": -75,
      "snr": 8.5,
      "agent_id": "agent_001"
    }
  ]
}
```

#### Get Nodes (Basic)
```
GET /api/nodes
```
Get basic node information across all agents.

**Query Parameters:**
- `agent_id` - Filter by specific agent
- `hours` - Hours back to include (default: 72)

#### Get Nodes (Detailed) ⭐
```
GET /api/nodes/detailed
```
Get detailed node information with packet history and user info. **This is the main endpoint used by the nodes page.**

**Query Parameters:**
- `hours` - Hours back to include (default: 72)
- `limit` - Maximum number of nodes (default: 100)
- `agent_id` - Filter by specific agent

**Response:**
```json
{
  "nodes": [
    {
      "node_id": "!12345678",
      "short_name": "NODE1",
      "long_name": "My Node 1",
      "hw_model": "HELTEC_V3",
      "role": "CLIENT_MUTE",
      "battery_level": 85,
      "position": [47.6062, -122.3321],
      "rssi": -75,
      "snr": 8.5,
      "updated_at": "2025-08-27T20:00:00Z",
      "hops_away": 2,
      "packet_count": 15,
      "agent_count": 2,
      "seeing_agents": ["agent_001", "agent_002"],
      "agent_routes": {
        "agent_001": {
          "hop_count": 2,
          "route_path": ["!agent001", "!relay", "!12345678"],
          "discovery_timestamp": "2025-08-27T19:30:00Z"
        }
      },
      "recent_packets": [...]
    }
  ]
}
```

### Network Analysis

#### Get Topology
```
GET /api/topology
```
Get network topology data showing hops from each agent to each node.

**Query Parameters:**
- `agent_id` - Filter by specific agent

**Response:**
```json
{
  "topology": {
    "agent_001": {
      "!12345678": {"hops": 2, "last_seen": "2025-08-27T20:00:00Z"},
      "!87654321": {"hops": 1, "last_seen": "2025-08-27T19:45:00Z"}
    }
  }
}
```

#### Get Connections
```
GET /api/connections
```
Get direct connections between nodes for network graph visualization.

**Query Parameters:**
- `agent_id` - Filter by specific agent
- `hours` - Hours back to analyze (default: 24)

#### Get Routes ⭐
```
GET /api/routes
```
Get discovered network routes for graph analysis. **This provides traceroute visualization data.**

**Query Parameters:**
- `agent_id` - Filter by specific agent
- `source_node` - Filter by source node ID
- `target_node` - Filter by target node ID  
- `hours` - Hours back to include (default: 24)
- `successful_only` - Only successful routes (default: true)

**Response:**
```json
{
  "routes": [
    {
      "discovery_id": "uuid-1234",
      "source_node_id": "!12345678",
      "target_node_id": "!87654321", 
      "agent_id": "agent_001",
      "route_path": ["!12345678", "!relay1", "!relay2", "!87654321"],
      "hop_count": 3,
      "total_time_ms": 1200,
      "discovery_timestamp": "2025-08-27T19:30:00Z",
      "response_timestamp": "2025-08-27T19:30:01Z",
      "success": true
    }
  ]
}
```

### System Statistics

#### Get Stats
```
GET /api/stats
```
Get overall system statistics.

**Response:**
```json
{
  "total_agents": 3,
  "total_nodes": 156,
  "total_packets": 5420,
  "active_nodes_1h": 45,
  "active_nodes_24h": 123,
  "packet_types": {
    "position": 2100,
    "telemetry": 1800,
    "text_message": 890
  }
}
```

## 🛠️ Debug Endpoints

### Debug Agents
```
GET /api/debug/agents
```
Debug endpoint to check agents in database.

### Debug Nodes  
```
GET /api/debug/nodes
```
Debug endpoint to check nodes in database.

### Debug Packets
```
GET /api/debug/packets  
```
Debug endpoint to check packets in database.

## 🌐 Web UI Pages

### Dashboard
```
GET /
```
Main dashboard page with overview statistics.

### Agents Page
```
GET /agents
```
Agent management and monitoring page.

### Packets Page
```
GET /packets
```
Packet viewer with filtering and search capabilities.

### Nodes Page ⭐
```
GET /nodes
```
**Enhanced nodes table page with role-based filtering, sorting, and GPS filters.**

Features:
- Role color coding (Router=Red, Client=Blue, Client_Mute=Green, etc.)
- Sortable columns (click headers to sort)
- Quick filter buttons:
  - All Nodes
  - Routers / Routers w/o GPS  
  - Clients / Client Mute
  - Has GPS
  - High Battery (>70%) / Low Battery (<30%)
- Real-time counters showing filter results
- Auto-refresh every 30 seconds

### Network Map
```
GET /map
```
Interactive network map visualization showing node locations and connections.

## 📊 Common Query Examples

```bash
# Get detailed nodes from last 6 hours
GET /api/nodes/detailed?hours=6&limit=100

# Get successful routes from specific agent in last 24 hours
GET /api/routes?agent_id=agent_007&successful_only=true&hours=24

# Get position packets from last hour
GET /api/packets?type=position&hours=1&limit=50

# Get topology data for network analysis
GET /api/topology?agent_id=agent_001

# Get system-wide statistics
GET /api/stats
```

## 🔐 Authentication

Currently, the API uses API keys for agent authentication. Agents must include their assigned API key when posting data to agent endpoints.

## 📝 Notes

- All timestamps are in ISO 8601 format with timezone information
- Node IDs follow the format `!12345678` (exclamation mark prefix)
- Coordinates are provided as `[latitude, longitude]` arrays
- Battery levels are percentages (0-100, though some nodes report >100%)
- RSSI values are in dBm (negative values, closer to 0 = stronger signal)
- SNR values are in dB (positive values = better signal quality)

---

**Server Base URL:** `http://localhost:8082` (local) or `https://roch-meshy.vdolan.com` (hosted)