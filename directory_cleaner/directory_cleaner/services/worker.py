"""
Worker thread implementation for background processing in the GUI.

This module provides a QThread-based worker implementation to prevent UI freezing
during long-running operations.
"""

import os
import traceback
import fnmatch
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, QObject, QEventLoop

from directory_cleaner.directory_cleaner.core.file_utils import (
    normalize_path, get_dir_size, format_size, parse_size, TRASH_SUPPORTED
)
from directory_cleaner.directory_cleaner.core.dir_operations import (
    delete_directory, should_process, delete_node_modules, delete_subdirectories,
    delete_pattern_directories, delete_empty_directories
)
from directory_cleaner.directory_cleaner.core.analysis import (
    analyze_disk_usage, find_cleaning_opportunities, delete_pattern_directories_multiple
)
from directory_cleaner.directory_cleaner.services.reporting import generate_html_report
from directory_cleaner.directory_cleaner.services.config import run_preset


class InteractiveConfirmation(QObject):
    """Helper class to handle interactive confirmations from the GUI thread"""
    confirmation_result = None
    wait_for_confirmation = pyqtSignal(str, float)  # Path and size


class WorkerThread(QThread):
    """Thread for running cleanup operations without blocking UI"""
    progress_update = pyqtSignal(int)
    log_update = pyqtSignal(str)
    operation_complete = pyqtSignal(dict)
    confirmation_needed = pyqtSignal(str, float)  # Path and size
    scan_complete = pyqtSignal(list)  # For selective deletion
    
    def __init__(self, operation, **kwargs):
        super().__init__()
        self.operation = operation
        self.kwargs = kwargs
        self.report_data = {
            "sections": [],
            "total_space": "0 B"
        }
        self.interactive_helper = InteractiveConfirmation()
        self.interactive_helper.wait_for_confirmation.connect(self.wait_for_user_confirmation)
        
        # Add operation progress tracking
        self.total_items = 0
        self.processed_items = 0
        
        # Add a monitor method for dir_cleaner functions to call
        self.update_progress_percent(0)  # Start at 0%
        
    def custom_delete_directory(self, path, dry_run=False, trash=False, interactive=False):
        """Override dir_cleaner's delete_directory to use GUI confirmation"""
        # Normalize the path first
        path = normalize_path(path)
        
        # Check if directory actually exists
        if not os.path.exists(path) or not os.path.isdir(path):
            self.log_update.emit(f"✗ Cannot delete: {path} - Directory does not exist")
            return 0
        
        size = get_dir_size(path)
        
        if interactive:
            # Instead of terminal input, emit signal for GUI confirmation
            self.confirmation_needed.emit(path, size)
            
            # Wait for the confirmation result
            loop = QEventLoop()
            self.interactive_helper.wait_for_confirmation.connect(lambda *args: loop.quit())
            loop.exec_()
            
            # Check the confirmation result
            if not self.interactive_helper.confirmation_result:
                self.log_update.emit(f"Skipping: {path}")
                return 0
        
        if not dry_run:
            try:
                if trash and TRASH_SUPPORTED:
                    # Path needs to be absolute for send2trash
                    absolute_path = os.path.abspath(path)
                    import send2trash
                    send2trash.send2trash(absolute_path)
                    self.log_update.emit(f"✓ Moved to trash: {path} ({format_size(size)})")
                else:
                    import shutil
                    shutil.rmtree(path)
                    self.log_update.emit(f"✓ Deleted: {path} ({format_size(size)})")
                return size
            except Exception as e:
                self.log_update.emit(f"✗ Failed to delete {path}: {e}")
                return 0
        else:
            self.log_update.emit(f"Would delete: {path} ({format_size(size)})")
            return size
    
    def wait_for_user_confirmation(self, path, size):
        """Wait method - this will be called after the main thread processes the confirmation dialog"""
        pass  # Just a placeholder to receive the signal when confirmation is complete

    def run(self):
        """Run the selected operation in the background"""
        result = {"count": 0, "saved": 0}
        
        try:
            # Redirect print statements to the log
            import builtins
            original_print = builtins.print
            
            def custom_print(*args, **kwargs):
                message = " ".join(str(arg) for arg in args)
                self.log_update.emit(message)
                # Still allow print to work normally
                original_print(*args, **kwargs)
            
            builtins.print = custom_print
            
            # Extract parameters
            directory = self.kwargs.get("directory")
            report_path = self.kwargs.get("report_path")
            interactive = self.kwargs.get("interactive", False)
            
            self.log_update.emit(f"Starting operation: {self.operation}")
            self.log_update.emit(f"Directory: {directory}")
            
            # For interactive mode, we'll use our custom delete_directory function
            if interactive:
                # Store reference to original function to restore later
                import directory_cleaner.directory_cleaner.core.dir_operations as dir_ops
                original_delete_directory = dir_ops.delete_directory
                # Replace with our custom function
                dir_ops.delete_directory = self.custom_delete_directory
            
            # Run the appropriate operation
            if self.operation == "node_modules":
                self.progress_update.emit(10)  # Show early progress to indicate we're working
                count, saved, deleted_items = delete_node_modules(
                    directory,
                    dry_run=self.kwargs.get("dry_run", False),
                    exclude=self.kwargs.get("exclude"),
                    older_than=self.kwargs.get("older_than"),
                    min_size=parse_size(self.kwargs.get("min_size", "0")) if self.kwargs.get("min_size") else 0,
                    trash=self.kwargs.get("trash", False),
                    interactive=self.kwargs.get("interactive", False),
                    parallel=False if self.kwargs.get("interactive", False) else self.kwargs.get("parallel", False)
                )
                self.progress_update.emit(90)  # Show progress near completion
                result["count"] = count
                result["saved"] = saved
                
                if report_path:
                    items = []
                    for path, size, status in deleted_items:
                        items.append({
                            "path": path,
                            "size": format_size(size),
                            "status": status
                        })
                    
                    self.report_data["sections"].append({
                        "title": "Node Modules",
                        "items": items
                    })
                    
                if count > 0:
                    self.log_update.emit(f"\nFound and processed {count} node_modules folders, saving {format_size(saved)}")
                else:
                    self.log_update.emit(f"\nNo node_modules folders found matching your criteria.")
                    
            elif self.operation == "subdirs":
                self.progress_update.emit(10)  # Show early progress to indicate we're working
                count, saved, deleted_items = delete_subdirectories(
                    directory,
                    dry_run=self.kwargs.get("dry_run", False),
                    exclude=self.kwargs.get("exclude"),
                    older_than=self.kwargs.get("older_than"),
                    min_size=parse_size(self.kwargs.get("min_size", "0")) if self.kwargs.get("min_size") else 0,
                    trash=self.kwargs.get("trash", False),
                    interactive=self.kwargs.get("interactive", False),
                    parallel=False if self.kwargs.get("interactive", False) else self.kwargs.get("parallel", False)
                )
                self.progress_update.emit(90)  # Show progress near completion
                result["count"] = count
                result["saved"] = saved
                
                if report_path:
                    items = []
                    for path, size, status in deleted_items:
                        items.append({
                            "path": path,
                            "size": format_size(size),
                            "status": status
                        })
                    
                    self.report_data["sections"].append({
                        "title": "Subdirectories",
                        "items": items
                    })
                    
                if count > 0:
                    self.log_update.emit(f"\nFound and processed {count} subdirectories, saving {format_size(saved)}")
                else:
                    self.log_update.emit(f"\nNo subdirectories found matching your criteria.")
                    
            elif self.operation == "pattern":
                self.progress_update.emit(10)  # Show early progress to indicate we're working
                pattern = self.kwargs.get("pattern")
                count, saved, deleted_items = delete_pattern_directories(
                    directory, 
                    pattern,
                    dry_run=self.kwargs.get("dry_run", False),
                    exclude=self.kwargs.get("exclude"),
                    older_than=self.kwargs.get("older_than"),
                    min_size=parse_size(self.kwargs.get("min_size", "0")) if self.kwargs.get("min_size") else 0,
                    trash=self.kwargs.get("trash", False),
                    interactive=self.kwargs.get("interactive", False),
                    parallel=False if self.kwargs.get("interactive", False) else self.kwargs.get("parallel", False)
                )
                self.progress_update.emit(90)  # Show progress near completion
                result["count"] = count
                result["saved"] = saved
                
                if report_path:
                    items = []
                    for path, size, status in deleted_items:
                        items.append({
                            "path": path,
                            "size": format_size(size),
                            "status": status
                        })
                    
                    self.report_data["sections"].append({
                        "title": f"Pattern: {pattern}",
                        "items": items
                    })
                    
                if count > 0:
                    self.log_update.emit(f"\nFound and processed {count} pattern matches, saving {format_size(saved)}")
                else:
                    self.log_update.emit(f"\nNo directories matching pattern found.")
                    
            elif self.operation == "analyze":
                self.progress_update.emit(10)  # Show early progress to indicate we're working
                depth = self.kwargs.get("depth", 3)
                results = analyze_disk_usage(directory, depth)
                self.progress_update.emit(90)  # Show progress near completion
                
                # For analysis, return the top results
                count = len(results)
                saved = sum(size for _, size in results)
                result["count"] = count
                result["saved"] = saved
                
                if report_path:
                    items = []
                    for path, size in results[:50]:  # Limit to top 50
                        items.append({
                            "path": path,
                            "size": format_size(size),
                            "status": "Analyzed"
                        })
                    
                    self.report_data["sections"].append({
                        "title": "Disk Usage Analysis",
                        "items": items
                    })
                    
                if count > 0:
                    self.log_update.emit(f"\nAnalyzed {count} directories, total size: {format_size(saved)}")
                else:
                    self.log_update.emit(f"\nNo directories found to analyze.")
                    
            elif self.operation == "discover":
                self.progress_update.emit(10)  # Show early progress to indicate we're working
                opportunities = find_cleaning_opportunities(directory)
                self.progress_update.emit(90)  # Show progress near completion
                
                # Flatten all opportunities for reporting
                all_items = []
                for category, items in opportunities.items():
                    result["count"] += len(items)
                    result["saved"] += sum(size for _, size in items)
                    all_items.extend([(category, path, size) for path, size in items])
                
                if report_path:
                    for category, items in opportunities.items():
                        category_items = []
                        for path, size in items:
                            category_items.append({
                                "path": path,
                                "size": format_size(size),
                                "status": "Potential cleanup"
                            })
                        
                        if category_items:
                            self.report_data["sections"].append({
                                "title": category.replace('_', ' ').title(),
                                "items": category_items
                            })
                    
                if result["count"] > 0:
                    self.log_update.emit(f"\nDiscovered {result['count']} cleanup opportunities, potential savings: {format_size(result['saved'])}")
                else:
                    self.log_update.emit(f"\nNo cleanup opportunities found.")
                    
            elif self.operation == "preset":
                self.progress_update.emit(10)  # Show early progress to indicate we're working
                preset_name = self.kwargs.get("preset_name")
                count, saved, deleted_items = run_preset(
                    preset_name, 
                    directory,
                    dry_run=self.kwargs.get("dry_run", False),
                    exclude=self.kwargs.get("exclude"),
                    older_than=self.kwargs.get("older_than"),
                    min_size=parse_size(self.kwargs.get("min_size", "0")) if self.kwargs.get("min_size") else 0,
                    trash=self.kwargs.get("trash", False),
                    interactive=self.kwargs.get("interactive", False),
                    parallel=False if self.kwargs.get("interactive", False) else self.kwargs.get("parallel", False)
                )
                self.progress_update.emit(90)  # Show progress near completion
                result["count"] = count
                result["saved"] = saved
                
                if report_path:
                    items = []
                    for path, size, status in deleted_items:
                        items.append({
                            "path": path,
                            "size": format_size(size),
                            "status": status
                        })
                    
                    self.report_data["sections"].append({
                        "title": f"Preset: {preset_name}",
                        "items": items
                    })
                    
                if count > 0:
                    self.log_update.emit(f"\nPreset '{preset_name}' processed {count} items, saving {format_size(saved)}")
                else:
                    self.log_update.emit(f"\nNo items found for preset '{preset_name}'.")
            
            elif self.operation == "empty_dirs":
                self.progress_update.emit(10)  # Show early progress to indicate we're working
                count, saved, deleted_items = delete_empty_directories(
                    directory,
                    dry_run=self.kwargs.get("dry_run", False),
                    exclude=self.kwargs.get("exclude"),
                    older_than=self.kwargs.get("older_than"),
                    min_size=parse_size(self.kwargs.get("min_size", "0")) if self.kwargs.get("min_size") else 0,
                    trash=self.kwargs.get("trash", False),
                    interactive=self.kwargs.get("interactive", False),
                    parallel=False if self.kwargs.get("interactive", False) else self.kwargs.get("parallel", False)
                )
                self.progress_update.emit(90)  # Show progress near completion
                result["count"] = count
                result["saved"] = saved
                
                if report_path:
                    items = []
                    for path, size, status in deleted_items:
                        items.append({
                            "path": path,
                            "size": format_size(size),
                            "status": status
                        })
                    
                    self.report_data["sections"].append({
                        "title": "Empty Directories",
                        "items": items
                    })
                    
                if count > 0:
                    self.log_update.emit(f"\nFound and deleted {count} empty directories")
                else:
                    self.log_update.emit(f"\nNo empty directories found matching your criteria.")
            
            # Generate report if requested
            if report_path:
                self.report_data["total_space"] = format_size(result["saved"])
                generated_file = generate_html_report(self.report_data, report_path)
                result["report_path"] = generated_file
            
            # Restore original delete_directory function if we replaced it
            if interactive:
                import directory_cleaner.directory_cleaner.core.dir_operations as dir_ops
                dir_ops.delete_directory = original_delete_directory
            
            # Restore original print function
            builtins.print = original_print
            
        except Exception as e:
            result["error"] = str(e)
            tb = traceback.format_exc()
            self.log_update.emit(f"Error: {e}\n{tb}")
        
        # Signal that the operation is complete
        self.operation_complete.emit(result)

    def set_confirmation_result(self, confirmed):
        """Set the confirmation result and continue processing"""
        self.interactive_helper.confirmation_result = confirmed
        self.interactive_helper.wait_for_confirmation.emit("", 0)  # This will unblock the waiting thread

    def update_progress_percent(self, percent):
        """Update progress as a percentage"""
        self.progress_update.emit(percent)
    
    def increment_progress(self, current, total):
        """Update progress based on items processed"""
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_update.emit(percent)
    
    def scan_only(self, operation, **kwargs):
        """Scan without deleting and return results for selection"""
        self.progress_update.emit(10)
        
        # Get directory from kwargs instead of as a positional argument
        directory = kwargs.get("directory")
        
        if operation == "node_modules":
            paths = []
            # Find all node_modules paths
            for root, dirs, _ in os.walk(directory, topdown=False):
                if 'node_modules' in dirs:
                    node_modules_path = os.path.join(root, 'node_modules')
                    node_modules_path = normalize_path(node_modules_path)
                    if should_process(node_modules_path, kwargs.get('exclude'), 
                                    kwargs.get('older_than'), 
                                    parse_size(kwargs.get("min_size", "0")) if kwargs.get("min_size") else 0):
                        size = get_dir_size(node_modules_path)
                        paths.append((node_modules_path, size, "node_modules"))
            
            self.scan_complete.emit(paths)
            return paths
            
        elif operation == "pattern":
            pattern = kwargs.get("pattern")
            paths = []
            
            # Find all pattern matches
            for root, dirs, _ in os.walk(directory, topdown=True):
                matching_dirs = [d for d in dirs if fnmatch.fnmatch(d, pattern)]
                for d in matching_dirs:
                    full_path = os.path.join(root, d)
                    full_path = normalize_path(full_path)
                    if should_process(full_path, kwargs.get('exclude'), 
                                    kwargs.get('older_than'), 
                                    parse_size(kwargs.get("min_size", "0")) if kwargs.get("min_size") else 0):
                        size = get_dir_size(full_path)
                        paths.append((full_path, size, f"pattern:{pattern}"))
                    
                    # Avoid descending into directories we've found
                    dirs.remove(d)
            
            self.scan_complete.emit(paths)
            return paths
            
        elif operation == "subdirs":
            paths = []
            
            # Find all immediate subdirectories
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                item_path = normalize_path(item_path)
                if os.path.isdir(item_path) and should_process(item_path, kwargs.get('exclude'), 
                                                            kwargs.get('older_than'), 
                                                            parse_size(kwargs.get("min_size", "0")) if kwargs.get("min_size") else 0):
                    size = get_dir_size(item_path)
                    paths.append((item_path, size, "subdir"))
            
            self.scan_complete.emit(paths)
            return paths
            
        elif operation == "empty_dirs":
            paths = []
            
            # Find all empty directories
            empty_dirs = find_empty_directories(directory, kwargs.get('exclude'))
            for path in empty_dirs:
                size = 0  # Empty directories are 0 bytes
                paths.append((path, size, "empty"))
            
            self.scan_complete.emit(paths)
            return paths

        elif operation == "discover":
            paths = []
            
            # Run the discovery function
            opportunities = find_cleaning_opportunities(directory)
            
            # Flatten all opportunities for the selection UI
            for category, items in opportunities.items():
                for path, size in items:
                    paths.append((path, size, category))
            
            self.scan_complete.emit(paths)
            return paths
        
        self.progress_update.emit(90)
        return []

    def delete_selected_items(self, items, dry_run=False, trash=False, interactive=False):
        """Delete a list of selected items"""
        total_size = 0
        count = 0
        deleted_items = []
        
        for path, size, category in items:
            self.progress_update.emit(int((count / len(items)) * 100))
            
            # Use our custom delete function for interactive mode
            if interactive:
                result_size = self.custom_delete_directory(path, dry_run, trash, interactive)
            else:
                result_size = delete_directory(path, dry_run, trash, interactive)
                
            if result_size > 0:
                count += 1
                total_size += result_size
                deleted_items.append((path, result_size, "Deleted" if not dry_run else "Would delete"))
        
        return count, total_size, deleted_items

    def delete_selected_items_and_emit(self, items, **kwargs):
        """Delete selected items and emit results"""
        try:
            count, saved, deleted_items = self.delete_selected_items(
                items,
                dry_run=kwargs.get("dry_run", False),
                trash=kwargs.get("trash", False),
                interactive=kwargs.get("interactive", False)
            )
            
            result = {
                "count": count,
                "saved": saved
            }
            
            # Create report if requested
            report_path = kwargs.get("report_path")
            if report_path:
                report_items = []
                for path, size, status in deleted_items:
                    report_items.append({
                        "path": path,
                        "size": format_size(size),
                        "status": status
                    })
                
                self.report_data["sections"].append({
                    "title": "Selected Items",
                    "items": report_items
                })
                
                self.report_data["total_space"] = format_size(saved)
                generated_file = generate_html_report(self.report_data, report_path)
                result["report_path"] = generated_file
            
            self.operation_complete.emit(result)
        except Exception as e:
            self.log_update.emit(f"Error: {e}")
            self.operation_complete.emit({"error": str(e)})