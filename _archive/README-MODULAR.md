# MeshyMcMapface - Modular Architecture

This document describes the new modular architecture implemented to make the codebase more maintainable and extensible.

## New Structure

```
src/
├── core/                   # Core system components
│   ├── config.py          # Configuration management
│   ├── database.py        # Database abstraction layer
│   └── exceptions.py      # Custom exceptions
├── meshtastic/            # Meshtastic integration
│   ├── connections.py     # Connection handling
│   ├── packet_parser.py   # Packet processing handlers
│   └── node_tracker.py    # Node status tracking
├── servers/               # Server communication
│   ├── client.py          # Server communication client
│   ├── health.py          # Health monitoring
│   └── queue_manager.py   # Multi-server queuing
├── agents/                # Agent implementations
│   ├── base_agent.py      # Base agent class
│   └── multi_server_agent.py  # Multi-server agent
└── utils/                 # Utility functions
    ├── logging.py         # Centralized logging
    └── helpers.py         # Utility functions
```

## Key Benefits

### 1. Modular Design
- Each component has a single responsibility
- Easy to test individual components
- Clear separation of concerns

### 2. Plugin Architecture
- Packet handlers can be added/removed easily
- Server types can be extended
- Agent types can be added without modifying existing code

### 3. Better Error Handling
- Custom exceptions for different error types
- Centralized error handling patterns
- More informative error messages

### 4. Configuration Management
- Centralized configuration loading
- Validation of configuration
- Type-safe configuration objects

### 5. Database Abstraction
- Repository pattern for data access
- Easy to switch database backends
- Proper connection management

## Usage

### Running the Modular Agent

```bash
# Create configuration
python3 mmm-agent-modular.py --create-config

# Run with default settings
python3 mmm-agent-modular.py

# Run with custom config and logging
python3 mmm-agent-modular.py --config my-config.ini --log-level DEBUG --log-file agent.log
```

### Adding New Features

#### Adding a New Packet Handler

```python
# In src/meshtastic/packet_parser.py
class MyCustomHandler(PacketHandler):
    def can_handle(self, packet: Dict) -> bool:
        return 'my_custom_data' in packet.get('decoded', {})
    
    def process(self, packet: Dict) -> Dict:
        packet_data = self._create_base_packet_data(packet)
        packet_data['type'] = 'my_custom_type'
        packet_data['payload'] = packet['decoded']['my_custom_data']
        return packet_data

# Add to processor
processor = PacketProcessor()
processor.add_handler(MyCustomHandler())
```

#### Adding a New Server Type

```python
# In src/servers/client.py
class MyCustomServerClient(ServerClient):
    async def send_data(self, agent_config, packets, node_status):
        # Custom implementation for your server protocol
        pass
```

#### Adding a New Agent Type

```python
# In src/agents/my_agent.py
class MyCustomAgent(BaseAgent):
    def _handle_processed_packet(self, packet_data: Dict):
        # Custom packet handling
        pass
    
    async def run(self):
        # Custom main loop
        pass

# Register in AgentFactory
```

## Migration from Original

The original `mmm-agent.py` is preserved. The new modular version provides the same functionality with better architecture.

### Key Differences

1. **Imports**: Uses relative imports within the `src/` package
2. **Configuration**: More structured configuration management
3. **Database**: Repository pattern instead of direct SQL
4. **Error Handling**: Custom exceptions and better error reporting
5. **Logging**: Centralized logging configuration
6. **Testing**: Each component can be tested independently

### Backwards Compatibility

- Configuration files are compatible
- Database schema is the same
- API behavior is preserved

## Future Enhancements Made Easy

With the new modular structure, adding features becomes much easier:

1. **Web Dashboard**: Add `src/web/` module
2. **Metrics/Monitoring**: Add `src/metrics/` module  
3. **Alerting System**: Add `src/alerts/` module
4. **API Server**: Add `src/api/` module
5. **Plugin System**: Extend the handler architecture
6. **Multiple Protocols**: Add protocol-specific modules
7. **Cloud Integration**: Add cloud-specific clients
8. **Mobile App API**: Add mobile-specific endpoints

## Performance Considerations

The modular structure introduces minimal overhead:

- **Import time**: Slightly longer due to more modules
- **Memory usage**: Comparable to original
- **Runtime performance**: Same or better due to optimizations
- **Maintainability**: Significantly improved

## Development Workflow

1. **Feature Development**: Work on specific modules
2. **Testing**: Test modules independently  
3. **Integration**: Use dependency injection
4. **Deployment**: Same process as before
5. **Monitoring**: Better logging and error tracking

The modular architecture sets up the codebase to handle many more feature requests while maintaining code quality and developer productivity.