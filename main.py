import os
import time
import ffmpeg
from flask import Flask, jsonify, request, send_file, abort
from flask_cors import CORS
from threading import Thread, Lock

# Configure the external hard drive directory
MEDIA_DIR = "/Volumes/Expansion/Media"  # Replace with your external drive's path

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

file_index = []  # Flat list for files
index_lock = Lock()  # To safely update the file index
last_scanned_time = 0  # Timestamp of the last scan
MAX_PAGE_SIZE = 100  # Set a reasonable max page size

EXCLUDED_FOLDERS = ["Games"]  # Folders to exclude
ALLOWED_EXTENSIONS = {  # Set of allowed video file extensions
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".mpg", ".mpeg", ".3gp", ".ogv", ".mpeg4", ".m4v", ".ts", 
    ".vob", ".rm", ".rmvb", ".asf", ".f4v", ".gif"
}


def get_video_resolution(file_path):
    """Get the resolution (width x height) of a video file using ffmpeg."""
    try:
        # Probe the video file for metadata
        probe = ffmpeg.probe(file_path, v='error', select_streams='v:0', show_entries='stream=width,height')
        # Extract the width and height
        width = probe['streams'][0]['width']
        height = probe['streams'][0]['height']
        return f"{width}x{height}"
    except ffmpeg.Error as e:
        print(f"Error getting resolution for {file_path}: {e}")
        return "Unknown"


def scan_files():
    """Scan files and update the cache with detailed logging, excluding certain folders and hidden files."""
    global file_index, last_scanned_time
    with index_lock:
        print(f"Starting scan of directory: {MEDIA_DIR}")
        temp_index = []
        file_count = 0

        for root, _, files in os.walk(MEDIA_DIR):
            # Extract folder name (Movies, Series, Videos, etc.)
            relative_path = os.path.relpath(root, MEDIA_DIR)
            folder_name = relative_path.split(os.sep)[0]  # Top-level folder

            # Skip excluded folders
            if folder_name in EXCLUDED_FOLDERS:
                print(f"Skipping folder: {folder_name}")
                continue

            for file in files:
                # Skip hidden files (those starting with '._')
                if file.startswith("._"):
                    print(f"Skipping hidden file: {file}")
                    continue

                file_path = os.path.join(root, file)
                try:
                    # Extract file extension
                    ext = os.path.splitext(file)[-1].lower()

                    # Add file only if it matches one of the allowed extensions
                    if ext in ALLOWED_EXTENSIONS:
                        # Get resolution for video files
                        resolution = "N/A"
                        if ext in [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"]:
                            resolution = get_video_resolution(file_path)

                        # Add file metadata with folder, extension, and resolution
                        file_metadata = {
                            "name": file,
                            "path": file_path,
                            "folder": folder_name,
                            "ext": ext,
                            "size": os.path.getsize(file_path),
                            "resolution": resolution
                        }
                        temp_index.append(file_metadata)
                        file_count += 1
                        print(f"Indexed file: {file_metadata}")
                except Exception as e:
                    print(f"Error accessing file: {file_path} - {e}")

        file_index = temp_index
        last_scanned_time = time.time()
        print(f"Scan complete: {file_count} files indexed.")


@app.route('/files', methods=['GET'])
def get_files():
    """List all media files that match the allowed extensions, with optional filters."""
    print("Fetching file list...")
    global last_scanned_time

    # Rescan only if cache is older than 30 seconds
    if time.time() - last_scanned_time > 30:
        scan_files()

    # Get filtering parameters from the request
    folder_filter = request.args.get('folder', '').lower()
    name_filter = request.args.get('name', '').lower()

    # Filter the file index based on the folder and name filters
    with index_lock:
        filtered_files = [
            file for file in file_index
            if (folder_filter in file['folder'].lower() and name_filter in file['name'].lower())
        ]

    return jsonify(filtered_files)


@app.route('/stream', methods=['GET'])
def stream_file():
    """Stream a specific file."""
    file_path = request.args.get('path')
    if not file_path or not os.path.exists(file_path):
        return abort(404, description="File not found")

    # Return the file as an attachment
    return send_file(file_path, as_attachment=False)


# Background thread to periodically update the file index
def start_file_scanner(interval=300):
    while True:
        scan_files()
        time.sleep(interval)


if __name__ == "__main__":
    # Initial scan
    scan_files()

    # Start the background scanner thread
    scanner_thread = Thread(target=start_file_scanner, daemon=True)
    scanner_thread.start()

    # Start the Flask server
    app.run(host="0.0.0.0", port=8000)
