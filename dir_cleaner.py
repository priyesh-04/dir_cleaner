import os
import shutil
import argparse
import fnmatch
import re
import time
import datetime
import concurrent.futures
import json
import configparser
from pathlib import Path
from tqdm import tqdm

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

def should_process(path, exclude_patterns, older_than, min_size):
    """Determine if a directory should be processed based on filters."""
    path = normalize_path(path)
    
    # Check if path exists first
    if not os.path.exists(path) or not os.path.isdir(path):
        return False
        
    # Check exclusion patterns
    if exclude_patterns:
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(path, pattern):
                return False
    
    # Check age if specified
    if older_than is not None:
        try:
            mtime = os.path.getmtime(path)
            age_days = (time.time() - mtime) / (24 * 3600)
            if age_days < older_than:
                return False
        except OSError:
            pass  # If we can't get mtime, don't filter by age
    
    # Check size if specified
    if min_size > 0:
        try:
            size = get_dir_size(path)
            if size < min_size:
                return False
        except OSError:
            pass  # If we can't get size, don't filter by size
    
    return True

def delete_directory(path, dry_run=False, trash=False, interactive=False):
    """Delete a directory with various options."""
    # Normalize the path first
    path = normalize_path(path)
    
    # Check if directory actually exists
    if not os.path.exists(path) or not os.path.isdir(path):
        print(f"✗ Cannot delete: {path} - Directory does not exist")
        return 0
    
    size = get_dir_size(path)
    
    if interactive:
        response = input(f"Delete {path}? [y/N] ").lower()
        if response != 'y':
            print(f"Skipping: {path}")
            return 0
    
    if not dry_run:
        try:
            if trash and TRASH_SUPPORTED:
                # Path needs to be absolute for send2trash
                absolute_path = os.path.abspath(path)
                send2trash.send2trash(absolute_path)
                print(f"✓ Moved to trash: {path} ({format_size(size)})")
            else:
                shutil.rmtree(path)
                print(f"✓ Deleted: {path} ({format_size(size)})")
            return size
        except Exception as e:
            print(f"✗ Failed to delete {path}: {e}")
            return 0
    else:
        print(f"Would delete: {path} ({format_size(size)})")
        return size

def delete_node_modules(directory, dry_run=False, exclude=None, older_than=None, 
                        min_size=0, trash=False, interactive=False, parallel=False):
    """Delete all node_modules folders recursively under the given directory."""
    # Normalize the directory path
    directory = normalize_path(directory)
    
    # Check if directory exists
    if not os.path.exists(directory) or not os.path.isdir(directory):
        print(f"Directory does not exist: {directory}")
        return 0, 0, []
    
    print(f"{'Scanning for' if dry_run else 'Deleting'} node_modules folders in {directory}...")
    
    total_size_saved = 0
    count = 0
    paths_to_delete = []
    deleted_items = []
    
    # First gather all node_modules paths
    try:
        for root, dirs, files in os.walk(directory, topdown=False):
            if 'node_modules' in dirs:
                node_modules_path = os.path.join(root, 'node_modules')
                node_modules_path = normalize_path(node_modules_path)
                if should_process(node_modules_path, exclude, older_than, min_size):
                    paths_to_delete.append(node_modules_path)
    except (PermissionError, OSError) as e:
        print(f"Error accessing some directories: {e}")
    
    # Process the directories
    if parallel and len(paths_to_delete) > 1 and not interactive:
        # Use parallel processing for multiple directories
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
            for path in paths_to_delete:
                future = executor.submit(delete_directory, path, dry_run, trash, interactive)
                futures.append(future)
            
            # Process results as they complete
            for future, path in tqdm(zip(concurrent.futures.as_completed(futures), paths_to_delete), 
                                    total=len(paths_to_delete), desc="Processing"):
                try:
                    size = future.result()
                    if size > 0:
                        count += 1
                        total_size_saved += size
                        deleted_items.append((path, size, "Deleted" if not dry_run else "Would delete"))
                except Exception as e:
                    print(f"Error processing {path}: {e}")
    else:
        # Sequential processing
        for path in tqdm(paths_to_delete, desc="Processing"):
            size = delete_directory(path, dry_run, trash, interactive)
            if size > 0:
                count += 1
                total_size_saved += size
                deleted_items.append((path, size, "Deleted" if not dry_run else "Would delete"))
    
    # Print summary only once at the end
    action = "Would delete" if dry_run else "Processed"
    if count > 0:
        print(f"\n{action} {count} node_modules folders, saving {format_size(total_size_saved)}")
    else:
        print("\nNo node_modules folders found or selected.")
    
    return count, total_size_saved, deleted_items

def delete_subdirectories(folder_path, dry_run=False, exclude=None, older_than=None, 
                         min_size=0, trash=False, interactive=False, parallel=False):
    """Delete all subdirectories in the given folder."""
    # Normalize the folder path
    folder_path = normalize_path(folder_path)
    
    # Check if the folder exists
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        print(f"The folder {folder_path} does not exist.")
        return 0, 0, []
    
    print(f"{'Scanning for' if dry_run else 'Deleting'} all subdirectories in {folder_path}...")
    
    total_size_saved = 0
    count = 0
    paths_to_delete = []
    deleted_items = []

    # Gather all subdirectories
    try:
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            item_path = normalize_path(item_path)
            if os.path.isdir(item_path) and should_process(item_path, exclude, older_than, min_size):
                paths_to_delete.append(item_path)
    except (PermissionError, OSError) as e:
        print(f"Error accessing directory contents: {e}")
    
    # Process the directories
    if parallel and len(paths_to_delete) > 1 and not interactive:
        # Use parallel processing
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
            for path in paths_to_delete:
                future = executor.submit(delete_directory, path, dry_run, trash, interactive)
                futures.append(future)
            
            for future, path in tqdm(zip(concurrent.futures.as_completed(futures), paths_to_delete), 
                                    total=len(paths_to_delete), desc="Processing"):
                try:
                    size = future.result()
                    if size > 0:
                        count += 1
                        total_size_saved += size
                        deleted_items.append((path, size, "Deleted" if not dry_run else "Would delete"))
                except Exception as e:
                    print(f"Error processing {path}: {e}")
    else:
        # Sequential processing
        for path in tqdm(paths_to_delete, desc="Processing"):
            size = delete_directory(path, dry_run, trash, interactive)
            if size > 0:
                count += 1
                total_size_saved += size
                deleted_items.append((path, size, "Deleted" if not dry_run else "Would delete"))
    
    # Print summary
    action = "Would delete" if dry_run else "Processed"
    if count > 0:
        print(f"\n{action} {count} directories, saving {format_size(total_size_saved)}")
    else:
        print("\nNo subdirectories found or selected.")
    
    return count, total_size_saved, deleted_items

def delete_pattern_directories(directory, pattern, dry_run=False, exclude=None, older_than=None, 
                              min_size=0, trash=False, interactive=False, parallel=False):
    """Delete all directories matching a pattern recursively under the given directory."""
    # Normalize the directory path
    directory = normalize_path(directory)
    
    # Check if directory exists
    if not os.path.exists(directory) or not os.path.isdir(directory):
        print(f"Directory does not exist: {directory}")
        return 0, 0, []
    
    print(f"{'Scanning for' if dry_run else 'Deleting'} directories matching '{pattern}' in {directory}...")
    
    total_size_saved = 0
    count = 0
    paths_to_delete = []
    deleted_items = []
    
    # Gather all matching directories
    try:
        for root, dirs, _ in os.walk(directory, topdown=True):
            matching_dirs = [d for d in dirs if fnmatch.fnmatch(d, pattern)]
            for d in matching_dirs:
                full_path = os.path.join(root, d)
                full_path = normalize_path(full_path)
                if should_process(full_path, exclude, older_than, min_size):
                    paths_to_delete.append(full_path)
                    # Avoid descending into directories we're going to delete
                    dirs.remove(d)
    except (PermissionError, OSError) as e:
        print(f"Error accessing some directories: {e}")
    
    # Process the directories
    if parallel and len(paths_to_delete) > 1 and not interactive:
        # Use parallel processing
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
            for path in paths_to_delete:
                future = executor.submit(delete_directory, path, dry_run, trash, interactive)
                futures.append(future)
            
            for future, path in tqdm(zip(concurrent.futures.as_completed(futures), paths_to_delete), 
                                    total=len(paths_to_delete), desc="Processing"):
                try:
                    size = future.result()
                    if size > 0:
                        count += 1
                        total_size_saved += size
                        deleted_items.append((path, size, "Deleted" if not dry_run else "Would delete"))
                except Exception as e:
                    print(f"Error processing {path}: {e}")
    else:
        # Sequential processing
        for path in tqdm(paths_to_delete, desc="Processing"):
            size = delete_directory(path, dry_run, trash, interactive)
            if size > 0:
                count += 1
                total_size_saved += size
                deleted_items.append((path, size, "Deleted" if not dry_run else "Would delete"))
    
    # Print summary
    action = "Would delete" if dry_run else "Processed"
    if count > 0:
        print(f"\n{action} {count} directories, saving {format_size(total_size_saved)}")
    else:
        print(f"\nNo directories matching '{pattern}' found or selected.")
    
    return count, total_size_saved, deleted_items

def delete_pattern_directories_multiple(directory, patterns, dry_run=False, exclude=None, older_than=None, 
                               min_size=0, trash=False, interactive=False, parallel=False):
    """Delete all directories matching any of the patterns recursively under the given directory."""
    # Normalize the directory path
    directory = normalize_path(directory)
    
    # Check if directory exists
    if not os.path.exists(directory) or not os.path.isdir(directory):
        print(f"Directory does not exist: {directory}")
        return 0, 0, []
    
    pattern_str = ", ".join(patterns)
    print(f"{'Scanning for' if dry_run else 'Deleting'} directories matching patterns: {pattern_str} in {directory}...")
    
    total_size_saved = 0
    count = 0
    paths_to_delete = []
    deleted_items = []
    
    # Gather all matching directories
    try:
        for root, dirs, _ in os.walk(directory, topdown=True):
            matching_dirs = []
            for d in list(dirs):  # Make a copy since we might modify dirs
                for pattern in patterns:
                    if fnmatch.fnmatch(d, pattern):
                        matching_dirs.append(d)
                        break  # Once matched, no need to check other patterns
            
            for d in matching_dirs:
                full_path = os.path.join(root, d)
                full_path = normalize_path(full_path)
                if should_process(full_path, exclude, older_than, min_size):
                    paths_to_delete.append(full_path)
                    # Avoid descending into directories we're going to delete
                    if d in dirs:  # Check if still in dirs (might have been removed already)
                        dirs.remove(d)
    except (PermissionError, OSError) as e:
        print(f"Error accessing some directories: {e}")
    
    # Process the directories
    if parallel and len(paths_to_delete) > 1 and not interactive:
        # Use parallel processing
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
            for path in paths_to_delete:
                future = executor.submit(delete_directory, path, dry_run, trash, interactive)
                futures.append(future)
            
            for future, path in tqdm(zip(concurrent.futures.as_completed(futures), paths_to_delete), 
                                    total=len(paths_to_delete), desc="Processing"):
                try:
                    size = future.result()
                    if size > 0:
                        count += 1
                        total_size_saved += size
                        deleted_items.append((path, size, "Deleted" if not dry_run else "Would delete"))
                except Exception as e:
                    print(f"Error processing {path}: {e}")
    else:
        # Sequential processing
        for path in tqdm(paths_to_delete, desc="Processing"):
            size = delete_directory(path, dry_run, trash, interactive)
            if size > 0:
                count += 1
                total_size_saved += size
                deleted_items.append((path, size, "Deleted" if not dry_run else "Would delete"))
    
    # Print summary
    action = "Would delete" if dry_run else "Processed"
    if count > 0:
        print(f"\n{action} {count} directories, saving {format_size(total_size_saved)}")
    else:
        print(f"\nNo directories matching patterns: {pattern_str} found or selected.")
    
    return count, total_size_saved, deleted_items

def analyze_disk_usage(directory, depth=3):
    """Analyze disk usage in the directory, showing largest directories."""
    # Normalize the directory path
    directory = normalize_path(directory)
    
    # Check if directory exists
    if not os.path.exists(directory) or not os.path.isdir(directory):
        print(f"Directory does not exist: {directory}")
        return []
    
    print(f"Analyzing disk usage in {directory}...")
    
    results = []
    
    # Walk directory tree up to the specified depth
    try:
        for root, dirs, files in os.walk(directory):
            # Calculate current level - use normalized paths for consistent separator handling
            norm_root = normalize_path(root)
            norm_directory = normalize_path(directory)
            
            # Path.relative_to can be more reliable for level calculation
            try:
                rel_path = Path(norm_root).relative_to(Path(norm_directory))
                level = len(rel_path.parts)
            except ValueError:
                # Fallback method if relative_to fails
                level = len(os.path.relpath(norm_root, norm_directory).split(os.sep))
            
            if level <= depth:
                for d in dirs:
                    full_path = os.path.join(root, d)
                    full_path = normalize_path(full_path)
                    try:
                        size = get_dir_size(full_path)
                        results.append((full_path, size))
                    except Exception as e:
                        print(f"Error analyzing {full_path}: {e}")
    except (PermissionError, OSError) as e:
        print(f"Error accessing some directories: {e}")
    
    # Sort results by size (largest first)
    results.sort(key=lambda x: x[1], reverse=True)
    
    # Print results
    print("\nLargest directories:")
    print("-" * 80)
    print(f"{'Size':>10} | Path")
    print("-" * 80)
    
    for path, size in results[:20]:  # Show top 20
        print(f"{format_size(size):>10} | {path}")
    
    return results

def find_cleaning_opportunities(directory):
    """Auto-discover potential cleanup opportunities."""
    # Normalize the directory path
    directory = normalize_path(directory)
    
    # Check if directory exists
    if not os.path.exists(directory) or not os.path.isdir(directory):
        print(f"Directory does not exist: {directory}")
        return {}
    
    print(f"Scanning for cleanup opportunities in {directory}...")
    
    opportunities = {
        "node_modules": [],
        "build_artifacts": [],
        "cache_dirs": [],
        "temp_files": [],
        "large_dirs": []
    }
    
    # Common patterns to look for
    build_patterns = ["build", "dist", "target", "bin", "obj"]
    cache_patterns = [".cache", ".npm", ".gradle", "__pycache__", ".nuget"]
    temp_patterns = ["tmp", "temp", "*.tmp", "*.bak"]
    
    # Walk the directory tree
    try:
        for root, dirs, files in os.walk(directory):
            # Check for node_modules
            if "node_modules" in dirs:
                path = os.path.join(root, "node_modules")
                path = normalize_path(path)
                size = get_dir_size(path)
                if size > 10 * 1024 * 1024:  # Only report if > 10MB
                    opportunities["node_modules"].append((path, size))
            
            # Check for build artifacts
            for pattern in build_patterns:
                for d in dirs:
                    if d == pattern or fnmatch.fnmatch(d, pattern):
                        path = os.path.join(root, d)
                        path = normalize_path(path)
                        size = get_dir_size(path)
                        if size > 5 * 1024 * 1024:  # Only report if > 5MB
                            opportunities["build_artifacts"].append((path, size))
            
            # Check for cache directories
            for pattern in cache_patterns:
                for d in dirs:
                    if d == pattern or fnmatch.fnmatch(d, pattern):
                        path = os.path.join(root, d)
                        path = normalize_path(path)
                        size = get_dir_size(path)
                        if size > 5 * 1024 * 1024:  # Only report if > 5MB
                            opportunities["cache_dirs"].append((path, size))
            
            # Check for temp files
            for pattern in temp_patterns:
                for d in dirs + files:
                    if fnmatch.fnmatch(d, pattern):
                        path = os.path.join(root, d)
                        path = normalize_path(path)
                        if os.path.isdir(path):
                            size = get_dir_size(path)
                        else:
                            try:
                                size = os.path.getsize(path)
                            except (OSError, FileNotFoundError):
                                size = 0
                        if size > 1 * 1024 * 1024:  # Only report if > 1MB
                            opportunities["temp_files"].append((path, size))
    except (PermissionError, OSError) as e:
        print(f"Error accessing some directories: {e}")
    
    # Find any unusually large directories
    all_dirs = []
    try:
        for root, dirs, _ in os.walk(directory, topdown=True):
            for d in dirs:
                path = os.path.join(root, d)
                path = normalize_path(path)
                try:
                    size = get_dir_size(path)
                    if size > 100 * 1024 * 1024:  # Only report if > 100MB
                        all_dirs.append((path, size))
                except Exception:
                    pass
    except (PermissionError, OSError) as e:
        print(f"Error accessing some directories: {e}")
    
    # Sort by size and take top 10
    all_dirs.sort(key=lambda x: x[1], reverse=True)
    opportunities["large_dirs"] = all_dirs[:10]
    
    # Print summary of opportunities
    for category, items in opportunities.items():
        if items:
            total_size = sum(size for _, size in items)
            print(f"\n{category.replace('_', ' ').title()} - {len(items)} items, {format_size(total_size)}")
            for path, size in sorted(items, key=lambda x: x[1], reverse=True)[:5]:
                print(f"  {format_size(size):>10} | {path}")
            if len(items) > 5:
                print(f"  ... and {len(items) - 5} more")
    
    return opportunities

def generate_html_report(report_data, filename="cleanup_report.html"):
    """Generate an HTML report from cleanup data."""
    # Normalize the output filename
    filename = normalize_path(filename)
    
    # Create directory for the report if it doesn't exist
    report_dir = os.path.dirname(filename)
    if report_dir and not os.path.exists(report_dir):
        try:
            os.makedirs(report_dir)
        except OSError as e:
            print(f"Error creating directory for report: {e}")
            # Fall back to current directory
            filename = os.path.basename(filename)
    
    # Get the timestamp
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_items = sum(len(section.get("items", [])) for section in report_data.get("sections", []))
    total_space = report_data.get("total_space", "0 B")
    
    # Create the HTML content with actual data
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Directory Cleanup Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1, h2 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f2f2f2; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .summary {{ background-color: #e9f7ef; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .timestamp {{ color: #666; font-size: 0.9em; }}
    </style>
</head>
<body>
    <h1>Directory Cleanup Report</h1>
    <div class="timestamp">Generated on: {now}</div>
    
    <div class="summary">
        <h2>Summary</h2>
        <p>Total items processed: {total_items}</p>
        <p>Total space saved: {total_space}</p>
    </div>
"""
    
    # Add each section with its items
    for section in report_data.get("sections", []):
        html += f"\n    <h2>{section['title']}</h2>\n"
        
        items = section.get("items", [])
        if items:
            html += """    <table>
        <tr>
            <th>Path</th>
            <th>Size</th>
            <th>Status</th>
        </tr>
"""
            # Add each item in the table
            for item in items:
                html += f"""        <tr>
            <td>{item['path']}</td>
            <td>{item['size']}</td>
            <td>{item['status']}</td>
        </tr>
"""
            html += "    </table>\n"
        else:
            html += "    <p>No items found.</p>\n"
    
    # Close the HTML document
    html += """</body>
</html>"""
    
    # Write to file
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"HTML report generated: {filename}")
    except Exception as e:
        print(f"Error writing report file: {e}")
        # Try writing to current directory as fallback
        fallback_path = os.path.basename(filename)
        try:
            with open(fallback_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"HTML report generated at fallback location: {fallback_path}")
            filename = fallback_path
        except Exception as e2:
            print(f"Failed to write report file: {e2}")
    
    return filename

def parse_config(config_file):
    """Parse a configuration file for cleaning profiles."""
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
    """Run a predefined preset cleaning operation."""
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

def find_empty_directories(directory, exclude=None):
    """Find all empty directories recursively under the given directory."""
    # Normalize the directory path
    directory = normalize_path(directory)
    
    # Check if directory exists
    if not os.path.exists(directory) or not os.path.isdir(directory):
        print(f"Directory does not exist: {directory}")
        return []
    
    print(f"Scanning for empty directories in {directory}...")
    
    empty_dirs = []
    
    # Walk the directory tree from bottom up to identify empty directories
    try:
        for root, dirs, files in os.walk(directory, topdown=False):
            # Skip directories that match exclude patterns
            if exclude and any(fnmatch.fnmatch(root, pattern) for pattern in exclude):
                continue
                
            # Check if directory is empty (no files and no non-empty subdirectories)
            if not files and not any(os.path.join(root, d) in empty_dirs for d in dirs):
                # Don't consider the root directory as an empty dir to delete
                if root != directory:
                    empty_dirs.append(root)
    except (PermissionError, OSError) as e:
        print(f"Error accessing some directories: {e}")
    
    return empty_dirs

def delete_empty_directories(directory, dry_run=False, exclude=None, older_than=None, 
                         min_size=0, trash=False, interactive=False, parallel=False):
    """Delete all empty directories recursively under the given directory."""
    # Normalize the directory path
    directory = normalize_path(directory)
    
    # Check if directory exists
    if not os.path.exists(directory) or not os.path.isdir(directory):
        print(f"Directory does not exist: {directory}")
        return 0, 0, []
    
    print(f"{'Scanning for' if dry_run else 'Deleting'} empty directories in {directory}...")
    
    # Find all empty directories
    empty_dirs = find_empty_directories(directory, exclude)
    
    total_size_saved = 0  # This will be close to 0 for empty dirs
    count = 0
    deleted_items = []
    
    # Process the directories
    if parallel and len(empty_dirs) > 1 and not interactive:
        # Use parallel processing
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
            for path in empty_dirs:
                future = executor.submit(delete_directory, path, dry_run, trash, interactive)
                futures.append(future)
            
            for future, path in tqdm(zip(concurrent.futures.as_completed(futures), empty_dirs), 
                                    total=len(empty_dirs), desc="Processing"):
                try:
                    size = future.result()
                    if size >= 0:  # Even if size is 0, consider it a success for empty dirs
                        count += 1
                        total_size_saved += size
                        deleted_items.append((path, size, "Deleted" if not dry_run else "Would delete"))
                except Exception as e:
                    print(f"Error processing {path}: {e}")
    else:
        # Sequential processing
        for path in tqdm(empty_dirs, desc="Processing"):
            size = delete_directory(path, dry_run, trash, interactive)
            if size >= 0:  # Even if size is 0, consider it a success for empty dirs
                count += 1
                total_size_saved += size
                deleted_items.append((path, size, "Deleted" if not dry_run else "Would delete"))
    
    # Print summary
    action = "Would delete" if dry_run else "Processed"
    if count > 0:
        print(f"\n{action} {count} empty directories")
    else:
        print("\nNo empty directories found or selected.")
    
    return count, total_size_saved, deleted_items

def main():
    parser = argparse.ArgumentParser(description="Directory cleaning utility")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Common arguments
    common_args = argparse.ArgumentParser(add_help=False)
    common_args.add_argument("directory", help="Directory to process")
    common_args.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    common_args.add_argument("--exclude", nargs="+", help="Patterns to exclude (e.g. '*important*')")
    common_args.add_argument("--older-than", type=int, help="Only process directories older than N days")
    common_args.add_argument("--min-size", help="Only process directories larger than SIZE (e.g. '10MB')")
    common_args.add_argument("--trash", action="store_true", help="Move to trash instead of deleting")
    common_args.add_argument("--interactive", "-i", action="store_true", help="Prompt before each deletion")
    common_args.add_argument("--parallel", action="store_true", help="Use parallel processing (faster)")
    common_args.add_argument("--report", help="Generate HTML report at specified path")
    
    # Node modules command
    node_parser = subparsers.add_parser("node-modules", help="Delete all node_modules directories", parents=[common_args])
    
    # Subdirs command
    subdir_parser = subparsers.add_parser("subdirs", help="Delete all subdirectories in a directory", parents=[common_args])
    
    # Pattern command
    pattern_parser = subparsers.add_parser("pattern", help="Delete directories matching a pattern", parents=[common_args])
    pattern_parser.add_argument("pattern", help="Directory name pattern to match (e.g. '*cache*')")
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze disk usage without deleting")
    analyze_parser.add_argument("directory", help="Directory to analyze")
    analyze_parser.add_argument("--depth", type=int, default=3, help="Directory depth for analysis")
    
    # Discover command
    discover_parser = subparsers.add_parser("discover", help="Auto-discover cleanup opportunities")
    discover_parser.add_argument("directory", help="Directory to scan")
    
    # Preset command - Modify to accept preset name first, then directory
    preset_parser = subparsers.add_parser("preset", help="Run a predefined cleaning preset")
    preset_parser.add_argument("preset_name", choices=["node-modules", "build-artifacts", "cache-dirs", "temp-files"],
                              help="Preset name to run")
    preset_parser.add_argument("directory", help="Directory to process")
    preset_parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    preset_parser.add_argument("--exclude", nargs="+", help="Patterns to exclude (e.g. '*important*')")
    preset_parser.add_argument("--older-than", type=int, help="Only process directories older than N days")
    preset_parser.add_argument("--min-size", help="Only process directories larger than SIZE (e.g. '10MB')")
    preset_parser.add_argument("--trash", action="store_true", help="Move to trash instead of deleting")
    preset_parser.add_argument("--interactive", "-i", action="store_true", help="Prompt before each deletion")
    preset_parser.add_argument("--parallel", action="store_true", help="Use parallel processing (faster)")
    preset_parser.add_argument("--report", help="Generate HTML report at specified path")
    
    # Config command
    config_parser = subparsers.add_parser("config", help="Run a cleanup profile from config file")
    config_parser.add_argument("config_file", help="Path to config file")
    config_parser.add_argument("profile", help="Profile name to run")
    config_parser.add_argument("directory", help="Directory to process")
    
    # Add empty directories command
    empty_dirs_parser = subparsers.add_parser("empty-dirs", help="Delete all empty directories", parents=[common_args])
    
    args = parser.parse_args()
    
    # Convert min-size to bytes if specified
    min_size = 0
    if hasattr(args, 'min_size') and args.min_size:
        try:
            min_size = parse_size(args.min_size)
        except ValueError as e:
            print(f"Error: {e}")
            return
    
    # Check if send2trash is available when --trash is used
    if hasattr(args, 'trash') and args.trash and not TRASH_SUPPORTED:
        print("Warning: 'send2trash' module not found. Installing it enables the trash feature:")
        print("pip install send2trash")
        print("Continuing with permanent deletion...")
        args.trash = False
    
    # Execute the appropriate command
    report_data = {
        "sections": [],
        "total_space": "0 B"
    }
    total_saved = 0
    
    try:
        if args.command == "node-modules":
            # Normalize directory path
            directory = normalize_path(args.directory)
            count, saved, deleted_items = delete_node_modules(
                directory, args.dry_run, args.exclude,
                args.older_than, min_size, args.trash,
                args.interactive, args.parallel
            )
            if args.report:
                items = []
                for path, size, status in deleted_items:
                    items.append({
                        "path": path,
                        "size": format_size(size),
                        "status": status
                    })
                
                report_data["sections"].append({
                    "title": "Node Modules",
                    "items": items
                })
                total_saved += saved
            
        elif args.command == "subdirs":
            # Normalize directory path
            directory = normalize_path(args.directory)
            count, saved, deleted_items = delete_subdirectories(
                directory, args.dry_run, args.exclude,
                args.older_than, min_size, args.trash,
                args.interactive, args.parallel
            )
            if args.report:
                items = []
                for path, size, status in deleted_items:
                    items.append({
                        "path": path,
                        "size": format_size(size),
                        "status": status
                    })
                
                report_data["sections"].append({
                    "title": "Subdirectories",
                    "items": items
                })
                total_saved += saved
            
        elif args.command == "pattern":
            # Normalize directory path
            directory = normalize_path(args.directory)
            count, saved, deleted_items = delete_pattern_directories(
                directory, args.pattern, args.dry_run,
                args.exclude, args.older_than, min_size,
                args.trash, args.interactive, args.parallel
            )
            if args.report:
                items = []
                for path, size, status in deleted_items:
                    items.append({
                        "path": path,
                        "size": format_size(size),
                        "status": status
                    })
                
                report_data["sections"].append({
                    "title": f"Pattern: {args.pattern}",
                    "items": items
                })
                total_saved += saved
            
        elif args.command == "analyze":
            # Normalize directory path
            directory = normalize_path(args.directory)
            results = analyze_disk_usage(directory, args.depth)
            
        elif args.command == "discover":
            # Normalize directory path
            directory = normalize_path(args.directory)
            opportunities = find_cleaning_opportunities(directory)
            
        elif args.command == "preset":
            # Normalize directory path
            directory = normalize_path(args.directory)
            count, saved, deleted_items = run_preset(
                args.preset_name, directory, dry_run=args.dry_run,
                exclude=args.exclude, older_than=args.older_than,
                min_size=min_size, trash=args.trash,
                interactive=args.interactive, parallel=args.parallel
            )
            if args.report:
                items = []
                for path, size, status in deleted_items:
                    items.append({
                        "path": path,
                        "size": format_size(size),
                        "status": status
                    })
                
                report_data["sections"].append({
                    "title": f"Preset: {args.preset_name}",
                    "items": items
                })
                total_saved += saved
            
        elif args.command == "config":
            # Normalize paths
            config_file = normalize_path(args.config_file)
            directory = normalize_path(args.directory)
            
            profiles = parse_config(config_file)
            if profiles and args.profile in profiles:
                profile = profiles[args.profile]
                if "type" not in profile:
                    print(f"Error: Profile {args.profile} missing 'type' specification")
                elif profile["type"] == "node-modules":
                    delete_node_modules(directory, **{k: v for k, v in profile.items() if k != "type"})
                elif profile["type"] == "subdirs":
                    delete_subdirectories(directory, **{k: v for k, v in profile.items() if k != "type"})
                elif profile["type"] == "pattern" and "pattern" in profile:
                    delete_pattern_directories(directory, profile["pattern"], 
                                            **{k: v for k, v in profile.items() if k not in ["type", "pattern"]})
                else:
                    print(f"Unknown profile type: {profile.get('type')}")
            else:
                if not profiles:
                    print(f"Error parsing config file: {config_file}")
                else:
                    print(f"Profile '{args.profile}' not found. Available profiles: {', '.join(profiles.keys())}")
        elif args.command == "empty-dirs":
            # Normalize directory path
            directory = normalize_path(args.directory)
            count, saved, deleted_items = delete_empty_directories(
                directory, args.dry_run, args.exclude,
                args.older_than, min_size, args.trash,
                args.interactive, args.parallel
            )
            if args.report:
                items = []
                for path, size, status in deleted_items:
                    items.append({
                        "path": path,
                        "size": format_size(size),
                        "status": status
                    })
                
                report_data["sections"].append({
                    "title": "Empty Directories",
                    "items": items
                })
                total_saved += saved
        else:
            parser.print_help()
    
    except KeyboardInterrupt:
        print("\nOperation canceled by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
        # Uncomment for debugging
        # import traceback
        # traceback.print_exc()
    
    # Generate HTML report if requested
    if hasattr(args, 'report') and args.report:
        report_data["total_space"] = format_size(total_saved)
        generate_html_report(report_data, args.report)

if __name__ == "__main__":
    main()