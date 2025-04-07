"""
Core functionality for directory cleaning operations.

This module provides functions for identifying and cleaning various types of directories
based on different criteria such as patterns, age, and size.
"""

import os
import fnmatch
import shutil
import time
import datetime
import concurrent.futures
from pathlib import Path
from tqdm import tqdm

from directory_cleaner.directory_cleaner.core.file_utils import (
    normalize_path, get_dir_size, format_size, TRASH_SUPPORTED
)


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
                import send2trash
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