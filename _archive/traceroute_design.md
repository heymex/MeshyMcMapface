# Meshtastic Network Traceroute Design

## Goal
Build a complete mesh network topology by discovering the actual routing paths between nodes.

## Approach: Custom Traceroute Protocol

Since Meshtastic may not have built-in traceroute, we'll implement our own:

### 1. Route Discovery Messages

Send special "route discovery" messages that record their path:

```json
{
  "type": "route_discovery",
  "target_node": "!12345678",
  "source_node": "!87654321", 
  "hop_count": 0,
  "max_hops": 8,
  "path": ["!87654321"],
  "timestamp": "2025-08-16T12:00:00Z",
  "discovery_id": "uuid-1234"
}
```

### 2. Path Recording Protocol

Each intermediate node that forwards the message:
1. **Adds itself to the path**: `path.append(own_node_id)`
2. **Increments hop_count**: `hop_count += 1`
3. **Forwards if under max_hops**: Continue to target
4. **Logs the route**: Store partial path information

### 3. Route Response Messages

When the target receives the discovery message, it sends back a response:

```json
{
  "type": "route_response",
  "target_node": "!12345678",
  "source_node": "!87654321",
  "discovery_id": "uuid-1234", 
  "complete_path": ["!87654321", "!11111111", "!22222222", "!12345678"],
  "hop_count": 3,
  "timestamp": "2025-08-16T12:00:05Z"
}
```

### 4. Database Schema for Routes

```sql
-- Complete discovered routes
CREATE TABLE network_routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discovery_id TEXT NOT NULL,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    route_path TEXT NOT NULL,  -- JSON array of node IDs
    hop_count INTEGER NOT NULL,
    total_time_ms INTEGER,     -- Round-trip time
    discovery_timestamp TEXT NOT NULL,
    response_timestamp TEXT,
    success BOOLEAN DEFAULT FALSE
);

-- Individual route segments (links between adjacent nodes)
CREATE TABLE route_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discovery_id TEXT NOT NULL,
    from_node_id TEXT NOT NULL,
    to_node_id TEXT NOT NULL,
    segment_order INTEGER NOT NULL,  -- Position in the route
    agent_id TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
```

## Implementation Strategy

### Phase 1: Passive Route Learning
Monitor existing packet headers to infer routing:
- Track `hopLimit` decreases to identify forwarding nodes
- Use SNR/RSSI patterns to detect direct vs. forwarded packets
- Build probabilistic routing maps

### Phase 2: Active Route Discovery  
Implement custom traceroute protocol:
- Send route discovery messages to known nodes
- Parse responses to build complete path maps
- Store routes in graph-like database structure

### Phase 3: Network Graph Database
Use the route data to build a complete network graph:
- Nodes: All mesh participants
- Edges: Direct connections with quality metrics
- Paths: Multi-hop routes between any two nodes
- Algorithms: Shortest path, network analysis

## Graph Database Considerations

### Option 1: SQL with Graph Queries
Use recursive CTEs and JSON for graph operations:

```sql
-- Find shortest path between two nodes
WITH RECURSIVE route_finder AS (
  -- Base case: direct connections
  SELECT from_node_id, to_node_id, 1 as hops, 
         json_array(from_node_id, to_node_id) as path
  FROM direct_connections 
  WHERE from_node_id = 'source'
  
  UNION ALL
  
  -- Recursive case: extend paths
  SELECT rf.from_node_id, dc.to_node_id, rf.hops + 1,
         json_insert(rf.path, '$[#]', dc.to_node_id)
  FROM route_finder rf
  JOIN direct_connections dc ON rf.to_node_id = dc.from_node_id
  WHERE rf.hops < 8 AND rf.to_node_id != 'target'
)
SELECT * FROM route_finder WHERE to_node_id = 'target'
ORDER BY hops LIMIT 1;
```

### Option 2: Dedicated Graph Database
Consider integrating with:
- **Neo4j**: Full graph database with Cypher queries
- **NetworkX**: Python graph analysis library
- **D3.js**: Client-side graph visualization

## Benefits

1. **Complete Topology Map**: See actual routing paths, not just hop counts
2. **Network Analysis**: Identify critical nodes, redundant paths, bottlenecks  
3. **Route Optimization**: Find best paths for different criteria
4. **Failure Detection**: Detect when routes change due to node failures
5. **Multi-Agent Perspective**: Compare routing from different network positions

## Challenges

1. **Message Overhead**: Route discovery generates extra mesh traffic
2. **Protocol Support**: Need cooperative nodes to forward/respond to discovery
3. **Dynamic Networks**: Routes change as nodes join/leave
4. **Scale**: Large networks may have too many possible routes to discover

## Next Steps

1. **Research** existing Meshtastic routing capabilities
2. **Prototype** passive route learning from packet analysis  
3. **Design** custom route discovery message format
4. **Implement** route storage and graph queries
5. **Build** network topology visualization