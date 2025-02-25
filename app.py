import os
import secrets
import yt_dlp
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from flask_socketio import SocketIO
from urllib.parse import urlparse

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuration
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Master API Key
MASTER_API_KEY = "ROYALDEV_SUPER_KEY"

# API Key Database
api_keys = {}

# Generate API Key
def generate_api_key(user_id, months=1):
    api_key = secrets.token_hex(16)  # 32-char hex API Key
    expiry_date = datetime.now() + timedelta(days=months * 30)
    api_keys[api_key] = {"user_id": user_id, "expiry": expiry_date}
    return api_key

# Validate API Key
def validate_api_key(api_key):
    if api_key == MASTER_API_KEY:
        return True  # Master API Key is always valid
    if api_key in api_keys:
        return datetime.now() < api_keys[api_key]["expiry"]  # Check expiry
    return False

# Validate Instagram URL
def validate_instagram_url(url):
    try:
        parsed_url = urlparse(url)
        if "instagram.com" not in parsed_url.netloc:
            return None
        path = parsed_url.path.strip("/").split("/")
        if path[0] == "p":
            return "Post"
        elif path[0] == "reel":
            return "Reel"
        elif path[0] == "stories":
            return "Story"
        elif path[0] == "tv":
            return "IGTV"
        return None
    except Exception:
        return None

# Download Instagram Video
def download_instagram_video(url):
    try:
        ydl_opts = {
            "outtmpl": f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
            "format": "bestvideo+bestaudio/best",
            "quiet": True  # Disable logs
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return {
                "title": info.get("title", "Unknown Video"),
                "filename": filename
            }
    except Exception as e:
        print(f"Error downloading video: {e}")
        return None

# Home Page
@app.route('/')
def index():
    return render_template("index.html")

# Generate API Key Page
@app.route('/generate_api', methods=['GET', 'POST'])
def generate_api_page():
    if request.method == 'POST':
        user_id = request.form.get("user_id")
        months = int(request.form.get("months", 1))  # Default 1 month
        if not user_id:
            return jsonify({"success": False, "message": "User ID required!"}), 400
        
        api_key = generate_api_key(user_id, months)
        return jsonify({"api_key": api_key, "expiry": api_keys[api_key]["expiry"].strftime("%Y-%m-%d")})
    return render_template("generate_api.html")

# API Key Page
@app.route('/api_key')
def api_key_page():
    return render_template("api_key.html")

# Download Page
@app.route('/download_page')
def download_page():
    return render_template("download.html")

# Download API (API Key Required)
@app.route('/download', methods=['POST'])
def download():
    api_key = request.headers.get("X-API-KEY")  # API Key Header

    if not validate_api_key(api_key):
        return jsonify({"success": False, "message": "Invalid or Expired API Key!"}), 401

    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({'success': False, 'message': 'URL is required'}), 400

    video_data = download_instagram_video(url)
    
    if not video_data:
        return jsonify({'success': False, 'message': 'Download failed'}), 500

    return jsonify({
        'success': True,
        'file_url': f"{request.host_url}downloaded/{os.path.basename(video_data['filename'])}"
    })

# Serve Downloaded Files
@app.route('/downloaded/<filename>')
def serve_file(filename):
    filepath = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        return jsonify({"success": False, "message": "File not found"}), 404
    return send_file(filepath, as_attachment=True)

# Run the App
if __name__ == '__main__':
    socketio.run(app, debug=False, port=5000)
    
