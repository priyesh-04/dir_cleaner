"""
Functionality for analyzing disk usage and discovering cleanup opportunities.

This module provides functions for analyzing directory structures to find
large directories and potential cleanup candidates.
"""

import os
import fnmatch
from tqdm import tqdm

from directory_cleaner.directory_cleaner.core.file_utils import (
    normalize_path, get_dir_size, format_size
)


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
                from pathlib import Path
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


def delete_pattern_directories_multiple(directory, patterns, dry_run=False, exclude=None, older_than=None, 
                               min_size=0, trash=False, interactive=False, parallel=False):
    """Delete all directories matching any of the patterns recursively under the given directory."""
    from directory_cleaner.directory_cleaner.core.dir_operations import delete_directory
    
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
                
                # Import should_process within the function to avoid circular imports
                from directory_cleaner.directory_cleaner.core.dir_operations import should_process
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
        import concurrent.futures
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