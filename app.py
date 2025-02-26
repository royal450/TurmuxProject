import os
import yt_dlp
from flask import Flask, request, jsonify, send_file, render_template, url_for
from flask_cors import CORS
from flask_socketio import SocketIO
from urllib.parse import urlparse

# ✅ Flask App Setup
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ✅ Download Folder Setup (Koyeb पर Compatible)
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# ✅ Validate Instagram URL
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

# ✅ Download Instagram Video
def download_instagram_video(url):
    def progress_hook(d):
        if d["status"] == "downloading":
            progress = d.get("_percent_str", "0%")
            socketio.emit("download_progress", {"progress": progress})

    try:
        ydl_opts = {
            "outtmpl": f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",
            "format": "bestvideo+bestaudio/best",
            "quiet": False,
            "progress_hooks": [progress_hook]
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return {
                "title": info.get("title", "Unknown Video"),
                "description": info.get("description", "No Description"),
                "thumbnail": info.get("thumbnail"),
                "filename": filename
            }
    except Exception as e:
        print(f"❌ Error downloading video: {e}")
        return None

# ✅ Home Page
@app.route('/')
def index():
    return render_template("index.html")

# ✅ Download API
@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({'success': False, 'message': '⚠️ URL is required'}), 400

    content_type = validate_instagram_url(url)
    if not content_type:
        return jsonify({'success': False, 'message': '❌ Invalid Instagram URL'}), 400

    socketio.emit("download_status", {"status": "Downloading started..."})

    video_data = download_instagram_video(url)
    
    if not video_data:
        socketio.emit("download_status", {"status": "Download failed!"})
        return jsonify({'success': False, 'message': '❌ Download failed'}), 500

    socketio.emit("download_status", {"status": "✅ Download complete!"})

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
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        return "❌ File Not Found", 404

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
    return send_file(f"{DOWNLOAD_FOLDER}/{filename}", as_attachment=True)

# ✅ Main Execution (Koyeb Compatible)
if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
