from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import requests
import re
import time
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="YouTube Channel Data API", version="1.0.0", description="Fetch YouTube channel data using FastAPI")

# CORS: Allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
def rate_limiter(request: Request):
    ip = request.client.host
    current_time = time.time()

    if ip in rate_limit_data:
        attempts, first_attempt_time = rate_limit_data[ip]

        # Reset after 24 hours
        if current_time - first_attempt_time > 86400:
            rate_limit_data[ip] = [1, current_time]
            save_rate_limit()
        elif attempts >= 5:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again after 24 hours.")
        else:
            rate_limit_data[ip][0] += 1
            save_rate_limit()
    else:
        rate_limit_data[ip] = [1, current_time]
        save_rate_limit()

# Root Route: Check API Status
@app.get("/")
def home():
    return {"message": "YouTube Channel Data API is Running!", "status": "OK"}

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
@app.post("/fetch_channel_data")
async def fetch_channel_data(request: Request, data: dict = Depends(rate_limiter)):
    body = await request.json()
    
    # Validate URL
    channel_url = body.get("channel_url")
    if not channel_url or not re.match(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.*$", channel_url):
        raise HTTPException(status_code=400, detail="Invalid URL format")

    # Extract Channel ID
    channel_id = extract_channel_id(channel_url)
    if not channel_id:
        raise HTTPException(status_code=400, detail="Invalid channel URL")

    # Fetch Data from YouTube API
    url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics,brandingSettings&id={channel_id}&key={API_KEY}"
    response = requests.get(url).json()

    if not response.get("items"):
        raise HTTPException(status_code=404, detail="Channel not found")

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

    return result

# Run app with uvicorn (for local testing)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
