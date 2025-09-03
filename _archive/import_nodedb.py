#!/usr/bin/env python3
"""
Import rich node data from JSON export file to populate remote server database
"""

import sqlite3
import json
import sys
import os

def import_nodedb(json_file):
    db_path = 'meshymcmapface.db'
    
    if not os.path.exists(json_file):
        print(f"Export file {json_file} not found")
        return False
    
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found")
        return False
    
    try:
        # Load export data
        with open(json_file, 'r') as f:
            export_data = json.load(f)
        
        nodes = export_data['nodes']
        print(f"Importing {len(nodes)} nodes from {json_file}")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if user_info table has required columns
        cursor.execute("PRAGMA table_info(user_info)")
        columns = [row[1] for row in cursor.fetchall()]
        required_columns = ['node_id', 'short_name', 'long_name', 'hw_model', 'role', 'hops_away']
        
        missing_columns = [col for col in required_columns if col not in columns]
        if missing_columns:
            print(f"Missing columns in user_info table: {missing_columns}")
            print("Run migrate_db.py first!")
            conn.close()
            return False
        
        updated_count = 0
        inserted_count = 0
        
        for node in nodes:
            # Check if node exists
            cursor.execute("SELECT COUNT(*) FROM user_info WHERE node_id = ?", (node['node_id'],))
            exists = cursor.fetchone()[0] > 0
            
            if exists:
                # Update existing node
                cursor.execute("""
                    UPDATE user_info SET 
                        short_name = ?, long_name = ?, macaddr = ?, hw_model = ?, role = ?,
                        voltage = ?, channel_utilization = ?, air_util_tx = ?, uptime_seconds = ?,
                        hops_away = ?, last_heard = ?, is_favorite = ?, is_licensed = ?,
                        data_source = ?, battery_level = ?
                    WHERE node_id = ?
                """, (
                    node['short_name'], node['long_name'], node['macaddr'], 
                    node['hw_model'], node['role'], node['voltage'],
                    node['channel_utilization'], node['air_util_tx'], node['uptime_seconds'],
                    node['hops_away'], node['last_heard'], node['is_favorite'],
                    node['is_licensed'], node['data_source'], node['battery_level'],
                    node['node_id']
                ))
                updated_count += 1
            else:
                # Insert new node
                cursor.execute("""
                    INSERT INTO user_info (
                        node_id, short_name, long_name, macaddr, hw_model, role,
                        voltage, channel_utilization, air_util_tx, uptime_seconds,
                        hops_away, last_heard, is_favorite, is_licensed,
                        data_source, battery_level
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    node['node_id'], node['short_name'], node['long_name'], node['macaddr'],
                    node['hw_model'], node['role'], node['voltage'], node['channel_utilization'],
                    node['air_util_tx'], node['uptime_seconds'], node['hops_away'],
                    node['last_heard'], node['is_favorite'], node['is_licensed'],
                    node['data_source'], node['battery_level']
                ))
                inserted_count += 1
        
        conn.commit()
        conn.close()
        
        print(f"Import completed: {updated_count} nodes updated, {inserted_count} nodes inserted")
        return True
        
    except Exception as e:
        print(f"Error importing nodedb: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 import_nodedb.py <json_export_file>")
        sys.exit(1)
    
    json_file = sys.argv[1]
    success = import_nodedb(json_file)
    sys.exit(0 if success else 1)