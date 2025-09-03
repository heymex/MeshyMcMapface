-- MeshyMcMapface Network Topology Database Schema
-- This schema captures the mesh network topology for visualization

-- Node topology table: captures how far each node is from each agent
CREATE TABLE IF NOT EXISTS node_topology (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    hops_away INTEGER,
    snr REAL,
    rssi INTEGER,
    last_heard INTEGER,
    timestamp TEXT NOT NULL,
    UNIQUE(node_id, agent_id) ON CONFLICT REPLACE
);

-- Direct connections table: captures direct mesh links between nodes
CREATE TABLE IF NOT EXISTS direct_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node_id TEXT NOT NULL,
    to_node_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,          -- Agent that observed this connection
    snr REAL,
    rssi INTEGER,
    link_quality REAL,              -- Signal quality metric
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    packet_count INTEGER DEFAULT 1,
    UNIQUE(from_node_id, to_node_id, agent_id) ON CONFLICT REPLACE
);

-- Network routes table: captures multi-hop paths through the network
CREATE TABLE IF NOT EXISTS network_routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node_id TEXT NOT NULL,
    to_node_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,         -- Agent that can see this route
    route_path TEXT,                -- JSON array of node IDs in path
    hop_count INTEGER,
    total_snr REAL,                 -- Cumulative SNR
    route_quality REAL,             -- Overall route quality metric
    timestamp TEXT NOT NULL,
    UNIQUE(from_node_id, to_node_id, agent_id) ON CONFLICT REPLACE
);

-- Network clusters table: groups of nodes that are closely connected
CREATE TABLE IF NOT EXISTS network_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    cluster_center BOOLEAN DEFAULT FALSE,
    distance_from_center INTEGER,
    timestamp TEXT NOT NULL,
    UNIQUE(cluster_id, node_id) ON CONFLICT REPLACE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_topology_node_agent ON node_topology(node_id, agent_id);
CREATE INDEX IF NOT EXISTS idx_topology_agent ON node_topology(agent_id);
CREATE INDEX IF NOT EXISTS idx_topology_timestamp ON node_topology(timestamp);

CREATE INDEX IF NOT EXISTS idx_connections_from_to ON direct_connections(from_node_id, to_node_id);
CREATE INDEX IF NOT EXISTS idx_connections_agent ON direct_connections(agent_id);
CREATE INDEX IF NOT EXISTS idx_connections_last_seen ON direct_connections(last_seen);

CREATE INDEX IF NOT EXISTS idx_routes_from_to ON network_routes(from_node_id, to_node_id);
CREATE INDEX IF NOT EXISTS idx_routes_agent ON network_routes(agent_id);
CREATE INDEX IF NOT EXISTS idx_routes_hop_count ON network_routes(hop_count);

CREATE INDEX IF NOT EXISTS idx_clusters_cluster_id ON network_clusters(cluster_id);
CREATE INDEX IF NOT EXISTS idx_clusters_node_id ON network_clusters(node_id);

-- Views for common queries

-- View: Current topology (most recent data per node-agent pair)
CREATE VIEW IF NOT EXISTS current_topology AS
SELECT nt.node_id, nt.agent_id, nt.hops_away, nt.snr, nt.rssi, 
       nt.last_heard, nt.timestamp,
       u.short_name, u.long_name, u.hw_model,
       a.location_name as agent_location
FROM node_topology nt
JOIN (
    SELECT node_id, agent_id, MAX(timestamp) as max_timestamp
    FROM node_topology
    GROUP BY node_id, agent_id
) latest ON nt.node_id = latest.node_id 
           AND nt.agent_id = latest.agent_id 
           AND nt.timestamp = latest.max_timestamp
LEFT JOIN user_info u ON nt.node_id = u.node_id
LEFT JOIN agents a ON nt.agent_id = a.agent_id;

-- View: Active direct connections (seen in last 24 hours)
CREATE VIEW IF NOT EXISTS active_connections AS
SELECT dc.from_node_id, dc.to_node_id, dc.agent_id,
       dc.snr, dc.rssi, dc.link_quality,
       dc.last_seen, dc.packet_count,
       uf.short_name as from_name, uf.long_name as from_long_name,
       ut.short_name as to_name, ut.long_name as to_long_name,
       a.location_name as agent_location
FROM direct_connections dc
LEFT JOIN user_info uf ON dc.from_node_id = uf.node_id
LEFT JOIN user_info ut ON dc.to_node_id = ut.node_id
LEFT JOIN agents a ON dc.agent_id = a.agent_id
WHERE datetime(dc.last_seen) > datetime('now', '-24 hours');

-- View: Network summary by agent
CREATE VIEW IF NOT EXISTS agent_network_summary AS
SELECT agent_id,
       COUNT(DISTINCT node_id) as nodes_visible,
       COUNT(CASE WHEN hops_away = 0 THEN 1 END) as direct_nodes,
       COUNT(CASE WHEN hops_away = 1 THEN 1 END) as one_hop_nodes,
       COUNT(CASE WHEN hops_away = 2 THEN 1 END) as two_hop_nodes,
       COUNT(CASE WHEN hops_away = 3 THEN 1 END) as three_hop_nodes,
       COUNT(CASE WHEN hops_away >= 4 THEN 1 END) as far_nodes,
       AVG(CAST(hops_away AS REAL)) as avg_hop_distance,
       MAX(hops_away) as max_hop_distance
FROM current_topology
GROUP BY agent_id;

-- View: Node reachability (how many agents can see each node)
CREATE VIEW IF NOT EXISTS node_reachability AS
SELECT node_id,
       COUNT(DISTINCT agent_id) as visible_to_agents,
       MIN(hops_away) as min_hops,
       MAX(hops_away) as max_hops,
       AVG(CAST(hops_away AS REAL)) as avg_hops,
       GROUP_CONCAT(DISTINCT agent_id) as seeing_agents
FROM current_topology
GROUP BY node_id;