#!/usr/bin/env python
"""
Directory Cleaner - A tool for efficiently cleaning and managing directories.

This module serves as the entry point to the application.
"""

import sys
from PyQt5.QtWidgets import QApplication

# Import from the correct package structure
from directory_cleaner.directory_cleaner.gui.main_window import MainWindow


def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()