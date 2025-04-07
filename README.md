# Directory Cleaner

A powerful utility designed to help developers reclaim disk space by efficiently cleaning development directories.

## Features

- **Delete Node Modules**: Recursively find and remove `node_modules` folders
- **Delete Subdirectories**: Remove immediate subdirectories in a folder
- **Delete Empty Directories**: Find and remove directories with no contents
- **Pattern Matching**: Find directories matching specific patterns
- **Analyze Disk Usage**: Identify which directories are consuming the most space
- **Discover Cleanup Opportunities**: Automatically find potential cleanup targets
- **Preset Cleaning Profiles**: Use predefined cleaning rules

## Safety Features

- **Dry Run Mode**: Preview what would be deleted without actually deleting
- **Move to Trash**: Send files to the recycle bin instead of permanent deletion
- **Interactive Mode**: Confirm each deletion with visual feedback
- **Selective Mode**: Choose exactly which items to delete after scanning
- **Exclusion Patterns**: Protect important directories from deletion
- **Age and Size Filters**: Only process directories meeting specific criteria

## Installation

### From PyPI

```bash
pip install directory-cleaner
```

### From Source

1. Clone the repository:
```bash
git clone https://github.com/directory-cleaner-team/directory-cleaner.git
cd directory-cleaner
```

2. Install the package:
```bash
pip install -e .
```

## Usage

### GUI Mode

```bash
directory-cleaner
```

Launch the graphical interface to interactively clean directories.

### Command Line Interface (CLI)

Basic usage:

```bash
python -m directory_cleaner.main
```

## Project Structure

The project has been organized into a modular structure:

```
directory_cleaner/
├── __init__.py
├── main.py                     # Entry point
├── directory_cleaner/
│   ├── core/                   # Core functionality
│   │   ├── file_utils.py       # File/directory utility functions
│   │   ├── dir_operations.py   # Directory cleaning operations
│   │   └── analysis.py         # Disk usage analysis
│   ├── gui/                    # GUI components
│   │   ├── main_window.py      # Main application window
│   │   └── dialogs/            # Dialog windows
│   │       └── selection_dialog.py  # Item selection dialog
│   └── services/               # Service layer
│       ├── config.py           # Configuration handling
│       ├── reporting.py        # HTML report generation
│       └── worker.py           # Background processing
```

## Requirements

- Python 3.8+
- PyQt5
- send2trash (optional, for trash bin support)
- tqdm (for progress bars)

## License

This project is licensed under the MIT License - see the LICENSE file for details.