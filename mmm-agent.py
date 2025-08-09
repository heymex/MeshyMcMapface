async def send_data_to_server(self, server: ServerConfig):
        """Send buffered data to a specific server"""
        try:
            # Get unsent packets for this server
            conn = self.get_db_connection()
            cursor = conn.execute('''
                SELECT id, packet_data, server_status FROM packet_buffer 
                WHERE created_at > datetime('now', '-1 hour')
                ORDER BY timestamp 
                LIMIT 100
            ''')
            packets = cursor.fetchall()
            
            if not packets:
                conn.close()
                return
            
            # Filter packets that need to be sent to this server
            packets_to_send = []
            packet_ids_to_update = []
            
            for packet_row in packets:
                packet_id, packet_data_str, server_status_str = packet_row
                server_status = json.loads(server_status_str)
                
                if (server.name in server_status and 
                    not server_status[server.name]['sent'] and
                    server_status[server.name]['retry_count'] < server.max_retries):
                    
                    packets_to_send.append(json.loads(packet_data_str))
                    packet_ids_to_update.append(packet_id)
            
            if not packets_to_send:
                conn.close()
                return
            
            # Get current node status - FIXED: Query the correct table with correct structure
            cursor = conn.execute('''
                SELECT node_id, last_seen, battery_level, position_lat, position_lon, rssi, snr
                FROM nodes 
                WHERE agent_id = ? AND datetime(updated_at) > datetime('now', '-24 hours')
            ''', (self.agent_id,))
            nodes = cursor.fetchall()
            conn.close()
            
            # Prepare payload
            payload = {
                'agent_id': self.agent_id,
                'location': {
                    'name': self.location_name,
                    'coordinates': [self.location_lat, self.location_lon]
                },
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'packets': packets_to_send,
                'node_status': [
                    {
                        'node_id': n[0],           # node_id
                        'last_seen': n[1],         # last_seen
                        'battery_level': n[2],     # battery_level
                        'position': [n[3], n[4]] if n[3] and n[4] else None,  # position_lat, position_lon
                        'rssi': n[5],              # rssi
                        'snr': n[6]                # snr
                    } for n in nodes
                ]
            }
            
            # Send to server
            headers = {
                'Content-Type': 'application/json',
                'X-API-Key': server.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{server.url}/api/agent/data",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=server.timeout)
                ) as response:
                    if response.status == 200:
                        # Mark packets as sent for this server
                        self.mark_packets_sent(packet_ids_to_update, server.name)
                        self.update_server_health(server.name, success=True)
                        
                        self.logger.info(f"Successfully sent {len(packets_to_send)} packets to {server.name}")
                    else:
                        self.logger.error(f"Server {server.name} returned status {response.status}")
                        self.update_server_health(server.name, success=False)
                        
        except Exception as e:
            self.logger.error(f"Error sending data to {server.name}: {e}")
            self.update_server_health(server.name, success=False)