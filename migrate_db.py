#!/usr/bin/env python3
"""
Database migration script to add new columns to user_info table
"""

import sqlite3
import os

def migrate_database():
    db_path = 'meshymcmapface.db'
    
    if not os.path.exists(db_path):
        print(f"Database {db_path} does not exist")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check current schema
    cursor.execute("PRAGMA table_info(user_info)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Current user_info columns: {columns}")
    
    # Add new columns if they don't exist
    new_columns = [
        ('hw_model', 'TEXT'),
        ('role', 'TEXT'),
        ('voltage', 'REAL'),
        ('channel_utilization', 'REAL'),
        ('air_util_tx', 'REAL'),
        ('uptime_seconds', 'INTEGER'),
        ('hops_away', 'INTEGER'),
        ('last_heard', 'INTEGER'),
        ('is_favorite', 'BOOLEAN DEFAULT 0'),
        ('is_licensed', 'BOOLEAN DEFAULT 0'),
        ('data_source', 'TEXT DEFAULT "packet"')
    ]
    
    for col_name, col_type in new_columns:
        if col_name not in columns:
            try:
                cursor.execute(f"ALTER TABLE user_info ADD COLUMN {col_name} {col_type}")
                print(f"Added column: {col_name}")
            except sqlite3.Error as e:
                print(f"Error adding column {col_name}: {e}")
    
    # Update battery_level column in user_info if it doesn't exist
    if 'battery_level' not in columns:
        try:
            cursor.execute("ALTER TABLE user_info ADD COLUMN battery_level INTEGER")
            print("Added column: battery_level")
        except sqlite3.Error as e:
            print(f"Error adding battery_level column: {e}")
    
    conn.commit()
    conn.close()
    print("Database migration completed")

if __name__ == "__main__":
    migrate_database()