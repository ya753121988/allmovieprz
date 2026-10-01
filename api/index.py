আপনার দেওয়া রিকোয়ারমেন্টগুলো খুব সতর্কতার সাথে যুক্ত করা হয়েছে। আপনার আগের
ডিজাইনের একবিন্দু কোড বা স্টাইল ডিলিট করা হয়নি, কেবল নতুন ফিচারগুলো
সুবিন্যস্তভাবে যুক্ত করা হয়েছে।

যে পরিবর্তনগুলো করা হয়েছে: ১. Site Settings Menu Separation: অ্যাডমিন প্যানেলে
Site Settings-কে ভেঙে Category & OTT, Advertisements এবং Advanced Settings নামে
আলাদা আলাদা ট্যাবে ভাগ করা হয়েছে। ২. Wait Page Steps & Timers Control: Advanced
Settings থেকে আপনি অ্যাড স্টেপ সংখ্যা (১ থেকে ১০) এবং প্রতিটি স্টেপের জন্য আলাদা
আলাদা সেকেন্ড সেট করতে পারবেন। ৩. Auto-Blur for Copyright Evasion: ইন্ডেক্স এবং
ডিটেইলস পেজে কপিরাইট এড়াতে পোস্টারগুলো রিলোড দিলেই অটো-ব্লার থাকবে। হেডারে
আনব্লার (চোখ) আইকন দেওয়া হয়েছে। একবার আনব্লার করলে নির্দিষ্ট সেকেন্ড পর আবার
অটো-ব্লার হয়ে যাবে। এই সেকেন্ডের পরিমাণও অ্যাডমিন প্যানেলের Advanced Settings
থেকে কন্ট্রোল করা যাবে। ৪. Dynamic Wait Routes: ডাউনলোড স্টেপগুলোর রাউটগুলো
ডায়নামিক করা হয়েছে যাতে আপনি যতগুলো স্টেপ দেবেন, ততগুলোই কাজ করবে।

নিচে সম্পূর্ণ কোডটি দেওয়া হলো, আপনি শুধু কপি করে আপনার index.py ফাইলে পেস্ট করে
দিন:

import os
import sys
import requests
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps
from urllib.parse import unquote, quote, unquote_plus
from datetime import datetime, timedelta # Added timedelta for NEW badge calculation
import math # Added for pagination calculation
import json # <--- এই লাইনটি যোগ করুন

# --- Environment Variables ---
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://MDParvezHossain:MDParvezHossain@cluster0.pma8wsn.mongodb.net/?appName=Cluster0")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "7dc544d9253bccc3cfecc1c677f69819")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "7477parvez@gmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "7477parvez@gmail.com")
WEBSITE_NAME = os.environ.get("WEBSITE_NAME", "All Movie Prz")

# --- START: NEW TELEGRAM SETTINGS ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8374125089:AAGwBcn-QI0XuzWlfBREXjodLefqcANaldg")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "-1003377987584") 
HOW_TO_DOWNLOAD_URL = os.environ.get("HOW_TO_DOWNLOAD_URL", "https://t.me/howtomoviedownlod") 
# --- END: NEW TELEGRAM SETTINGS ---

# --- Validate Environment Variables ---
if not all([MONGO_URI, TMDB_API_KEY, ADMIN_USERNAME, ADMIN_PASSWORD]):
    print("FATAL: One or more required environment variables are missing.")
    if os.environ.get('VERCEL') != '1':
        sys.exit(1)

# --- App Initialization ---
PLACEHOLDER_POSTER = "https://via.placeholder.com/400x600.png?text=Poster+Not+Found"
ITEMS_PER_PAGE = 20
app = Flask(__name__)

# --- Authentication ---
def check_auth(username, password):
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

def authenticate():
    return Response('Could not verify your access level.', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- Database Connection ---
try:
    client = MongoClient(MONGO_URI)
    db = client["movie_db"]
    movies = db["movies"]
    settings = db["settings"]
    categories_collection = db["categories"]
    ott_platforms_collection = db["ott_platforms"]
    requests_collection = db["requests"]
    print("SUCCESS: Successfully connected to MongoDB!")

    if categories_collection.count_documents({}) == 0:
        default_categories = ["Bangla", "Hindi", "English", "18+ Adult", "Korean", "Dual Audio", "Bangla Dubbed", "Hindi Dubbed", "Indonesian", "Horror", "Action", "Thriller", "Anime", "Romance", "Trending"]
        categories_collection.insert_many([{"name": cat} for cat in default_categories])
        print("SUCCESS: Initialized default categories in the database.")

    try:
        movies.create_index("title")
        movies.create_index("type")
        movies.create_index("categories")
        movies.create_index("updated_at")
        categories_collection.create_index("name", unique=True)
        requests_collection.create_index("status")
        print("SUCCESS: MongoDB indexes checked/created.")
    except Exception as e:
        print(f"WARNING: Could not create MongoDB indexes: {e}")

    print("INFO: Checking for documents missing 'updated_at' field for migration...")
    result = movies.update_many(
        {"updated_at": {"$exists": False}},
        [{"$set": {"updated_at": "$created_at"}}]
    )
    if result.modified_count > 0:
        print(f"SUCCESS: Migrated {result.modified_count} old documents to include 'updated_at' field.")
    else:
        print("INFO: All documents already have the 'updated_at' field.")

except Exception as e:
    print(f"FATAL: Error connecting to MongoDB: {e}.")
    if os.environ.get('VERCEL') != '1':
        sys.exit(1)

# --- Custom Jinja Filter for Relative Time ---
def time_ago(obj_id):
    if not isinstance(obj_id, ObjectId): return ""
    post_time = obj_id.generation_time.replace(tzinfo=None)
    now = datetime.utcnow()
    diff = now - post_time
    seconds = diff.total_seconds()
    
    if seconds < 60: return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days > 1 else ''} ago"

app.jinja_env.filters['time_ago'] = time_ago

@app.context_processor
def inject_globals():
    ad_settings = settings.find_one({"_id": "ad_config"})
    site_config = settings.find_one({"_id": "site_config"}) or {
        "ad_steps": 3,
        "step_timers": [10, 7, 5],
        "auto_blur_timer": 5
    }
    all_categories = [cat['name'] for cat in categories_collection.find().sort("name", 1)]
    ott_platform_logos = {
    "Netflix": "https://i.postimg.cc/GtHdbb5h/images-3.png",
    "Amazon Prime": "https://i.postimg.cc/XvLvzbxp/Amazon-Prime-Logo-Transparent.png",
    "Disney+ Hotstar": "https://i.postimg.cc/9Xx6c5VM/images-2.png",
    "AppleTV": "https://i.postimg.cc/0jWWWbKm/Apple-TV-logo.png",
    "SonyLIV": "https://i.postimg.cc/gjLmmXFy/sony-liv-logo.webp",
    "ZEE5": "https://i.postimg.cc/CMBMpt4D/images.png",
    "JioCinema": "https://i.postimg.cc/wMyC5VcJ/IMG-20251031-201544-410.jpg",
    "Hoichoi": "https://i.postimg.cc/fTsQHjwz/images-4.png",
    "Chorki": "https://i.ibb.co.com/PZh6wWNQ/Chorki-Logo.png",
    "Bongo": "https://i.ibb.co.com/wFHM61sz/KV0.jpg",
    "iScreen": "https://i.postimg.cc/ncVV786p/IMG-20251031-200605-353.jpg",
    "Toffee": "https://i.postimg.cc/7Z9V9zV1/Toffee-logo.png",
    "Bioscope": "https://i.postimg.cc/Ssdm096m/Bioscope-logo.png",
    "Binge": "https://i.postimg.cc/vH876kvX/Binge-logo.png",
    "Aha": "https://i.postimg.cc/1X9V8r8x/Aha-Logo.png",
    "Sun NXT": "https://i.postimg.cc/qR5yYyYp/Sun-NXT-logo.png",
    "MX Player": "https://i.postimg.cc/63pPqPq6/MX-Player-logo.png",
    "Discovery+": "https://i.postimg.cc/9f0R5y1z/Discovery-Plus-logo.png",
    "Eros Now": "https://i.postimg.cc/V6f9y8zM/Eros-Now-logo.png",
    "ALTBalaji": "https://i.postimg.cc/50vY4Yk7/ALTBalaji-logo.png",
    "Hungama Play": "https://i.postimg.cc/85zM6m7M/Hungama-Play-logo.png",
    "ShemarooMe": "https://i.postimg.cc/02W8W8zM/Shemaroo-Me-logo.png",
    "Lionsgate Play": "https://i.postimg.cc/85zM6m7M/Lionsgate-Play-logo.png",
    "Addatimes": "https://i.postimg.cc/mD8m8z4G/Addatimes-logo.png",
    "Klikk": "https://i.postimg.cc/6q0X0Z0P/Klikk-logo.png",
    "Chaupal": "https://i.ibb.co.com/mC3Y7z0y/Chaupal.jpg",
    "Planet Marathi": "https://i.ibb.co.com/pBfV5n0y/Planet-Marathi.png",
    "ManoramaMAX": "https://i.ibb.co.com/vC4z9x0y/Manorama-Max.png",
    "ETV Win": "https://i.ibb.co.com/mB5z9x0y/ETV-Win.png",
    "SainaPlay": "https://i.ibb.co.com/vC4z9x0y/Saina-Play.png",
    "Stage": "https://i.ibb.co.com/mB5z9x0y/Stage-OTT.png",
    "Cinematic": "https://i.postimg.cc/4NfX4x5L/Cinematic-logo.png",
    "DeeptoPlay": "https://i.ibb.co.com/mC3Y7z0y/Deepto-Play.jpg",
    "Rabbitholebd": "https://i.ibb.co.com/pBfV5n0y/Rabbithole.jpg",
    "BanglaFlix": "https://i.ibb.co.com/vC4z9x0y/Banglaflix.png",
    "Cinespot": "https://i.ibb.co.com/mB5z9x0y/Cinespot.png",
    "AynaOTT": "https://i.ibb.co.com/vC4z9x0y/Ayna-OTT.png",
    "Jagobd": "https://i.ibb.co.com/mB5z9x0y/Jagobd.png",
    "Rtv Plus": "https://i.ibb.co.com/vC4z9x0y/Rtv-Plus.png",
    "Airtel Xstream": "https://i.ibb.co.com/mB5z9x0y/Airtel-Xstream.png",
    "VI Movies & TV": "https://i.ibb.co.com/vC4z9x0y/VI-Movies.png",
    "Epic On": "https://i.ibb.co.com/mB5z9x0y/Epic-On.png",
    "MUBI": "https://i.ibb.co.com/vC4z9x0y/Mubi.png",
    "Curiosity Stream": "https://i.ibb.co.com/mB5z9x0y/Curiosity.png",
    "Docubay": "https://i.ibb.co.com/vC4z9x0y/Docubay.png",
    "Spuul": "https://i.ibb.co.com/mB5z9x0y/Spuul.png",
    "YuppTV": "https://i.ibb.co.com/vC4z9x0y/YuppTV.png",
    "Simply South": "https://i.ibb.co.com/mB5z9x0y/Simply-South.png",
    "Tentkotta": "https://i.ibb.co.com/vC4z9x0y/Tentkotta.png",
    "Koode": "https://i.ibb.co.com/mB5z9x0y/Koode.png",
    "ReelDrama": "https://i.ibb.co.com/vC4z9x0y/Reeldrama.png",
    "OHO Gujarati": "https://i.ibb.co.com/mB5z9x0y/Oho-Gujarati.png",
    "CityShor TV": "https://i.ibb.co.com/vC4z9x0y/Cityshor.png",
    "Namma Flix": "https://i.ibb.co.com/mB5z9x0y/Nammaflix.png",
    "Olly Plus": "https://i.ibb.co.com/vC4z9x0y/Ollyplus.png",
    "Aao NXT": "https://i.ibb.co.com/mB5z9x0y/Aaonxt.png",
    "KableOne": "https://i.ibb.co.com/vC4z9x0y/Kableone.png",
    "Atrangii": "https://i.ibb.co.com/mB5z9x0y/Atrangii.png",
    "Dangal Play": "https://i.ibb.co.com/vC4z9x0y/Dangal-Play.png",
    "EORTV": "https://i.ibb.co.com/mB5z9x0y/Eortv.png",
    "Ullu": "https://i.ibb.co.com/vC4z9x0y/Ullu.png",
    "Kooku": "https://i.ibb.co.com/mB5z9x0y/Kooku.png",
    "PrimePlay": "https://i.ibb.co.com/vC4z9x0y/Primeplay.png",
    "Voovi": "https://i.ibb.co.com/mB5z9x0y/Voovi.png",
    "Hunters": "https://i.ibb.co.com/vC4z9x0y/Hunters.png",
    "Fliz Movies": "https://i.ibb.co.com/mB5z9x0y/Fliz.png",
    "CSpace": "https://i.ibb.co.com/vC4z9x0y/Cspace.png",
    "Filmeraa": "https://i.ibb.co.com/mB5z9x0y/Filmeraa.png",
    "MovieSaints": "https://i.ibb.co.com/vC4z9x0y/Moviesaints.png",
    "FanCode": "https://i.ibb.co.com/mB5z9x0y/Fancode.png",
    "PTC Play": "https://i.ibb.co.com/vC4z9x0y/Ptcplay.png",
    "Tubi": "https://i.ibb.co.com/mB5z9x0y/Tubi.png",
    "Plex": "https://i.ibb.co.com/vC4z9x0y/Plex.png",
    "Rakuten Viki": "https://i.ibb.co.com/mB5z9x0y/Viki.png",
    "Hayu": "https://i.ibb.co.com/vC4z9x0y/Hayu.png",
    "Crunchyroll": "https://i.ibb.co.com/mB5z9x0y/Crunchyroll.png",
    "TVF Play": "https://i.ibb.co.com/vC4z9x0y/Tvfplay.png",
    "Pocket TV": "https://i.ibb.co.com/mB5z9x0y/Pockettv.png",
    "VROTT": "https://i.ibb.co.com/mB5z9x0y/Vrott.png",
    "Hippiix": "https://i.ibb.co.com/vC4z9x0y/Hippiix.png",
    "TeleFlix": "https://i.ibb.co.com/mB5z9x0y/Teleflix.png",
    "BD IPTV": "https://i.ibb.co.com/vC4z9x0y/Bdiptv.png",
    "Bongo Sports": "https://i.ibb.co.com/mB5z9x0y/Bongosports.png",
    "Sony Max": "https://i.ibb.co.com/vC4z9x0y/Sonymax.png",
    "Star Plus OTT": "https://i.ibb.co.com/mB5z9x0y/Starplus.png",
    "Colors Play": "https://i.ibb.co.com/vC4z9x0y/Colors.png",
    "Zee Bangla OTT": "https://i.ibb.co.com/mB5z9x0y/Zeebangla.png",
    "News7 Tamil": "https://i.ibb.co.com/vC4z9x0y/News7.png",
    "Republic World": "https://i.ibb.co.com/mB5z9x0y/Republic.png",
    "Aaj Tak OTT": "https://i.ibb.co.com/vC4z9x0y/Aajtak.png",
    "NDTV App": "https://i.ibb.co.com/mB5z9x0y/Ndtv.png",
    "Voot Kids": "https://i.ibb.co.com/vC4z9x0y/Vootkids.png",
    "Disney Junior": "https://i.ibb.co.com/mB5z9x0y/Disneyjr.png",
    "Cartoon Network": "https://i.ibb.co.com/vC4z9x0y/Cn.png",
    "Nick India": "https://i.ibb.co.com/mB5z9x0y/Nick.png",
    "Pogo OTT": "https://i.ibb.co.com/vC4z9x0y/Pogo.png",
    "Discovery Kids": "https://i.ibb.co.com/mB5z9x0y/Discoverykids.png",
    "Animax": "https://i.ibb.co.com/vC4z9x0y/Animax.png",
    "ShortsTV": "https://i.ibb.co.com/mB5z9x0y/Shortstv.png",
    "Docflix": "https://i.ibb.co.com/vC4z9x0y/Docflix.png",
    "T-Series OTT": "https://i.ibb.co.com/mB5z9x0y/Tseries.png",
    "Sony Music": "https://i.ibb.co.com/vC4z9x0y/Sonymusic.png",
    "Gaana": "https://i.ibb.co.com/mB5z9x0y/Gaana.png",
    "Saavn": "https://i.ibb.co.com/vC4z9x0y/Saavn.png",
    "Wynk Music": "https://i.ibb.co.com/vC4z9x0y/Wynk.png",
    "Spotify": "https://i.ibb.co.com/mB5z9x0y/Spotify.png",
    "YouTube": "https://i.ibb.co.com/mB5z9x0y/Youtube.png"
}
    
    category_icons = {
        "Bangla": "fa-clapperboard", "Hindi": "fa-theater-masks", "English": "fa-video", "18+ Adult": "fa-exclamation-triangle",
        "Korean": "fa-tv", "Dual Audio": "fa-headphones", "Bangla Dubbed": "fa-comment", "Hindi Dubbed": "fa-comments",
        "Horror": "fa-skull", "Action": "fa-fist-raised", "Thriller": "fa-eye", "Anime": "fa-ghost", "Romance": "fa-heart",
        "Trending": "fa-fire", "ALL MOVIES": "fa-film", "WEB SERIES & TV SHOWS": "fa-play-circle", "HOME": "fa-home"
    }

    return dict(
        website_name=WEBSITE_NAME,
        ad_settings=ad_settings or {},
        site_config=site_config,
        predefined_categories=all_categories,
        quote=quote,
        datetime=datetime,
        category_icons=category_icons,
        ott_platform_logos=ott_platform_logos
    )

# =========================================================================================
# === [START] HTML TEMPLATES ==============================================================
# =========================================================================================
index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<title>{{ website_name }} - ‌The Largest Movie Link Store Of Bangladesh</title>
<link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
<a name="description" content="Watch and download the latest movies and series on {{ website_name }}. Your ultimate entertainment hub.">
<meta name="keywords" content="movies, series, download, watch online, {{ website_name }}, bengali movies, hindi movies, english movies">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
{{ ad_settings.ad_header | safe }}
<style>
  :root {
    --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a;
    --text-light: #ffffff; --text-dark: #a0a0a0; --nav-height: 60px;
    --cyan-accent: #00FFFF; --yellow-accent: #FFFF00; --trending-color: #F83D61;
    --type-color: #00E599; --new-color: #ffc107;
    --search-accent-color: #00bfff; 
  }
  @keyframes rgb-glow {
    0%   { border-color: #ff00de; box-shadow: 0 0 5px #ff00de, 0 0 10px #ff00de inset; }
    25%  { border-color: #00ffff; box-shadow: 0 0 7px #00ffff, 0 0 12px #00ffff inset; }
    50%  { border-color: #00ff7f; box-shadow: 0 0 5px #00ff7f, 0 0 10px #00ff7f inset; }
    75%  { border-color: #f83d61; box-shadow: 0 0 7px #f83d61, 0 0 12px #f83d61 inset; }
    100% { border-color: #ff00de; box-shadow: 0 0 5px #ff00de, 0 0 10px #ff00de inset; }
  }
  @keyframes pulse-glow {
    0%, 100% { color: var(--text-dark); text-shadow: none; }
    50% { color: var(--text-light); text-shadow: 0 0 10px var(--cyan-accent); }
  }
  html { box-sizing: border-box; } *, *:before, *:after { box-sizing: inherit; }
  body {font-family: 'Poppins', sans-serif;background-color: var(--bg-color);color: var(--text-light);overflow-x: hidden; padding-bottom: 70px;}
  a { text-decoration: none; color: inherit; } img { max-width: 100%; display: block; }
  .container { max-width: 1400px; margin: 0 auto; padding: 0 10px; }
  
  .main-header { position: fixed; top: 0; left: 0; width: 100%; height: var(--nav-height); display: flex; align-items: center; z-index: 1000; transition: background-color 0.3s ease; background-color: rgba(0,0,0,0.7); backdrop-filter: blur(5px); }
  .header-content { display: flex; justify-content: space-between; align-items: center; width: 100%; }
  .logo { font-size: 1.8rem; font-weight: 700; color: var(--primary-color); }
  .menu-toggle { display: block; font-size: 1.8rem; cursor: pointer; background: none; border: none; color: white; z-index: 1001;}
  
  .nav-grid-container { padding: 15px 0; }
  .nav-grid { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
  .nav-grid-item { display: inline-flex; align-items: center; justify-content: center; color: white; padding: 6px 12px; border-radius: 6px; font-size: 0.75rem; font-weight: 500; text-transform: uppercase; text-decoration: none; transition: all 0.3s ease; background: linear-gradient(145deg, #d40a0a, #a00000); border: 1px solid #ff4b4b; box-shadow: 0 2px 8px -3px rgba(229, 9, 20, 0.6); }
  .nav-grid-item:hover { transform: translateY(-2px); box-shadow: 0 4px 12px -4px rgba(229, 9, 20, 0.9); filter: brightness(1.1); }
  .nav-grid-item i { margin-right: 6px; font-size: 1em; line-height: 1; }
  .icon-18 { font-family: sans-serif; display: inline-flex; align-items: center; justify-content: center; border: 1.5px solid white; border-radius: 50%; width: 16px; height: 16px; font-size: 10px; line-height: 1; margin-right: 6px; font-weight: bold; }

  .home-search-section { padding: 10px 0 20px 0; }
  .home-search-form { display: flex; width: 100%; max-width: 800px; margin: 0 auto; border: 2px solid var(--search-accent-color); border-radius: 8px; overflow: hidden; background-color: var(--card-bg); }
  .home-search-input { flex-grow: 1; border: none; background-color: transparent; color: var(--text-light); padding: 12px 20px; font-size: 1rem; outline: none; }
  .home-search-input::placeholder { color: var(--text-dark); }
  .home-search-button { background-color: var(--search-accent-color); border: none; color: white; padding: 0 25px; cursor: pointer; font-size: 1.2rem; display: flex; align-items: center; justify-content: center; transition: background-color 0.2s ease; }
  .home-search-button:hover { filter: brightness(1.1); }

  .glowing-link { position: relative; color: #fff; text-shadow: 0 0 5px #ffc107, 0 0 10px #ffc107, 0 0 15px #ffc107; animation: pulsate 2s infinite; }
  @keyframes pulsate { 0% { text-shadow: 0 0 5px #ffc107, 0 0 10px #ffc107; } 50% { text-shadow: 0 0 10px #ffc107, 0 0 20px #ffc107, 0 0 25px #ffc107; } 100% { text-shadow: 0 0 5px #ffc107, 0 0 10px #ffc107; } }
  .glowing-link::before, .glowing-link::after { content: '★'; position: absolute; color: #ffeb3b; font-size: 14px; opacity: 0; animation: sparkle 3s infinite; }
  .glowing-link::before { top: -5px; left: -20px; animation-delay: 0.5s; }
  .glowing-link::after { bottom: -5px; right: -20px; animation-delay: 1.5s; }
  @keyframes sparkle { 0%, 100% { transform: scale(0.5); opacity: 0; } 25%, 75% { transform: scale(1.2); opacity: 1; } 50% { transform: scale(0.8); opacity: 0.5; } }
  .create-website-section { text-align: center; padding: 50px 20px; margin-top: 40px; background-color: var(--card-bg); }
  .create-website-section h2 { font-size: 2rem; font-weight: 700; margin-bottom: 20px; }
  .create-website-section .glowing-link { display: inline-block; padding: 15px 35px; border: 2px solid #ffc107; border-radius: 50px; font-size: 1.3rem; font-weight: 600; transition: all 0.3s ease; }
  .create-website-section .glowing-link:hover { background-color: #ffc107; color: var(--bg-color); text-shadow: none; transform: scale(1.05); }

  @keyframes cyan-glow { 0% { box-shadow: 0 0 15px 2px #00D1FF; } 50% { box-shadow: 0 0 25px 6px #00D1FF; } 100% { box-shadow: 0 0 15px 2px #00D1FF; } }
  .hero-slider-section { margin-bottom: 30px; }
  .hero-slider { width: 100%; aspect-ratio: 16 / 9; background-color: var(--card-bg); border-radius: 12px; overflow: hidden; animation: cyan-glow 5s infinite linear; }
  .hero-slider .swiper-slide { position: relative; display: block; }
  .hero-slider .hero-bg-img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1; }
  .hero-slider .hero-slide-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to top, rgba(0,0,0,0.8) 0%, rgba(0,0,0,0.5) 40%, transparent 70%); z-index: 2; }
  .hero-slider .hero-slide-content { position: absolute; bottom: 0; left: 0; width: 100%; padding: 20px; z-index: 3; color: white; }
  .hero-slider .hero-title { font-size: 1.5rem; font-weight: 700; margin: 0 0 5px 0; text-shadow: 2px 2px 4px rgba(0,0,0,0.7); }
  .hero-slider .hero-meta { font-size: 0.9rem; margin: 0; color: var(--text-dark); }
  .hero-slide-content .hero-type-tag { position: absolute; bottom: 20px; right: 20px; background: linear-gradient(45deg, #00FFA3, #00D1FF); color: black; padding: 5px 15px; border-radius: 50px; font-size: 0.75rem; font-weight: 700; z-index: 4; text-transform: uppercase; box-shadow: 0 4px 10px rgba(0, 255, 163, 0.2); }
  .hero-slider .swiper-pagination { position: absolute; bottom: 10px !important; left: 20px !important; width: auto !important; }
  .hero-slider .swiper-pagination-bullet { background: rgba(255, 255, 255, 0.5); width: 8px; height: 8px; opacity: 0.7; transition: all 0.2s ease; }
  .hero-slider .swiper-pagination-bullet-active { background: var(--text-light); width: 24px; border-radius: 5px; opacity: 1; }

  .category-section { margin: 30px 0; }
  .category-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
  .category-title { font-size: 1.8rem; font-weight: 700; margin-bottom: 20px; padding-left: 15px; border-left: 5px solid var(--primary-color); line-height: 1.2; }
  .view-all-link { font-size: 0.9rem; color: var(--text-dark); font-weight: 500; padding: 6px 15px; border-radius: 20px; background-color: #222; transition: all 0.3s ease; animation: pulse-glow 2.5s ease-in-out infinite; }
  .category-grid, .full-page-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }

  .movie-card { display: flex; flex-direction: column; border-radius: 8px; overflow: hidden; background-color: var(--card-bg); border: 2px solid transparent; transition: transform 0.2s ease, box-shadow 0.2s ease; }
  .movie-card:hover { transform: translateY(-5px); box-shadow: 0 8px 20px rgba(0, 255, 255, 0.2); }
  .poster-wrapper { position: relative; }
  .movie-poster { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; display: block; }
  .card-preloader { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.75); z-index: 5; display: none; justify-content: center; align-items: center; backdrop-filter: blur(4px); border-radius: 8px; transition: opacity 0.2s; }
  .card-preloader.active { display: flex; }
  .play-button-loader-small { width: 60px; height: 60px; border: 4px solid rgba(255, 255, 255, 0.4); border-top-color: #fff; border-radius: 50%; position: relative; animation: spin 1s ease-in-out infinite; }
  .play-button-loader-small::after { content: ''; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 0; height: 0; border-style: solid; border-width: 15px 0 15px 25px; border-color: transparent transparent transparent white; margin-left: 4px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .card-info { padding: 10px; background-color: var(--card-bg); }
  .card-title { font-size: 0.9rem; font-weight: 500; color: var(--text-light); margin: 0 0 5px 0; line-height: 1.4; min-height: 2.8em; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .card-meta { font-size: 0.75rem; color: var(--text-dark); display: flex; align-items: center; gap: 5px; }
  .card-meta i { color: var(--cyan-accent); }
  .type-tag, .language-tag { position: absolute; color: white; padding: 2px 8px; font-size: 0.65rem; font-weight: 600; z-index: 2; text-transform: uppercase; border-radius: 4px; }
  .language-tag { padding: 2px 6px; font-size: 0.6rem; top: 8px; right: 8px; background-color: rgba(0,0,0,0.6); }
  .type-tag { bottom: 8px; right: 8px; background-color: var(--type-color); }
  .rating-tag { position: absolute; bottom: 8px; left: 8px; background-color: rgba(245, 197, 24, 0.9); color: #000; padding: 2px 8px; font-size: 0.7rem; font-weight: 700; z-index: 2; border-radius: 4px; display: flex; align-items: center; }
  .rating-tag i { margin-right: 4px; }
  .new-badge { position: absolute; top: 0; left: 0; background-color: var(--primary-color); color: white; padding: 4px 12px 4px 8px; font-size: 0.7rem; font-weight: 700; z-index: 3; clip-path: polygon(0 0, 100% 0, 85% 100%, 0 100%); }

  .full-page-grid-container { padding: 80px 10px 20px; }
  .full-page-grid-title { font-size: 1.8rem; font-weight: 700; margin-bottom: 20px; text-align: center; }
  .main-footer { background-color: #111; padding: 20px; text-align: center; color: var(--text-dark); margin-top: 30px; font-size: 0.8rem; }
  .ad-container { margin: 20px auto; width: 100%; max-width: 100%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
  .ad-container > * { max-width: 100% !important; }
  .mobile-nav-menu {position: fixed;top: 0;left: 0;width: 100%;height: 100%;background-color: var(--bg-color);z-index: 9999;display: flex;flex-direction: column;align-items: center;justify-content: center;transform: translateX(-100%);transition: transform 0.3s ease-in-out;}
  .mobile-nav-menu.active {transform: translateX(0);}
  .mobile-nav-menu .close-btn {position: absolute;top: 20px;right: 20px;font-size: 2.5rem;color: white;background: none;border: none;cursor: pointer;}
  .mobile-links {display: flex;flex-direction: column;text-align: center;gap: 25px;}
  .mobile-links a {font-size: 1.5rem;font-weight: 500;color: var(--text-light);transition: color 0.2s;}
  .mobile-links a:hover {color: var(--primary-color);}
  .mobile-links hr {width: 50%;border-color: #333;margin: 10px auto;}
  .bottom-nav { display: flex; position: fixed; bottom: 0; left: 0; right: 0; height: 65px; background-color: #181818; box-shadow: 0 -2px 10px rgba(0,0,0,0.5); z-index: 1000; justify-content: space-around; align-items: center; padding-top: 5px; }
  .bottom-nav .nav-item { display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--text-dark); background: none; border: none; font-size: 12px; flex-grow: 1; font-weight: 500; }
  .bottom-nav .nav-item i { font-size: 22px; margin-bottom: 5px; }
  .bottom-nav .nav-item.active, .bottom-nav .nav-item:hover { color: var(--primary-color); }
  .search-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.95); z-index: 10000; display: none; flex-direction: column; padding: 20px; }
  .search-overlay.active { display: flex; }
  .search-container { width: 100%; max-width: 800px; margin: 0 auto; }
  .close-search-btn { position: absolute; top: 20px; right: 20px; font-size: 2.5rem; color: white; background: none; border: none; cursor: pointer; }
  #search-input-live { width: 100%; padding: 15px; font-size: 1.2rem; border-radius: 8px; border: 2px solid var(--primary-color); background: var(--card-bg); color: white; margin-top: 60px; }
  #search-results-live { margin-top: 20px; max-height: calc(100vh - 150px); overflow-y: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 15px; }
  .search-result-item { color: white; text-align: center; }
  .search-result-item img { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 5px; margin-bottom: 5px; }
  .pagination { display: flex; justify-content: center; align-items: center; gap: 10px; margin: 30px 0; }
  .pagination a, .pagination span { padding: 12px 25px; border-radius: 8px; font-weight: 600; font-size: 1rem; transition: all 0.2s ease; text-align: center; border: none; text-decoration: none; }
  .pagination a { background-color: var(--card-bg); color: var(--text-light); }
  .pagination a:hover { background-color: #333; color: white; transform: translateY(-1px); }
  .pagination .current { background-color: var(--primary-color); color: white; box-shadow: 0 4px 10px rgba(229, 9, 20, 0.4); }
  
  @media (min-width: 769px) { 
    .container { padding: 0 40px; } .main-header { padding: 0 40px; }
    body { padding-bottom: 0; } .bottom-nav { display: none; }
    .hero-slider .hero-title { font-size: 2.2rem; }
    .hero-slider .hero-slide-content { padding: 40px; }
    .category-grid { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
    .full-page-grid { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }
    .full-page-grid-container { padding: 120px 40px 20px; }
  }
  .theme-toggle { position: relative; margin-right: 10px; }
  .theme-btn { background: none; border: none; color: white; font-size: 1.3rem; cursor: pointer; transition: transform 0.2s; }
  .theme-btn:hover { transform: scale(1.1); }
  .theme-popup { position: absolute; top: 120%; right: 0; background-color: #1a1a1a !important; border: 1px solid #333; border-radius: 8px; display: none; flex-direction: column; padding: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.5); z-index: 10000; }
  .theme-option { display: flex; align-items: center; gap: 10px; color: white; padding: 8px 15px; cursor: pointer; border-radius: 5px; transition: background 0.2s; }
  .theme-option:hover { background-color: rgba(255,255,255,0.1); }

  body.light-mode { --bg-color: #f0f2f5; --card-bg: #ffffff; --text-light: #1c1e21; --text-dark: #65676b; --nav-height: 60px; }
  body.light-mode .bottom-nav, body.light-mode .mobile-nav-menu, body.light-mode .search-overlay, body.light-mode .home-search-form { background-color: var(--card-bg); color: var(--text-light); }
  body.light-mode .close-btn, body.light-mode .close-search-btn { color: var(--text-light); }
  body.light-mode .home-search-input { color: var(--text-light); }
  body.light-mode .home-search-input::placeholder { color: var(--text-dark); }
  body.light-mode .news-ticker-container { background-color: #e0f2f1; }
  body.light-mode .ticker-text { color: #004d40; }
  body.light-mode .main-footer { background-color: #e9ecef; }

  .news-ticker-container { display: flex; align-items: stretch; background-color: #004d40; border-radius: 6px; overflow: hidden; margin: 15px 0 20px 0; box-shadow: 0 4px 10px rgba(0,0,0,0.5); line-height: 1.5; }
  .ticker-label { display: flex; align-items: center; justify-content: center; background-color: var(--primary-color); color: white; padding: 10px 20px; font-weight: 700; font-size: 0.9rem; white-space: nowrap; flex-shrink: 0; }
  .ticker-content { flex-grow: 1; overflow: hidden; position: relative; padding: 0 10px; }
  .ticker-text { position: absolute; top: 15%; transform: translateY(-50%); white-space: nowrap; font-size: 1rem; color: white; will-change: transform; animation: scroll-left 60s linear infinite; }
  @keyframes scroll-left { 0% { transform: translate(100vw, -50%); } 100% { transform: translate(-100%, -50%); } }

  .platform-section { margin: 40px 0; overflow: hidden; }
  .platform-slider .swiper-slide { width: 100px; }
  .platform-item { display: flex; flex-direction: column; align-items: center; justify-content: center; text-decoration: none; color: var(--text-dark); transition: transform 0.2s ease, color 0.2s ease; }
  .platform-item:hover { transform: scale(1.08); color: var(--text-light); }
  .platform-logo-wrapper { width: 80px; height: 80px; border-radius: 50%; background-color: #fff; display: flex; align-items: center; justify-content: center; margin-bottom: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); border: 2px solid #444; transition: all 0.3s ease; }
  .platform-item:hover .platform-logo-wrapper { border-color: var(--cyan-accent); box-shadow: 0 0 20px rgba(0, 255, 255, 0.4); }
  .platform-logo-wrapper img { max-width: 65%; max-height: 65%; object-fit: contain; }
  .platform-item span { font-weight: 500; font-size: 0.8rem; text-align: center; }
  .section-title-simple { font-size: 1.6rem; font-weight: 600; margin-bottom: 20px; padding-left: 10px; border-left: 4px solid var(--primary-color); }
  @media (min-width: 769px) { .platform-slider .swiper-slide { width: 130px; } .platform-logo-wrapper { width: 100px; height: 100px; } .platform-item span { font-size: 0.9rem; } }

  .featured-badge { position: absolute; top: 0; left: 0; background-color: #ffc107; color: #000; padding: 4px 12px 4px 8px; font-size: 0.7rem; font-weight: 700; z-index: 3; clip-path: polygon(0 0, 100% 0, 85% 100%, 0 100%); }
  .platform-header { text-align: center; margin-bottom: 20px; }
  .platform-logo-display { display: inline-flex; justify-content: center; align-items: center; width: 100px; height: 100px; background-color: #fff; border-radius: 50%; padding: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.4); border: 2px solid #444; }
  .platform-logo-display img { max-width: 100%; max-height: 100%; object-fit: contain; }

  .professional-footer { background: linear-gradient(to bottom, #1a1a1a, #0f0f0f); color: var(--text-dark); padding-top: 60px; margin-top: 50px; border-top: 4px solid #000; }
  .footer-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 40px; padding-bottom: 50px; }
  .footer-column-title { font-size: 1.3rem; font-weight: 600; color: var(--text-light); margin-bottom: 25px; position: relative; padding-bottom: 10px; }
  .footer-column-title::after { content: ''; position: absolute; bottom: 0; left: 0; width: 50px; height: 3px; background-color: var(--primary-color); }
  .footer-logo img { max-width: 160px; margin-bottom: 15px; }
  .footer-description { font-size: 0.95rem; line-height: 1.7; }
  .links-section ul { list-style: none; padding: 0; margin: 0; }
  .links-section ul li { margin-bottom: 12px; }
  .links-section ul li a { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--text-dark); transition: all 0.2s ease-in-out; }
  .links-section ul li a:hover { color: var(--primary-color); transform: translateX(5px); }
  .telegram-buttons-container { display: flex; flex-direction: column; gap: 15px; }
  .telegram-button { display: flex; align-items: center; gap: 15px; padding: 12px 15px; border-radius: 8px; text-decoration: none; color: white; background-color: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); transition: all 0.2s ease; }
  .telegram-button:hover { background-color: rgba(255, 255, 255, 0.1); border-color: var(--primary-color); transform: translateY(-2px); }
  .telegram-button i { font-size: 1.8rem; width: 30px; text-align: center; }
  .telegram-button.notification i { color: #34B7F1; } .telegram-button.request i { color: #f5c518; } .telegram-button.backup i { color: #28a745; }
  .telegram-button span { display: flex; flex-direction: column; } .telegram-button small { font-size: 0.75rem; color: var(--text-dark); }
  .footer-note { font-size: 0.8rem; color: var(--text-dark); margin-top: 20px; background-color: rgba(0,0,0,0.2); padding: 10px; border-radius: 5px; }
  .footer-note a { color: #34B7F1; font-weight: bold; }
  .footer-bottom-bar { background-color: #000; text-align: center; padding: 20px; font-size: 0.9rem; border-top: 1px solid #222; }
  @media (max-width: 768px) { .footer-grid { text-align: center; } .footer-column-title::after { left: 50%; transform: translateX(-50%); } .footer-logo { margin-left: auto; margin-right: auto; } .links-section ul li a { justify-content: center; } }
  
  /* CSS for auto-blur poster */
  .blurred {
      filter: blur(15px) !important;
      transition: filter 0.4s ease;
  }
</style>
</head>
<body>
{{ ad_settings.ad_body_top | safe }}
<header class="main-header">
    <div class="container header-content">
    <a href="{{ url_for('home') }}" class="logo">
    <img src="https://i.postimg.cc/3wxTc4K7/1000020248-removebg-preview.png" alt="{{ website_name }} Logo" style="height: 45px; width: auto;">
</a>
    <div style="display: flex; align-items: center;">
        <button id="poster-blur-toggle" class="theme-btn" aria-label="Toggle Poster Blur" style="margin-right: 15px;"><i class="fas fa-eye-slash"></i></button>
        <div class="theme-toggle">
            <button class="theme-btn" aria-label="Toggle Theme"><i class="fas fa-palette"></i></button>
            <div class="theme-popup">
                <div class="theme-option" data-theme="dark"><i class="fas fa-moon"></i> Dark</div>
                <div class="theme-option" data-theme="light"><i class="fas fa-sun"></i> Light</div>
            </div>
        </div>
        <button class="menu-toggle"><i class="fas fa-bars"></i></button>
    </div>
</div>
</header>
<div class="mobile-nav-menu">
    <button class="close-btn">&times;</button>
    <div class="mobile-links">
        <a href="{{ url_for('home') }}">Home</a>
        <a href="{{ url_for('all_movies') }}">All Movies</a>
        <a href="{{ url_for('all_series') }}">All Series</a>
        <a href="{{ url_for('request_content') }}">Request Content</a>
        <a href="{{ url_for('disclaimer') }}">Disclaimer</a>
        <a href="{{ url_for('dmca') }}">DMCA</a>
        <a href="{{ url_for('create_website') }}" class="glowing-link">Create Your Own Website</a>
        <hr>
    </div>
</div>
<main>
  {% macro render_movie_card(m, is_featured=false) %} 
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
      <div class="poster-wrapper">
        <div class="card-preloader">
            <div class="play-button-loader-small"></div>
        </div>
        
        {% if m.vote_average and m.vote_average > 0 %}
            <span class="rating-tag"><i class="fas fa-star"></i> {{ "%.1f"|format(m.vote_average) }}</span>
        {% endif %}

        {% if is_featured %}
            <span class="featured-badge">Featured</span>
        {% elif (datetime.utcnow() - m._id.generation_time.replace(tzinfo=None)).days < 7 %}
            <span class="new-badge">NEW</span>
        {% endif %}

        {% if m.poster_badge %}<span class="language-tag">{{ m.poster_badge }}</span>{% endif %}
        <img class="movie-poster" loading="lazy" src="{{ m.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ m.title }}">
        <span class="type-tag">{{ m.type | title }}</span>
      </div>
      <div class="card-info">
        <h4 class="card-title">
          {{ m.title }}
          {% if m.release_year %} ({{ m.release_year }}){% elif m.release_date %} ({{ m.release_date.split('-')[0] }}){% endif %}
        </h4>
      </div>
    </a>
  {% endmacro %}

  {% if is_full_page_list %}
    <div class="full-page-grid-container">
        {% if platform_info and ott_platform_logos.get(platform_info.name) %}
        <div class="platform-header">
            <div class="platform-logo-display">
                <img src="{{ ott_platform_logos[platform_info.name] }}" alt="{{ platform_info.name }} Logo">
            </div>
        </div>
        {% endif %}
        
        <h2 class="full-page-grid-title">{{ query }}</h2>
        {% if movies|length == 0 %}<p style="text-align:center;">No content found.</p>
        {% else %}
        <div class="full-page-grid">
            {% for m in movies %}
                {{ render_movie_card(m, is_featured=is_featured_page) }}
            {% endfor %}
        </div>
        {% if pagination and pagination.total_pages > 1 %}
        <div class="pagination">
            {% if pagination.has_prev %}<a href="{{ url_for(request.endpoint, page=pagination.prev_num, name=query if 'category' in request.endpoint or 'platform' in request.endpoint else None, genre_name=query.replace('Genres: ', '') if 'genre' in request.endpoint else None) }}">&laquo; Prev</a>{% endif %}
            
            <span class="current">Page {{ pagination.page }} of {{ pagination.total_pages }}</span>
            
            {% if pagination.has_next %}<a href="{{ url_for(request.endpoint, page=pagination.next_num, name=query if 'category' in request.endpoint or 'platform' in request.endpoint else None, genre_name=query.replace('Genres: ', '') if 'genre' in request.endpoint else None) }}">Next &raquo;</a>{% endif %}
        </div>
        {% endif %}
        {% endif %}
    </div>
  {% else %}
    <div style="height: var(--nav-height);"></div>
    
    <section class="nav-grid-container container">
        <div class="nav-grid">
            <a href="{{ url_for('home') }}" class="nav-grid-item">
                <i class="fas {{ category_icons.get('HOME', 'fa-tag') }}"></i> HOME
            </a>
            {% for cat in predefined_categories %}
                <a href="{{ url_for('movies_by_category', name=cat) }}" class="nav-grid-item">
                    {% if '18+' in cat %}
                        <span class="icon-18">18</span>
                    {% else %}
                        <i class="fas {{ category_icons.get(cat, 'fa-tag') }}"></i>
                    {% endif %}
                    {{ cat }}
                </a>
            {% endfor %}
            <a href="{{ url_for('all_movies') }}" class="nav-grid-item">
                <i class="fas {{ category_icons.get('ALL MOVIES', 'fa-tag') }}"></i> ALL MOVIES
            </a>
            <a href="{{ url_for('all_series') }}" class="nav-grid-item">
                <i class="fas {{ category_icons.get('WEB SERIES & TV SHOWS', 'fa-tag') }}"></i> WEB SERIES & TV SHOWS
            </a>
        </div>
    </section>

    <section class="home-search-section container">
        <form action="{{ url_for('home') }}" method="get" class="home-search-form">
            <input type="text" name="q" class="home-search-input" placeholder="Search and explore your favorite content...">
            <button type="submit" class="home-search-button" aria-label="Search">
                <i class="fas fa-search"></i>
            </button>
        </form>
    </section>
    
    <section class="container">
        <div class="news-ticker-container">
            <div class="ticker-label">Notice</div>
            <div class="ticker-content">
                <p class="ticker-text">
                    A warm welcome to you at {{ website_name }}. Here you can search and explore all the latest movies and web series. If you can't find your favorite content, feel free to let us know using the 'Request' option. For all the latest updates and news on new releases, please join our official Telegram channel: @allmoviepsz. Thank you for visiting and stay with us. ••• {{ website_name }} এ আপনাকে আন্তরিকভাবে স্বাগতম। এখানে আপনি নতুন-পুরানো সব মুভি ও সিরিজ সার্চ করতে এবং দেখতে পারবেন। আপনার পছন্দের কোনো কনটেন্ট খুঁজে না পেলে, 'Request' অপশন ব্যবহার করে আমাদের জানাতে পারেন। সর্বশেষ আপডেট এবং নতুন সব কনটেন্টের খবরের জন্য আমাদের টেলিগ্রাম চ্যানেলে যোগ দিন: @allmoviepsz। আমাদের সাথে থাকার জন্য ধন্যবাদ।
                </p>
            </div>
        </div>
    </section>

    {% if slider_content %}
    <section class="hero-slider-section container">
        <div class="swiper hero-slider">
            <div class="swiper-wrapper">
                {% for item in slider_content %}
                <div class="swiper-slide">
                    <a href="{{ url_for('movie_detail', movie_id=item._id) }}">
                        <img src="{{ item.backdrop or item.poster }}" class="hero-bg-img" alt="{{ item.title }}">
                        <div class="hero-slide-overlay"></div>
                        <div class="hero-slide-content">
                            <h2 class="hero-title">{{ item.title }}</h2>
                            <p class="hero-meta">
                                {% if item.release_date %}{{ item.release_date.split('-')[0] }}{% endif %}
                            </p>
                            <span class="hero-type-tag">{{ item.type | title }}</span>
                        </div>
                    </a>
                </div>
                {% endfor %}
            </div>
            <div class="swiper-pagination"></div>
        </div>
    </section>
    {% endif %}

    {% if available_otts %}
    <section class="platform-section container">
        <h2 class="section-title-simple">Available On</h2>
        <div class="swiper platform-slider">
            <div class="swiper-wrapper">
                {% for platform in available_otts %}
                    {% if ott_platform_logos.get(platform) %}
                    <div class="swiper-slide">
                        <a href="{{ url_for('movies_by_platform', platform_name=platform) }}" class="platform-item">
                            <div class="platform-logo-wrapper">
                                <img src="{{ ott_platform_logos[platform] }}" alt="{{ platform }} Logo">
                            </div>
                            <span>{{ platform }}</span>
                        </a>
                    </div>
                    {% endif %}
                {% endfor %}
            </div>
        </div>
    </section>
    {% endif %}

    <div class="container">
    {% if featured_content %}
    <section class="category-section">
        <div class="category-header">
            <h2 class="category-title">Featured</h2>
            <a href="{{ url_for('movies_by_category', name='Featured') }}" class="view-all-link">View All &rarr;</a>
        </div>
        <div class="swiper featured-slider">
            <div class="swiper-wrapper">
                {% for m in featured_content %}
                <div class="swiper-slide">
                    {{ render_movie_card(m, is_featured=True) }}
                </div>
                {% endfor %}
            </div>
        </div>
    </section>
    {% endif %}
      
      {% if trending_content %}
      <section class="category-section">
          <div class="category-header">
              <h2 class="category-title">Trending Now</h2>
              <a href="{{ url_for('movies_by_category', name='Trending') }}" class="view-all-link">View All &rarr;</a>
          </div>
          <div class="category-grid">
                  {% for m in trending_content %}
                      {{ render_movie_card(m, is_featured=False) }} 
                  {% endfor %}
              </div>
      </section>
      {% endif %}

      {% if latest_content %}
      <section class="category-section">
          <div class="category-header">
              <h2 class="category-title">Recently Added</h2>
              <a href="{{ url_for('all_content') }}" class="view-all-link">View All &rarr;</a>
          </div>
          <div class="category-grid">
              {% for m in latest_content %}
                  {{ render_movie_card(m) }}
              {% endfor %}
          </div>
      </section>
      {% endif %}
      
      {% if ad_settings.ad_list_page %}<div class="ad-container">{{ ad_settings.ad_list_page | safe }}</div>{% endif %}
      
      {% if latest_movies %}
      <section class="category-section">
          <div class="category-header">
              <h2 class="category-title">Latest Movies</h2>
              <a href="{{ url_for('all_movies') }}" class="view-all-link">View All &rarr;</a>
          </div>
          <div class="category-grid">
              {% for m in latest_movies %}
                  {{ render_movie_card(m) }}
              {% endfor %}
          </div>
      </section>
      {% endif %}

      {% if latest_series %}
      <section class="category-section">
          <div class="category-header">
              <h2 class="category-title">Latest Series</h2>
              <a href="{{ url_for('all_series') }}" class="view-all-link">View All &rarr;</a>
          </div>
          <div class="category-grid">
              {% for m in latest_series %}
                  {{ render_movie_card(m) }}
              {% endfor %}
          </div>
      </section>
      {% endif %}

      {% if coming_soon %}
      <section class="category-section">
          <div class="category-header">
              <h2 class="category-title">Coming Soon</h2>
              <a href="{{ url_for('movies_by_category', name='Coming Soon') }}" class="view-all-link">View All &rarr;</a>
          </div>
          <div class="category-grid">
              {% for m in coming_soon %}
                  {{ render_movie_card(m) }}
              {% endfor %}
          </div>
      </section>
      {% endif %}

    </div>
  {% endif %}
</main>

<section class="create-website-section">
    <div class="container">
        <h2>Want a Website Like This?</h2>
        <a href="{{ url_for('create_website') }}" class="glowing-link">
            <i class="fas fa-star"></i> Create Your Own Website With Us <i class="fas fa-star"></i>
        </a>
    </div>
</section>

<footer class="professional-footer">
    <div class="container footer-grid">
        <div class="footer-column about-section">
            <a href="{{ url_for('home') }}" class="footer-logo">
                <img src="https://i.postimg.cc/3wxTc4K7/1000020248-removebg-preview.png" alt="{{ website_name }} Logo">
            </a>
            <p class="footer-description">
                Your ultimate destination for the latest movies and web series. We are dedicated to providing a seamless entertainment experience.
            </p>
        </div>
        <div class="footer-column links-section">
            <h4 class="footer-column-title">Site Links</h4>
            <ul>
                <li><a href="{{ url_for('dmca') }}"><i class="fas fa-gavel"></i> DMCA Policy</a></li>
                <li><a href="{{ url_for('disclaimer') }}"><i class="fas fa-exclamation-triangle"></i> Disclaimer</a></li>
                <li><a href="{{ url_for('create_website') }}"><i class="fas fa-palette"></i> Create Your Website</a></li>
            </ul>
        </div>
        <div class="footer-column community-section">
            <h4 class="footer-column-title">Join Our Community</h4>
            <div class="telegram-buttons-container">
                <a href="https://t.me/allmoviepsz" target="_blank" class="telegram-button notification">
                    <i class="fas fa-bell"></i>
                    <span><strong>New Content Alerts</strong><small>Get notified for every new upload</small></span>
                </a>
                <a href="https://t.me/+0kZRI3EUX54wM2Nl" target="_blank" class="telegram-button request">
                    <i class="fas fa-comments"></i>
                    <span><strong>Join Request Group</strong><small>Request your favorite content</small></span>
                </a>
                <a href="https://t.me/Yabotz" target="_blank" class="telegram-button backup">
                    <i class="fas fa-shield-alt"></i>
                    <span><strong>Backup Channel</strong><small>Join for future updates</small></span>
                </a>
            </div>
            <p class="footer-note">
                <strong>Alternatively,</strong> you can use the <a href="{{ url_for('request_content') }}">Request</a> option in our bottom menu to submit requests directly on the site.
            </p>
        </div>
    </div>
    <div class="footer-bottom-bar">
        <p>&copy; {{ datetime.utcnow().year }} {{ website_name }}. All Rights Reserved. Crafted with care for movie lovers.</p>
    </div>
</footer>

<nav class="bottom-nav">
  <a href="{{ url_for('home') }}" class="nav-item active"><i class="fas fa-home"></i><span>Home</span></a>
  <a href="{{ url_for('genres_page') }}" class="nav-item"><i class="fas fa-layer-group"></i><span>Genres</span></a>
  <a href="{{ url_for('request_content') }}" class="nav-item"><i class="fas fa-plus-circle"></i><span>Request</span></a>
  <button id="live-search-btn" class="nav-item"><i class="fas fa-search"></i><span>Search</span></button>
</nav>
<div id="search-overlay" class="search-overlay">
  <button id="close-search-btn" class="close-search-btn">&times;</button>
  <div class="search-container">
    <input type="text" id="search-input-live" placeholder="Type to search for movies or series..." autocomplete="off">
    <div id="search-results-live"><p style="color: #555; text-align: center;">Start typing to see results</p></div>
  </div>
</div>
<script src="https://unpkg.com/swiper/swiper-bundle.min.js"></script>
<script>
    const header = document.querySelector('.main-header');
    window.addEventListener('scroll', () => { window.scrollY > 10 ? header.classList.add('scrolled') : header.classList.remove('scrolled'); });
    const menuToggle = document.querySelector('.menu-toggle');
    const mobileMenu = document.querySelector('.mobile-nav-menu');
    const closeBtn = document.querySelector('.close-btn');
    if (menuToggle && mobileMenu && closeBtn) {
        menuToggle.addEventListener('click', () => { mobileMenu.classList.add('active'); });
        closeBtn.addEventListener('click', () => { mobileMenu.classList.remove('active'); });
        document.querySelectorAll('.mobile-links a').forEach(link => { link.addEventListener('click', () => { mobileMenu.classList.remove('active'); }); });
    }
    const liveSearchBtn = document.getElementById('live-search-btn');
    const searchOverlay = document.getElementById('search-overlay');
    const closeSearchBtn = document.getElementById('close-search-btn');
    const searchInputLive = document.getElementById('search-input-live');
    const searchResultsLive = document.getElementById('search-results-live');
    let debounceTimer;
    liveSearchBtn.addEventListener('click', () => { searchOverlay.classList.add('active'); searchInputLive.focus(); });
    closeSearchBtn.addEventListener('click', () => { searchOverlay.classList.remove('active'); });
    searchInputLive.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const query = searchInputLive.value.trim();
            if (query.length > 1) {
                searchResultsLive.innerHTML = '<p style="color: #555; text-align: center;">Searching...</p>';
                fetch(`/api/search?q=${encodeURIComponent(query)}`).then(response => response.json()).then(data => {
                    let html = '';
                    if (data.length > 0) {
                        data.forEach(item => { html += `<a href="/movie/${item._id}" class="search-result-item"><img src="${item.poster}" alt="${item.title}"><span>${item.title}</span></a>`; });
                    } else { html = '<p style="color: #555; text-align: center;">No results found.</p>'; }
                    searchResultsLive.innerHTML = html;
                });
            } else { searchResultsLive.innerHTML = '<p style="color: #555; text-align: center;">Start typing to see results</p>'; }
        }, 300);
    });
    new Swiper('.hero-slider', {
        loop: true, autoplay: { delay: 5000, disableOnInteraction: false },
        pagination: { el: '.swiper-pagination', clickable: true },
        effect: 'fade', fadeEffect: { crossFade: true },
    });
    
    let featuredAutoplayTimeout;
    const featuredSwiper = new Swiper('.featured-slider', {
        breakpoints: {
            320: { slidesPerView: 2, spaceBetween: 15 },
            768: { slidesPerView: 4, spaceBetween: 20 }
        },
        speed: 800,
        loop: false,
    });
    function startFeaturedAutoplay() {
        stopFeaturedAutoplay();
        featuredAutoplayTimeout = setInterval(() => {
            if (featuredSwiper.isEnd) {
                stopFeaturedAutoplay();
                setTimeout(() => {
                    featuredSwiper.slideTo(0, 2000); 
                    setTimeout(() => {
                        startFeaturedAutoplay();
                    }, 2000); 
                }, 1500); 
            } else {
                featuredSwiper.slideNext();
            }
        }, 3000);
    }
    function stopFeaturedAutoplay() { clearInterval(featuredAutoplayTimeout); }
    const featuredSliderEl = document.querySelector('.featured-slider');
    let featuredInteractionTimeout;
    const onFeaturedInteractionStart = () => { stopFeaturedAutoplay(); clearTimeout(featuredInteractionTimeout); };
    const onFeaturedInteractionEnd = () => { featuredInteractionTimeout = setTimeout(() => { startFeaturedAutoplay(); }, 3500); };
    if(featuredSliderEl) {
        featuredSliderEl.addEventListener('touchstart', onFeaturedInteractionStart, { passive: true });
        featuredSliderEl.addEventListener('touchend', onFeaturedInteractionEnd, { passive: true });
        featuredSliderEl.addEventListener('mouseenter', onFeaturedInteractionStart);
        featuredSliderEl.addEventListener('mouseleave', onFeaturedInteractionEnd);
        startFeaturedAutoplay();
    }
    
    let autoplayTimeout; 
    const platformSwiper = new Swiper('.platform-slider', {
        slidesPerView: 'auto',
        spaceBetween: 25,
        speed: 800,
        loop: false, 
        on: {
            reachEnd: function () {
                setTimeout(() => {
                    this.slideTo(0, 1500); 
                }, 1000); 
            },
        },
    });
    function startAutoplay() {
        stopAutoplay(); 
        autoplayTimeout = setInterval(() => {
            if (!platformSwiper.isEnd) {
                platformSwiper.slideNext();
            }
        }, 3000); 
    }
    function stopAutoplay() { clearInterval(autoplayTimeout); }
    const platformSliderEl = document.querySelector('.platform-slider');
    let interactionTimeout; 
    const onInteractionStart = () => { stopAutoplay(); clearTimeout(interactionTimeout); };
    const onInteractionEnd = () => { interactionTimeout = setTimeout(() => { startAutoplay(); }, 3500); };
    if(platformSliderEl) {
        platformSliderEl.addEventListener('touchstart', onInteractionStart, { passive: true });
        platformSliderEl.addEventListener('touchend', onInteractionEnd, { passive: true });
        platformSliderEl.addEventListener('mouseenter', onInteractionStart);
        platformSliderEl.addEventListener('mouseleave', onInteractionEnd);
        startAutoplay();
    }

    function initializeCardLoaders() {
        const contentLinks = document.querySelectorAll('.movie-card');
        contentLinks.forEach(card => {
            card.addEventListener('click', function(event) {
                event.preventDefault();
                const preloader = this.querySelector('.card-preloader');
                if (preloader) { preloader.classList.add('active'); }
                const destinationUrl = this.href;
                setTimeout(() => { window.location.href = destinationUrl; }, 150); 
            });
        });
    }
    document.addEventListener('DOMContentLoaded', function() { initializeCardLoaders(); });
    window.addEventListener('pageshow', function(event) {
        if (event.persisted) {
            document.querySelectorAll('.card-preloader.active').forEach(preloader => {
                preloader.classList.remove('active');
            });
        }
    });
    
const initializePaginationJump = () => {
    const pageJumpInput = document.getElementById('page-jump-input');
    const pageJumpBtn = document.getElementById('page-jump-btn'); 
    const goToPage = () => {
        if (!pageJumpInput) return;
        const totalPages = parseInt(pageJumpInput.getAttribute('max'));
        let pageNumber = parseInt(pageJumpInput.value);
        if (isNaN(pageNumber) || pageNumber < 1) { pageNumber = 1; } else if (pageNumber > totalPages) { pageNumber = totalPages; }
        const url = new URL(window.location.href);
        url.searchParams.set('page', pageNumber);
        window.location.href = url.toString();
    };
    if (pageJumpInput) { pageJumpInput.addEventListener('keydown', function(event) { if (event.key === 'Enter') { goToPage(); } }); }
    if (pageJumpBtn) { pageJumpBtn.addEventListener('click', goToPage); }
};
document.addEventListener('DOMContentLoaded', function() {
    initializePaginationJump();
    if (typeof initializeCardLoaders === 'function') { initializeCardLoaders(); }
});
    
    const themeBtn = document.querySelector('.theme-btn');
    const themePopup = document.querySelector('.theme-popup');
    const themeOptions = document.querySelectorAll('.theme-option');
    const applyTheme = (theme) => {
        if (theme === 'light') { document.body.classList.add('light-mode'); } else { document.body.classList.remove('light-mode'); }
    };
    const savedTheme = localStorage.getItem('theme') || 'dark';
    applyTheme(savedTheme);
    if(themeBtn && themePopup){
        themeBtn.addEventListener('click', () => {
            const isDisplayed = themePopup.style.display === 'flex';
            themePopup.style.display = isDisplayed ? 'none' : 'flex';
        });
        themeOptions.forEach(option => {
            option.addEventListener('click', () => {
                const selectedTheme = option.getAttribute('data-theme');
                localStorage.setItem('theme', selectedTheme);
                applyTheme(selectedTheme);
                themePopup.style.display = 'none';
            });
        });
        document.addEventListener('click', (event) => {
            if (!themeBtn.contains(event.target) && !themePopup.contains(event.target)) {
                themePopup.style.display = 'none';
            }
        });
    }

    // === Poster Auto Blur Logic ===
    const blurToggleBtn = document.getElementById('poster-blur-toggle');
    let blurTimeout;
    const autoBlurSeconds = {{ site_config.auto_blur_timer | default(5) }};
    let isBlurred = true;
    const posterSelectors = '.movie-poster, .hero-bg-img, .hero-backdrop-img, .overlay-poster, .changing-image, .thumbnail-item img';

    function applyBlur() {
        document.querySelectorAll(posterSelectors).forEach(img => img.classList.add('blurred'));
        if(blurToggleBtn) blurToggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i>';
        isBlurred = true;
    }

    function removeBlur() {
        document.querySelectorAll(posterSelectors).forEach(img => img.classList.remove('blurred'));
        if(blurToggleBtn) blurToggleBtn.innerHTML = '<i class="fas fa-eye"></i>';
        isBlurred = false;
        
        clearTimeout(blurTimeout);
        if (autoBlurSeconds > 0) {
            blurTimeout = setTimeout(applyBlur, autoBlurSeconds * 1000);
        }
    }

    if(blurToggleBtn) {
        blurToggleBtn.addEventListener('click', () => {
            if (isBlurred) {
                removeBlur();
            } else {
                applyBlur();
                clearTimeout(blurTimeout);
            }
        });
    }
    
    // Apply blur on page load
    applyBlur();
</script>
{{ ad_settings.ad_footer | safe }}
</body></html>
"""

detail_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<title>{{ movie.title if movie else "Content Not Found" }} - {{ website_name }}</title>
<link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
<meta name="description" content="{{ movie.overview|striptags|truncate(160) }}">
<meta name="keywords" content="{{ movie.title }}, movie details, download {{ movie.title }}, {{ website_name }}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
{{ ad_settings.ad_header | safe }}
<style>
  :root {--primary-color: #E50914; --watch-color: #007bff; --bg-color: #141414;--card-bg: #1a1a1a;--text-light: #ffffff;--text-dark: #a0a0a0;}
  html { box-sizing: border-box; } *, *:before, *:after { box-sizing: inherit; }
  body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); overflow-x: hidden; }
  a { text-decoration: none; color: inherit; }
  .container { max-width: 1200px; margin: 0 auto; padding: 0 15px; }

  .page-header { padding: 20px 15px 15px 15px; }
  .go-back-btn { display: inline-flex; align-items: center; gap: 10px; background-color: rgba(45, 45, 45, 0.9); color: #fff; padding: 10px 20px; border-radius: 12px; font-size: 1rem; font-weight: 500; border: none;}
  .hero-section-wrapper { margin: 0 15px 30px 15px; position: relative; overflow: visible; margin-bottom: 120px; }
  .detail-hero-backdrop { width: 100%; aspect-ratio: 16 / 9; border-radius: 16px; overflow: hidden; position: relative; box-shadow: 0 0 30px 0 rgba(0, 255, 255, 0.25); border: 1px solid rgba(0, 255, 255, 0.2); background-color: #000; }
  .hero-backdrop-img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1; }
  .hero-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 2; background: linear-gradient(180deg, rgba(20,20,20,0) 50%, rgba(20,20,20,0.8) 100%); }
  .overlay-poster { position: absolute; z-index: 4; bottom: -80px; left: 20px; width: 35%; max-width: 150px; border-radius: 12px; border: 3px solid rgba(255, 255, 255, 0.15); box-shadow: 0 15px 35px rgba(0,0,0,0.8); }
  .content-type-badge { position: absolute; z-index: 3; bottom: 20px; right: 20px; background-color: #00ff00; color: #000; padding: 10px 25px; border-radius: 10px; font-size: 0.9rem; font-weight: 700; text-transform: uppercase; }
  
  .content-info-section { padding: 20px; }
  .detail-title { font-size: 2rem; font-weight: 700; line-height: 1.3; margin-bottom: 15px; }
  .detail-meta { display: flex; flex-wrap: wrap; gap: 10px 20px; color: var(--text-dark); margin-bottom: 20px; font-size: 0.9rem; }
  .meta-item { display: flex; align-items: center; gap: 8px; }
  .meta-item.rating { color: #f5c518; font-weight: 600; }
  .detail-overview { font-size: 1rem; line-height: 1.7; color: var(--text-dark); margin-bottom: 30px; }
  
  .section-title { font-size: 1.5rem; font-weight: 700; margin: 30px 0 20px 0; padding-bottom: 5px; border-bottom: 2px solid var(--primary-color); display: inline-block; }
  .ad-container { margin: 30px 0; text-align: center; }
  .links-wrapper { margin-top: 10px; }
  .links-container { display: flex; flex-wrap: wrap; gap: 40px; align-items: flex-start; }
  .link-section { flex: 1; min-width: 250px; }
  .download-button { display: block; width: 100%; padding: 12px 20px; color: white; text-decoration: none; border-radius: 4px; font-weight: 700; transition: background-color 0.3s ease; margin-bottom: 10px; text-align: center; background-color: var(--primary-color); }
  .download-button:hover { background-color: #f61f29; }
  .telegram-button { background-color: #2AABEE; display: flex; align-items: center; justify-content: center; gap: 10px; }
  .telegram-button:hover { background-color: #1e96d1; }
  .telegram-button i { font-size: 1.2rem; }
  
  .episode-item { display: flex; flex-direction: column; align-items: stretch; margin-bottom: 15px; padding: 15px; border-radius: 5px; background-color: var(--card-bg); border-left: 4px solid var(--primary-color); }
  .episode-info { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; flex-wrap: wrap; }
  .episode-title { font-size: 1.1rem; font-weight: 500; color: #fff; }
  .episode-buttons { display: flex; flex-wrap: wrap; gap: 10px; }
  .episode-button { display: inline-flex; flex: 1; justify-content: center; align-items: center; gap: 8px; padding: 10px 15px; color: white; border-radius: 4px; font-weight: 700; transition: background-color 0.3s ease; text-align: center; }
  .episode-button.stream-btn { background-color: #007bff; } .episode-button.stream-btn:hover { background-color: #0069d9; }
  .episode-button.download-btn { background-color: var(--primary-color); } .episode-button.download-btn:hover { background-color: #f61f29; }
  .episode-button.custom-btn { background-color: #555; } .episode-button.custom-btn:hover { background-color: #444; }

  .trailer-section { margin: 0 0 40px 0; }
  .trailer-section h2 { font-size: 1.5rem; font-weight: 600; margin-bottom: 20px; }
  .trailer-video-wrap { position: relative; width: 100%; max-width: 900px; margin: 0 auto; aspect-ratio: 16 / 9; border-radius: 12px; overflow: hidden; }
  .trailer-video-wrap iframe { position: absolute; width: 100%; height: 100%; top: 0; left: 0; border: 0; }
  .related-content { margin-top: 50px; }
  .movie-carousel .swiper-slide { width: 150px; }
  .card-title { font-size: 0.9rem; font-weight: 500; }
  .card-meta { font-size: 0.8rem; color: var(--text-dark); }
  .swiper-button-next, .swiper-button-prev { color: var(--text-light); display: none; }

  @media (min-width: 768px) {
    .container { padding: 0 40px; }
    .hero-section-wrapper { margin: 0 40px 40px 40px; margin-bottom: 60px; }
    .overlay-poster { left: 50px; bottom: -80px; max-width: 220px; }
    .content-info-section { padding-left: 300px; }
    .detail-title { font-size: 2.5rem; }
    .movie-carousel .swiper-slide { width: 180px; }
    .swiper-button-next, .swiper-button-prev { display: flex; }
  }
  .category-section { margin: 50px 0; }
  .category-title { font-size: 1.5rem; font-weight: 600; }
  .movie-carousel .swiper-slide { width: 150px; }
  .movie-card { display: block; }
  .movie-poster { 
    width: 100%; 
    aspect-ratio: 2 / 3; 
    object-fit: cover; 
    border-radius: 8px; 
    margin-bottom: 10px; 
  }
  @media (min-width: 768px) {
    .movie-carousel .swiper-slide { width: 220px; }
  }
  .category-section { margin-top: 50px; }
  .category-header { margin-bottom: 20px; }
  .category-title { font-size: 1.5rem; font-weight: 600; padding-bottom: 5px; border-bottom: 2px solid var(--primary-color); display: inline-block; }
  .related-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; }
  .movie-card { display: block; border-radius: 12px; overflow: hidden; background-color: var(--card-bg); border: 1px solid #2a2a2a; transition: transform 0.2s ease, box-shadow 0.2s ease; }
  .movie-card:hover { transform: translateY(-5px); box-shadow: 0 8px 25px rgba(0, 0, 0, 0.5); }
  .poster-wrapper { position: relative; }
  .movie-poster { width: 100%; aspect-ratio: 2 / 3; object-fit: cover; display: block; }
  .card-info { padding: 12px; }
  .card-title { font-size: 0.9rem; font-weight: 500; color: var(--text-light); margin: 0; line-height: 1.4; min-height: 2.8em; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .badges-top, .badges-bottom { position: absolute; left: 0; right: 0; display: flex; justify-content: space-between; align-items: center; z-index: 2; pointer-events: none; }
  .badges-top { top: 0; }
  .badges-bottom { bottom: 8px; padding: 0 8px; }
  .badge-group-left, .badge-group-right { display: flex; gap: 6px; pointer-events: all; align-items: center; }
  .badges-top .badge-group-right { padding-right: 8px; }
  .language-tag, .rating-tag, .type-tag { padding: 4px 10px; font-size: 0.75rem; font-weight: 600; border-radius: 6px; color: white; display: inline-flex; align-items: center; gap: 4px; }
  .language-tag { background-color: rgba(0, 0, 0, 0.7); }
  .rating-tag { background-color: rgba(245, 197, 24, 0.9); color: #000; }
  .type-tag { background-color: #00E599; color: #000; }
  .new-badge { background-color: var(--primary-color); color: white; font-weight: 700; padding: 4px 12px 4px 8px; font-size: 0.7rem; clip-path: polygon(0 0, 100% 0, 85% 100%, 0 100%); }

  @media (max-width: 768px) {
      .related-grid { gap: 10px; }
      .card-title { font-size: 0.8rem; }
      .badges-bottom { bottom: 6px; padding: 0 6px; }
      .language-tag, .rating-tag, .type-tag { padding: 2px 7px; font-size: 0.6rem; border-radius: 4px; }
      .new-badge { padding: 3px 10px 3px 6px; font-size: 0.6rem; }
  }
  @media (min-width: 769px) { .related-grid { grid-template-columns: repeat(4, 1fr); } }

  .card-preloader { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.75); z-index: 5; display: none; justify-content: center; align-items: center; backdrop-filter: blur(4px); }
  .card-preloader.active { display: flex; }
  .play-button-loader-small { width: 40px; height: 40px; border: 4px solid rgba(255, 255, 255, 0.4); border-top-color: #fff; border-radius: 50%; animation: spin 1s ease-in-out infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  
body.light-mode { --bg-color: #f0f2f5; --card-bg: #ffffff; --text-light: #1c1e21; --text-dark: #65676b; }
body.light-mode .go-back-btn { background-color: #e9ecef; color: #495057; border: 1px solid #dee2e6; }
body.light-mode .hero-section-wrapper { margin-bottom: 40px; }
body.light-mode .detail-hero-backdrop { box-shadow: 0 8px 25px rgba(0,0,0,0.1); border: 1px solid #e9ecef; }
body.light-mode .overlay-poster { border-color: rgba(0,0,0,0.1); }
body.light-mode .episode-item { border-left-color: #007bff; }

.main-footer { text-align: center; padding: 15px 10px; background-color: #111; color: #ccc; font-size: 0.9rem; border-top: 1px solid rgba(255,255,255,0.1); margin-top: 40px; transition: background 0.3s; }
.main-footer:hover { background-color: #222; color: #fff; }
  .report-button { display: inline-flex; align-items: center; gap: 10px; background-color: #555; color: #fff; padding: 12px 25px; border-radius: 8px; font-size: 1rem; font-weight: 500; border: 1px solid #666; transition: background-color 0.2s ease; }
  .report-button:hover { background-color: #6c757d; }
  .report-button i { font-size: 1.1rem; }
  
.edit-icon-link { position: absolute; top: 20px; right: 20px; background-color: rgba(0, 0, 0, 0.6); color: #fff; padding: 10px; width: 40px; height: 40px; display: flex; justify-content: center; align-items: center; border-radius: 50%; font-size: 1.2rem; transition: background-color 0.2s, transform 0.2s; z-index: 10; border: 2px solid #555; box-shadow: 0 4px 10px rgba(0,0,0,0.5); }
.edit-icon-link:hover { background-color: var(--primary-color); border-color: var(--primary-color); transform: scale(1.1); }
@media (min-width: 768px) { .edit-icon-link { right: 50px; } }

  .professional-footer { background: linear-gradient(to bottom, #1a1a1a, #0f0f0f); color: var(--text-dark); padding-top: 60px; margin-top: 50px; border-top: 4px solid #000; }
  .footer-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 40px; padding-bottom: 50px; }
  .footer-column-title { font-size: 1.3rem; font-weight: 600; color: var(--text-light); margin-bottom: 25px; position: relative; padding-bottom: 10px; }
  .footer-column-title::after { content: ''; position: absolute; bottom: 0; left: 0; width: 50px; height: 3px; background-color: var(--primary-color); }
  .footer-logo img { max-width: 160px; margin-bottom: 15px; }
  .footer-description { font-size: 0.95rem; line-height: 1.7; }
  .links-section ul { list-style: none; padding: 0; margin: 0; }
  .links-section ul li { margin-bottom: 12px; }
  .links-section ul li a { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--text-dark); transition: all 0.2s ease-in-out; }
  .links-section ul li a:hover { color: var(--primary-color); transform: translateX(5px); }
  .telegram-buttons-container { display: flex; flex-direction: column; gap: 15px; }
  .telegram-button { display: flex; align-items: center; gap: 15px; padding: 12px 15px; border-radius: 8px; text-decoration: none; color: white; background-color: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); transition: all 0.2s ease; }
  .telegram-button:hover { background-color: rgba(255, 255, 255, 0.1); border-color: var(--primary-color); transform: translateY(-2px); }
  .telegram-button i { font-size: 1.8rem; width: 30px; text-align: center; }
  .telegram-button.notification i { color: #34B7F1; } .telegram-button.request i { color: #f5c518; } .telegram-button.backup i { color: #28a745; }
  .telegram-button span { display: flex; flex-direction: column; } .telegram-button small { font-size: 0.75rem; color: var(--text-dark); }
  .footer-note { font-size: 0.8rem; color: var(--text-dark); margin-top: 20px; background-color: rgba(0,0,0,0.2); padding: 10px; border-radius: 5px; }
  .footer-note a { color: #34B7F1; font-weight: bold; }
  .footer-bottom-bar { background-color: #000; text-align: center; padding: 20px; font-size: 0.9rem; border-top: 1px solid #222; }
  @media (max-width: 768px) { .footer-grid { text-align: center; } .footer-column-title::after { left: 50%; transform: translateX(-50%); } .footer-logo { margin-left: auto; margin-right: auto; } .links-section ul li a { justify-content: center; } }
  
.gallery-section { margin: 40px 0; }
@keyframes rgb-glow-border { 0% { border-color: #ff00de; box-shadow: 0 0 8px #ff00de; } 25% { border-color: #00ffff; box-shadow: 0 0 10px #00ffff; } 50% { border-color: #00ff7f; box-shadow: 0 0 8px #00ff7f; } 75% { border-color: #f83d61; box-shadow: 0 0 10px #f83d61; } 100% { border-color: #ff00de; box-shadow: 0 0 8px #ff00de; } }
.gallery-content-wrapper { max-width: 90%; margin: 0 auto; }
.gallery-item a { display: block; position: relative; padding-top: 56.25%; border-radius: 8px; overflow: hidden; border: 2px solid transparent; animation: rgb-glow-border 5s linear infinite; }
.gallery-item img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; transition: opacity 0.7s ease-in-out; }
.thumbnail-stack { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
#auto-change-item .changing-image { opacity: 0; } #auto-change-item .changing-image.active { opacity: 1; }
@media (min-width: 768px) { .gallery-content-wrapper { display: grid; grid-template-columns: 2fr 1fr; gap: 15px; max-width: 1200px; } .hero-image-container { grid-column: 1 / 2; } .thumbnail-stack { grid-column: 2 / 3; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 0; } }

.download-hub-section { background-color: var(--card-bg); border: 1px solid #2a2a2a; border-radius: 12px; padding: 25px; margin: 40px auto; max-width: 800px; text-align: center; }
.hub-section-title { display: flex; align-items: center; justify-content: center; gap: 12px; font-size: 1.5rem; font-weight: 600; margin: 0 0 10px 0; }
.hub-section-description { color: var(--text-dark); margin: 0 0 25px 0; font-size: 1rem; line-height: 1.6; }
.hub-proceed-button { display: inline-flex; align-items: center; justify-content: center; gap: 12px; background-color: var(--primary-color); color: white; padding: 15px 35px; border-radius: 8px; font-size: 1.2rem; font-weight: 700; text-decoration: none; transition: all 0.2s ease; border: none; cursor: pointer; box-shadow: 0 4px 15px rgba(229, 9, 20, 0.3); }
.hub-proceed-button:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(229, 9, 20, 0.5); filter: brightness(1.1); }

.custom-loading-container { position: relative; width: 100%; max-width: 600px; margin: 50px auto; padding: 60px 0; text-align: center; background: #111; border-radius: 12px; box-shadow: 0 0 25px rgba(0,0,0,0.5); }
.custom-loading-spinner { margin: 0 auto 25px; width: 100px; height: 100px; border: 10px solid #444; border-top: 10px solid #ff0000; border-radius: 50%; animation: enhanced-spin 1s linear infinite; display: block; }
.custom-loading-text { color: #fff; font-size: 1.3rem; font-weight: bold; line-height: 1.4; }
@keyframes enhanced-spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
@media(max-width: 600px){ .custom-loading-spinner { width: 70px; height: 70px; border-width: 8px; } .custom-loading-text { font-size: 1.1rem; } }

  /* CSS for auto-blur poster */
  .blurred {
      filter: blur(15px) !important;
      transition: filter 0.4s ease;
  }
</style>
</head>
<body>
{{ ad_settings.ad_body_top | safe }}

{% macro render_movie_card(m) %}
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
      <div class="poster-wrapper">
        <div class="card-preloader">
            <div class="play-button-loader-small"></div>
        </div>
        <div class="badges-top">
            <div class="badge-group-left">
                {% if (datetime.utcnow() - m._id.generation_time.replace(tzinfo=None)).days < 7 %}
                    <span class="new-badge">NEW</span>
                {% endif %}
            </div>
            <div class="badge-group-right">
                {% if m.poster_badge %}
                    <span class="language-tag">{{ m.poster_badge }}</span>
                {% endif %}
            </div>
        </div>
        <img class="movie-poster" loading="lazy" src="{{ m.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ m.title }}">
        <div class="badges-bottom">
            <div class="badge-group-left">
                {% if m.vote_average and m.vote_average > 0 %}
                    <span class="rating-tag"><i class="fas fa-star"></i> {{ "%.1f"|format(m.vote_average) }}</span>
                {% endif %}
            </div>
            <div class="badge-group-right">
                <span class="type-tag">{{ m.type | title }}</span>
            </div>
        </div>
      </div>
      <div class="card-info">
        <h4 class="card-title">
          {{ m.title }}
          {% if m.release_year %} ({{ m.release_year }}){% elif m.release_date %} ({{ m.release_date.split('-')[0] }}){% endif %}
        </h4>
      </div>
    </a>
{% endmacro %}

{% if movie %}
<div class="page-header" style="position: relative; display: flex; align-items: center; justify-content: space-between;">
    <div style="display: flex; align-items: center;">
        <a href="{{ url_for('home') }}" class="go-back-btn"><i class="fas fa-arrow-left"></i><span> Go Back</span></a>
        <button id="poster-blur-toggle" class="go-back-btn" style="margin-left: 10px; cursor:pointer;" aria-label="Toggle Poster Blur"><i class="fas fa-eye-slash"></i></button>
    </div>
    
    {% if movie %}
        <a href="{{ url_for('edit_auth_redirect', movie_id=movie._id) }}" class="edit-icon-link" style="position: static;" title="Edit Content" onclick="return confirm('You are about to enter the Admin Edit area. Continue?')">
            <i class="fas fa-pencil-alt"></i>
        </a>
    {% endif %}
</div>
<div class="hero-section-wrapper">
    <div class="detail-hero-backdrop"><img src="{{ movie.backdrop or movie.poster }}" class="hero-backdrop-img" alt="Backdrop"><div class="hero-overlay"></div></div>
    <img src="{{ movie.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ movie.title }}" class="overlay-poster">
    {% if movie.type %}<div class="content-type-badge">{{ movie.type | title }}</div>{% endif %}
</div>
<div class="container content-info-section">
    <div class="detail-info">
        <h1 class="detail-title">{{ movie.title }}</h1>
        <div class="detail-meta">
            {% if movie.vote_average %}<div class="meta-item rating"><i class="fas fa-star"></i> {{ "%.1f"|format(movie.vote_average) }}</div>{% endif %}
            {% if movie.release_year %}<div class="meta-item"><i class="fas fa-calendar-alt"></i> {{ movie.release_year }}</div>{% elif movie.release_date %}<div class="meta-item"><i class="fas fa-calendar-alt"></i> {{ movie.release_date.split('-')[0] }}</div>{% endif %}
            {% if movie.languages %}<div class="meta-item"><i class="fas fa-language"></i> {{ movie.languages | join(' / ') }}</div>{% endif %}
            {% if movie.genres %}<div class="meta-item"><i class="fas fa-tag"></i> {{ movie.genres | join(' / ') }}</div>{% endif %}
        </div>
        <p class="detail-overview">{{ movie.overview }}</p>
    </div>
</div>
<div class="container">
    {% if movie.trailer_url %}
    <div class="trailer-section">
        <h2 class="section-title"><i class="fas fa-video"></i> Watch Trailer</h2>
        <div class="trailer-video-wrap"><iframe src="{{ movie.trailer_url }}" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>
    </div>
    {% endif %}

    <div style="text-align: center; margin: 40px 0;">
        <a href="{{ url_for('request_content', report_id=movie._id, title=movie.title) }}" class="report-button">
            <i class="fas fa-flag"></i> Report a Problem
        </a>
    </div>

{% if movie.backdrop_images and movie.backdrop_images|length > 0 %}
<section class="gallery-section">
    <h2 class="section-title"><i class="fas fa-images"></i> Image Gallery</h2>
    <div class="gallery-content-wrapper">
        <div class="gallery-item hero-image-container" id="auto-change-item">
            <a href="{{ movie.backdrop_images[0] }}" target="_blank">
                {% set images_for_hero = movie.backdrop_images[:1] + movie.backdrop_images[5:] %}
                {% for image in images_for_hero %}
                    <img src="{{ image }}" class="changing-image {% if loop.first %}active{% endif %}" alt="{{ movie.title }} backdrop image">
                {% endfor %}
            </a>
        </div>
        {% if movie.backdrop_images|length > 1 %}
        <div class="thumbnail-stack">
            {% for img_url in movie.backdrop_images[1:5] %}
            <div class="gallery-item thumbnail-item">
                <a href="{{ img_url }}" target="_blank">
                    <img src="{{ img_url }}" loading="lazy" alt="{{ movie.title }} backdrop thumbnail">
                </a>
            </div>
            {% endfor %}
        </div>
        {% endif %}
    </div>
</section>
{% endif %}
    
    {% if ad_settings.ad_detail_page %}<div class="ad-container">{{ ad_settings.ad_detail_page | safe }}</div>{% endif %}
    
    {% if movie.type == 'movie' %}
        {% set has_links = movie.streaming_links or movie.links or movie.files %}
        {% if has_links %}
            <div class="download-hub-section">
                <h3 class="hub-section-title">
                    <i class="fas fa-download"></i>
                    <span>Streaming & Download Options</span>
                </h3>
                <p class="hub-section-description">
                    All available links (1080p, 720p, Stream, Direct Dawnload, Telegram File etc.) are organized on the next page for your convenience 🔗👇.
                </p>
                <a href="{{ url_for('wait_page', target=quote(url_for('download_hub', movie_id=movie._id))) }}" class="hub-proceed-button">
                    <span>🍿 Proceed to Movie Link 🍿</span>
                    <i class="fas fa-arrow-right"></i>
                </a>
            </div>
        {% endif %}
   {% elif movie.type == 'series' %}
        {% if movie.episodes %}
            <div class="download-hub-section">
                <h3 class="hub-section-title">
                    <i class="fas fa-play-circle"></i>
                    <span>Watch All Episodes</span>
                </h3>
                <p class="hub-section-description">
                    All available seasons and episodes (1080p, 720p, Stream, Direct Dawnload, Telegram File etc.) are organized on the next page. Click below to see all links 🔗👇.
                </p>
                <a href="{{ url_for('wait_page', target=quote(url_for('series_hub', series_id=movie._id))) }}" class="hub-proceed-button">
                    <span>🍿 Proceed to Series Link 🍿</span>
                    <i class="fas fa-arrow-right"></i>
                </a>
            </div>
        {% endif %}
    {% endif %}
    
{% set all_links = [] %}
{% if movie.streaming_links %}{% set _ = all_links.append('stream') %}{% endif %}
{% if movie.links %}{% set _ = all_links.append('download') %}{% endif %}
{% if movie.files %}{% set _ = all_links.append('telegram') %}{% endif %}
{% if movie.episodes %}
    {% for ep in movie.episodes %}
        {% if ep.stream_link or ep.download_link or ep.links %}
            {% set _ = all_links.append('episode') %}
        {% endif %}
    {% endfor %}
{% endif %}

{% if all_links|length == 0 %}
<div style="margin-top:30px;text-align:center;">
  {% if movie.type == 'movie' %}
      <h3 class="section-title"><i class="fas fa-link"></i> Links & Downloads</h3>
      <p style="font-size:1rem;color:#ccc;margin-bottom:5px;">
          Oops! No streaming or download links are available for "{{ movie.title }}" yet. We are working to add them soon 🍿.
      </p>
      <hr style="width:50px;border:2px solid red;margin:auto;margin-bottom:20px;">
  {% elif movie.type == 'series' %}
      <h3 class="section-title"><i class="fas fa-play-circle"></i> Links & Episodes</h3>
      <p style="font-size:1rem;color:#ccc;margin-bottom:5px;">
          Oops! All episodes of "{{ movie.title }}" are currently unavailable. Please check back soon 🍿.
      </p>
      <hr style="width:50px;border:2px solid red;margin:auto;margin-bottom:20px;">
  {% endif %}
  <div class="custom-loading-container">
    <div class="custom-loading-spinner"></div>
    <div class="custom-loading-text">Loading<br>Please Wait</div>
  </div>
</div>
{% endif %}
    
{% if related_content %}
<section class="category-section">
    <div class="category-header">
        <h2 class="category-title">You Might Also Like</h2>
    </div>
    <div class="related-grid">
        {% for m in related_content %}
            {{ render_movie_card(m) }} 
        {% endfor %}
    </div>
</section>
{% endif %}
</div>
{% else %}<div style="display:flex; justify-content:center; align-items:center; height:100vh;"><h2>Content not found.</h2></div>{% endif %}
<script src="https://unpkg.com/swiper/swiper-bundle.min.js"></script>
<footer class="professional-footer">
    <div class="container footer-grid">
        <div class="footer-column about-section">
            <a href="{{ url_for('home') }}" class="footer-logo">
                <img src="https://i.postimg.cc/3wxTc4K7/1000020248-removebg-preview.png" alt="{{ website_name }} Logo">
            </a>
            <p class="footer-description">
                Your ultimate destination for the latest movies and web series. We are dedicated to providing a seamless entertainment experience.
            </p>
        </div>
        <div class="footer-column links-section">
            <h4 class="footer-column-title">Site Links</h4>
            <ul>
                <li><a href="{{ url_for('dmca') }}"><i class="fas fa-gavel"></i> DMCA Policy</a></li>
                <li><a href="{{ url_for('disclaimer') }}"><i class="fas fa-exclamation-triangle"></i> Disclaimer</a></li>
                <li><a href="{{ url_for('create_website') }}"><i class="fas fa-palette"></i> Create Your Website</a></li>
            </ul>
        </div>
        <div class="footer-column community-section">
            <h4 class="footer-column-title">Join Our Community</h4>
            <div class="telegram-buttons-container">
                <a href="https://t.me/allmoviepsz" target="_blank" class="telegram-button notification">
                    <i class="fas fa-bell"></i>
                    <span><strong>New Content Alerts</strong><small>Get notified for every new upload</small></span>
                </a>
                <a href="https://t.me/+0kZRI3EUX54wM2Nl" target="_blank" class="telegram-button request">
                    <i class="fas fa-comments"></i>
                    <span><strong>Join Request Group</strong><small>Request your favorite content</small></span>
                </a>
                <a href="https://t.me/Yabotz" target="_blank" class="telegram-button backup">
                    <i class="fas fa-shield-alt"></i>
                    <span><strong>Backup Channel</strong><small>Join for future updates</small></span>
                </a>
            </div>
            <p class="footer-note">
                <strong>Alternatively,</strong> you can use the <a href="{{ url_for('request_content') }}">Request</a> option in our bottom menu to submit requests directly on the site.
            </p>
        </div>
    </div>
    <div class="footer-bottom-bar">
        <p>&copy; {{ datetime.utcnow().year }} {{ website_name }}. All Rights Reserved. Crafted with care for movie lovers.</p>
    </div>
</footer>
<script>
    document.addEventListener('DOMContentLoaded', function () {
        const applySavedTheme = () => {
            const savedTheme = localStorage.getItem('theme') || 'dark';
            if (savedTheme === 'light') {
                document.body.classList.add('light-mode');
            } else {
                document.body.classList.remove('light-mode');
            }
        };
        applySavedTheme();

        const autoChangeContainer = document.getElementById('auto-change-item');
        if (autoChangeContainer) {
            const images = autoChangeContainer.querySelectorAll('.changing-image');
            const link = autoChangeContainer.querySelector('a');
            let currentIndex = 0;
            if (images.length > 1) {
                setInterval(() => {
                    images[currentIndex].classList.remove('active');
                    currentIndex = (currentIndex + 1) % images.length;
                    images[currentIndex].classList.add('active');
                    link.href = images[currentIndex].src;
                }, 1500); 
            }
        }
    });

    // === Poster Auto Blur Logic ===
    const blurToggleBtn = document.getElementById('poster-blur-toggle');
    let blurTimeout;
    const autoBlurSeconds = {{ site_config.auto_blur_timer | default(5) }};
    let isBlurred = true;
    const posterSelectors = '.movie-poster, .hero-bg-img, .hero-backdrop-img, .overlay-poster, .changing-image, .thumbnail-item img';

    function applyBlur() {
        document.querySelectorAll(posterSelectors).forEach(img => img.classList.add('blurred'));
        if(blurToggleBtn) blurToggleBtn.innerHTML = '<i class="fas fa-eye-slash"></i>';
        isBlurred = true;
    }

    function removeBlur() {
        document.querySelectorAll(posterSelectors).forEach(img => img.classList.remove('blurred'));
        if(blurToggleBtn) blurToggleBtn.innerHTML = '<i class="fas fa-eye"></i>';
        isBlurred = false;
        
        clearTimeout(blurTimeout);
        if (autoBlurSeconds > 0) {
            blurTimeout = setTimeout(applyBlur, autoBlurSeconds * 1000);
        }
    }

    if(blurToggleBtn) {
        blurToggleBtn.addEventListener('click', () => {
            if (isBlurred) {
                removeBlur();
            } else {
                applyBlur();
                clearTimeout(blurTimeout);
            }
        });
    }
    
    // Apply blur on page load
    applyBlur();
</script>
{{ ad_settings.ad_footer | safe }}
</body></html>
"""

# =======================================================================================
# === [START] UPDATED WAITING PAGE TEMPLATES ============================================
# =======================================================================================

# --- STEP 1 HTML ---
wait_step1_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Generating Link... (Step {{ step }}/{{ total_steps }}) - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    {{ ad_settings.ad_header | safe }}
    <style>
        :root {--primary-color: #E50914; --bg-color: #000000; --card-bg: #1a1a1a; --text-light: #ffffff; --text-dark: #a0a0a0;}
        html { scroll-behavior: smooth; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); text-align: center; margin: 0; padding: 0; }
        .fixed-header { position: fixed; top: 0; left: 0; width: 100%; background-color: var(--card-bg); padding: 10px 0; z-index: 1000; display: flex; justify-content: center; align-items: center; box-shadow: 0 2px 10px rgba(0,0,0,0.5); border-bottom: 1px solid #333; }
        .fixed-header img { height: 50px; width: auto; }
        .page-section { min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 20px; box-sizing: border-box; }
        #top-content { padding-top: 80px; }
        .wait-container { background-color: var(--card-bg); padding: 40px; border-radius: 12px; max-width: 500px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { font-size: 1.8rem; color: var(--primary-color); margin-bottom: 20px; }
        p { color: var(--text-dark); margin-bottom: 30px; font-size: 1rem; }
        .timer { font-size: 2.5rem; font-weight: 700; color: var(--text-light); margin-bottom: 30px; }
        .action-btn { display: inline-block; text-decoration: none; color: white; font-weight: 600; cursor: pointer; border: none; padding: 12px 30px; border-radius: 50px; font-size: 1rem; background-color: #555; transition: background-color 0.2s; }
        .action-btn:disabled { cursor: not-allowed; }
        .action-btn.ready { background-color: var(--primary-color); }
        .ad-container { margin: 30px auto; width: 100%; max-width: 90%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
        #bottom-content { display: none; }
        .main-footer { text-align: center; padding: 15px 10px; background-color: #111; color: #ccc; font-size: 0.9rem; border-top: 1px solid rgba(255,255,255,0.1); margin-top: 40px; transition: background 0.3s; }
        .main-footer:hover { background-color: #222; color: #fff; }
    </style>
</head>
<body>
    <header class="fixed-header">
        <img src="https://i.postimg.cc/3wxTc4K7/1000020248-removebg-preview.png" alt="Website Logo">
    </header>

    <div id="top-content" class="page-section">
        {{ ad_settings.ad_body_top | safe }}
        <div class="wait-container">
            <h1>Please Wait</h1>
            <p>Your download link is being prepared. Please scroll down after the timer ends.</p>
            <div id="timer-text" class="timer">Please wait <span id="countdown">{{ timer }}</span> seconds...</div>
            <a id="continue-btn-1" href="#bottom-content" class="action-btn" disabled>Preparing Link...</a>
        </div>
        {% if ad_settings.ad_wait_page %}<div class="ad-container">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>

    <div class="ad-section" style="padding: 50px 0;">
        <h2>Advertisement</h2>
        {% if ad_settings.ad_wait_page %}<div class="ad-container" style="min-height: 200px;">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
        {% if ad_settings.ad_detail_page %}<div class="ad-container">{{ ad_settings.ad_detail_page | safe }}</div>{% endif %}
    </div>
    
    <div id="bottom-content" class="page-section">
        <div class="wait-container">
            <h1>Ready to Continue</h1>
            <p>Click the button below to proceed to the next step.</p>
            <a href="{{ next_step_url }}" class="action-btn ready">Continue</a>
        </div>
    </div>
    <a href="https://t.me/allmoviepsz" target="_blank" rel="noopener noreferrer" style="text-decoration: none;">
  <footer class="main-footer">
      <p>&copy; {{ datetime.utcnow().year }} {{ website_name }}. All Rights Reserved.</p>
  </footer>
</a>

    <script>
        (function() {
            let timeLeft = {{ timer }};
            const countdownElement = document.getElementById('countdown');
            const timerTextElement = document.getElementById('timer-text');
            const continueBtn1 = document.getElementById('continue-btn-1');
            const bottomContent = document.getElementById('bottom-content');

            const timer = setInterval(() => {
                if (timeLeft <= 0) {
                    clearInterval(timer);
                    timerTextElement.textContent = "Please scroll down and click continue.";
                    continueBtn1.removeAttribute('disabled');
                    continueBtn1.classList.add('ready');
                    continueBtn1.textContent = 'Click Here to Continue';
                    bottomContent.style.display = 'flex';
                } else {
                    countdownElement.textContent = timeLeft;
                }
                timeLeft--;
            }, 1000);
        })();
    </script>
    
    {{ ad_settings.ad_footer | safe }}
</body>
</html>
"""

# --- STEP 2 HTML ---
wait_step2_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Processing... (Step {{ step }}/{{ total_steps }}) - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    {{ ad_settings.ad_header | safe }}
    <style>
        :root {--primary-color: #007bff; --bg-color: #000000; --card-bg: #1a1a1a; --text-light: #ffffff; --text-dark: #a0a0a0;}
        html { scroll-behavior: smooth; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); text-align: center; margin: 0; padding: 0; }
        .fixed-header { position: fixed; top: 0; left: 0; width: 100%; background-color: var(--card-bg); padding: 10px 0; z-index: 1000; display: flex; justify-content: center; align-items: center; box-shadow: 0 2px 10px rgba(0,0,0,0.5); border-bottom: 1px solid #333; }
        .fixed-header img { height: 50px; width: auto; }
        .page-section { min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 20px; box-sizing: border-box; }
        #top-content { padding-top: 80px; }
        .wait-container { background-color: var(--card-bg); padding: 40px; border-radius: 12px; max-width: 500px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { font-size: 1.8rem; color: var(--primary-color); margin-bottom: 20px; }
        p { color: var(--text-dark); margin-bottom: 30px; font-size: 1rem; }
        .timer { font-size: 2.5rem; font-weight: 700; color: var(--text-light); margin-bottom: 30px; }
        .action-btn { display: inline-block; text-decoration: none; color: white; font-weight: 600; cursor: pointer; border: none; padding: 12px 30px; border-radius: 50px; font-size: 1rem; background-color: #555; transition: background-color 0.2s; }
        .action-btn:disabled { cursor: not-allowed; }
        .action-btn.ready { background-color: var(--primary-color); }
        .ad-container { margin: 30px auto; width: 100%; max-width: 90%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
        #bottom-content { display: none; }
        .main-footer { text-align: center; padding: 15px 10px; background-color: #111; color: #ccc; font-size: 0.9rem; border-top: 1px solid rgba(255,255,255,0.1); margin-top: 40px; transition: background 0.3s; }
        .main-footer:hover { background-color: #222; color: #fff; }
    </style>
</head>
<body>
    <header class="fixed-header">
        <img src="https://i.postimg.cc/3wxTc4K7/1000020248-removebg-preview.png" alt="Website Logo">
    </header>

    <div id="top-content" class="page-section">
        {{ ad_settings.ad_body_top | safe }}
        <div class="wait-container">
            <h1>Almost There...</h1>
            <p>Please wait while we process your request. Scroll down after the timer.</p>
            <div id="timer-text" class="timer">Wait <span id="countdown">{{ timer }}</span> seconds...</div>
            <a id="continue-btn-1" href="#bottom-content" class="action-btn" disabled>Processing...</a>
        </div>
        {% if ad_settings.ad_wait_page %}<div class="ad-container">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>

    <div class="ad-section" style="padding: 50px 0;">
        <h2>Advertisement</h2>
        {% if ad_settings.ad_wait_page %}<div class="ad-container" style="min-height: 200px;">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>
    
    <div id="bottom-content" class="page-section">
        <div class="wait-container">
            <h1>Ready for Next Step</h1>
            <p>Click the button below to proceed.</p>
            <a href="{{ next_step_url }}" class="action-btn ready">Continue to Next Step</a>
        </div>
    </div>
    <a href="https://t.me/allmoviepsz" target="_blank" rel="noopener noreferrer" style="text-decoration: none;">
  <footer class="main-footer">
      <p>&copy; {{ datetime.utcnow().year }} {{ website_name }}. All Rights Reserved.</p>
  </footer>
</a>

    <script>
        (function() {
            let timeLeft = {{ timer }};
            const countdownElement = document.getElementById('countdown');
            const timerTextElement = document.getElementById('timer-text');
            const continueBtn1 = document.getElementById('continue-btn-1');
            const bottomContent = document.getElementById('bottom-content');

            const timer = setInterval(() => {
                if (timeLeft <= 0) {
                    clearInterval(timer);
                    timerTextElement.innerHTML = "Ready! Please scroll down.";
                    continueBtn1.removeAttribute('disabled');
                    continueBtn1.classList.add('ready');
                    continueBtn1.textContent = 'Click to Continue';
                    bottomContent.style.display = 'flex';
                } else {
                    countdownElement.textContent = timeLeft;
                }
                timeLeft--;
            }, 1000);
        })();
    </script>
    {{ ad_settings.ad_footer | safe }}
</body>
</html>
"""

# --- STEP 3 HTML (FINAL PAGE) ---
wait_step3_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Link Ready! (Step {{ step }}/{{ total_steps }}) - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    {{ ad_settings.ad_header | safe }}
    <style>
        :root {--primary-color: #28a745; --bg-color: #000000; --card-bg: #1a1a1a; --text-light: #ffffff; --text-dark: #a0a0a0;}
        html { scroll-behavior: smooth; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); text-align: center; margin: 0; padding: 0; }
        .fixed-header { position: fixed; top: 0; left: 0; width: 100%; background-color: var(--card-bg); padding: 10px 0; z-index: 1000; display: flex; justify-content: center; align-items: center; box-shadow: 0 2px 10px rgba(0,0,0,0.5); border-bottom: 1px solid #333; }
        .fixed-header img { height: 50px; width: auto; }
        .page-section { min-height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 20px; box-sizing: border-box; }
        #top-content { padding-top: 80px; }
        .wait-container { background-color: var(--card-bg); padding: 40px; border-radius: 12px; max-width: 500px; width: 100%; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { font-size: 1.8rem; color: var(--primary-color); margin-bottom: 20px; }
        p { color: var(--text-dark); margin-bottom: 30px; font-size: 1rem; }
        .timer { font-size: 2.5rem; font-weight: 700; color: var(--text-light); margin-bottom: 30px; }
        .action-btn { display: inline-block; text-decoration: none; color: white; font-weight: 600; cursor: pointer; border: none; padding: 12px 30px; border-radius: 50px; font-size: 1rem; background-color: #555; transition: background-color 0.2s; }
        .action-btn:disabled { cursor: not-allowed; }
        .action-btn.ready { background-color: var(--primary-color); }
        .ad-container { margin: 30px auto; width: 100%; max-width: 90%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
        #bottom-content { display: none; }
    </style>
</head>
<body>
    <header class="fixed-header">
        <img src="https://i.postimg.cc/3wxTc4K7/1000020248-removebg-preview.png" alt="Website Logo">
    </header>

    <div id="top-content" class="page-section">
        {{ ad_settings.ad_body_top | safe }}
        <div class="wait-container">
            <h1>Final Step</h1>
            <p>Your download link is ready. Please scroll down after the timer.</p>
            <div id="timer-text" class="timer">Please wait <span id="countdown">{{ timer }}</span> seconds...</div>
            <a id="continue-btn-1" href="#bottom-content" class="action-btn" disabled>Generating Link...</a>
        </div>
        {% if ad_settings.ad_wait_page %}<div class="ad-container">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>

    <div class="ad-section" style="padding: 50px 0;">
        <h2>Advertisement</h2>
        {% if ad_settings.ad_wait_page %}<div class="ad-container" style="min-height: 200px;">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>
    
    <div id="bottom-content" class="page-section">
        <div class="wait-container">
            <h1>Your Link is Ready!</h1>
            <p>Click the button below to get your file.</p>
            <a href="{{ target_url | safe }}" class="action-btn ready">Get Link</a>
        </div>
    </div>

    <script>
        (function() {
            let timeLeft = {{ timer }};
            const countdownElement = document.getElementById('countdown');
            const timerTextElement = document.getElementById('timer-text');
            const continueBtn1 = document.getElementById('continue-btn-1');
            const bottomContent = document.getElementById('bottom-content');

            const timer = setInterval(() => {
                if (timeLeft <= 0) {
                    clearInterval(timer);
                    timerTextElement.innerHTML = "Link is Ready! Scroll Down.";
                    continueBtn1.removeAttribute('disabled');
                    continueBtn1.classList.add('ready');
                    continueBtn1.textContent = 'Click to Scroll Down';
                    bottomContent.style.display = 'flex';
                } else {
                    countdownElement.textContent = timeLeft;
                }
                timeLeft--;
            }, 1000);
        })();
    </script>
    {{ ad_settings.ad_footer | safe }}
</body>
</html>
"""

# =======================================================================================
# === [END] UPDATED WAITING PAGE TEMPLATES ==============================================
# =======================================================================================

request_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Contact Us / Report - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root { --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a; --text-light: #f5f5f5; --text-dark: #a0a0a0; }
        body { font-family: 'Poppins', sans-serif; background: var(--bg-color); color: var(--text-light); padding: 20px; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 100vh; }
        .contact-container { max-width: 600px; width: 100%; background: var(--card-bg); padding: 30px; border-radius: 8px; }
        h2 { color: var(--primary-color); font-size: 2.5rem; text-align: center; margin-bottom: 25px; }
        .form-group { margin-bottom: 20px; } label { display: block; margin-bottom: 8px; font-weight: 500; }
        input, select, textarea { width: 100%; padding: 12px; border-radius: 4px; border: 1px solid #333; font-size: 1rem; background: #222; color: var(--text-light); box-sizing: border-box; }
        textarea { resize: vertical; min-height: 120px; }
        button[type="submit"] { background: var(--primary-color); color: white; font-weight: 700; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1.1rem; width: 100%; }
        .success-message { text-align: center; padding: 20px; background-color: #1f4e2c; color: #d4edda; border-radius: 5px; margin-bottom: 20px; }
        .back-link { display: block; text-align: center; margin-top: 20px; color: var(--primary-color); text-decoration: none; font-weight: bold; }
    </style>
</head>
<body>
<div class="contact-container">
    <h2>Contact Us</h2>
    {% if message_sent %}
        <div class="success-message"><p>Your message has been sent successfully. Thank you!</p></div>
        <a href="{{ url_for('home') }}" class="back-link">← Back to Home</a>
    {% else %}
        <form method="post">
            <div class="form-group">
                <label for="type">Subject:</label>
                <select name="type" id="type">
                    <option value="Movie Request" {% if prefill_type == 'Problem Report' %}disabled{% endif %}>Movie/Series Request</option>
                    <option value="Problem Report" {% if prefill_type == 'Problem Report' %}selected{% endif %}>Report a Problem</option>
                    <option value="General Feedback">General Feedback</option>
                </select>
            </div>
            <div class="form-group">
                <label for="content_title">Movie/Series Title:</label>
                <input type="text" name="content_title" id="content_title" value="{{ prefill_title }}" required>
            </div>
            <div class="form-group">
                <label for="message">Your Message:</label>
                <textarea name="message" id="message" required {% if prefill_id %}autofocus{% endif %}></textarea>
            </div>
            <div class="form-group">
                <label for="email">Your Email (Optional):</label>
                <input type="email" name="email" id="email">
            </div>
            <input type="hidden" name="reported_content_id" value="{{ prefill_id }}">
            <button type="submit">Submit</button>
        </form>
        <a href="{{ url_for('home') }}" class="back-link">← Cancel</a>
    {% endif %}
</div>
</body>
</html>
"""


admin_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>    
        :root { --netflix-red: #E50914; --netflix-black: #141414; --dark-gray: #222; --light-gray: #333; --text-light: #f5f5f5; }
        body { font-family: 'Roboto', sans-serif; background: var(--netflix-black); color: var(--text-light); margin: 0; padding: 20px; }
        .admin-container { max-width: 1200px; margin: 20px auto; }
        .admin-header { display: flex; align-items: center; justify-content: space-between; border-bottom: 2px solid var(--netflix-red); padding-bottom: 10px; margin-bottom: 30px; }
        .admin-header h1 { font-family: 'Bebas Neue', sans-serif; font-size: 3rem; color: var(--netflix-red); margin: 0; }
        h2 { font-family: 'Bebas Neue', sans-serif; color: var(--netflix-red); font-size: 2.2rem; margin-top: 40px; margin-bottom: 20px; border-left: 4px solid var(--netflix-red); padding-left: 15px; }
        form { background: var(--dark-gray); padding: 25px; border-radius: 8px; }
        fieldset { border: 1px solid var(--light-gray); border-radius: 5px; padding: 20px; margin-bottom: 20px; }
        legend { font-weight: bold; color: var(--netflix-red); padding: 0 10px; font-size: 1.2rem; }
        .form-group { margin-bottom: 15px; } label { display: block; margin-bottom: 8px; font-weight: bold; }
        input, textarea, select { width: 100%; padding: 12px; border-radius: 4px; border: 1px solid var(--light-gray); font-size: 1rem; background: var(--light-gray); color: var(--text-light); box-sizing: border-box; }
        textarea { resize: vertical; min-height: 100px;}
        .btn { display: inline-block; text-decoration: none; color: white; font-weight: 700; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1rem; transition: background-color 0.2s; }
        .btn:disabled { background-color: #555; cursor: not-allowed; }
        .btn-primary { background: var(--netflix-red); } .btn-primary:hover:not(:disabled) { background-color: #B20710; }
        .btn-secondary { background: #555; } .btn-danger { background: #dc3545; }
        .btn-edit { background: #007bff; } .btn-success { background: #28a745; }
        .table-container { display: block; overflow-x: auto; white-space: nowrap; }
        table { width: 100%; border-collapse: collapse; } th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid var(--light-gray); }
        .action-buttons { display: flex; gap: 10px; }
        .dynamic-item { border: 1px solid var(--light-gray); padding: 15px; margin-bottom: 15px; border-radius: 5px; position: relative; }
        .dynamic-item .btn-danger { position: absolute; top: 10px; right: 10px; padding: 4px 8px; font-size: 0.8rem; }
        hr { border: 0; height: 1px; background-color: var(--light-gray); margin: 30px 0; }
        .tmdb-fetcher { display: flex; gap: 10px; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 15px; padding: 10px 0; } .checkbox-group label { display: flex; align-items: center; gap: 8px; font-weight: normal; cursor: pointer;}
        .checkbox-group input { width: auto; }
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 2000; display: none; justify-content: center; align-items: center; padding: 20px; }
        .modal-content { background: var(--dark-gray); padding: 30px; border-radius: 8px; width: 100%; max-width: 900px; max-height: 90vh; display: flex; flex-direction: column; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-shrink: 0; }
        .modal-body { overflow-y: auto; }
        .modal-close { background: none; border: none; color: #fff; font-size: 2rem; cursor: pointer; }
        #search-results { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 20px; }
        .result-item { cursor: pointer; text-align: center; }
        .result-item img { width: 100%; aspect-ratio: 2/3; object-fit: cover; border-radius: 5px; margin-bottom: 10px; border: 2px solid transparent; transition: all 0.2s; }
        .result-item:hover img { transform: scale(1.05); border-color: var(--netflix-red); }
        .manage-content-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; }
        .search-form { display: flex; gap: 10px; flex-grow: 1; max-width: 500px; }
        .dashboard-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: var(--dark-gray); padding: 20px; border-radius: 8px; text-align: center; border-left: 5px solid var(--netflix-red); }
        .stat-card h3 { margin: 0 0 10px; font-size: 1.2rem; } .stat-card p { font-size: 2.5rem; font-weight: 700; margin: 0; color: var(--netflix-red); }
        .category-management { display: flex; flex-wrap: wrap; gap: 30px; align-items: flex-start; }
        .status-badge { padding: 4px 8px; border-radius: 4px; color: white; font-size: 0.8rem; font-weight: bold; }
        .status-pending { background-color: #ffc107; color: black; } .status-fulfilled { background-color: #28a745; } .status-rejected { background-color: #6c757d; }
        .pagination { display: flex; justify-content: center; align-items: center; gap: 10px; margin: 30px 0; }
        .pagination a, .pagination span { padding: 10px 18px; border-radius: 6px; font-weight: 600; font-size: 0.9rem; text-decoration: none; border: none; }
        .pagination a { background-color: var(--light-gray); color: var(--text-light); }
        .pagination a:hover { background-color: #444; }
        .pagination .current { background-color: var(--netflix-red); color: white; }
        
        /* Admin Panel Tabs CSS */
        .admin-tabs { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 25px; border-bottom: 2px solid var(--light-gray); }
        .tab-button { padding: 15px 20px; cursor: pointer; background: none; border: none; color: var(--text-light); font-size: 1.1rem; font-weight: bold; border-bottom: 3px solid transparent; transition: all 0.2s ease-in-out; }
        .tab-button:hover { background-color: var(--light-gray); }
        .tab-button.active { color: var(--netflix-red); border-bottom-color: var(--netflix-red); }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.5s; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    </style>
</head>
<body>
<div class="admin-container">
    <header class="admin-header"><h1>Admin Panel</h1><a href="{{ url_for('home') }}" target="_blank">View Site</a></header>
    
    <div class="admin-tabs">
        <button class="tab-button active" onclick="openTab(event, 'add-content')"><i class="fas fa-plus-circle"></i> Add/Edit Content</button>
        <button class="tab-button" onclick="openTab(event, 'manage-content')"><i class="fas fa-tasks"></i> Content Management</button>
        <button class="tab-button" onclick="openTab(event, 'category-ott')"><i class="fas fa-tags"></i> Categories & OTT</button>
        <button class="tab-button" onclick="openTab(event, 'ad-settings')"><i class="fas fa-bullhorn"></i> Advertisements</button>
        <button class="tab-button" onclick="openTab(event, 'advanced-settings')"><i class="fas fa-cogs"></i> Advanced Settings</button>
    </div>

    <!-- Tab 1: Add Content -->
    <div id="add-content" class="tab-content active">
        <h2><i class="fas fa-plus-circle"></i> Add New Content</h2>
        <fieldset><legend>Automatic Method (Search TMDB)</legend><div class="form-group"><div class="tmdb-fetcher"><input type="text" id="tmdb_search_query" placeholder="e.g., Avengers Endgame"><button type="button" id="tmdb_search_btn" class="btn btn-primary" onclick="searchTmdb()">Search</button></div></div></fieldset>
        <form method="post">
            <input type="hidden" name="form_action" value="add_content"><input type="hidden" name="tmdb_id" id="tmdb_id">
            <fieldset><legend>Core Details</legend>
                <div class="form-group"><label>Title:</label><input type="text" name="title" id="title" required></div>
                <div class="form-group"><label>Poster URL:</label><input type="url" name="poster" id="poster"></div>
                <div class="form-group"><label>Backdrop URL:</label><input type="url" name="backdrop" id="backdrop"></div>
                <div class="form-group"><label>Overview:</label><textarea name="overview" id="overview"></textarea></div>
                <div class="form-group"><label>Languages (comma-separated):</label><input type="text" name="languages" id="languages" placeholder="e.g. Hindi, English"></div>
                <div class="form-group"><label>Poster Badge:</label><input type="text" name="poster_badge" placeholder="e.g., 4K HDR, Bsub, Dubbed"></div>
                <div class="form-group"><label>Genres (comma-separated):</label><input type="text" name="genres" id="genres"></div>
                <div class="form-group"><label>Release Year:</label><input type="text" name="release_year" id="release_year" placeholder="e.g., 2024"></div>
                <div class="form-group"><label>Trailer URL (YouTube Embed):</label><input type="url" name="trailer_url" id="trailer_url" placeholder="https://www.youtube.com/embed/VIDEO_ID"></div>
                <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie">Movie</option><option value="series">Series</option></select></div>
            </fieldset>
            <fieldset><legend>Backdrop Images</legend>
                <div id="backdrop_images_container"></div>
                <button type="button" onclick="addBackdropField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Backdrop Image</button>
            </fieldset>
            <fieldset><legend>Categories</legend>
                <div class="form-group checkbox-group">
                    {% for cat in categories_list %}<label><input type="checkbox" name="categories" value="{{ cat.name }}"> {{ cat.name }}</label>{% endfor %}
                </div>
            </fieldset>
            <fieldset><legend>OTT Platforms</legend>
                <div class="form-group checkbox-group">
                    {% for platform in ott_platforms_list %}<label><input type="checkbox" name="ott_platforms" value="{{ platform.name }}"> {{ platform.name }}</label>{% endfor %}
                </div>
            </fieldset>
            <div id="movie_fields">
                <fieldset><legend>Movie Links</legend>
                    <p><b>Streaming Links (Optional)</b></p>
                    <div class="form-group"><label>Streaming Link 1 (e.g., 480p Server):</label><input type="url" name="streaming_link_1" /></div>
                    <div class="form-group"><label>Streaming Link 2 (e.g., 720p Server):</label><input type="url" name="streaming_link_2" /></div>
                    <div class="form-group"><label>Streaming Link 3 (e.g., 1080p Server):</label><input type="url" name="streaming_link_3" /></div><hr style="margin:20px 0;">
                    <p><b>Direct Download Links</b></p>
                    <div class="form-group"><label>480p Link:</label><input type="url" name="link_480p" /></div>
                    <div class="form-group"><label>720p Link:</label><input type="url" name="link_720p" /></div>
                    <div class="form-group"><label>1080p Link:</label><input type="url" name="link_1080p" /></div><hr style="margin:20px 0;">
                    <p><b>Get from Telegram</b></p>
                    <div class="form-group"><label>480p Telegram Link:</label><input type="url" name="telegram_link_480p" /></div>
                    <div class="form-group"><label>720p Telegram Link:</label><input type="url" name="telegram_link_720p" /></div>
                    <div class="form-group"><label>1080p Telegram Link:</label><input type="url" name="telegram_link_1080p" /></div>
                </fieldset>
            </div>
            <div id="episode_fields" style="display: none;">
                <fieldset><legend>Series Episodes</legend>
                    <div id="episodes_container"></div>
                    <button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button>
                </fieldset>
            </div>
            <button type="submit" class="btn btn-primary"><i class="fas fa-check"></i> Add Content</button>
        </form>
    </div>

    <!-- Tab 2: Content Management -->
    <div id="manage-content" class="tab-content">
        <h2><i class="fas fa-tachometer-alt"></i> At a Glance</h2>
        <div class="dashboard-stats">
            <div class="stat-card"><h3>Total Content</h3><p>{{ stats.total_content }}</p></div>
            <div class="stat-card"><h3>Total Movies</h3><p>{{ stats.total_movies }}</p></div>
            <div class="stat-card"><h3>Total Series</h3><p>{{ stats.total_series }}</p></div>
            <div class="stat-card"><h3>Pending Requests</h3><p>{{ stats.pending_requests }}</p></div>
        </div>
        <hr>
        <h2><i class="fas fa-inbox"></i> Manage Requests</h2>
        <div class="table-container">
            <table>
                <thead><tr><th>Subject (Type)</th><th>Title</th><th>Message</th><th>Email</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody>
                {% for req in requests_list %}
                <tr>
                    <td>{{ req.type or 'N/A' }}</td>
                    <td>{{ req.name }}</td>
                    <td style="white-space: pre-wrap; min-width: 200px;">{{ req.info }}</td>
                    <td>{{ req.email or 'N/A' }}</td>
                    <td><span class="status-badge status-{{ req.status|lower }}">{{ req.status }}</span></td>
                    <td class="action-buttons">
                        <a href="{{ url_for('update_request_status', req_id=req._id, status='Fulfilled') }}" class="btn btn-success" style="padding: 5px 10px;">Fulfilled</a>
                        <a href="{{ url_for('update_request_status', req_id=req._id, status='Rejected') }}" class="btn btn-secondary" style="padding: 5px 10px;">Rejected</a>
                        <a href="{{ url_for('delete_request', req_id=req._id) }}" class="btn btn-danger" style="padding: 5px 10px;" onclick="return confirm('Are you sure?')">Delete</a>
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="6" style="text-align:center;">No pending requests.</td></tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
        <hr>
        <div class="manage-content-header">
            <h2><i class="fas fa-tasks"></i> Manage Content</h2>
            <div class="search-form"><input type="search" id="admin-live-search" placeholder="Type to search content live..." autocomplete="off"></div>
        </div>
        <form method="post" id="bulk-action-form">
            <input type="hidden" name="form_action" value="bulk_delete">
            <div class="table-container"><table>
                <thead><tr><th><input type="checkbox" id="select-all"></th><th>Title</th><th>Type</th><th>Views</th><th>Actions</th></tr></thead>
                <tbody id="content-table-body">
                {% for movie in content_list %}
                <tr>
                    <td><input type="checkbox" name="selected_ids" value="{{ movie._id }}" class="row-checkbox"></td>
                    <td>{{ movie.title }}</td><td>{{ movie.type|title }}</td><td><i class="fas fa-eye"></i> {{ movie.view_count or 0 }}</td>
                    <td class="action-buttons">
                        <a href="{{ url_for('edit_movie', movie_id=movie._id) }}" class="btn btn-edit">Edit</a>
                        <a href="{{ url_for('delete_movie', movie_id=movie._id) }}" onclick="return confirm('Are you sure?')" class="btn btn-danger">Delete</a>
                    </td>
                </tr>
                {% endfor %}
                </tbody>
            </table></div>
            {% if pagination and pagination.total_pages > 1 %}
            <div class="pagination">
                {% if pagination.has_prev %}<a href="{{ url_for('admin', page=pagination.prev_num) }}">&laquo; Prev</a>{% endif %}
                <span class="current">Page {{ pagination.page }} of {{ pagination.total_pages }}</span>
                {% if pagination.has_next %}<a href="{{ url_for('admin', page=pagination.next_num) }}">Next &raquo;</a>{% endif %}
            </div>
            {% endif %}
            <button type="submit" class="btn btn-danger" style="margin-top: 15px;" onclick="return confirm('Delete selected items?')"><i class="fas fa-trash-alt"></i> Delete Selected</button>
        </form>
    </div>

    <!-- Tab 3: Categories & OTT -->
    <div id="category-ott" class="tab-content">
        <h2><i class="fas fa-tags"></i> Category Management</h2>
        <div class="category-management">
            <form method="post" style="flex: 1; min-width: 300px;">
                <input type="hidden" name="form_action" value="add_category">
                <fieldset><legend>Add New Category</legend>
                    <div class="form-group"><label>Category Name:</label><input type="text" name="category_name" required></div>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-plus"></i> Add Category</button>
                </fieldset>
            </form>
            <div style="flex: 1; min-width: 250px;">
                <h3>Existing Categories</h3>
                {% for cat in categories_list %}<div style="display: flex; justify-content: space-between; align-items: center; background: var(--dark-gray); padding: 10px 15px; border-radius: 4px; margin-bottom: 10px;"><span>{{ cat.name }}</span><a href="{{ url_for('delete_category', cat_id=cat._id) }}" onclick="return confirm('Are you sure?')" class="btn btn-danger" style="padding: 5px 10px; font-size: 0.8rem;">Delete</a></div>{% endfor %}
            </div>
        </div>
        <hr>
        <h2><i class="fas fa-tv"></i> OTT Platform Management</h2>
        <div class="category-management">
            <form method="post" style="flex: 1; min-width: 300px;">
                <input type="hidden" name="form_action" value="add_ott_platform">
                <fieldset><legend>Add New OTT Platform</legend>
                    <div class="form-group"><label>Platform Name:</label><input type="text" name="ott_platform_name" required></div>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-plus"></i> Add Platform</button>
                </fieldset>
            </form>
            <div style="flex: 1; min-width: 250px;">
                <h3>Existing Platforms</h3>
                {% for platform in ott_platforms_list %}<div style="display: flex; justify-content: space-between; align-items: center; background: var(--dark-gray); padding: 10px 15px; border-radius: 4px; margin-bottom: 10px;"><span>{{ platform.name }}</span><a href="{{ url_for('delete_ott_platform', platform_id=platform._id) }}" onclick="return confirm('Are you sure?')" class="btn btn-danger" style="padding: 5px 10px; font-size: 0.8rem;">Delete</a></div>{% endfor %}
            </div>
        </div>
    </div>

    <!-- Tab 4: Advertisement Settings -->
    <div id="ad-settings" class="tab-content">
        <h2><i class="fas fa-bullhorn"></i> Advertisement Management</h2>
        <form method="post">
            <input type="hidden" name="form_action" value="update_ads">
            <fieldset><legend>Global Ad Codes</legend>
                <div class="form-group"><label>Header Script:</label><textarea name="ad_header" rows="4">{{ ad_settings.ad_header or '' }}</textarea></div>
                <div class="form-group"><label>Body Top Script:</label><textarea name="ad_body_top" rows="4">{{ ad_settings.ad_body_top or '' }}</textarea></div>
                <div class="form-group"><label>Footer Script:</label><textarea name="ad_footer" rows="4">{{ ad_settings.ad_footer or '' }}</textarea></div>
            </fieldset>
            <fieldset><legend>In-Page Ad Units</legend>
                 <div class="form-group"><label>Homepage Ad:</label><textarea name="ad_list_page" rows="4">{{ ad_settings.ad_list_page or '' }}</textarea></div>
                 <div class="form-group"><label>Details Page Ad:</label><textarea name="ad_detail_page" rows="4">{{ ad_settings.ad_detail_page or '' }}</textarea></div>
                 <div class="form-group"><label>Wait Page Ad:</label><textarea name="ad_wait_page" rows="4">{{ ad_settings.ad_wait_page or '' }}</textarea></div>
            </fieldset>
            <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Save Ad Settings</button>
        </form>
    </div>

    <!-- Tab 5: Advanced Settings -->
    <div id="advanced-settings" class="tab-content">
        <h2><i class="fas fa-cogs"></i> Advanced Settings</h2>
        <form method="post">
            <input type="hidden" name="form_action" value="update_advanced">
            <fieldset><legend>Wait Page Settings (Download Steps)</legend>
                <div class="form-group">
                    <label>Number of Ad Steps (Max 10):</label>
                    <input type="number" id="ad_steps_input" name="ad_steps" value="{{ site_config.ad_steps }}" min="1" max="10" onchange="generateTimerInputs()">
                </div>
                <div id="step_timers_container">
                    <!-- JS generated -->
                </div>
            </fieldset>
            <fieldset><legend>Poster Auto-Blur Settings</legend>
                <div class="form-group">
                    <label>Auto-Blur Delay (Seconds):</label>
                    <input type="number" name="auto_blur_timer" value="{{ site_config.auto_blur_timer }}" min="1">
                    <small>Posters will automatically blur again after this many seconds when unblurred.</small>
                </div>
            </fieldset>
            <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Save Advanced Settings</button>
        </form>
    </div>
    
</div>

<div class="modal-overlay" id="search-modal"><div class="modal-content"><div class="modal-header"><h2>Select Content</h2><button class="modal-close" onclick="closeModal()">&times;</button></div><div class="modal-body" id="search-results"></div></div></div>
<script>
    function toggleFields() { const isSeries = document.getElementById('content_type').value === 'series'; document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; }
    function addTelegramFileField() { const c = document.getElementById('telegram_files_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button><div class="form-group"><label>Quality (e.g., 720p):</label><input type="text" name="telegram_quality[]" required /></div><div class="form-group"><label>Telegram URL:</label><input type="url" name="telegram_url[]" placeholder="https://t.me/..." required /></div>`; c.appendChild(d); }
    function addEpisodeField() { const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="1" required></div><div class="form-group"><label>Episode Number (e.g., 1 or 1-10):</label><input type="text" name="episode_number[]" required></div><div class="form-group"><label>Title:</label><input type="text" name="episode_title[]"></div><hr style="margin:15px 0;"><p><b>Links:</b></p><div class="form-group"><label>Streaming Link:</label><input type="url" name="episode_stream_link[]" /></div><div class="form-group"><label>Download Link:</label><input type="url" name="episode_download_link[]" /></div><div class="form-group"><label>Telegram Link:</label><input type="url" name="episode_telegram_link[]" /></div><hr style="margin:15px 0;"><p><b>Custom Links (Optional):</b></p><div class="form-group"><label>Links (One per line: Button Text | URL):</label><textarea name="episode_links[]" rows="3" placeholder="e.g., Watch G-Drive | https://..."></textarea></div>`; c.appendChild(d); }
    function addBackdropField() { const c = document.getElementById('backdrop_images_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button><div class="form-group"><label>Image URL:</label><input type="url" name="backdrop_images[]" placeholder="https://image.tmdb.org/..." required /></div>`; c.appendChild(d); }
    function openModal() { document.getElementById('search-modal').style.display = 'flex'; }
    function closeModal() { document.getElementById('search-modal').style.display = 'none'; }
    async function searchTmdb() { const query = document.getElementById('tmdb_search_query').value.trim(); if (!query) return; const searchBtn = document.getElementById('tmdb_search_btn'); searchBtn.disabled = true; searchBtn.innerHTML = 'Searching...'; openModal(); try { const response = await fetch('/admin/api/search?query=' + encodeURIComponent(query)); const results = await response.json(); const container = document.getElementById('search-results'); container.innerHTML = ''; if(results.length > 0) { results.forEach(item => { const resultDiv = document.createElement('div'); resultDiv.className = 'result-item'; resultDiv.onclick = () => selectResult(item.id, item.media_type); resultDiv.innerHTML = `<img src="${item.poster}" alt="${item.title}"><p><strong>${item.title}</strong> (${item.year})</p>`; container.appendChild(resultDiv); }); } else { container.innerHTML = '<p>No results found.</p>'; } } finally { searchBtn.disabled = false; searchBtn.innerHTML = 'Search'; } }
    async function selectResult(tmdbId, mediaType) {
        closeModal();
        const response = await fetch(`/admin/api/details?id=${tmdbId}&type=${mediaType}`);
        const data = await response.json();
        document.getElementById('tmdb_id').value = data.tmdb_id || '';
        document.getElementById('title').value = data.title || '';
        document.getElementById('overview').value = data.overview || '';
        document.getElementById('poster').value = data.poster || '';
        document.getElementById('backdrop').value = data.backdrop || '';
        document.getElementById('genres').value = data.genres ? data.genres.join(', ') : '';
        if (data.release_date) {
            document.getElementById('release_year').value = data.release_date.split('-')[0];
        }
        document.getElementById('trailer_url').value = data.trailer_url || '';
        document.getElementById('content_type').value = data.type === 'series' ? 'series' : 'movie';
        toggleFields();
        const backdropContainer = document.getElementById('backdrop_images_container');
        backdropContainer.innerHTML = '';
        if (data.backdrop_images && data.backdrop_images.length > 0) {
            data.backdrop_images.forEach(imgUrl => {
                const d = document.createElement('div');
                d.className = 'dynamic-item';
                d.innerHTML = `
                    <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button>
                    <div class="form-group">
                        <label>Image URL:</label>
                        <input type="url" name="backdrop_images[]" value="${imgUrl}">
                    </div>
                `;
                backdropContainer.appendChild(d);
            });
        }
    }
    let debounceTimer; const searchInput = document.getElementById('admin-live-search'); const tableBody = document.getElementById('content-table-body'); searchInput.addEventListener('input', () => { clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { const query = searchInput.value.trim(); tableBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Loading...</td></tr>'; fetch(`/admin/api/live_search?q=${encodeURIComponent(query)}`).then(response => response.json()).then(data => { tableBody.innerHTML = ''; if (data.length > 0) { data.forEach(movie => { const row = `<tr><td><input type="checkbox" name="selected_ids" value="${movie._id}" class="row-checkbox"></td><td>${movie.title}</td><td>${movie.type.charAt(0).toUpperCase() + movie.type.slice(1)}</td><td><i class="fas fa-eye"></i> ${movie.view_count || 0}</td><td class="action-buttons"><a href="/edit_movie/${movie._id}" class="btn btn-edit">Edit</a><a href="/delete_movie/${movie._id}" onclick="return confirm('Are you sure?')" class="btn btn-danger">Delete</a></td></tr>`; tableBody.innerHTML += row; }); } else { tableBody.innerHTML = '<tr><td colspan="5" style="text-align:center;">No content found.</td></tr>'; } }); }, 400); });
    
    function generateTimerInputs() {
        const steps = parseInt(document.getElementById('ad_steps_input').value) || 1;
        const container = document.getElementById('step_timers_container');
        const existingTimers = {{ site_config.step_timers | tojson }};
        container.innerHTML = '';
        for(let i=0; i<steps; i++) {
            const val = existingTimers[i] !== undefined ? existingTimers[i] : 5;
            container.innerHTML += `<div class="form-group"><label>Step ${i+1} Timer (Seconds):</label><input type="number" name="timer_${i+1}" value="${val}" min="1"></div>`;
        }
    }
    
    document.addEventListener('DOMContentLoaded', function() { 
        toggleFields(); 
        const selectAll = document.getElementById('select-all'); 
        if(selectAll) { selectAll.addEventListener('change', e => document.querySelectorAll('.row-checkbox').forEach(c => c.checked = e.target.checked)); } 
        generateTimerInputs();
    });

    function openTab(event, tabName) {
        const tabContents = document.getElementsByClassName('tab-content');
        for (let i = 0; i < tabContents.length; i++) {
            tabContents[i].style.display = 'none';
            tabContents[i].classList.remove('active');
        }
        const tabButtons = document.getElementsByClassName('tab-button');
        for (let i = 0; i < tabButtons.length; i++) {
            tabButtons[i].classList.remove('active');
        }
        document.getElementById(tabName).style.display = 'block';
        document.getElementById(tabName).classList.add('active');
        event.currentTarget.classList.add('active');
    }
</script>
</body></html>
"""

edit_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit Content - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>
        :root { --netflix-red: #E50914; --netflix-black: #141414; --dark-gray: #222; --light-gray: #333; --text-light: #f5f5f5; }
        body { font-family: 'Roboto', sans-serif; background: var(--netflix-black); color: var(--text-light); padding: 20px; }
        .admin-container { max-width: 800px; margin: 20px auto; }
        .back-link { display: inline-block; margin-bottom: 20px; color: #999; text-decoration: none; }
        h2 { font-family: 'Bebas Neue', sans-serif; color: var(--netflix-red); font-size: 2.5rem; }
        form { background: var(--dark-gray); padding: 25px; border-radius: 8px; }
        fieldset { border: 1px solid var(--light-gray); padding: 20px; margin-bottom: 20px; border-radius: 5px;}
        legend { font-weight: bold; color: var(--netflix-red); padding: 0 10px; font-size: 1.2rem; }
        .form-group { margin-bottom: 15px; } label { display: block; margin-bottom: 8px; font-weight: bold;}
        input, textarea, select { width: 100%; padding: 12px; border-radius: 4px; border: 1px solid var(--light-gray); font-size: 1rem; background: var(--light-gray); color: var(--text-light); box-sizing: border-box; }
        .btn { display: inline-block; color: white; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1rem; }
        .btn-primary { background: var(--netflix-red); } .btn-secondary { background: #555; } .btn-danger { background: #dc3545; }
        .dynamic-item { border: 1px solid var(--light-gray); padding: 15px; margin-bottom: 15px; border-radius: 5px; position: relative; }
        .dynamic-item .btn-danger { position: absolute; top: 10px; right: 10px; padding: 4px 8px; font-size: 0.8rem; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 15px; } .checkbox-group label { display: flex; align-items: center; gap: 5px; font-weight: normal; }
        .checkbox-group input { width: auto; }
        hr { border: 0; height: 1px; background-color: var(--light-gray); margin: 20px 0; }
    </style>
</head>
<body>
<div class="admin-container">
  <a href="{{ url_for('admin') }}" class="back-link"><i class="fas fa-arrow-left"></i> Back to Admin Panel</a>
  <h2>Edit: {{ movie.title }}</h2>
  <form method="post">
    <fieldset><legend>Core Details</legend>
        <div class="form-group"><label>Title:</label><input type="text" name="title" value="{{ movie.title }}" required></div>
        <div class="form-group"><label>Poster URL:</label><input type="url" name="poster" value="{{ movie.poster or '' }}"></div>
        <div class="form-group"><label>Backdrop URL:</label><input type="url" name="backdrop" value="{{ movie.backdrop or '' }}"></div>
        <div class="form-group"><label>Overview:</label><textarea name="overview">{{ movie.overview or '' }}</textarea></div>
        <div class="form-group"><label>Languages:</label><input type="text" name="languages" value="{{ movie.languages|join(', ') if movie.languages else '' }}"></div>
        <div class="form-group"><label>Poster Badge:</label><input type="text" name="poster_badge" value="{{ movie.poster_badge or '' }}" placeholder="e.g., 4K HDR, Bsub, Dubbed"></div>
        <div class="form-group"><label>Genres:</label><input type="text" name="genres" value="{{ movie.genres|join(', ') if movie.genres else '' }}"></div>
        <div class="form-group"><label>Release Year:</label><input type="text" name="release_year" value="{{ movie.release_year or '' }}" placeholder="e.g., 2024"></div>
        <div class="form-group"><label>Trailer URL (YouTube Embed):</label><input type="url" name="trailer_url" value="{{ movie.trailer_url or '' }}" placeholder="https://www.youtube.com/embed/VIDEO_ID"></div>
        <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie" {% if movie.type == 'movie' %}selected{% endif %}>Movie</option><option value="series" {% if movie.type == 'series' %}selected{% endif %}>Series</option></select></div>
    </fieldset>
    
    <fieldset><legend>Backdrop Images</legend>
        <div id="backdrop_images_container">
            {% if movie.backdrop_images %}
                {% for img_url in movie.backdrop_images %}
                <div class="dynamic-item">
                    <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button>
                    <div class="form-group">
                        <label>Image URL:</label>
                        <input type="url" name="backdrop_images[]" value="{{ img_url }}">
                    </div>
                </div>
                {% endfor %}
            {% endif %}
        </div>
        <button type="button" onclick="addBackdropField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Backdrop Image</button>
    </fieldset>

    <fieldset><legend>Categories</legend>
        <div class="form-group checkbox-group">
            {% for cat in categories_list %}<label><input type="checkbox" name="categories" value="{{ cat.name }}" {% if movie.categories and cat.name in movie.categories %}checked{% endif %}> {{ cat.name }}</label>{% endfor %}
        </div>
    </fieldset>

    <fieldset><legend>OTT Platforms</legend>
        <div class="form-group checkbox-group">
            {% for platform in ott_platforms_list %}<label><input type="checkbox" name="ott_platforms" value="{{ platform.name }}" {% if movie.ott_platforms and platform.name in movie.ott_platforms %}checked{% endif %}> {{ platform.name }}</label>{% endfor %}
        </div>
    </fieldset>

    <div id="movie_fields">
        <fieldset><legend>Movie Links</legend>
            {% set stream_link_1 = (movie.streaming_links | selectattr('name', 'equalto', '480p') | map(attribute='url') | first) or '' %}
            {% set stream_link_2 = (movie.streaming_links | selectattr('name', 'equalto', '720p') | map(attribute='url') | first) or '' %}
            {% set stream_link_3 = (movie.streaming_links | selectattr('name', 'equalto', '1080p') | map(attribute='url') | first) or '' %}
            <p><b>Streaming Links (Optional)</b></p>
            <div class="form-group"><label>Streaming Link 1 (480p):</label><input type="url" name="streaming_link_1" value="{{ stream_link_1 }}" /></div>
            <div class="form-group"><label>Streaming Link 2 (720p):</label><input type="url" name="streaming_link_2" value="{{ stream_link_2 }}" /></div>
            <div class="form-group"><label>Streaming Link 3 (1080p):</label><input type="url" name="streaming_link_3" value="{{ stream_link_3 }}" /></div><hr>
            
            <p><b>Direct Download Links</b></p>
            <div class="form-group"><label>480p Link:</label><input type="url" name="link_480p" value="{% for l in movie.links %}{% if l.quality == '480p' %}{{ l.url }}{% endif %}{% endfor %}" /></div>
            <div class="form-group"><label>720p Link:</label><input type="url" name="link_720p" value="{% for l in movie.links %}{% if l.quality == '720p' %}{{ l.url }}{% endif %}{% endfor %}" /></div>
            <div class="form-group"><label>1080p Link:</label><input type="url" name="link_1080p" value="{% for l in movie.links %}{% if l.quality == '1080p' %}{{ l.url }}{% endif %}{% endfor %}" /></div><hr>

            <p><b>Get from Telegram</b></p>
            <div class="form-group"><label>480p Telegram Link:</label><input type="url" name="telegram_link_480p" value="{% for f in movie.files %}{% if f.quality == '480p' %}{{ f.url }}{% endif %}{% endfor %}" /></div>
            <div class="form-group"><label>720p Telegram Link:</label><input type="url" name="telegram_link_720p" value="{% for f in movie.files %}{% if f.quality == '720p' %}{{ f.url }}{% endif %}{% endfor %}" /></div>
            <div class="form-group"><label>1080p Telegram Link:</label><input type="url" name="telegram_link_1080p" value="{% for f in movie.files %}{% if f.quality == '1080p' %}{{ f.url }}{% endif %}{% endfor %}" /></div>
        </fieldset>
    </div>

    <div id="episode_fields" style="display: none;">
      <fieldset><legend>Individual Episodes</legend>
        <div id="episodes_container">
        {% if movie.type == 'series' and movie.episodes %}{% for ep in movie.episodes|sort(attribute='episode_number')|sort(attribute='season') %}<div class="dynamic-item">
            <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button>
            <div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="{{ ep.season or 1 }}" required></div>
            <div class="form-group"><label>Episode Number (e.g., 1 or 1-10):</label><input type="text" name="episode_number[]" value="{{ ep.episode_number }}" required></div>
            <div class="form-group"><label>Title:</label><input type="text" name="episode_title[]" value="{{ ep.title or '' }}"></div><hr>
            <p><b>Links:</b></p>
            <div class="form-group"><label>Streaming Link:</label><input type="url" name="episode_stream_link[]" value="{{ ep.stream_link or '' }}"></div>
            <div class="form-group"><label>Download Link:</label><input type="url" name="episode_download_link[]" value="{{ ep.download_link or '' }}"></div>
            <div class="form-group"><label>Telegram Link:</label><input type="url" name="episode_telegram_link[]" value="{{ ep.telegram_link or '' }}"></div><hr>
            <p><b>Custom Links (Optional):</b></p>
            <div class="form-group"><label>Links (One per line: Button Text | URL):</label><textarea name="episode_links[]" rows="3">{% for link in ep.links %}{{ link.text }} | {{ link.url }}{% if not loop.last %}
{% endif %}{% endfor %}</textarea></div>
        </div>{% endfor %}{% endif %}</div><button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button></fieldset>
    </div>
    
    <div class="form-group" style="background: #111; padding: 15px; border-radius: 5px;">
        <label style="display: flex; align-items: center; gap: 10px; cursor: pointer;">
            <input type="checkbox" name="notify_telegram" value="yes" style="width: auto; height: 20px; width: 20px;">
            <strong>Notify Telegram Channel About This Update</strong>
        </label>
    </div>
    
    <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Update Content</button>
  </form>
</div>
<script>
    function toggleFields() { var isSeries = document.getElementById('content_type').value === 'series'; document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; }
    function addTelegramFileField() { const c = document.getElementById('telegram_files_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button><div class="form-group"><label>Quality (e.g., 720p):</label><input type="text" name="telegram_quality[]" required /></div><div class="form-group"><label>Telegram URL:</label><input type="url" name="telegram_url[]" placeholder="https://t.me/..." required /></div>`; c.appendChild(d); }
    function addEpisodeField() { const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="form-group"><label>Season:</label><input type="number" name="episode_season[]" value="1" required></div><div class="form-group"><label>Episode Number (e.g., 1 or 1-10):</label><input type="text" name="episode_number[]" required></div><div class="form-group"><label>Title:</label><input type="text" name="episode_title[]"></div><hr style="margin:15px 0;"><p><b>Links:</b></p><div class="form-group"><label>Streaming Link:</label><input type="url" name="episode_stream_link[]" /></div><div class="form-group"><label>Download Link:</label><input type="url" name="episode_download_link[]" /></div><div class="form-group"><label>Telegram Link:</label><input type="url" name="episode_telegram_link[]" /></div><hr style="margin:15px 0;"><p><b>Custom Links (Optional):</b></p><div class="form-group"><label>Links (One per line: Button Text | URL):</label><textarea name="episode_links[]" rows="3" placeholder="e.g., Watch G-Drive | https://..."></textarea></div>`; c.appendChild(d); }
    function addBackdropField() { const c = document.getElementById('backdrop_images_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; d.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger"><i class="fas fa-times"></i></button><div class="form-group"><label>Image URL:</label><input type="url" name="backdrop_images[]" placeholder="https://image.tmdb.org/..." required /></div>`; c.appendChild(d); }
    document.addEventListener('DOMContentLoaded', toggleFields);
</script>
</body></html>
"""

# ... (আগের কোডগুলোর মতো download_hub_html এবং series_hub_html অপরিবর্তিত থাকবে)
download_hub_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Download Hub: {{ movie.title }} - {{ website_name }}</title>
    <link rel="icon" href="https://i.postimg.cc/LXSgKV1P/IMG-20251021-044957-147.jpg" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>
        :root { --primary-color: #E50914; --bg-color: #141414; --card-bg: #1a1a1a; --text-light: #ffffff; --text-dark: #a0a0a0; --stream-color: #007bff; --telegram-color: #2AABEE; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); margin: 0; padding: 20px; display: flex; flex-direction: column; justify-content: center; align-items: center; min-height: 100vh; }
        .hub-container { background-color: var(--card-bg); width: 100%; max-width: 700px; border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,0.6); overflow: hidden; border: 1px solid #333; margin-bottom: 40px; }
        .hub-header { padding: 20px; background-color: #111; text-align: center; }
        .hub-header h1 { font-size: 1.5rem; margin: 0 0 5px 0; }
        .hub-header p { font-size: 0.9rem; color: var(--text-dark); margin: 0; }
        .hub-body { padding: 25px; }
        .disclaimer-box { background-color: rgba(255, 193, 7, 0.1); border: 1px solid #ffc107; color: #ffc107; padding: 15px; border-radius: 8px; margin-bottom: 25px; font-size: 0.9rem; text-align: center; }
        .quality-tabs { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 25px; }
        .tab-btn { flex-grow: 1; padding: 12px 10px; font-size: 1rem; font-weight: 600; color: var(--text-dark); background-color: #282828; border: none; border-radius: 6px; cursor: pointer; transition: all 0.2s ease; }
        .tab-btn.active { background-color: var(--primary-color); color: white; }
        .quality-content { display: none; }
        .quality-content.active { display: block; animation: fadeIn 0.4s; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        .link-button { display: flex; align-items: center; width: 100%; text-align: left; padding: 15px 20px; margin-bottom: 12px; border-radius: 8px; text-decoration: none; color: white; font-weight: 500; font-size: 1rem; transition: transform 0.2s ease, background-color 0.2s ease; box-sizing: border-box; }
        .link-button:hover { transform: scale(1.02); }
        .link-button i { font-size: 1.3rem; margin-right: 15px; width: 25px; text-align: center; }
        .link-button.stream { background-color: var(--stream-color); } .link-button.stream:hover { background-color: #0069d9; }
        .link-button.download { background-color: var(--primary-color); } .link-button.download:hover { background-color: #B20710; }
        .link-button.telegram { background-color: var(--telegram-color); } .link-button.telegram:hover { background-color: #1e96d1; }
        .no-links { text-align: center; color: var(--text-dark); padding: 20px; }
        .hub-footer-actions { text-align: center; padding: 0 25px 25px; }
        .report-button-hub { display: inline-flex; align-items: center; gap: 10px; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-size: 0.9rem; font-weight: 500; background-color: #444; color: var(--text-light); transition: background-color 0.2s ease; }
        .report-button-hub:hover { background-color: #555; }
        .professional-footer { width: 100%; background: linear-gradient(to bottom, #1a1a1a, #0f0f0f); color: var(--text-dark); padding-top: 60px; margin-top: auto; border-top: 4px solid #000; }
        .footer-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 40px; padding-bottom: 50px; max-width: 1200px; margin: 0 auto; padding-left: 20px; padding-right: 20px; }
        .footer-column-title { font-size: 1.3rem; font-weight: 600; color: var(--text-light); margin-bottom: 25px; position: relative; padding-bottom: 10px; }
        .footer-column-title::after { content: ''; position: absolute; bottom: 0; left: 0; width: 50px; height: 3px; background-color: var(--
