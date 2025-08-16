#!/usr/bin/env python3
"""
Export rich node data from local database to JSON file for import on remote servers
"""

import sqlite3
import json
import sys
from datetime import datetime

def export_nodedb():
    db_path = 'meshymcmapface.db'
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Export user_info table data
        cursor.execute("""
            SELECT node_id, short_name, long_name, macaddr, hw_model, role,
                   voltage, channel_utilization, air_util_tx, uptime_seconds,
                   hops_away, last_heard, is_favorite, is_licensed, 
                   data_source, battery_level
            FROM user_info 
            WHERE hw_model IS NOT NULL OR short_name IS NOT NULL OR hops_away IS NOT NULL
        """)
        
        nodes = cursor.fetchall()
        
        node_data = []
        for node in nodes:
            node_dict = {
                'node_id': node[0],
                'short_name': node[1],
                'long_name': node[2], 
                'macaddr': node[3],
                'hw_model': node[4],
                'role': node[5],
                'voltage': node[6],
                'channel_utilization': node[7],
                'air_util_tx': node[8],
                'uptime_seconds': node[9],
                'hops_away': node[10],
                'last_heard': node[11],
                'is_favorite': node[12],
                'is_licensed': node[13],
                'data_source': node[14],
                'battery_level': node[15]
            }
            node_data.append(node_dict)
        
        conn.close()
        
        export_data = {
            'exported_at': datetime.now().isoformat(),
            'total_nodes': len(node_data),
            'nodes': node_data
        }
        
        filename = f'nodedb_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        print(f"Exported {len(node_data)} nodes to {filename}")
        return filename
        
    except Exception as e:
        print(f"Error exporting nodedb: {e}")
        return None

if __name__ == "__main__":
    export_nodedb()