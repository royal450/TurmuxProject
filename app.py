import os
import yt_dlp
from flask import Flask, request, jsonify, send_file, render_template, url_for
from flask_cors import CORS
from flask_socketio import SocketIO
from urllib.parse import urlparse

# ✅ Flask App Setup (Static Folder Disabled)
app = Flask(__name__, template_folder="templates", static_folder=None)  # Disable static folder
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ✅ Download Folder Setup (Koyeb Compatible)
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# ✅ Validate Instagram URL
def validate_instagram_url(url):
    """
    Validates Instagram URLs to check if they belong to a valid post, reel, story, or IGTV.
    """
    try:
        parsed_url = urlparse(url)
        if "instagram.com" not in parsed_url.netloc:
            return None  # Not an Instagram URL
        path = parsed_url.path.strip("/").split("/")
        if path[0] == "p":
            return "Post"
        elif path[0] == "reel":
            return "Reel"
        elif path[0] == "stories":
            return "Story"
        elif path[0] == "tv":
            return "IGTV"
        return None  # Invalid path
    except Exception:
        return None  # Exception in URL parsing

# ✅ Download Instagram Video
def download_instagram_video(url):
    """
    Downloads the Instagram video from the given URL using yt-dlp and tracks progress.
    """
    def progress_hook(d):
        """
        Sends download progress to the frontend via SocketIO.
        """
        if d["status"] == "downloading":
            progress = d.get("_percent_str", "0%")
            socketio.emit("download_progress", {"progress": progress})  # Emit progress

    try:
        # yt-dlp options
        ydl_opts = {
            "outtmpl": f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",  # Template for downloaded files
            "format": "bestvideo+bestaudio/best",  # Best video and audio format
            "quiet": False,  # Set to False to show logs
            "progress_hooks": [progress_hook],  # Hook to track progress
            "cookiefile": "cookies.txt",  # Add this to use cookies file (optional)
            "username": "your_instagram_username",  # Use your credentials for login (optional)
            "password": "your_instagram_password"   # Use your credentials for login (optional)
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)  # Get the filename
            return {
                "title": info.get("title", "Unknown Video"),
                "description": info.get("description", "No Description"),
                "thumbnail": info.get("thumbnail", ""),
                "filename": filename
            }
    except Exception as e:
        print(f"❌ Error downloading video: {e}")
        return None  # Error occurred

# ✅ Home Page
@app.route('/')
def index():
    return render_template("index.html")  # Renders the homepage

# ✅ Download API
@app.route('/download', methods=['POST'])
def download():
    """
    Accepts a POST request with the URL, validates, and starts the download.
    Returns download status and redirects to the download page.
    """
    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({'success': False, 'message': '⚠️ URL is required'}), 400  # URL is required

    content_type = validate_instagram_url(url)
    if not content_type:
        return jsonify({'success': False, 'message': '❌ Invalid Instagram URL'}), 400  # Invalid URL

    socketio.emit("download_status", {"status": "Downloading started..."})  # Emit download start status

    video_data = download_instagram_video(url)
    
    if not video_data:
        socketio.emit("download_status", {"status": "Download failed!"})  # Emit download failure status
        return jsonify({'success': False, 'message': '❌ Download failed'}), 500

    socketio.emit("download_status", {"status": "✅ Download complete!"})  # Emit download complete status

    return jsonify({
        'success': True,
        'redirect_url': url_for('download_page', 
                                filename=os.path.basename(video_data["filename"]),
                                title=video_data["title"],
                                description=video_data["description"],
                                thumbnail=video_data["thumbnail"]),
        'file_url': f"/downloaded/{os.path.basename(video_data['filename'])}"
    })

# ✅ Download Page
@app.route('/download-page/<filename>')
def download_page(filename):
    """
    Renders the download page with the file info and provides the download link.
    """
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        return "❌ File Not Found", 404  # File not found

    title = request.args.get("title", "Unknown Video")
    description = request.args.get("description", "No Description")
    thumbnail = request.args.get("thumbnail", "")

    return render_template("download.html", 
                           filename=filename, 
                           file_url=f"/downloaded/{filename}", 
                           title=title, 
                           description=description,
                           thumbnail=thumbnail)

# ✅ Serve Downloaded Files (Static Access for Koyeb)
@app.route('/downloaded/<filename>')
def serve_file(filename):
    """
    Serve the downloaded video file for user download.
    """
    return send_file(f"{DOWNLOAD_FOLDER}/{filename}", as_attachment=True)  # Send file as attachment

# ✅ Main Execution (Koyeb Compatible)
if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))  # Koyeb-friendly execution
