"""
Server communication client
"""
import aiohttp
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..core.config import ServerConfig, AgentConfig
from ..core.exceptions import ServerConnectionError


class ServerClient:
    """Client for communicating with a single server"""
    
    def __init__(self, server_config: ServerConfig):
        self.config = server_config
        self.logger = logging.getLogger(__name__)
    
    async def register_agent(self, agent_config: AgentConfig) -> bool:
        """Register this agent with the server"""
        try:
            payload = {
                'agent_id': agent_config.id,
                'location': {
                    'name': agent_config.location_name,
                    'coordinates': [agent_config.location_lat, agent_config.location_lon]
                }
            }
            
            headers = {
                'Content-Type': 'application/json',
                'X-API-Key': self.config.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.url}/api/agent/register",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.logger.info(f"Successfully registered with {self.config.name}: {result.get('agent_id')}")
                        return True
                    else:
                        self.logger.error(f"Failed to register with {self.config.name}: {response.status}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"Error registering with {self.config.name}: {e}")
            raise ServerConnectionError(f"Registration failed for {self.config.name}: {e}")
    
    async def send_data(self, agent_config: AgentConfig, packets: List[Dict], node_status: List[Dict]) -> bool:
        """Send packet and node data to the server"""
        try:
            payload = {
                'agent_id': agent_config.id,
                'location': {
                    'name': agent_config.location_name,
                    'coordinates': [agent_config.location_lat, agent_config.location_lon]
                },
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'packets': packets,
                'node_status': node_status
            }
            
            headers = {
                'Content-Type': 'application/json',
                'X-API-Key': self.config.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.url}/api/agent/data",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as response:
                    if response.status == 200:
                        self.logger.info(f"Successfully sent {len(packets)} packets and {len(node_status)} nodes to {self.config.name}")
                        return True
                    else:
                        response_text = await response.text()
                        self.logger.error(f"Server {self.config.name} returned status {response.status}: {response_text}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"Error sending data to {self.config.name}: {e}")
            raise ServerConnectionError(f"Data send failed for {self.config.name}: {e}")
    
    async def send_nodedb_data(self, agent_config: AgentConfig, nodes_data: Dict) -> bool:
        """Send extended node database information to the server"""
        try:
            if not nodes_data:
                return True  # No data to send is success
            
            payload = {
                'agent_id': agent_config.id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'nodes': nodes_data
            }
            
            headers = {
                'Content-Type': 'application/json',
                'X-API-Key': self.config.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.config.url}/api/agent/nodedb",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as response:
                    if response.status == 200:
                        self.logger.info(f"Successfully sent nodedb data for {len(nodes_data)} nodes to {self.config.name}")
                        return True
                    else:
                        response_text = await response.text()
                        self.logger.error(f"Server {self.config.name} returned status {response.status} for nodedb: {response_text}")
                        return False
                        
        except Exception as e:
            self.logger.error(f"Error sending nodedb data to {self.config.name}: {e}")
            raise ServerConnectionError(f"Nodedb send failed for {self.config.name}: {e}")
    
    async def health_check(self) -> bool:
        """Perform a health check against the server"""
        try:
            headers = {
                'X-API-Key': self.config.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.config.url}/api/health",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                ) as response:
                    return response.status == 200
                    
        except Exception as e:
            self.logger.debug(f"Health check failed for {self.config.name}: {e}")
            return False


class MultiServerClient:
    """Manages communication with multiple servers"""
    
    def __init__(self, server_configs: Dict[str, ServerConfig]):
        self.servers = {name: ServerClient(config) for name, config in server_configs.items()}
        self.logger = logging.getLogger(__name__)
    
    async def register_all(self, agent_config: AgentConfig) -> Dict[str, bool]:
        """Register with all enabled servers"""
        results = {}
        
        # Create tasks for all enabled servers
        tasks = []
        server_names = []
        
        for name, server_client in self.servers.items():
            if server_client.config.enabled:
                task = server_client.register_agent(agent_config)
                tasks.append(task)
                server_names.append(name)
        
        # Execute all registrations in parallel
        if tasks:
            registration_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(registration_results):
                server_name = server_names[i]
                if isinstance(result, Exception):
                    self.logger.error(f"Registration failed for {server_name}: {result}")
                    results[server_name] = False
                else:
                    results[server_name] = result
        
        return results
    
    async def send_to_server(self, server_name: str, agent_config: AgentConfig, packets: List[Dict], node_status: List[Dict]) -> bool:
        """Send data to a specific server"""
        if server_name not in self.servers:
            self.logger.error(f"Server {server_name} not configured")
            return False
        
        server_client = self.servers[server_name]
        
        if not server_client.config.enabled:
            self.logger.debug(f"Server {server_name} is disabled, skipping")
            return True  # Return True to avoid marking as failure
        
        try:
            return await server_client.send_data(agent_config, packets, node_status)
        except Exception as e:
            self.logger.error(f"Failed to send to {server_name}: {e}")
            return False
    
    async def send_nodedb_to_server(self, server_name: str, agent_config: AgentConfig, nodes_data: Dict) -> bool:
        """Send extended node data to a specific server"""
        if server_name not in self.servers:
            self.logger.error(f"Server {server_name} not configured")
            return False
        
        server_client = self.servers[server_name]
        
        if not server_client.config.enabled:
            self.logger.debug(f"Server {server_name} is disabled, skipping")
            return True  # Return True to avoid marking as failure
        
        try:
            return await server_client.send_nodedb_data(agent_config, nodes_data)
        except Exception as e:
            self.logger.error(f"Failed to send nodedb to {server_name}: {e}")
            return False
    
    async def send_nodedb_to_all(self, agent_config: AgentConfig, nodes_data: Dict) -> Dict[str, bool]:
        """Send nodedb data to all enabled servers"""
        results = {}
        
        if not nodes_data:
            # No data to send, return success for all enabled servers
            for name, server_client in self.servers.items():
                if server_client.config.enabled:
                    results[name] = True
            return results
        
        # Create tasks for all enabled servers
        tasks = []
        server_names = []
        
        for name, server_client in self.servers.items():
            if server_client.config.enabled:
                task = server_client.send_nodedb_data(agent_config, nodes_data)
                tasks.append(task)
                server_names.append(name)
        
        # Execute all sends in parallel
        if tasks:
            send_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(send_results):
                server_name = server_names[i]
                if isinstance(result, Exception):
                    self.logger.error(f"Nodedb send failed for {server_name}: {result}")
                    results[server_name] = False
                else:
                    results[server_name] = result
        
        return results
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Perform health checks on all enabled servers"""
        results = {}
        
        # Create tasks for all enabled servers
        tasks = []
        server_names = []
        
        for name, server_client in self.servers.items():
            if server_client.config.enabled:
                task = server_client.health_check()
                tasks.append(task)
                server_names.append(name)
        
        # Execute all health checks in parallel
        if tasks:
            health_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(health_results):
                server_name = server_names[i]
                if isinstance(result, Exception):
                    self.logger.debug(f"Health check failed for {server_name}: {result}")
                    results[server_name] = False
                else:
                    results[server_name] = result
        
        return results
    
    def get_server_client(self, server_name: str) -> Optional[ServerClient]:
        """Get a specific server client"""
        return self.servers.get(server_name)
    
    def get_enabled_servers(self) -> Dict[str, ServerClient]:
        """Get all enabled server clients"""
        return {name: client for name, client in self.servers.items() if client.config.enabled}
    
    def update_server_config(self, server_name: str, config: ServerConfig):
        """Update configuration for a specific server"""
        self.servers[server_name] = ServerClient(config)
        self.logger.info(f"Updated configuration for server {server_name}")
    
    def add_server(self, server_name: str, config: ServerConfig):
        """Add a new server"""
        self.servers[server_name] = ServerClient(config)
        self.logger.info(f"Added new server: {server_name}")
    
    def remove_server(self, server_name: str):
        """Remove a server"""
        if server_name in self.servers:
            del self.servers[server_name]
            self.logger.info(f"Removed server: {server_name}")