"""
Selection dialog implementation for the Directory Cleaner application.

This module provides a dialog for selecting which items to delete when
using selective deletion mode.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QAbstractItemView, QFrame,
    QGroupBox, QComboBox, QLineEdit
)
from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QIcon, QFont

from directory_cleaner.directory_cleaner.core.file_utils import format_size


class SelectionDialog(QDialog):
    """Dialog for selecting items to delete from scan results."""
    
    def __init__(self, items, parent=None):
        """Initialize the selection dialog.
        
        Args:
            items: List of tuples (path, size, category) representing scan results
            parent: Parent widget
        """
        super().__init__(parent)
        self.items = items
        self.selected_items = []
        
        self.setWindowTitle("Select Items to Delete")
        self.resize(800, 600)
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the dialog UI."""
        # Main layout
        layout = QVBoxLayout(self)
        
        # Header label
        header_label = QLabel(f"Found {len(self.items)} items. Select which ones to delete:")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)
        
        # Filter controls
        filter_group = QGroupBox("Filter Results")
        filter_layout = QHBoxLayout()
        
        # Category filter
        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories")
        
        # Collect unique categories
        categories = sorted(set(category for _, _, category in self.items))
        for category in categories:
            self.category_combo.addItem(category)
            
        filter_layout.addWidget(QLabel("Category:"))
        filter_layout.addWidget(self.category_combo)
        
        # Text filter
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter by path...")
        filter_layout.addWidget(QLabel("Path:"))
        filter_layout.addWidget(self.filter_input)
        
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        
        # Connect filter signals
        self.category_combo.currentIndexChanged.connect(self.apply_filters)
        self.filter_input.textChanged.connect(self.apply_filters)
        
        # Create table for items
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["", "Path", "Size", "Category"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # Set column properties
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setFixedHeight(30)
        
        # Set column widths
        self.table.setColumnWidth(0, 30)  # Checkbox column
        
        layout.addWidget(self.table)
        
        # Selection controls
        controls_layout = QHBoxLayout()
        
        # Selection stats
        self.stats_label = QLabel("0 items selected (0 B)")
        controls_layout.addWidget(self.stats_label)
        
        controls_layout.addStretch()
        
        # Selection buttons
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all)
        controls_layout.addWidget(select_all_btn)
        
        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(self.select_none)
        controls_layout.addWidget(select_none_btn)
        
        layout.addLayout(controls_layout)
        
        # Add separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self.accept)
        self.delete_btn.setStyleSheet("background-color: #f44336; color: white;")
        button_layout.addWidget(self.delete_btn)
        
        layout.addLayout(button_layout)
        
        # Fill table with items
        self.populate_table()
        
    def populate_table(self, filter_text="", filter_category=""):
        """Populate the table with items matching the filters."""
        # Clear table
        self.table.setRowCount(0)
        
        # Add filtered items
        for row, (path, size, category) in enumerate(self.items):
            # Apply filters
            if filter_category and filter_category != "All Categories" and category != filter_category:
                continue
                
            if filter_text and filter_text.lower() not in path.lower():
                continue
                
            # Add row
            self.table.insertRow(row)
            
            # Checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(False)
            checkbox.stateChanged.connect(self.update_selected_count)
            
            checkbox_cell = QTableWidgetItem()
            checkbox_cell.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            
            self.table.setItem(row, 0, checkbox_cell)
            self.table.setCellWidget(row, 0, checkbox)
            
            # Path
            path_item = QTableWidgetItem(path)
            self.table.setItem(row, 1, path_item)
            
            # Size
            size_item = QTableWidgetItem(format_size(size))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, size_item)
            
            # Category
            category_item = QTableWidgetItem(category)
            self.table.setItem(row, 3, category_item)
            
        # Update column sizes
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(1, max(300, self.table.columnWidth(1)))
    
    def apply_filters(self):
        """Apply current filters to the table."""
        filter_text = self.filter_input.text()
        filter_category = self.category_combo.currentText()
        
        self.populate_table(filter_text, filter_category)
        self.update_selected_count()
    
    def select_all(self):
        """Select all items currently visible in the table."""
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            checkbox.setChecked(True)
    
    def select_none(self):
        """Deselect all items."""
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            checkbox.setChecked(False)
    
    def update_selected_count(self):
        """Update the count of selected items."""
        count = 0
        size = 0
        
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                count += 1
                # Extract size from the item text (e.g., "10.50 MB" -> need to convert back to bytes)
                # For simplicity, we'll use the original size from self.items
                path = self.table.item(row, 1).text()
                for item_path, item_size, _ in self.items:
                    if item_path == path:
                        size += item_size
                        break
        
        self.stats_label.setText(f"{count} items selected ({format_size(size)})")
        self.delete_btn.setEnabled(count > 0)
    
    def get_selected_items(self):
        """Get the selected items as a list of (path, size, category) tuples."""
        selected = []
        
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                path = self.table.item(row, 1).text()
                
                # Find the original item to get exact size and category
                for item_path, item_size, item_category in self.items:
                    if item_path == path:
                        selected.append((item_path, item_size, item_category))
                        break
        
        return selected