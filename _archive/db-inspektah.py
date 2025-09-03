#!/usr/bin/env python3
"""
Database Inspector for MeshyMcMapface Agent
"""

import sqlite3
import sys
from datetime import datetime, timezone

def inspect_database(db_path):
    """Inspect the agent database contents"""
    try:
        conn = sqlite3.connect(db_path)
        
        print(f"=== Inspecting database: {db_path} ===\n")
        
        # Check tables
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"Tables found: {[t[0] for t in tables]}\n")
        
        # Check nodes table
        cursor = conn.execute("SELECT COUNT(*) FROM nodes")
        node_count = cursor.fetchone()[0]
        print(f"Total nodes: {node_count}")
        
        if node_count > 0:
            cursor = conn.execute("""
                SELECT node_id, agent_id, last_seen, battery_level, 
                       position_lat, position_lon, rssi, snr, updated_at
                FROM nodes 
                ORDER BY updated_at DESC 
                LIMIT 10
            """)
            nodes = cursor.fetchall()
            
            print("\nRecent nodes:")
            print("Node ID          | Agent    | Last Seen           | Battery | Position              | RSSI | SNR  | Updated")
            print("-" * 120)
            
            for node in nodes:
                node_id = node[0][:15] if node[0] else "None"
                agent_id = node[1][:8] if node[1] else "None"
                last_seen = node[2][:19] if node[2] else "None"
                battery = node[3] if node[3] is not None else "None"
                position = f"{node[4]:.4f},{node[5]:.4f}" if node[4] and node[5] else "None"
                rssi = node[6] if node[6] is not None else "None"
                snr = node[7] if node[7] is not None else "None"
                updated = node[8][:19] if node[8] else "None"
                
                print(f"{node_id:16} | {agent_id:8} | {last_seen:19} | {battery:7} | {position:20} | {rssi:4} | {snr:4} | {updated}")
        
        # Check packet buffer
        cursor = conn.execute("SELECT COUNT(*) FROM packet_buffer")
        packet_count = cursor.fetchone()[0]
        print(f"\nTotal packets in buffer: {packet_count}")
        
        if packet_count > 0:
            cursor = conn.execute("""
                SELECT timestamp, server_status
                FROM packet_buffer 
                ORDER BY timestamp DESC 
                LIMIT 5
            """)
            packets = cursor.fetchall()
            
            print("\nRecent packets:")
            for i, packet in enumerate(packets):
                print(f"{i+1}. {packet[0]} - Server status: {packet[1]}")
        
        # Check recent nodes with GPS
        cursor = conn.execute("""
            SELECT node_id, position_lat, position_lon, updated_at
            FROM nodes 
            WHERE position_lat IS NOT NULL AND position_lon IS NOT NULL
            ORDER BY updated_at DESC 
            LIMIT 5
        """)
        gps_nodes = cursor.fetchall()
        
        print(f"\nNodes with GPS data: {len(gps_nodes)}")
        if gps_nodes:
            for node in gps_nodes:
                print(f"  {node[0]}: {node[1]:.6f}, {node[2]:.6f} (updated: {node[3]})")
        
        conn.close()
        
    except Exception as e:
        print(f"Error inspecting database: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 inspect_db.py <database_path>")
        print("Example: python3 inspect_db.py agent_001_buffer.db")
        sys.exit(1)
    
    db_path = sys.argv[1]
    inspect_database(db_path)