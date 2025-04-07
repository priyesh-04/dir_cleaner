"""
Configuration handling for Directory Cleaner.

This module provides functionality for parsing and managing configuration
files and cleaning presets.
"""

import os
import configparser

from directory_cleaner.directory_cleaner.core.file_utils import (
    normalize_path, parse_size
)


def parse_config(config_file):
    """Parse a configuration file for cleaning profiles.
    
    Args:
        config_file (str): Path to the configuration file
        
    Returns:
        dict: Dictionary of cleaning profiles with their settings
    """
    # Normalize the config file path
    config_file = normalize_path(config_file)
    
    if not os.path.exists(config_file):
        print(f"Config file not found: {config_file}")
        return None
    
    try:
        config = configparser.ConfigParser()
        config.read(config_file)
        
        profiles = {}
        for section in config.sections():
            profile = {}
            for key in config[section]:
                if key == 'patterns':
                    profile[key] = [p.strip() for p in config[section][key].split(',')]
                elif key == 'exclude':
                    profile[key] = [p.strip() for p in config[section][key].split(',')]
                elif key in ('older_than', 'min_size'):
                    try:
                        profile[key] = int(config[section][key])
                    except ValueError:
                        try:
                            profile[key] = parse_size(config[section][key])
                        except ValueError:
                            print(f"Warning: Invalid value for {key} in profile {section}")
                            continue
                elif key in ('dry_run', 'trash', 'interactive', 'parallel'):
                    profile[key] = config[section].getboolean(key)
                else:
                    profile[key] = config[section][key]
            
            profiles[section] = profile
    except Exception as e:
        print(f"Error parsing config file: {e}")
        return None
    
    return profiles


def run_preset(preset_name, directory, **kwargs):
    """Run a predefined preset cleaning operation.
    
    Args:
        preset_name (str): Name of the preset to run
        directory (str): Directory to clean
        **kwargs: Additional arguments for the cleaning operation
        
    Returns:
        tuple: (count, saved, deleted_items) representing number of items deleted,
               bytes saved, and details of deleted items
    """
    from directory_cleaner.directory_cleaner.core.dir_operations import delete_node_modules
    from directory_cleaner.directory_cleaner.core.analysis import delete_pattern_directories_multiple
    
    # Normalize the directory path
    directory = normalize_path(directory)
    
    # Check if directory exists
    if not os.path.exists(directory) or not os.path.isdir(directory):
        print(f"Directory does not exist: {directory}")
        return 0, 0, []
    
    presets = {
        "node-modules": {
            "func": delete_node_modules,
            "args": {"directory": directory}
        },
        "build-artifacts": {
            "func": delete_pattern_directories_multiple,
            "args": {
                "directory": directory, 
                "patterns": ["build", "dist", "target", "out", "bin", "obj"]
            }
        },
        "cache-dirs": {
            "func": delete_pattern_directories_multiple,
            "args": {
                "directory": directory,
                "patterns": [".cache", "__pycache__", ".gradle", ".npm", ".nuget"]
            }
        },
        "temp-files": {
            "func": delete_pattern_directories_multiple,
            "args": {
                "directory": directory,
                "patterns": ["tmp", "temp", "*tmp", "*bak"]
            }
        }
    }
    
    if preset_name not in presets:
        print(f"Unknown preset: {preset_name}")
        return 0, 0, []
    
    preset = presets[preset_name]
    args = preset["args"].copy()
    args.update(kwargs)
    
    return preset["func"](**args)