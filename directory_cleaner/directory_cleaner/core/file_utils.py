"""
Core functionality for file and directory operations.

This module provides utility functions for working with files and directories,
including size calculations, path normalization, and format conversions.
"""

import os
import re
from pathlib import Path

try:
    import send2trash
    TRASH_SUPPORTED = True
except ImportError:
    TRASH_SUPPORTED = False


def normalize_path(path):
    """Normalize path for cross-platform compatibility."""
    if not path:
        return path
        
    # Convert to absolute path with proper separators for the current OS
    normalized = os.path.abspath(os.path.normpath(path))
    
    # Strip any Windows long path prefix that might have been added
    if normalized.startswith('\\\\?\\'):
        normalized = normalized[4:]
    
    # Handle mixed slashes by converting to Path and back to string
    normalized = str(Path(normalized))
    
    return normalized


def get_dir_size(path):
    """Calculate the total size of a directory in bytes."""
    path = normalize_path(path)
    
    # Check if path exists before proceeding
    if not os.path.exists(path) or not os.path.isdir(path):
        return 0
        
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp) and not os.path.islink(fp):  # Check to avoid broken symlinks
                    try:
                        total_size += os.path.getsize(fp)
                    except (OSError, FileNotFoundError):
                        pass  # Skip files that can't be accessed
    except (PermissionError, OSError) as e:
        print(f"Warning: Couldn't access all files in {path}: {e}")
    
    return total_size


def format_size(bytes_value):
    """Convert bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024
    return f"{bytes_value:.2f} PB"


def parse_size(size_str):
    """Convert string like '10MB' to bytes."""
    if not size_str:
        return 0
        
    size_str = size_str.upper()
    units = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
    
    match = re.match(r'^(\d+\.?\d*)([A-Z]+)$', size_str)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}. Use format like '10MB'")
        
    size, unit = match.groups()
    if unit not in units:
        raise ValueError(f"Unknown unit: {unit}. Use one of {', '.join(units.keys())}")
        
    return float(size) * units[unit]