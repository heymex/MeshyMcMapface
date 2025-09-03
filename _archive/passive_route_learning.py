#!/usr/bin/env python3
"""
Passive Route Learning for Meshtastic Networks

This module implements passive route discovery by analyzing packet metadata
to infer network topology without sending additional discovery traffic.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional, Tuple

class PassiveRouteAnalyzer:
    """Analyzes packets to infer mesh network routing topology"""
    
    def __init__(self):
        self.potential_routes: Dict[str, Dict] = {}
        self.hop_patterns: Dict[str, List] = {}
        self.direct_connections: Set[Tuple[str, str]] = set()
        
    def analyze_packet(self, packet_data: Dict) -> Optional[Dict]:
        """
        Analyze a single packet to extract routing information
        
        Returns inferred route data or None if no routing info can be determined
        """
        from_node = packet_data.get('from_node')
        to_node = packet_data.get('to_node') 
        hop_limit = packet_data.get('hop_limit')
        rssi = packet_data.get('rssi')
        snr = packet_data.get('snr')
        timestamp = packet_data.get('timestamp')
        
        # Skip invalid packets
        if not from_node or not to_node or from_node in ['^all', '^local']:
            return None
            
        route_info = {
            'from_node': from_node,
            'to_node': to_node,
            'hop_limit': hop_limit,
            'rssi': rssi,
            'snr': snr,
            'timestamp': timestamp,
            'inferred_hops': None,
            'is_direct_connection': False,
            'route_quality': None
        }
        
        # Detect direct connections (strong signal)
        if self._is_direct_connection(rssi, snr):
            route_info['is_direct_connection'] = True
            route_info['inferred_hops'] = 1
            self.direct_connections.add((from_node, to_node))
            
        # Infer hop count from hop_limit pattern
        elif hop_limit is not None:
            inferred_hops = self._infer_hops_from_limit(from_node, to_node, hop_limit)
            route_info['inferred_hops'] = inferred_hops
            
        # Calculate route quality
        route_info['route_quality'] = self._calculate_route_quality(rssi, snr, route_info['inferred_hops'])
        
        return route_info
    
    def _is_direct_connection(self, rssi: Optional[int], snr: Optional[float]) -> bool:
        """Determine if signal strength indicates direct connection"""
        if snr is not None:
            # High SNR typically indicates direct connection
            return snr > 5.0
        elif rssi is not None:
            # Strong RSSI indicates direct connection  
            return rssi > -80
        return False
    
    def _infer_hops_from_limit(self, from_node: str, to_node: str, hop_limit: int) -> Optional[int]:
        """
        Infer actual hop count by analyzing hop_limit patterns
        
        In Meshtastic, hop_limit decreases by 1 at each hop.
        By tracking hop_limit values for the same source, we can infer routing.
        """
        node_pair = f"{from_node}->{to_node}"
        
        if node_pair not in self.hop_patterns:
            self.hop_patterns[node_pair] = []
            
        self.hop_patterns[node_pair].append(hop_limit)
        
        # If we've seen multiple hop_limit values, infer the route
        limits = self.hop_patterns[node_pair]
        if len(limits) >= 3:
            # Most common hop_limit probably represents the actual path
            from collections import Counter
            most_common_limit = Counter(limits).most_common(1)[0][0]
            
            # Typical initial hop_limit is 3-8, so inferred hops = initial - observed
            # This is approximate without knowing the initial value
            if most_common_limit <= 1:
                return 3  # Likely 2-3 hops away
            elif most_common_limit <= 2:
                return 2  # Likely 1-2 hops away  
            else:
                return 1  # Likely direct or 1 hop
                
        return None
    
    def _calculate_route_quality(self, rssi: Optional[int], snr: Optional[float], 
                               hops: Optional[int]) -> Optional[float]:
        """Calculate overall route quality (0.0 = poor, 1.0 = excellent)"""
        quality_factors = []
        
        # SNR quality factor
        if snr is not None:
            if snr > 10:
                quality_factors.append(1.0)
            elif snr > 0:
                quality_factors.append(0.8)
            elif snr > -10:
                quality_factors.append(0.5)
            else:
                quality_factors.append(0.2)
        
        # RSSI quality factor  
        if rssi is not None:
            if rssi > -60:
                quality_factors.append(1.0)
            elif rssi > -80:
                quality_factors.append(0.8)
            elif rssi > -100:
                quality_factors.append(0.5)
            else:
                quality_factors.append(0.2)
                
        # Hop count quality factor (fewer hops = better)
        if hops is not None:
            if hops == 1:
                quality_factors.append(1.0)
            elif hops == 2:
                quality_factors.append(0.8)
            elif hops == 3:
                quality_factors.append(0.6)
            else:
                quality_factors.append(0.4)
        
        return sum(quality_factors) / len(quality_factors) if quality_factors else None
    
    def infer_route_from_patterns(self, source: str, target: str) -> Optional[Dict]:
        """
        Infer a likely route between two nodes based on observed patterns
        
        This uses the direct connections and hop patterns to build probable paths
        """
        # Try to find a path using known direct connections
        path = self._find_path_through_connections(source, target)
        
        if path:
            return {
                'discovery_id': str(uuid.uuid4()),
                'source_node_id': source,
                'target_node_id': target,
                'route_path': path,
                'hop_count': len(path) - 1,
                'confidence': self._calculate_path_confidence(path),
                'discovery_method': 'passive_inference',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        
        return None
    
    def _find_path_through_connections(self, source: str, target: str, 
                                     max_hops: int = 5) -> Optional[List[str]]:
        """Find path using breadth-first search through known direct connections"""
        from collections import deque
        
        if source == target:
            return [source]
            
        # BFS to find shortest path
        queue = deque([(source, [source])])
        visited = {source}
        
        while queue:
            current, path = queue.popleft()
            
            if len(path) > max_hops:
                continue
                
            # Check all direct connections from current node
            for from_node, to_node in self.direct_connections:
                if from_node == current and to_node not in visited:
                    new_path = path + [to_node]
                    
                    if to_node == target:
                        return new_path
                        
                    visited.add(to_node)
                    queue.append((to_node, new_path))
        
        return None
    
    def _calculate_path_confidence(self, path: List[str]) -> float:
        """Calculate confidence in inferred path based on observed data"""
        if len(path) <= 1:
            return 1.0
            
        confidence = 1.0
        
        # Reduce confidence for each hop (longer paths less certain)
        confidence *= (0.8 ** (len(path) - 1))
        
        # Check if we've observed all links in the path
        observed_links = 0
        total_links = len(path) - 1
        
        for i in range(len(path) - 1):
            if (path[i], path[i + 1]) in self.direct_connections:
                observed_links += 1
                
        # Boost confidence if we've directly observed the links
        link_confidence = observed_links / total_links if total_links > 0 else 0
        confidence = (confidence + link_confidence) / 2
        
        return min(confidence, 1.0)
    
    def get_network_graph(self) -> Dict:
        """Get the current state of the inferred network graph"""
        return {
            'direct_connections': list(self.direct_connections),
            'hop_patterns': self.hop_patterns,
            'total_connections': len(self.direct_connections),
            'analyzed_pairs': len(self.hop_patterns)
        }

# Integration with existing server code
def add_passive_route_analysis_to_server():
    """
    Shows how to integrate passive route learning into the existing server
    """
    
    example_integration = '''
    # In mmm-server.py, modify receive_agent_data method:
    
    class MeshyMcMapfaceServer:
        def __init__(self):
            # ... existing init code ...
            self.route_analyzer = PassiveRouteAnalyzer()
        
        async def receive_agent_data(self, request):
            # ... existing packet processing ...
            
            for packet in packets:
                # Existing packet storage code ...
                
                # NEW: Passive route analysis
                route_info = self.route_analyzer.analyze_packet(packet)
                if route_info:
                    # Store inferred route data
                    if route_info['is_direct_connection']:
                        # Update direct_connections table
                        await self.store_direct_connection(route_info, agent_id)
                    
                    # Try to infer complete routes periodically
                    if should_infer_routes():  # e.g., every 100 packets
                        await self.infer_and_store_routes(agent_id)
        
        async def infer_and_store_routes(self, agent_id):
            """Infer routes between known nodes and store them"""
            known_nodes = await self.get_known_nodes()
            
            for source in known_nodes:
                for target in known_nodes:
                    if source != target:
                        route = self.route_analyzer.infer_route_from_patterns(source, target)
                        if route and route['confidence'] > 0.5:  # Only store confident routes
                            await self.store_inferred_route(route, agent_id)
    '''
    
    return example_integration

if __name__ == "__main__":
    # Example usage
    analyzer = PassiveRouteAnalyzer()
    
    # Simulate some packet analysis
    sample_packets = [
        {
            'from_node': '!12345678',
            'to_node': '!87654321', 
            'hop_limit': 3,
            'rssi': -45,
            'snr': 12.5,
            'timestamp': '2025-08-16T12:00:00Z'
        },
        {
            'from_node': '!12345678',
            'to_node': '!abcdef00',
            'hop_limit': 2, 
            'rssi': -85,
            'snr': -2.1,
            'timestamp': '2025-08-16T12:01:00Z'
        }
    ]
    
    print("=== PASSIVE ROUTE LEARNING DEMO ===\n")
    
    for i, packet in enumerate(sample_packets):
        print(f"Analyzing packet {i+1}:")
        route_info = analyzer.analyze_packet(packet)
        print(json.dumps(route_info, indent=2))
        print()
    
    print("Network graph state:")
    graph = analyzer.get_network_graph()
    print(json.dumps(graph, indent=2))