from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re
import time
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all domains

# Secure API Key from .env file
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError("API Key not found! Set it in the .env file.")

# Rate Limit File
RATE_LIMIT_FILE = "rate_limit.json"

# Ensure rate limit file exists
if not os.path.exists(RATE_LIMIT_FILE):
    with open(RATE_LIMIT_FILE, "w") as f:
        json.dump({}, f)

# Load Rate Limit Data
with open(RATE_LIMIT_FILE, "r") as f:
    rate_limit_data = json.load(f)

# Function to Save Data to JSON
def save_rate_limit():
    with open(RATE_LIMIT_FILE, "w") as f:
        json.dump(rate_limit_data, f)

# Function to Check Rate Limit
def rate_limiter(ip):
    current_time = time.time()

    if ip in rate_limit_data:
        attempts, first_attempt_time = rate_limit_data[ip]

        # Reset after 24 hours
        if current_time - first_attempt_time > 86400:
            rate_limit_data[ip] = [1, current_time]
            save_rate_limit()
        elif attempts >= 5:
            return False
        else:
            rate_limit_data[ip][0] += 1
            save_rate_limit()
    else:
        rate_limit_data[ip] = [1, current_time]
        save_rate_limit()
    return True

# Root Route: Check API Status
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "YouTube Channel Data API is Running!", "status": "OK"}), 200

# Extract Channel ID from URL
def extract_channel_id(url):
    if "channel/" in url:
        return url.split("channel/")[-1].split("/")[0]
    elif "user/" in url:
        username = url.split("user/")[-1].split("/")[0]
        user_info = requests.get(
            f"https://www.googleapis.com/youtube/v3/channels?part=id&forUsername={username}&key={API_KEY}"
        ).json()
        return user_info["items"][0]["id"] if user_info["items"] else None
    elif "youtube.com/@" in url:
        handle = re.search(r"youtube\.com/@([^/?]+)", url)
        if handle:
            handle_name = handle.group(1)
            res = requests.get(
                f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={handle_name}&type=channel&key={API_KEY}"
            ).json()
            return res["items"][0]["snippet"]["channelId"] if res["items"] else None
    return None

# Fetch Channel Data API
@app.route("/fetch_channel_data", methods=["POST"])
def fetch_channel_data():
    ip = request.remote_addr
    if not rate_limiter(ip):
        return jsonify({"error": "Rate limit exceeded. Try again after 24 hours."}), 429

    body = request.json
    channel_url = body.get("channel_url")

    # Validate URL
    if not channel_url or not re.match(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.*$", channel_url):
        return jsonify({"error": "Invalid URL format"}), 400

    # Extract Channel ID
    channel_id = extract_channel_id(channel_url)
    if not channel_id:
        return jsonify({"error": "Invalid channel URL"}), 400

    # Fetch Data from YouTube API
    url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics,brandingSettings&id={channel_id}&key={API_KEY}"
    response = requests.get(url).json()

    if not response.get("items"):
        return jsonify({"error": "Channel not found"}), 404

    channel_data = response["items"][0]
    snippet = channel_data["snippet"]
    stats = channel_data["statistics"]
    branding = channel_data.get("brandingSettings", {}).get("image", {})

    # Get Thumbnails & Banner URL
    thumbnail_url = snippet["thumbnails"].get("maxres", {}).get("url") or \
                    snippet["thumbnails"].get("high", {}).get("url") or \
                    snippet["thumbnails"].get("medium", {}).get("url") or \
                    snippet["thumbnails"].get("default", {}).get("url")

    banner_url = branding.get("bannerExternalUrl") or branding.get("bannerImageUrl") or ""

    result = {
        "channel_id": channel_id,
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "published_at": snippet.get("publishedAt"),
        "country": snippet.get("country", "N/A"),
        "thumbnail": thumbnail_url,
        "banner_url": banner_url,
        "subscribers": stats.get("subscriberCount"),
        "total_views": stats.get("viewCount"),
        "total_videos": stats.get("videoCount"),
        "custom_url": snippet.get("customUrl", "N/A"),
        "full_json_response": channel_data
    }

    return jsonify(result), 200

# Run app locally
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
