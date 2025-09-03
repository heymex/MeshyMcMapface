"""
Centralized logging configuration for MeshyMcMapface
"""
import logging
import logging.handlers
import socket
import sys
from pathlib import Path
from typing import Optional, List, Dict


def setup_logging(
    level: str = 'INFO',
    log_file: Optional[str] = None,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    format_string: Optional[str] = None,
    syslog_configs: Optional[List[Dict]] = None
) -> logging.Logger:
    """
    Set up centralized logging configuration
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        max_file_size: Maximum size of log file before rotation
        backup_count: Number of backup files to keep
        format_string: Custom format string
        syslog_configs: List of syslog configurations
                       Each config: {'host': str, 'port': int, 'protocol': 'tcp'|'udp', 'facility': str}
    
    Returns:
        Configured logger
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {level}')
    
    # Default format
    if format_string is None:
        format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Create formatter
    formatter = logging.Formatter(format_string)
    
    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(numeric_level)
    
    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_file_size,
            backupCount=backup_count
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Syslog handlers (optional)
    if syslog_configs:
        for syslog_config in syslog_configs:
            try:
                syslog_handler = create_syslog_handler(syslog_config, numeric_level, formatter)
                if syslog_handler:
                    logger.addHandler(syslog_handler)
            except Exception as e:
                print(f"Warning: Failed to create syslog handler for {syslog_config}: {e}", file=sys.stderr)
    
    return logger


def create_syslog_handler(syslog_config: Dict, level: int, formatter: logging.Formatter) -> Optional[logging.Handler]:
    """
    Create a syslog handler with the specified configuration
    
    Args:
        syslog_config: Dictionary with 'host', 'port', 'protocol', 'facility'
        level: Logging level
        formatter: Log formatter
        
    Returns:
        Configured syslog handler or None if creation failed
    """
    try:
        host = syslog_config.get('host', 'localhost')
        port = int(syslog_config.get('port', 514))
        protocol = syslog_config.get('protocol', 'udp').lower()
        facility = syslog_config.get('facility', 'local0')
        
        # Map facility string to SysLogHandler facility constant
        facility_map = {
            'kern': logging.handlers.SysLogHandler.LOG_KERN,
            'user': logging.handlers.SysLogHandler.LOG_USER,
            'mail': logging.handlers.SysLogHandler.LOG_MAIL,
            'daemon': logging.handlers.SysLogHandler.LOG_DAEMON,
            'auth': logging.handlers.SysLogHandler.LOG_AUTH,
            'syslog': logging.handlers.SysLogHandler.LOG_SYSLOG,
            'lpr': logging.handlers.SysLogHandler.LOG_LPR,
            'news': logging.handlers.SysLogHandler.LOG_NEWS,
            'uucp': logging.handlers.SysLogHandler.LOG_UUCP,
            'cron': logging.handlers.SysLogHandler.LOG_CRON,
            'authpriv': logging.handlers.SysLogHandler.LOG_AUTHPRIV,
            'ftp': logging.handlers.SysLogHandler.LOG_FTP,
            'local0': logging.handlers.SysLogHandler.LOG_LOCAL0,
            'local1': logging.handlers.SysLogHandler.LOG_LOCAL1,
            'local2': logging.handlers.SysLogHandler.LOG_LOCAL2,
            'local3': logging.handlers.SysLogHandler.LOG_LOCAL3,
            'local4': logging.handlers.SysLogHandler.LOG_LOCAL4,
            'local5': logging.handlers.SysLogHandler.LOG_LOCAL5,
            'local6': logging.handlers.SysLogHandler.LOG_LOCAL6,
            'local7': logging.handlers.SysLogHandler.LOG_LOCAL7,
        }
        
        facility_code = facility_map.get(facility.lower(), logging.handlers.SysLogHandler.LOG_LOCAL0)
        
        # Create socket type based on protocol
        if protocol == 'tcp':
            socktype = socket.SOCK_STREAM
        elif protocol == 'udp':
            socktype = socket.SOCK_DGRAM
        else:
            raise ValueError(f"Invalid syslog protocol: {protocol}. Must be 'tcp' or 'udp'")
        
        # Create syslog handler
        syslog_handler = logging.handlers.SysLogHandler(
            address=(host, port),
            facility=facility_code,
            socktype=socktype
        )
        
        syslog_handler.setLevel(level)
        syslog_handler.setFormatter(formatter)
        
        return syslog_handler
        
    except Exception as e:
        print(f"Error creating syslog handler: {e}", file=sys.stderr)
        return None


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name"""
    return logging.getLogger(name)


class LoggerMixin:
    """Mixin class to add logging capability to other classes"""
    
    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class"""
        return logging.getLogger(self.__class__.__module__ + '.' + self.__class__.__name__)


def log_exceptions(logger: Optional[logging.Logger] = None):
    """Decorator to log exceptions from functions"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if logger:
                    logger.exception(f"Exception in {func.__name__}: {e}")
                else:
                    logging.exception(f"Exception in {func.__name__}: {e}")
                raise
        return wrapper
    return decorator