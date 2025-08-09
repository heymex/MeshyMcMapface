#!/usr/bin/env python3
"""
Script to reset and verify the multi-server agent database
"""

import sqlite3
import os
import sys

def reset_database(agent_id="agent_001"):
    db_path = f"{agent_id}_buffer.db"
    
    # Remove old database if it exists
    if os.path.exists(db_path):
        print(f"Removing old database: {db_path}")
        os.remove(db_path)
    
    # Create new database with correct schema
    print(f"Creating new database: {db_path}")
    conn = sqlite3.connect(db_path)
    
    # Create tables with correct schema
    conn.execute('''
        CREATE TABLE IF NOT EXISTS packet_buffer (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            packet_data TEXT,
            server_status TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT,
            agent_id TEXT,
            last_seen TEXT,
            battery_level INTEGER,
            position_lat REAL,
            position_lon REAL,
            rssi INTEGER,
            snr REAL,
            updated_at TEXT,
            PRIMARY KEY (node_id, agent_id)
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS server_health (
            server_name TEXT PRIMARY KEY,
            last_success TEXT,
            last_failure TEXT,
            consecutive_failures INTEGER DEFAULT 0,
            total_packets_sent INTEGER DEFAULT 0,
            is_healthy BOOLEAN DEFAULT 1
        )
    ''')
    
    conn.commit()
    
    # Verify tables were created
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Created tables:")
    for table in tables:
        print(f"  - {table[0]}")
    
    # Verify nodes table schema
    cursor = conn.execute("PRAGMA table_info(nodes);")
    columns = cursor.fetchall()
    print("\nNodes table schema:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
    
    conn.close()
    print(f"\nDatabase {db_path} reset successfully!")

if __name__ == "__main__":
    agent_id = sys.argv[1] if len(sys.argv) > 1 else "agent_001"
    reset_database(agent_id)