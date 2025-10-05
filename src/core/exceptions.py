"""
Custom exceptions for MeshyMcMapface
"""


class MeshyMcMapfaceError(Exception):
    """Base exception for MeshyMcMapface application"""
    pass


class ConfigurationError(MeshyMcMapfaceError):
    """Raised when there's a configuration issue"""
    pass


class MeshtasticConnectionError(MeshyMcMapfaceError):
    """Raised when unable to connect to Meshtastic device"""
    pass


class ServerConnectionError(MeshyMcMapfaceError):
    """Raised when unable to connect to a server"""
    pass


class DatabaseError(MeshyMcMapfaceError):
    """Raised when there's a database operation issue"""
    pass


class PacketProcessingError(MeshyMcMapfaceError):
    """Raised when there's an error processing a packet"""
    pass


class NodeTrackingError(MeshyMcMapfaceError):
    """Raised when there's an error tracking node status"""
    pass