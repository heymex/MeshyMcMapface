"""
Utility helper functions for MeshyMcMapface
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def safe_json_loads(data: str, default: Optional[Dict] = None) -> Dict:
    """Safely load JSON data with fallback"""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError) as e:
        logging.warning(f"Failed to parse JSON data: {e}")
        return default or {}


def safe_json_dumps(data: Any, default: Optional[str] = None) -> str:
    """Safely dump data to JSON with fallback"""
    try:
        return json.dumps(data, default=str)
    except (TypeError, ValueError) as e:
        logging.warning(f"Failed to serialize data to JSON: {e}")
        return default or "{}"


def get_current_timestamp() -> str:
    """Get current UTC timestamp in ISO format"""
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse ISO format timestamp string"""
    try:
        # Handle Z suffix (replace with +00:00)
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        logging.warning(f"Failed to parse timestamp: {timestamp_str}")
        return None


def is_valid_node_id(node_id: str) -> bool:
    """Check if node ID is valid (not system/broadcast IDs)"""
    if not node_id or not isinstance(node_id, str):
        return False
    
    # Skip system node IDs
    invalid_ids = ['^all', '^local', 'null', '', 'unknown']
    return node_id not in invalid_ids


def is_valid_position(lat: Any, lon: Any) -> bool:
    """Check if latitude/longitude values are valid"""
    try:
        lat_f = float(lat) if lat is not None else 0
        lon_f = float(lon) if lon is not None else 0
        
        # Check for valid ranges and non-zero values
        return (
            -90 <= lat_f <= 90 and 
            -180 <= lon_f <= 180 and 
            (lat_f != 0 or lon_f != 0)  # At least one should be non-zero
        )
    except (ValueError, TypeError):
        return False


def format_position(lat: float, lon: float, precision: int = 6) -> str:
    """Format position as a string"""
    return f"{lat:.{precision}f}, {lon:.{precision}f}"


def sanitize_string(value: Any, max_length: int = 255, fallback: str = '') -> str:
    """Sanitize string value"""
    if value is None:
        return fallback
    
    try:
        str_value = str(value).strip()
        return str_value[:max_length] if str_value else fallback
    except Exception:
        return fallback


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to integer"""
    try:
        return int(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float"""
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def chunk_list(data_list: list, chunk_size: int) -> list:
    """Split a list into chunks of specified size"""
    return [data_list[i:i + chunk_size] for i in range(0, len(data_list), chunk_size)]


def merge_dicts(dict1: Dict, dict2: Dict, deep: bool = False) -> Dict:
    """Merge two dictionaries"""
    if not deep:
        return {**dict1, **dict2}
    
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value, deep=True)
        else:
            result[key] = value
    
    return result


def filter_dict_keys(data: Dict, allowed_keys: set) -> Dict:
    """Filter dictionary to only include allowed keys"""
    return {k: v for k, v in data.items() if k in allowed_keys}


def get_nested_value(data: Dict, key_path: str, separator: str = '.', default: Any = None) -> Any:
    """Get nested dictionary value using dot notation"""
    keys = key_path.split(separator)
    current = data
    
    try:
        for key in keys:
            current = current[key]
        return current
    except (KeyError, TypeError, AttributeError):
        return default


def set_nested_value(data: Dict, key_path: str, value: Any, separator: str = '.') -> Dict:
    """Set nested dictionary value using dot notation"""
    keys = key_path.split(separator)
    current = data
    
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    current[keys[-1]] = value
    return data


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers using Haversine formula"""
    import math
    
    # Convert latitude and longitude from degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = (math.sin(dlat / 2) ** 2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(math.sqrt(a))
    
    # Earth's radius in kilometers
    earth_radius = 6371.0
    
    return earth_radius * c


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


def format_duration(seconds: float) -> str:
    """Format duration in human readable format"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"