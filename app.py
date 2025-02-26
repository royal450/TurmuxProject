import os
import yt_dlp
from flask import Flask, request, jsonify, send_file, render_template, url_for
from flask_cors import CORS
from flask_socketio import SocketIO
from urllib.parse import urlparse

# ✅ Flask App Setup (Static Folder Disabled)
app = Flask(__name__, template_folder="templates", static_folder=None)  # Static folder disable
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ✅ Download Folder Setup (Koyeb Compatible)
DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# ✅ Validate Instagram URL
def validate_instagram_url(url):
    """
    Instagram URLs को चेक करना कि क्या वो वैध पोस्ट, रील, स्टोरी या IGTV से संबंधित हैं।
    """
    try:
        parsed_url = urlparse(url)
        if "instagram.com" not in parsed_url.netloc:
            return None  # यह इंस्टाग्राम URL नहीं है
        path = parsed_url.path.strip("/").split("/")
        if path[0] == "p":
            return "Post"
        elif path[0] == "reel":
            return "Reel"
        elif path[0] == "stories":
            return "Story"
        elif path[0] == "tv":
            return "IGTV"
        return None  # अमान्य पथ
    except Exception:
        return None  # URL पार्सिंग में कोई समस्या

# ✅ Download Instagram Video
def download_instagram_video(url):
    """
    yt-dlp का उपयोग करके Instagram वीडियो डाउनलोड करना और प्रगति ट्रैक करना।
    """
    def progress_hook(d):
        """
        डाउनलोड प्रगति को फ्रंटेंड तक भेजना (SocketIO के माध्यम से)।
        """
        if d["status"] == "downloading":
            progress = d.get("_percent_str", "0%")
            socketio.emit("download_progress", {"progress": progress})  # प्रगति भेजें

    try:
        # yt-dlp विकल्प
        ydl_opts = {
            "outtmpl": f"{DOWNLOAD_FOLDER}/%(title)s.%(ext)s",  # डाउनलोड फाइल के लिए टेम्पलेट
            "format": "bestvideo+bestaudio/best",  # सर्वोत्तम वीडियो और ऑडियो प्रारूप
            "quiet": False,  # False करने पर लॉग दिखाई देंगे
            "progress_hooks": [progress_hook],  # प्रगति ट्रैक करने के लिए हुक
            "cookiefile": "cookies.txt",  # कुकीज़ फ़ाइल का उपयोग (वैकल्पिक)
            "username": "your_instagram_username",  # इंस्टाग्राम क्रेडेंशियल्स (वैकल्पिक)
            "password": "your_instagram_password"   # इंस्टाग्राम क्रेडेंशियल्स (वैकल्पिक)
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)  # फाइल का नाम प्राप्त करें
            return {
                "title": info.get("title", "Unknown Video"),
                "description": info.get("description", "No Description"),
                "thumbnail": info.get("thumbnail", ""),
                "filename": filename
            }
    except Exception as e:
        print(f"❌ वीडियो डाउनलोड करने में समस्या: {e}")
        return None  # अगर कोई समस्या आती है तो

# ✅ Home Page
@app.route('/')
def index():
    return render_template("index.html")  # होमपेज रेंडर करें

# ✅ Download API
@app.route('/download', methods=['POST'])
def download():
    """
    URL प्राप्त करता है, उसे वैधता की जांच करता है, और डाउनलोड शुरू करता है।
    डाउनलोड की स्थिति और डाउनलोड पेज पर रीडायरेक्ट करता है।
    """
    data = request.json
    url = data.get("url")

    if not url:
        return jsonify({'success': False, 'message': '⚠️ URL आवश्यक है'}), 400  # URL आवश्यक है

    content_type = validate_instagram_url(url)
    if not content_type:
        return jsonify({'success': False, 'message': '❌ अवैध Instagram URL'}), 400  # अवैध URL

    socketio.emit("download_status", {"status": "डाउनलोड शुरू हो गया..."})  # डाउनलोड शुरू होने की स्थिति

    video_data = download_instagram_video(url)
    
    if not video_data:
        socketio.emit("download_status", {"status": "डाउनलोड विफल!"})  # डाउनलोड विफल होने की स्थिति
        return jsonify({'success': False, 'message': '❌ डाउनलोड विफल'}), 500

    socketio.emit("download_status", {"status": "✅ डाउनलोड पूरा!"})  # डाउनलोड पूरा होने की स्थिति

    # सही रीडायरेक्ट URL
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
    डाउनलोड पेज को रेंडर करता है, जिसमें फाइल की जानकारी और डाउनलोड लिंक प्रदान किया जाता है।
    """
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(file_path):
        return "❌ फाइल नहीं मिली", 404  # फाइल नहीं मिली

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
    डाउनलोड की गई वीडियो फाइल को उपयोगकर्ता को डाउनलोड करने के लिए भेजता है।
    """
    return send_file(f"{DOWNLOAD_FOLDER}/{filename}", as_attachment=True)  # फाइल को अटैचमेंट के रूप में भेजें

# ✅ Main Execution (Koyeb Compatible)
if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))  # Koyeb-friendly execution
