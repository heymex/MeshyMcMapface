"""
Centralized logging configuration for MeshyMcMapface
"""
import json
import logging
import logging.handlers
import socket
import ssl
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict


def setup_logging(
    level: str = 'INFO',
    log_file: Optional[str] = None,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    format_string: Optional[str] = None,
    json_tcp_configs: Optional[List[Dict]] = None
) -> logging.Logger:
    """
    Set up centralized logging configuration
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        max_file_size: Maximum size of log file before rotation
        backup_count: Number of backup files to keep
        format_string: Custom format string
        json_tcp_configs: List of JSON TCP logging configurations
                         Each config: {'host': str, 'port': int, 'application': str, 'environment': str}
    
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
    
    # JSON TCP handlers (optional)
    if json_tcp_configs:
        for json_tcp_config in json_tcp_configs:
            try:
                json_tcp_handler = create_json_tcp_handler(json_tcp_config, numeric_level)
                if json_tcp_handler:
                    logger.addHandler(json_tcp_handler)
            except Exception as e:
                print(f"Warning: Failed to create JSON TCP handler for {json_tcp_config}: {e}", file=sys.stderr)
    
    return logger


class JsonTcpHandler(logging.Handler):
    """
    Custom logging handler that sends structured JSON logs over TCP
    """
    
    def __init__(self, host: str, port: int, application: str = "meshymcmapface", environment: str = "production", auth_token: Optional[str] = None, use_tls: bool = False, verify_ssl: bool = True):
        super().__init__()
        self.host = host
        self.port = port
        self.application = application
        self.environment = environment
        self.auth_token = auth_token
        self.use_tls = use_tls
        self.verify_ssl = verify_ssl
        self.socket = None
        self.authenticated = False
        
    def emit(self, record: logging.LogRecord):
        """
        Emit a log record as JSON over TCP
        """
        try:
            # Create JSON log entry
            log_entry = {
                "timestamp": time.time(),
                "iso_timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "application": self.application,
                "environment": self.environment,
                "host": socket.gethostname(),
                "thread": record.thread,
                "thread_name": record.threadName,
                "process": record.process,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno
            }
            
            # Add exception info if present
            if record.exc_info:
                log_entry["exception"] = self.format(record)
            
            # Convert to JSON string with newline delimiter
            json_message = json.dumps(log_entry, default=str) + '\n'
            
            # Send over TCP
            self._send_message(json_message.encode('utf-8'))
            
        except Exception as e:
            # Don't let logging errors crash the application
            print(f"Error in JsonTcpHandler.emit: {e}", file=sys.stderr)
    
    def _send_message(self, message: bytes):
        """
        Send message over TCP with connection retry logic and authentication
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Create new socket if needed
                if self.socket is None:
                    raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    raw_socket.settimeout(5.0)  # 5 second timeout
                    
                    # Wrap with TLS if requested
                    if self.use_tls:
                        context = ssl.create_default_context()
                        if not self.verify_ssl:
                            context.check_hostname = False
                            context.verify_mode = ssl.CERT_NONE
                        self.socket = context.wrap_socket(raw_socket, server_hostname=self.host)
                    else:
                        self.socket = raw_socket
                    
                    self.socket.connect((self.host, self.port))
                    self.authenticated = False  # Reset authentication status on new connection
                
                # Send authentication token if required and not yet authenticated
                if self.auth_token and not self.authenticated:
                    auth_message = json.dumps({"auth_token": self.auth_token}) + '\n'
                    self.socket.sendall(auth_message.encode('utf-8'))
                    self.authenticated = True
                
                # Send the actual log message
                self.socket.sendall(message)
                return  # Success
                
            except (socket.error, ConnectionError, OSError) as e:
                # Close the socket and retry
                self._close_socket()
                retry_count += 1
                
                if retry_count >= max_retries:
                    print(f"Failed to send log message after {max_retries} retries: {e}", file=sys.stderr)
                else:
                    time.sleep(0.1 * retry_count)  # Brief backoff
    
    def _close_socket(self):
        """
        Close the socket connection
        """
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            finally:
                self.socket = None
                self.authenticated = False
    
    def close(self):
        """
        Close the handler and socket
        """
        self._close_socket()
        super().close()


def create_json_tcp_handler(config: Dict, level: int) -> Optional[JsonTcpHandler]:
    """
    Create a JSON TCP handler with the specified configuration
    
    Args:
        config: Dictionary with 'host', 'port', 'application', 'environment', 'auth_token', 'use_tls', 'verify_ssl'
        level: Logging level
        
    Returns:
        Configured JSON TCP handler or None if creation failed
    """
    try:
        host = config.get('host', 'localhost')
        port = int(config.get('port', 5140))
        application = config.get('application', 'meshymcmapface')
        environment = config.get('environment', 'production')
        auth_token = config.get('auth_token')
        use_tls = config.get('use_tls', False)
        verify_ssl = config.get('verify_ssl', True)
        
        # Convert string representations to boolean
        if isinstance(use_tls, str):
            use_tls = use_tls.lower() in ('true', '1', 'yes', 'on')
        if isinstance(verify_ssl, str):
            verify_ssl = verify_ssl.lower() in ('true', '1', 'yes', 'on')
        
        handler = JsonTcpHandler(host, port, application, environment, auth_token, use_tls, verify_ssl)
        handler.setLevel(level)
        
        return handler
        
    except Exception as e:
        print(f"Error creating JSON TCP handler: {e}", file=sys.stderr)
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