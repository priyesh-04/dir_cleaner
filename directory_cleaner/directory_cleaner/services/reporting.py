"""
Reporting functionality for Directory Cleaner.

This module provides functions to generate HTML reports of cleaning operations.
"""

import os
import datetime

from directory_cleaner.directory_cleaner.core.file_utils import normalize_path


def generate_html_report(report_data, filename="cleanup_report.html"):
    """Generate an HTML report from cleanup data.
    
    Args:
        report_data (dict): Data to include in the report with format:
            {
                "sections": [
                    {
                        "title": str,
                        "items": [{"path": str, "size": str, "status": str}, ...]
                    },
                    ...
                ],
                "total_space": str
            }
        filename (str): Path where to save the HTML report
        
    Returns:
        str: Path to the saved report file
    """
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