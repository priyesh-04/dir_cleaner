import sys
import os
import webbrowser
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QTreeView, QTextEdit, 
                            QProgressBar, QFileDialog, QLabel, QComboBox, 
                            QCheckBox, QTabWidget, QLineEdit, QSpinBox,
                            QListWidget, QListWidgetItem, QAbstractItemView,
                            QGroupBox, QRadioButton, QSplitter, QMessageBox,
                            QStatusBar, QToolBar, QAction, QMenu, QSizePolicy,
                            QFormLayout, QDoubleSpinBox, QGridLayout, QStyle,
                            QFrame, QDialog, QTableWidget, QTableWidgetItem,
                            QHeaderView)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QSize, QDir, QTimer
from PyQt5.QtGui import QIcon, QFont, QPixmap, QTextCursor

# Import the worker thread implementation
from worker import WorkerThread

# Import the existing functionality 
import dir_cleaner

# Add to the imports at the top
import json
import datetime
from pathlib import Path

class DirCleanerWindow(QMainWindow):
    """Main application window"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Directory Cleaner")
        self.resize(1200, 800)
        self.setWindowIcon(QIcon(self.style().standardIcon(QStyle.SP_TrashIcon)))
        
        # Initialize variables
        self.current_directory = None
        self.current_operation = None
        self.worker_thread = None
        self.config_file = os.path.join(os.path.expanduser("~"), ".dircleaner_config.json")
        
        # Load saved configuration
        self.load_config()
        
        # Set up the UI components
        self.setup_ui()
        self.create_menu()
        
        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")
        
        # Connect signals
        self.connect_signals()
        
    def load_config(self):
        """Load configuration from file"""
        self.config = {
            "last_directory": os.path.expanduser("~"),
            "last_report_directory": os.path.expanduser("~")
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                    # Update config with loaded values
                    self.config.update(loaded_config)
                    
                    # Validate that the last directory still exists
                    if not os.path.exists(self.config["last_directory"]):
                        self.config["last_directory"] = os.path.expanduser("~")
        except Exception as e:
            print(f"Error loading config: {e}")
    
    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f)
        except Exception as e:
            print(f"Error saving config: {e}")
        
    def setup_ui(self):
        """Set up the user interface"""
        # Main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Horizontal split between operation panel and results
        hsplitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(hsplitter)
        
        # Left panel - Operations
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        hsplitter.addWidget(left_panel)
        
        # Directory selection
        dir_group = QGroupBox("Directory Selection")
        dir_layout = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setReadOnly(True)
        self.dir_edit.setPlaceholderText("Select a directory...")
        dir_browse_btn = QPushButton("Browse...")
        dir_browse_btn.clicked.connect(self.browse_directory)
        dir_layout.addWidget(self.dir_edit)
        dir_layout.addWidget(dir_browse_btn)
        dir_group.setLayout(dir_layout)
        left_layout.addWidget(dir_group)
        
        # Operation selection
        op_group = QGroupBox("Operation")
        op_layout = QVBoxLayout()
        self.op_combo = QComboBox()
        self.op_combo.addItems([
            "Delete Node Modules",
            "Delete Subdirectories",
            "Delete Empty Directories", # Added new option
            "Delete by Pattern",
            "Analyze Disk Usage",
            "Discover Cleanup Opportunities",
            "Run Preset"
        ])
        op_layout.addWidget(self.op_combo)
        op_group.setLayout(op_layout)
        left_layout.addWidget(op_group)
        
        # Operation configuration panel (will swap based on selected operation)
        self.config_panel = QTabWidget()
        self.config_panel.setTabPosition(QTabWidget.South)
        
        # Basic options tab
        basic_tab = QWidget()
        
        # Change from FormLayout to VBoxLayout for better organization
        basic_layout = QVBoxLayout(basic_tab)
        
        # Create a form layout for operation-specific inputs
        input_form = QFormLayout()
        
        # Pattern input (for pattern operation)
        self.pattern_layout = QHBoxLayout()
        self.pattern_input = QLineEdit()
        self.pattern_input.setPlaceholderText("e.g. *cache*")
        self.pattern_layout.addWidget(self.pattern_input)
        
        # Preset selection (for preset operation)
        self.preset_layout = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "node-modules",
            "build-artifacts",
            "cache-dirs",
            "temp-files"
        ])
        self.preset_layout.addWidget(self.preset_combo)
        
        # Add these layouts to the form (they'll be shown/hidden as needed)
        self.operation_form = QFormLayout()
        self.operation_form.addRow("Pattern:", self.pattern_layout)
        self.operation_form.addRow("Preset:", self.preset_layout)
        basic_layout.addLayout(self.operation_form)
        
        # Add a separator for visual clarity
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        basic_layout.addWidget(separator)
        
        # Add a "General Options" label
        options_label = QLabel("General Options:")
        options_label.setStyleSheet("font-weight: bold;")
        basic_layout.addWidget(options_label)
        
        # Options that apply to most operations - use vertical box for checkboxes
        checkbox_layout = QVBoxLayout()
        
        self.dry_run_cb = QCheckBox("Dry run (preview only)")
        self.dry_run_cb.setChecked(True)
        checkbox_layout.addWidget(self.dry_run_cb)
        
        self.trash_cb = QCheckBox("Move to trash instead of deleting")
        if not dir_cleaner.TRASH_SUPPORTED:
            self.trash_cb.setEnabled(False)
            self.trash_cb.setToolTip("Install send2trash package to enable this feature")
        checkbox_layout.addWidget(self.trash_cb)
        
        self.interactive_cb = QCheckBox("Interactive mode (confirm each deletion)")
        checkbox_layout.addWidget(self.interactive_cb)
        
        self.parallel_cb = QCheckBox("Use parallel processing (faster)")
        checkbox_layout.addWidget(self.parallel_cb)
        
        self.selective_cb = QCheckBox("Selective mode (choose what to delete from scan results)")
        checkbox_layout.addWidget(self.selective_cb)
        
        # Add checkbox layout to main layout with some spacing
        basic_layout.addLayout(checkbox_layout)
        basic_layout.addStretch(1)  # Add stretch to push everything to the top
        
        self.config_panel.addTab(basic_tab, "Basic")
        
        # Advanced options tab
        advanced_tab = QWidget()
        
        # Use VBoxLayout for advanced tab as well for consistency
        adv_layout = QVBoxLayout(advanced_tab)
        adv_form = QFormLayout()
        
        self.exclude_input = QLineEdit()
        self.exclude_input.setPlaceholderText("e.g. *important*,*backup*")
        adv_form.addRow("Exclude patterns:", self.exclude_input)
        
        self.older_than_spin = QSpinBox()
        self.older_than_spin.setRange(0, 3650)
        self.older_than_spin.setValue(0)
        self.older_than_spin.setSpecialValueText("Any age")
        adv_form.addRow("Older than (days):", self.older_than_spin)
        
        self.min_size_combo = QComboBox()
        self.min_size_combo.addItems(["Any size", "1MB", "10MB", "50MB", "100MB", "500MB", "1GB"])
        adv_form.addRow("Minimum size:", self.min_size_combo)
        
        # Analysis depth for analyze operation
        self.depth_layout = QHBoxLayout()
        self.depth_spin = QSpinBox()
        self.depth_spin.setRange(1, 10)
        self.depth_spin.setValue(3)
        self.depth_layout.addWidget(self.depth_spin)
        adv_form.addRow("Analysis depth:", self.depth_layout)
        
        adv_layout.addLayout(adv_form)
        
        # Add a separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setFrameShadow(QFrame.Sunken)
        adv_layout.addWidget(separator2)
        
        # HTML report section
        report_label = QLabel("Report Options:")
        report_label.setStyleSheet("font-weight: bold;")
        adv_layout.addWidget(report_label)
        
        report_layout = QVBoxLayout()
        
        self.report_cb = QCheckBox("Generate HTML report")
        report_layout.addWidget(self.report_cb)
        
        report_path_layout = QHBoxLayout()
        self.report_path = QLineEdit()
        self.report_path.setPlaceholderText("Report file path (optional)")
        self.report_path.setEnabled(False)
        report_path_layout.addWidget(self.report_path)
        
        report_browse_btn = QPushButton("Browse...")
        report_browse_btn.setEnabled(False)
        report_browse_btn.clicked.connect(self.browse_report_path)
        report_path_layout.addWidget(report_browse_btn)
        
        report_layout.addLayout(report_path_layout)
        
        self.report_cb.toggled.connect(self.report_path.setEnabled)
        self.report_cb.toggled.connect(report_browse_btn.setEnabled)
        
        adv_layout.addLayout(report_layout)
        adv_layout.addStretch(1)  # Add stretch to push everything to the top
        
        self.config_panel.addTab(advanced_tab, "Advanced")
        
        left_layout.addWidget(self.config_panel)
        
        # Run button
        self.run_btn = QPushButton("Run Operation")
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.run_operation)
        self.run_btn.setMinimumHeight(50)
        left_layout.addWidget(self.run_btn)
        
        # Right panel - Results
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        hsplitter.addWidget(right_panel)
        
        # Results area
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout()
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setPlaceholderText("Operation results will appear here...")
        results_layout.addWidget(self.results_text)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)
        results_layout.addWidget(self.progress_bar)
        
        results_group.setLayout(results_layout)
        right_layout.addWidget(results_group)
        
        # Statistics/summary panel
        stats_group = QGroupBox("Summary")
        stats_layout = QGridLayout()
        
        stats_layout.addWidget(QLabel("Items processed:"), 0, 0)
        self.items_label = QLabel("0")
        stats_layout.addWidget(self.items_label, 0, 1)
        
        stats_layout.addWidget(QLabel("Space saved:"), 1, 0)
        self.space_label = QLabel("0 B")
        stats_layout.addWidget(self.space_label, 1, 1)
        
        stats_layout.addWidget(QLabel("Status:"), 2, 0)
        self.status_label = QLabel("Ready")
        stats_layout.addWidget(self.status_label, 2, 1)
        
        stats_group.setLayout(stats_layout)
        right_layout.addWidget(stats_group)
        
        # Open report button
        self.open_report_btn = QPushButton("Open Report")
        self.open_report_btn.setVisible(False)
        self.open_report_btn.clicked.connect(self.open_report)
        right_layout.addWidget(self.open_report_btn)
        
        # Set stretch factors
        hsplitter.setStretchFactor(0, 1)
        hsplitter.setStretchFactor(1, 2)
        
        # Update the UI to show/hide appropriate controls
        self.op_combo.currentIndexChanged.connect(self.update_ui_for_operation)
        self.update_ui_for_operation()
        
        # Set the last used directory if available
        if self.config["last_directory"] and os.path.exists(self.config["last_directory"]):
            self.dir_edit.setText(self.config["last_directory"])
            self.current_directory = self.config["last_directory"]
            self.validate_input()  # Make sure the Run button is enabled if appropriate
    
    def create_menu(self):
        """Create application menu"""
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("&File")
        
        open_action = QAction("&Open Directory", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.browse_directory)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Operations menu
        op_menu = menu_bar.addMenu("&Operations")
        
        for i in range(self.op_combo.count()):
            action = QAction(self.op_combo.itemText(i), self)
            action.triggered.connect(lambda checked, idx=i: self.op_combo.setCurrentIndex(idx))
            op_menu.addAction(action)
        
        # Help menu
        help_menu = menu_bar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def connect_signals(self):
        """Connect signals and slots"""
        self.dir_edit.textChanged.connect(self.validate_input)
        self.op_combo.currentIndexChanged.connect(self.validate_input)
        self.pattern_input.textChanged.connect(self.validate_input)
    
    def validate_input(self):
        """Check if inputs are valid to enable the Run button"""
        # Basic directory check
        if not self.dir_edit.text():
            self.run_btn.setEnabled(False)
            return
            
        # Operation-specific checks
        op_index = self.op_combo.currentIndex()
        if op_index == 3:  # Delete by Pattern (index is 3)
            if not self.pattern_input.text():
                self.run_btn.setEnabled(False)
                return
                
        # If we got here, enable the button
        self.run_btn.setEnabled(True)
    
    def update_ui_for_operation(self):
        """Update UI components based on selected operation"""
        op_index = self.op_combo.currentIndex()
        
        # Hide all operation-specific controls first
        for i in range(self.operation_form.rowCount()):
            self.operation_form.itemAt(i, QFormLayout.LabelRole).widget().setVisible(False)
            self.operation_form.itemAt(i, QFormLayout.FieldRole).layout().itemAt(0).widget().setVisible(False)
        
        # Show controls specific to the selected operation
        if op_index == 3:  # Delete by Pattern (correct index is 3)
            self.operation_form.itemAt(0, QFormLayout.LabelRole).widget().setVisible(True)
            self.operation_form.itemAt(0, QFormLayout.FieldRole).layout().itemAt(0).widget().setVisible(True)
        elif op_index == 6:  # Run Preset (correct index is 6)
            self.operation_form.itemAt(1, QFormLayout.LabelRole).widget().setVisible(True)
            self.operation_form.itemAt(1, QFormLayout.FieldRole).layout().itemAt(0).widget().setVisible(True)
        
        # Validate inputs again
        self.validate_input()
    
    def browse_directory(self):
        """Open directory browser dialog"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory", 
            self.config["last_directory"], 
            QFileDialog.ShowDirsOnly
        )
        if directory:
            self.dir_edit.setText(directory)
            self.current_directory = directory
            
            # Save the selected directory for next time
            self.config["last_directory"] = directory
            self.save_config()
    
    def browse_report_path(self):
        """Open file save dialog for the report path"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Report As", 
            os.path.join(self.config["last_report_directory"], "cleanup_report.html"),
            "HTML Files (*.html)"
        )
        if file_path:
            # Make sure the path ends with .html
            if not file_path.lower().endswith('.html'):
                file_path += '.html'
            self.report_path.setText(file_path)
            
            # Save the report directory for next time
            self.config["last_report_directory"] = os.path.dirname(file_path)
            self.save_config()
    
    def run_operation(self):
        """Run the selected operation with the specified options"""
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.warning(self, "Operation in Progress", 
                               "An operation is already running. Please wait for it to complete.")
            return
        
        # Get all settings
        directory = self.dir_edit.text()
        op_index = self.op_combo.currentIndex()
        operation_name = self.op_combo.currentText()
        
        # Common parameters
        params = {
            "directory": directory,
            "dry_run": self.dry_run_cb.isChecked(),
            "trash": self.trash_cb.isChecked() if dir_cleaner.TRASH_SUPPORTED else False,
            "interactive": self.interactive_cb.isChecked(),
            "parallel": self.parallel_cb.isChecked(),
            "selective": self.selective_cb.isChecked()  # Add selective mode parameter
        }
        
        # Add advanced options if specified
        if self.exclude_input.text():
            params["exclude"] = self.exclude_input.text().split(",")
        
        if self.older_than_spin.value() > 0:
            params["older_than"] = self.older_than_spin.value()
        
        if self.min_size_combo.currentIndex() > 0:
            params["min_size"] = self.min_size_combo.currentText()
        
        # Add a report path if enabled
        if self.report_cb.isChecked():
            if self.report_path.text():
                report_file = self.report_path.text()
                # Make sure it's a file, not a directory
                if not os.path.splitext(report_file)[1]:
                    report_file += ".html"
                params["report_path"] = report_file
                
                # Save the report directory for next time
                self.config["last_report_directory"] = os.path.dirname(report_file)
                self.save_config()
            else:
                # Create a timestamped report in last used report directory
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                report_file = os.path.join(self.config["last_report_directory"], f"cleanup_report_{timestamp}.html")
                params["report_path"] = report_file
        
        # Map the operation to the actual function
        if op_index == 0:  # Delete Node Modules
            operation = "node_modules"
        elif op_index == 1:  # Delete Subdirectories
            operation = "subdirs"
        elif op_index == 2:  # Delete Empty Directories
            operation = "empty_dirs"
        elif op_index == 3:  # Delete by Pattern
            operation = "pattern"
            params["pattern"] = self.pattern_input.text()
        elif op_index == 4:  # Analyze Disk Usage
            operation = "analyze"
            params["depth"] = self.depth_spin.value()
        elif op_index == 5:  # Discover Cleanup Opportunities
            operation = "discover"
        elif op_index == 6:  # Run Preset
            operation = "preset"
            params["preset_name"] = self.preset_combo.currentText()
        
        # Check for interactive and parallel mode conflict
        if params.get("interactive", False) and params.get("parallel", False):
            # Disable parallel mode when interactive is enabled
            params["parallel"] = False
            self.update_log("Note: Parallel processing is disabled in interactive mode")
        
        # Check for selective mode
        if params.get("selective", False):
            # Create and start worker thread for scanning only
            self.worker_thread = WorkerThread(operation, **params)
            self.worker_thread.log_update.connect(self.update_log)
            self.worker_thread.progress_update.connect(self.update_progress)
            self.worker_thread.scan_complete.connect(self.show_selection_dialog)
            
            # Clear results
            self.results_text.clear()
            self.items_label.setText("0")
            self.space_label.setText("0 B")
            self.status_label.setText("Scanning...")
            self.open_report_btn.setVisible(False)
            
            # Show progress bar
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            
            self.update_log(f"Scanning directory: {directory}")
            self.statusBar.showMessage(f"Scanning for {operation_name}...")
            
            # Start scan operation
            self.worker_thread.scan_only(operation, **params)
        else:
            # Clear results
            self.results_text.clear()
            self.items_label.setText("0")
            self.space_label.setText("0 B")
            self.status_label.setText("Running...")
            self.open_report_btn.setVisible(False)
            
            # Show progress bar
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            
            # Create and start worker thread
            self.worker_thread = WorkerThread(operation, **params)
            self.worker_thread.log_update.connect(self.update_log)
            self.worker_thread.progress_update.connect(self.update_progress)
            self.worker_thread.operation_complete.connect(self.operation_completed)
            
            # Connect the confirmation signal if we're in interactive mode
            if params.get("interactive", False):
                self.worker_thread.confirmation_needed.connect(self.show_confirmation_dialog)
            
            self.worker_thread.start()
            self.statusBar.showMessage(f"Running {operation_name}...")
    
    def update_log(self, message):
        """Update the log text with a new message"""
        self.results_text.append(message)
        # Scroll to bottom
        self.results_text.moveCursor(QTextCursor.End)
    
    def update_progress(self, progress):
        """Update the progress bar"""
        self.progress_bar.setValue(progress)
    
    def operation_completed(self, result):
        """Handle completion of an operation"""
        self.progress_bar.setValue(100)
        
        # Update status
        if result.get("error"):
            self.status_label.setText("Error")
            self.update_log(f"Error: {result['error']}")
            self.statusBar.showMessage("Operation failed")
        else:
            self.status_label.setText("Completed")
            self.statusBar.showMessage("Operation completed successfully")
            
            # Update summary
            count = result.get("count", 0)
            self.items_label.setText(str(count))
            
            saved = result.get("saved", 0)
            if saved > 0:
                self.space_label.setText(dir_cleaner.format_size(saved))
            
            # Show report button if a report was generated
            if "report_path" in result and os.path.exists(result["report_path"]):
                self.open_report_btn.setVisible(True)
                self.report_file_path = result["report_path"]
        
        # Hide progress bar after a delay
        QTimer.singleShot(2000, lambda: self.progress_bar.setVisible(False))
        
        # Clean up worker thread
        self.worker_thread = None
    
    def open_report(self):
        """Open the generated HTML report in the default browser"""
        if hasattr(self, "report_file_path") and os.path.exists(self.report_file_path):
            webbrowser.open(f"file://{os.path.abspath(self.report_file_path)}")
    
    def show_confirmation_dialog(self, path, size):
        """Show a confirmation dialog when interactive mode is enabled"""
        size_str = dir_cleaner.format_size(size)
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Confirm Deletion")
        msg_box.setText(f"Delete the following directory?\n\n{path}\n\nSize: {size_str}")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        
        # Make this dialog stay on top
        msg_box.setWindowFlags(msg_box.windowFlags() | Qt.WindowStaysOnTopHint)
        
        # Show the dialog and get the response
        result = msg_box.exec_()
        confirmed = (result == QMessageBox.Yes)
        
        # Send the result back to the worker thread
        self.worker_thread.set_confirmation_result(confirmed)
    
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(self, "About Directory Cleaner",
                         """<h1>Directory Cleaner</h1>
                         <p>A comprehensive utility to clean up development directories.</p>
                         <p>Features:</p>
                         <ul>
                         <li>Delete node_modules folders</li>
                         <li>Delete subdirectories</li>
                         <li>Delete by pattern</li>
                         <li>Analyze disk usage</li>
                         <li>Discover cleanup opportunities</li>
                         <li>Run common cleanup presets</li>
                         </ul>
                         <p>&copy; 2025 Your Name</p>""")

    def closeEvent(self, event):
        """Handle window close event"""
        # Save configuration before closing
        self.save_config()
        event.accept()

    def show_selection_dialog(self, items):
        """Show dialog to let user select which items to delete"""
        if not items:
            self.update_log("No items found matching your criteria.")
            self.operation_completed({"count": 0, "saved": 0})
            return
        
        self.update_log(f"Found {len(items)} items. Showing selection dialog...")
        
        # Create and show the selection dialog
        dialog = SelectionDialog(items, self)
        result = dialog.exec_()
        
        if result == QDialog.Accepted:
            selected_items = dialog.get_selected_items()
            
            if not selected_items:
                self.update_log("No items selected for deletion.")
                self.operation_completed({"count": 0, "saved": 0})
                return
            
            self.update_log(f"Deleting {len(selected_items)} selected items...")
            
            # Get current parameters
            params = {
                "dry_run": self.dry_run_cb.isChecked(),
                "trash": self.trash_cb.isChecked() if dir_cleaner.TRASH_SUPPORTED else False,
                "interactive": self.interactive_cb.isChecked()
            }
            
            # Create a new worker to handle deletions
            self.worker_thread = WorkerThread("selected_items", **params)
            self.worker_thread.log_update.connect(self.update_log)
            self.worker_thread.progress_update.connect(self.update_progress)
            self.worker_thread.operation_complete.connect(self.operation_completed)
            
            # Connect the confirmation signal if we're in interactive mode
            if params.get("interactive", False):
                self.worker_thread.confirmation_needed.connect(self.show_confirmation_dialog)
            
            # Start deleting
            self.worker_thread.start()
            
            # Add a run method to delete_selected_items in WorkerThread class
            self.worker_thread.run = lambda: self.worker_thread.delete_selected_items_and_emit(selected_items, **params)
            
            self.statusBar.showMessage(f"Deleting {len(selected_items)} selected items...")
        else:
            self.update_log("Operation cancelled by user.")
            self.operation_completed({"count": 0, "saved": 0})

class SelectionDialog(QDialog):
    """Dialog for selecting items to delete"""
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Items to Delete")
        self.setMinimumSize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # Create description label
        desc = QLabel("Select the items you want to delete:")
        desc.setStyleSheet("font-weight: bold;")
        layout.addWidget(desc)
        
        # Create table for items
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Select", "Path", "Size", "Type"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table)
        
        # Populate the table
        self.table.setRowCount(len(items))
        
        for i, (path, size, item_type) in enumerate(items):
            # Checkbox for selection
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            checkbox.setCheckState(Qt.Checked)  # Default to checked
            self.table.setItem(i, 0, checkbox)
            
            # Path
            self.table.setItem(i, 1, QTableWidgetItem(path))
            
            # Size
            size_item = QTableWidgetItem(dir_cleaner.format_size(size))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 2, size_item)
            
            # Type
            self.table.setItem(i, 3, QTableWidgetItem(item_type))
        
        # Controls for selecting/deselecting all
        control_layout = QHBoxLayout()
        
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all)
        control_layout.addWidget(select_all_btn)
        
        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self.deselect_all)
        control_layout.addWidget(deselect_all_btn)
        
        # Add sort controls
        sort_label = QLabel("Sort by:")
        control_layout.addWidget(sort_label)
        
        sort_combo = QComboBox()
        sort_combo.addItems(["Path", "Size (largest first)", "Size (smallest first)", "Type"])
        sort_combo.currentIndexChanged.connect(self.sort_items)
        control_layout.addWidget(sort_combo)
        
        layout.addLayout(control_layout)
        
        # Statistics
        stats_layout = QHBoxLayout()
        stats_layout.addWidget(QLabel("Total selected:"))
        self.selected_count = QLabel("0")
        stats_layout.addWidget(self.selected_count)
        
        stats_layout.addWidget(QLabel("Total size:"))
        self.selected_size = QLabel("0 B")
        stats_layout.addWidget(self.selected_size)
        
        layout.addLayout(stats_layout)
        
        # Connect checkbox changes to update statistics
        self.table.itemChanged.connect(self.update_statistics)
        
        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.ok_btn = QPushButton("Delete Selected")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
        button_layout.addWidget(self.ok_btn)
        
        layout.addLayout(button_layout)
        
        # Store the items
        self.items = items
        
        # Initialize statistics
        self.update_statistics()
    
    def select_all(self):
        """Select all items"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            item.setCheckState(Qt.Checked)
    
    def deselect_all(self):
        """Deselect all items"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            item.setCheckState(Qt.Unchecked)
    
    def update_statistics(self):
        """Update the selection statistics"""
        count = 0
        total_size = 0
        
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() == Qt.Checked:
                count += 1
                # Get the size from the original items list as the formatted size in the table can't be parsed
                _, size, _ = self.items[row]
                total_size += size
        
        self.selected_count.setText(str(count))
        self.selected_size.setText(dir_cleaner.format_size(total_size))
        
        # Update the OK button text
        self.ok_btn.setText(f"Delete Selected ({count})")
        
        # Disable the OK button if nothing is selected
        self.ok_btn.setEnabled(count > 0)
    
    def sort_items(self, index):
        """Sort the items by the selected column"""
        self.table.setSortingEnabled(True)
        if index == 0:  # Path
            self.table.sortItems(1)
        elif index == 1:  # Size (largest first)
            self.table.sortItems(2, Qt.DescendingOrder)
        elif index == 2:  # Size (smallest first)
            self.table.sortItems(2, Qt.AscendingOrder)
        elif index == 3:  # Type
            self.table.sortItems(3)
        self.table.setSortingEnabled(False)
    
    def get_selected_items(self):
        """Return the list of selected items"""
        selected = []
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() == Qt.Checked:
                selected.append(self.items[row])
        return selected

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DirCleanerWindow()
    window.show()
    sys.exit(app.exec_())