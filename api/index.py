import os
import sys
import requests
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps
from urllib.parse import unquote, quote, unquote_plus
from datetime import datetime, timedelta
import math
import json

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

    if seconds < 60:
        return "just now"
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
    wait_settings = settings.find_one({"_id": "wait_config"}) or {"step1": 10, "step2": 7, "step3": 5, "total_steps": 3}
    blur_settings = settings.find_one({"_id": "blur_config"}) or {"timer": 5, "enabled": "yes"}
    all_categories = [cat['name'] for cat in categories_collection.find().sort("name", 1)]
    ott_platform_logos = {
        "Netflix": "https://i.postimg.cc/GtHdbb5h/images-3.png", "Amazon Prime": "https://i.postimg.cc/XvLvzbxp/Amazon-Prime-Logo-Transparent.png",
        "Disney+ Hotstar": "https://i.postimg.cc/9Xx6c5VM/images-2.png", "AppleTV": "https://i.postimg.cc/0jWWWbKm/Apple-TV-logo.png",
        "SonyLIV": "https://i.postimg.cc/gjLmmXFy/sony-liv-logo.webp", "ZEE5": "https://i.postimg.cc/CMBMpt4D/images.png",
        "JioCinema": "https://i.postimg.cc/wMyC5VcJ/IMG-20251031-201544-410.jpg", "Hoichoi": "https://i.postimg.cc/fTsQHjwz/images-4.png",
        "Chorki": "https://i.ibb.co.com/PZh6wWNQ/Chorki-Logo.png", "Bongo": "https://i.ibb.co.com/wFHM61sz/KV0.jpg",
        "iScreen": "https://i.postimg.cc/ncVV786p/IMG-20251031-200605-353.jpg", "Toffee": "https://i.postimg.cc/7Z9V9zV1/Toffee-logo.png",
        "Bioscope": "https://i.postimg.cc/Ssdm096m/Bioscope-logo.png", "Binge": "https://i.postimg.cc/vH876kvX/Binge-logo.png",
        "Aha": "https://i.postimg.cc/1X9V8r8x/Aha-Logo.png", "Sun NXT": "https://i.postimg.cc/qR5yYyYp/Sun-NXT-logo.png",
        "MX Player": "https://i.postimg.cc/63pPqPq6/MX-Player-logo.png", "Discovery+": "https://i.postimg.cc/9f0R5y1z/Discovery-Plus-logo.png",
        "Eros Now": "https://i.postimg.cc/V6f9y8zM/Eros-Now-logo.png", "ALTBalaji": "https://i.postimg.cc/50vY4Yk7/ALTBalaji-logo.png",
        "Hungama Play": "https://i.postimg.cc/85zM6m7M/Hungama-Play-logo.png", "ShemarooMe": "https://i.postimg.cc/02W8W8zM/Shemaroo-Me-logo.png",
        "Lionsgate Play": "https://i.postimg.cc/85zM6m7M/Lionsgate-Play-logo.png", "Addatimes": "https://i.postimg.cc/mD8m8z4G/Addatimes-logo.png",
        "Klikk": "https://i.postimg.cc/6q0X0Z0P/Klikk-logo.png", "Chaupal": "https://i.ibb.co.com/mC3Y7z0y/Chaupal.jpg",
        "Planet Marathi": "https://i.ibb.co.com/pBfV5n0y/Planet-Marathi.png", "ManoramaMAX": "https://i.ibb.co.com/vC4z9x0y/Manorama-Max.png",
        "ETV Win": "https://i.ibb.co.com/mB5z9x0y/ETV-Win.png", "SainaPlay": "https://i.ibb.co.com/vC4z9x0y/Saina-Play.png",
        "Stage": "https://i.ibb.co.com/mB5z9x0y/Stage-OTT.png", "Cinematic": "https://i.postimg.cc/4NfX4x5L/Cinematic-logo.png",
        "DeeptoPlay": "https://i.ibb.co.com/mC3Y7z0y/Deepto-Play.jpg", "Rabbitholebd": "https://i.ibb.co.com/pBfV5n0y/Rabbithole.jpg",
        "BanglaFlix": "https://i.ibb.co.com/vC4z9x0y/Banglaflix.png", "Cinespot": "https://i.ibb.co.com/mB5z9x0y/Cinespot.png",
        "AynaOTT": "https://i.ibb.co.com/vC4z9x0y/Ayna-OTT.png", "Jagobd": "https://i.ibb.co.com/mB5z9x0y/Jagobd.png",
        "Rtv Plus": "https://i.ibb.co.com/vC4z9x0y/Rtv-Plus.png", "Airtel Xstream": "https://i.ibb.co.com/mB5z9x0y/Airtel-Xstream.png",
        "VI Movies & TV": "https://i.ibb.co.com/vC4z9x0y/VI-Movies.png", "Epic On": "https://i.ibb.co.com/mB5z9x0y/Epic-On.png",
        "MUBI": "https://i.ibb.co.com/vC4z9x0y/Mubi.png", "Curiosity Stream": "https://i.ibb.co.com/mB5z9x0y/Curiosity.png",
        "Docubay": "https://i.ibb.co.com/vC4z9x0y/Docubay.png", "Spuul": "https://i.ibb.co.com/mB5z9x0y/Spuul.png",
        "YuppTV": "https://i.ibb.co.com/vC4z9x0y/YuppTV.png", "Simply South": "https://i.ibb.co.com/mB5z9x0y/Simply-South.png",
        "Tentkotta": "https://i.ibb.co.com/vC4z9x0y/Tentkotta.png", "Koode": "https://i.ibb.co.com/mB5z9x0y/Koode.png",
        "ReelDrama": "https://i.ibb.co.com/vC4z9x0y/Reeldrama.png", "OHO Gujarati": "https://i.ibb.co.com/mB5z9x0y/Oho-Gujarati.png",
        "CityShor TV": "https://i.ibb.co.com/vC4z9x0y/Cityshor.png", "Namma Flix": "https://i.ibb.co.com/mB5z9x0y/Nammaflix.png",
        "Olly Plus": "https://i.ibb.co.com/vC4z9x0y/Ollyplus.png", "Aao NXT": "https://i.ibb.co.com/mB5z9x0y/Aaonxt.png",
        "KableOne": "https://i.ibb.co.com/vC4z9x0y/Kableone.png", "Atrangii": "https://i.ibb.co.com/mB5z9x0y/Atrangii.png",
        "Dangal Play": "https://i.ibb.co.com/vC4z9x0y/Dangal-Play.png", "EORTV": "https://i.ibb.co.com/mB5z9x0y/Eortv.png",
        "Ullu": "https://i.ibb.co.com/vC4z9x0y/Ullu.png", "Kooku": "https://i.ibb.co.com/mB5z9x0y/Kooku.png",
        "PrimePlay": "https://i.ibb.co.com/vC4z9x0y/Primeplay.png", "Voovi": "https://i.ibb.co.com/mB5z9x0y/Voovi.png",
        "Hunters": "https://i.ibb.co.com/vC4z9x0y/Hunters.png", "Fliz Movies": "https://i.ibb.co.com/mB5z9x0y/Fliz.png",
        "CSpace": "https://i.ibb.co.com/vC4z9x0y/Cspace.png", "Filmeraa": "https://i.ibb.co.com/mB5z9x0y/Filmeraa.png",
        "MovieSaints": "https://i.ibb.co.com/vC4z9x0y/Moviesaints.png", "FanCode": "https://i.ibb.co.com/mB5z9x0y/Fancode.png",
        "PTC Play": "https://i.ibb.co.com/vC4z9x0y/Ptcplay.png", "Tubi": "https://i.ibb.co.com/mB5z9x0y/Tubi.png",
        "Plex": "https://i.ibb.co.com/vC4z9x0y/Plex.png", "Rakuten Viki": "https://i.ibb.co.com/mB5z9x0y/Viki.png",
        "Hayu": "https://i.ibb.co.com/vC4z9x0y/Hayu.png", "Crunchyroll": "https://i.ibb.co.com/mB5z9x0y/Crunchyroll.png",
        "TVF Play": "https://i.ibb.co.com/vC4z9x0y/Tvfplay.png", "Pocket TV": "https://i.ibb.co.com/mB5z9x0y/Pockettv.png",
        "VROTT": "https://i.ibb.co.com/mB5z9x0y/Vrott.png", "Hippiix": "https://i.ibb.co.com/vC4z9x0y/Hippiix.png",
        "TeleFlix": "https://i.ibb.co.com/mB5z9x0y/Teleflix.png", "BD IPTV": "https://i.ibb.co.com/vC4z9x0y/Bdiptv.png",
        "Bongo Sports": "https://i.ibb.co.com/mB5z9x0y/Bongosports.png", "Sony Max": "https://i.ibb.co.com/vC4z9x0y/Sonymax.png",
        "Star Plus OTT": "https://i.ibb.co.com/mB5z9x0y/Starplus.png", "Colors Play": "https://i.ibb.co.com/vC4z9x0y/Colors.png",
        "Zee Bangla OTT": "https://i.ibb.co.com/mB5z9x0y/Zeebangla.png", "News7 Tamil": "https://i.ibb.co.com/vC4z9x0y/News7.png",
        "Republic World": "https://i.ibb.co.com/mB5z9x0y/Republic.png", "Aaj Tak OTT": "https://i.ibb.co.com/vC4z9x0y/Aajtak.png",
        "NDTV App": "https://i.ibb.co.com/mB5z9x0y/Ndtv.png", "Voot Kids": "https://i.ibb.co.com/vC4z9x0y/Vootkids.png",
        "Disney Junior": "https://i.ibb.co.com/mB5z9x0y/Disneyjr.png", "Cartoon Network": "https://i.ibb.co.com/vC4z9x0y/Cn.png",
        "Nick India": "https://i.ibb.co.com/mB5z9x0y/Nick.png", "Pogo OTT": "https://i.ibb.co.com/vC4z9x0y/Pogo.png",
        "Discovery Kids": "https://i.ibb.co.com/mB5z9x0y/Discoverykids.png", "Animax": "https://i.ibb.co.com/vC4z9x0y/Animax.png",
        "ShortsTV": "https://i.ibb.co.com/mB5z9x0y/Shortstv.png", "Docflix": "https://i.ibb.co.com/vC4z9x0y/Docflix.png",
        "T-Series OTT": "https://i.ibb.co.com/mB5z9x0y/Tseries.png", "Sony Music": "https://i.ibb.co.com/vC4z9x0y/Sonymusic.png",
        "Gaana": "https://i.ibb.co.com/mB5z9x0y/Gaana.png", "Saavn": "https://i.ibb.co.com/vC4z9x0y/Saavn.png",
        "Wynk Music": "https://i.ibb.co.com/vC4z9x0y/Wynk.png", "Spotify": "https://i.ibb.co.com/mB5z9x0y/Spotify.png",
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
        wait_settings=wait_settings,
        blur_settings=blur_settings,
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
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ website_name }} - Watch Movies and Series</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@10/swiper-bundle.min.css" />
    <style>
        :root {
            --bg-color: #000000;
            --card-bg: #1a1a1a;
            --primary-color: #e50914;
            --text-light: #ffffff;
            --text-dark: #aaaaaa;
            --nav-height: 60px;
            --cyan-accent: #00ffff;
            --search-accent-color: #00bcd4;
            --type-color: #00E599;
        }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); margin: 0; padding-bottom: 60px; overflow-x: hidden; transition: background-color 0.3s, color 0.3s; }
        a { text-decoration: none; color: inherit; }
        .container { width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 15px; box-sizing: border-box; }

        .main-header { position: fixed; top: 0; left: 0; width: 100%; height: var(--nav-height); display: flex; align-items: center; z-index: 1000; transition: background-color 0.3s ease; background-color: rgba(0,0,0,0.7); backdrop-filter: blur(5px); }
        .header-content { display: flex; justify-content: space-between; align-items: center; width: 100%; }
        .logo { font-size: 1.8rem; font-weight: 700; color: var(--primary-color); }
        .menu-toggle { display: block; font-size: 1.8rem; cursor: pointer; background: none; border: none; color: white; z-index: 1001;}

        .nav-grid-container { padding: 15px 0; margin-top: 60px; }
        .nav-grid { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
        .nav-grid-item { display: inline-flex; align-items: center; justify-content: center; color: white; padding: 6px 12px; border-radius: 6px; font-size: 0.75rem; font-weight: 500; text-transform: uppercase; text-decoration: none; transition: all 0.3s ease; background: linear-gradient(145deg, #d40a0a, #a00000); border: 1px solid #ff4b4b; box-shadow: 0 2px 8px -3px rgba(229, 9, 20, 0.6); }
        .nav-grid-item:hover { transform: translateY(-2px); box-shadow: 0 4px 12px -4px rgba(229, 9, 20, 0.9); filter: brightness(1.1); }
        .nav-grid-item i { margin-right: 6px; font-size: 1em; line-height: 1; }
        .icon-18 { font-family: sans-serif; display: inline-flex; align-items: center; justify-content: center; border: 1.5px solid white; border-radius: 50%; width: 16px; height: 16px; font-size: 10px; line-height: 1; margin-right: 6px; font-weight: bold; }

        /* START: New Home Page Search Bar Styles */
        .home-search-section { padding: 10px 0 20px 0; }
        .home-search-form { display: flex; width: 100%; max-width: 800px; margin: 0 auto; border: 2px solid var(--search-accent-color); border-radius: 8px; overflow: hidden; background-color: var(--card-bg); }
        .home-search-input { flex-grow: 1; border: none; background-color: transparent; color: var(--text-light); padding: 12px 20px; font-size: 1rem; outline: none; }
        .home-search-input::placeholder { color: var(--text-dark); }
        .home-search-button { background-color: var(--search-accent-color); border: none; color: white; padding: 0 25px; cursor: pointer; font-size: 1.2rem; display: flex; align-items: center; justify-content: center; transition: background-color 0.2s ease; }
        .home-search-button:hover { filter: brightness(1.1); }
        
        /* === [NEW] STAR ANIMATION FOR "CREATE WEBSITE" LINK === */
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
        
        /* Auto Blur System CSS */
        body.auto-blur .movie-poster { filter: blur(12px); transition: filter 0.3s ease; }
        body.auto-blur .hero-bg-img { filter: blur(15px); transition: filter 0.3s ease; }
        body.auto-blur .movie-poster:hover { filter: blur(0px); }
        body.auto-blur .hero-bg-img:hover { filter: blur(0px); }
        .blur-toggle-btn { background: none; border: none; color: white; font-size: 1.3rem; cursor: pointer; transition: transform 0.2s; margin-right: 15px;}
        .blur-toggle-btn:hover { transform: scale(1.1); }

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
        .type-tag { bottom: 8px; right: 8px; background-color: var(--type-color); color: #000; }
        .rating-tag { position: absolute; bottom: 8px; left: 8px; background-color: rgba(245, 197, 24, 0.9); color: #000; padding: 2px 8px; font-size: 0.7rem; font-weight: 700; z-index: 2; border-radius: 4px; display: flex; align-items: center; }
        .rating-tag i { margin-right: 4px; }
        
        .new-badge { position: absolute; top: 0; left: 0; background-color: var(--primary-color); color: white; padding: 4px 12px 4px 8px; font-size: 0.7rem; font-weight: 700; z-index: 3; clip-path: polygon(0 0, 100% 0, 85% 100%, 0 100%); }
        .featured-badge { position: absolute; top: 0; left: 0; background-color: #ffc107; color: #000; padding: 4px 12px 4px 8px; font-size: 0.7rem; font-weight: 700; z-index: 3; clip-path: polygon(0 0, 100% 0, 85% 100%, 0 100%); }

        .full-page-grid-container { padding: 80px 10px 20px; }
        .full-page-grid-title { font-size: 1.8rem; font-weight: 700; margin-bottom: 20px; text-align: center; }
        
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
        body.light-mode .blur-toggle-btn { color: var(--text-light); }
        body.light-mode .theme-btn { color: var(--text-light); }
        
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
        .telegram-button.notification i { color: #34B7F1; }
        .telegram-button.request i { color: #f5c518; }
        .telegram-button.backup i { color: #28a745; }
        .telegram-button span { display: flex; flex-direction: column; }
        .telegram-button small { font-size: 0.75rem; color: var(--text-dark); }
        .footer-note { font-size: 0.8rem; color: var(--text-dark); margin-top: 20px; background-color: rgba(0,0,0,0.2); padding: 10px; border-radius: 5px; }
        .footer-note a { color: #34B7F1; font-weight: bold; }
        .footer-bottom-bar { background-color: #000; text-align: center; padding: 20px; font-size: 0.9rem; border-top: 1px solid #222; }

        @media (max-width: 768px) {
            .footer-grid { text-align: center; }
            .footer-column-title::after { left: 50%; transform: translateX(-50%); }
            .footer-logo { margin-left: auto; margin-right: auto; }
            .links-section ul li a { justify-content: center; }
        }

        @media (min-width: 769px) {
            .container { padding: 0 40px; }
            .main-header { padding: 0 40px; }
            body { padding-bottom: 0; }
            .bottom-nav { display: none; }
            .hero-slider .hero-title { font-size: 2.2rem; }
            .hero-slider .hero-slide-content { padding: 40px; }
            .category-grid { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
            .full-page-grid { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); }
            .full-page-grid-container { padding: 120px 40px 20px; }
            .platform-slider .swiper-slide { width: 130px; }
            .platform-logo-wrapper { width: 100px; height: 100px; }
            .platform-item span { font-size: 0.9rem; }
        }
    </style>
    {{ ad_settings.ad_header | safe }}
</head>
<body>

    <header class="main-header">
        <div class="header-content container">
            <button class="menu-toggle" id="mobile-menu-btn" aria-label="Open Menu"><i class="fas fa-bars"></i></button>
            <a href="{{ url_for('home') }}" class="logo">{{ website_name }}</a>
            <div class="header-icons" style="display:flex; align-items:center;">
                
                <!-- NEW: Eye Icon for Auto Blur Toggle -->
                <button id="blur-toggle-btn" class="blur-toggle-btn" title="Toggle Anti-Copyright Blur">
                    <i class="fas fa-eye-slash" id="blur-icon"></i>
                </button>

                <div class="theme-toggle">
                    <button class="theme-btn"><i class="fas fa-adjust"></i></button>
                    <div class="theme-popup">
                        <div class="theme-option" data-theme="dark"><i class="fas fa-moon"></i> Dark Mode</div>
                        <div class="theme-option" data-theme="light"><i class="fas fa-sun"></i> Light Mode</div>
                    </div>
                </div>
                <button class="menu-toggle" onclick="document.getElementById('search-overlay').classList.add('active')" aria-label="Search" style="margin-left:10px;"><i class="fas fa-search"></i></button>
            </div>
        </div>
    </header>

    <div class="mobile-nav-menu" id="mobile-nav">
        <button class="close-btn" id="close-menu-btn">&times;</button>
        <div class="mobile-links">
            <a href="{{ url_for('home') }}">Home</a>
            <a href="{{ url_for('all_movies') }}">Movies</a>
            <a href="{{ url_for('all_series') }}">Web Series</a>
            <a href="{{ url_for('genres_page') }}">Genres</a>
            <a href="{{ url_for('request_content') }}">Request Content</a>
            <hr>
            {% for cat in predefined_categories %}
                <a href="{{ url_for('movies_by_category', name=cat) }}">{{ cat }}</a>
            {% endfor %}
        </div>
    </div>

    <nav class="bottom-nav">
        <a href="{{ url_for('home') }}" class="nav-item active"><i class="fas fa-home"></i>Home</a>
        <a href="{{ url_for('all_movies') }}" class="nav-item"><i class="fas fa-film"></i>Movies</a>
        <a href="{{ url_for('all_series') }}" class="nav-item"><i class="fas fa-tv"></i>Series</a>
        <a href="{{ url_for('genres_page') }}" class="nav-item"><i class="fas fa-masks-theater"></i>Genres</a>
        <a href="{{ url_for('request_content') }}" class="nav-item"><i class="fas fa-paper-plane"></i>Request</a>
    </nav>

    <div class="search-overlay" id="search-overlay">
        <button class="close-search-btn" onclick="document.getElementById('search-overlay').classList.remove('active')">&times;</button>
        <div class="search-container">
            <input type="text" id="search-input-live" placeholder="Search movies, series..." autocomplete="off">
            <div id="search-results-live"></div>
        </div>
    </div>

    {{ ad_settings.ad_body_top | safe }}

    {% macro render_movie_card(m, is_featured=False) %}
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
      <div class="poster-wrapper">
        <div class="card-preloader"><div class="play-button-loader-small"></div></div>
        
        <div class="badges-top">
            <div class="badge-group-left">
                {% if is_featured %}
                    <span class="featured-badge">Featured</span>
                {% elif (datetime.utcnow() - m._id.generation_time.replace(tzinfo=None)).days < 7 %}
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

    {% if is_full_page_list %} 

        <div class="full-page-grid-container container">
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
                        A warm welcome to you at {{ website_name }}. Here you can search and explore all the latest movies and web series. If you can't find your favorite content, feel free to let us know using the 'Request' option. For all the latest updates and news on new releases, please join our official Telegram channel: @allmoviepsz. Thank you for visiting and stay with us. ••• {{ website_name }} এ আপনাকে আন্তরিকভাবে স্বাগতম।
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
            <div class="swiper featured-slider" style="overflow: hidden; padding-bottom: 20px;">
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

    <footer class="professional-footer">
        <div class="footer-grid">
            <div class="footer-column about-section">
                <h4 class="footer-column-title">About {{ website_name }}</h4>
                <div class="footer-logo">
                    <h2 style="color: var(--primary-color); margin: 0 0 10px 0;">{{ website_name }}</h2>
                </div>
                <p class="footer-description">
                    Your ultimate destination for downloading and streaming the latest movies and web series. We provide high-quality content ranging from 480p to 4K.
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

    {{ ad_settings.ad_footer | safe }}
    <script src="https://cdn.jsdelivr.net/npm/swiper@10/swiper-bundle.min.js"></script>
    <script>
        // === [NEW] AUTO BLUR LOGIC ===
        const blurConfig = {
            enabled: "{{ blur_settings.enabled }}" === "yes",
            timer: parseInt("{{ blur_settings.timer }}") * 1000
        };
        let isBlurred = false;
        let blurTimeout;

        function applyBlur() {
            document.body.classList.add('auto-blur');
            const icon = document.getElementById('blur-icon');
            if(icon) { icon.classList.remove('fa-eye-slash'); icon.classList.add('fa-eye'); }
            isBlurred = true;
        }

        function removeBlur() {
            document.body.classList.remove('auto-blur');
            const icon = document.getElementById('blur-icon');
            if(icon) { icon.classList.remove('fa-eye'); icon.classList.add('fa-eye-slash'); }
            isBlurred = false;
        }

        if (blurConfig.enabled) {
            if(blurConfig.timer === 0) {
                applyBlur(); // Instant blur
            } else {
                blurTimeout = setTimeout(applyBlur, blurConfig.timer);
            }
        }

        const blurBtn = document.getElementById('blur-toggle-btn');
        if(blurBtn) {
            blurBtn.addEventListener('click', function() {
                if (isBlurred) {
                    removeBlur();
                    clearTimeout(blurTimeout);
                } else {
                    applyBlur();
                }
            });
        }
        // === END AUTO BLUR LOGIC ===

        const mobileMenuBtn = document.getElementById('mobile-menu-btn');
        const closeMenuBtn = document.getElementById('close-menu-btn');
        const mobileNav = document.getElementById('mobile-nav');
        if(mobileMenuBtn){ mobileMenuBtn.addEventListener('click', () => mobileNav.classList.add('active')); }
        if(closeMenuBtn){ closeMenuBtn.addEventListener('click', () => mobileNav.classList.remove('active')); }

        const searchInput = document.getElementById('search-input-live');
        const searchResults = document.getElementById('search-results-live');
        let searchTimeout;
        if(searchInput){
            searchInput.addEventListener('input', function() {
                clearTimeout(searchTimeout);
                const query = this.value.trim();
                if (query.length > 2) {
                    searchTimeout = setTimeout(() => {
                        fetch(`/api/search?q=${encodeURIComponent(query)}`)
                            .then(res => res.json())
                            .then(data => {
                                searchResults.innerHTML = '';
                                if (data.length > 0) {
                                    data.forEach(item => {
                                        const a = document.createElement('a');
                                        a.href = `/movie/${item._id}`;
                                        a.className = 'search-result-item';
                                        a.innerHTML = `<img src="${item.poster || 'https://via.placeholder.com/400x600.png'}" alt="${item.title}"><div>${item.title}</div>`;
                                        searchResults.appendChild(a);
                                    });
                                } else { searchResults.innerHTML = '<p style="color:white;text-align:center;width:100%;">No results found</p>'; }
                            });
                    }, 300);
                } else { searchResults.innerHTML = ''; }
            });
        }

        const heroSliderEl = document.querySelector('.hero-slider');
        if(heroSliderEl) {
            new Swiper('.hero-slider', {
                loop: true, autoplay: { delay: 4000, disableOnInteraction: false },
                pagination: { el: '.swiper-pagination', clickable: true }, effect: 'fade'
            });
        }

        const featuredSliderEl = document.querySelector('.featured-slider');
        if(featuredSliderEl) {
            const featuredSwiper = new Swiper('.featured-slider', {
                breakpoints: { 320: { slidesPerView: 2, spaceBetween: 15 }, 768: { slidesPerView: 4, spaceBetween: 20 } },
                speed: 800, loop: false,
            });
            let featuredAutoplayTimeout;
            function startFeaturedAutoplay() {
                clearInterval(featuredAutoplayTimeout);
                featuredAutoplayTimeout = setInterval(() => {
                    if (featuredSwiper.isEnd) {
                        clearInterval(featuredAutoplayTimeout);
                        setTimeout(() => { featuredSwiper.slideTo(0, 2000); setTimeout(() => { startFeaturedAutoplay(); }, 2000); }, 1500);
                    } else { featuredSwiper.slideNext(); }
                }, 3000);
            }
            startFeaturedAutoplay();
        }

        const platformSliderEl = document.querySelector('.platform-slider');
        if(platformSliderEl) {
            const platformSwiper = new Swiper('.platform-slider', {
                slidesPerView: 'auto', spaceBetween: 25, speed: 800, loop: false,
                on: { reachEnd: function () { setTimeout(() => { this.slideTo(0, 1500); }, 1000); } },
            });
            let pAutoPlay;
            function startPAutoplay() {
                clearInterval(pAutoPlay);
                pAutoPlay = setInterval(() => { if (!platformSwiper.isEnd) platformSwiper.slideNext(); }, 3000);
            }
            startPAutoplay();
        }

        function initializeCardLoaders() {
            document.querySelectorAll('.movie-card').forEach(card => {
                card.addEventListener('click', function(event) {
                    event.preventDefault();
                    const preloader = this.querySelector('.card-preloader');
                    if (preloader) preloader.classList.add('active');
                    const destinationUrl = this.href;
                    setTimeout(() => { window.location.href = destinationUrl; }, 150); 
                });
            });
        }
        document.addEventListener('DOMContentLoaded', initializeCardLoaders);
        window.addEventListener('pageshow', function(event) {
            if (event.persisted) document.querySelectorAll('.card-preloader.active').forEach(p => p.classList.remove('active'));
        });

        const themeBtn = document.querySelector('.theme-btn');
        const themePopup = document.querySelector('.theme-popup');
        const themeOptions = document.querySelectorAll('.theme-option');
        const applyTheme = (theme) => {
            if (theme === 'light') document.body.classList.add('light-mode');
            else document.body.classList.remove('light-mode');
        };
        applyTheme(localStorage.getItem('theme') || 'dark');
        
        if(themeBtn){
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
                if (!themeBtn.contains(event.target) && !themePopup.contains(event.target)) themePopup.style.display = 'none';
            });
        }
    </script>
</body>
</html>
"""

detail_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ movie.title }} - {{ website_name }}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg-color: #000000; --card-bg: #1a1a1a; --primary-color: #e50914; --text-light: #ffffff; --text-dark: #aaaaaa; --nav-height: 60px; --cyan-accent: #00ffff; --type-color: #00E599; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); margin: 0; padding-bottom: 60px; }
        a { text-decoration: none; color: inherit; }
        .container { width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 15px; box-sizing: border-box; }
        
        .main-header { position: fixed; top: 0; left: 0; width: 100%; height: var(--nav-height); display: flex; align-items: center; z-index: 1000; background-color: rgba(0,0,0,0.7); backdrop-filter: blur(5px); }
        .header-content { display: flex; justify-content: space-between; align-items: center; width: 100%; }
        .logo { font-size: 1.8rem; font-weight: 700; color: var(--primary-color); }
        .menu-toggle { font-size: 1.8rem; cursor: pointer; background: none; border: none; color: white; }

        .page-header { padding: 20px 15px 15px 15px; margin-top: var(--nav-height);} 
        .go-back-btn { display: inline-flex; align-items: center; gap: 10px; background-color: rgba(45, 45, 45, 0.9); color: #fff; padding: 10px 20px; border-radius: 12px; font-size: 1rem; font-weight: 500; } 
        
        .hero-section-wrapper { margin: 0 15px 30px 15px; position: relative; overflow: visible; margin-bottom: 120px; } 
        .detail-hero-backdrop { width: 100%; aspect-ratio: 16 / 9; border-radius: 16px; overflow: hidden; position: relative; box-shadow: 0 0 30px 0 rgba(0, 255, 255, 0.25); border: 1px solid rgba(0, 255, 255, 0.2); background-color: #000; } 
        .hero-backdrop-img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1; } 
        .hero-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 2; background: linear-gradient(180deg, rgba(20,20,20,0) 50%, rgba(20,20,20,0.8) 100%); } 
        .overlay-poster { position: absolute; z-index: 4; bottom: -80px; left: 20px; width: 35%; max-width: 150px; border-radius: 12px; border: 3px solid rgba(255, 255, 255, 0.15); box-shadow: 0 15px 35px rgba(0,0,0,0.8); } 
        .content-type-badge { position: absolute; z-index: 3; bottom: 20px; right: 20px; background-color: #00ff00; color: #000; padding: 10px 25px; border-radius: 10px; font-size: 0.9rem; font-weight: 700; text-transform: uppercase; }

        /* Auto Blur System CSS */
        body.auto-blur .movie-poster, body.auto-blur .overlay-poster { filter: blur(12px); transition: filter 0.3s ease; }
        body.auto-blur .hero-backdrop-img { filter: blur(15px); transition: filter 0.3s ease; }
        body.auto-blur .movie-poster:hover, body.auto-blur .overlay-poster:hover { filter: blur(0px); }
        body.auto-blur .hero-backdrop-img:hover { filter: blur(0px); }
        .blur-toggle-btn { background: none; border: none; color: white; font-size: 1.3rem; cursor: pointer; transition: transform 0.2s; margin-right: 15px;}

        .content-info-section { padding: 20px; } 
        .detail-title { font-size: 2rem; font-weight: 700; line-height: 1.3; margin-bottom: 15px; } 
        .detail-meta { display: flex; flex-wrap: wrap; gap: 10px 20px; color: var(--text-dark); margin-bottom: 20px; font-size: 0.9rem; } 
        .meta-item { display: flex; align-items: center; gap: 8px; } 
        .meta-item.rating { color: #f5c518; font-weight: 600; } 
        .detail-overview { font-size: 1rem; line-height: 1.7; color: var(--text-dark); margin-bottom: 30px; }

        .section-title { font-size: 1.5rem; font-weight: 700; margin: 30px 0 20px 0; padding-bottom: 5px; border-bottom: 2px solid var(--primary-color); display: inline-block; } 
        .ad-container { margin: 30px auto; text-align: center; width: 100%; max-width: 100%; display: flex; justify-content: center; overflow: hidden; } 
        
        .trailer-section { margin: 0 0 40px 0; } 
        .trailer-section h2 { font-size: 1.5rem; font-weight: 600; margin-bottom: 20px; } 
        .trailer-video-wrap { position: relative; width: 100%; max-width: 900px; margin: 0 auto; aspect-ratio: 16 / 9; border-radius: 12px; overflow: hidden; } 
        .trailer-video-wrap iframe { position: absolute; width: 100%; height: 100%; top: 0; left: 0; border: 0; }

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

        .report-button { display: inline-flex; align-items: center; gap: 10px; background-color: #555; color: #fff; padding: 12px 25px; border-radius: 8px; font-size: 1rem; font-weight: 500; border: 1px solid #666; transition: background-color 0.2s ease; } 
        .report-button:hover { background-color: #6c757d; } 
        .edit-icon-link { position: absolute; top: 20px; right: 20px; background-color: rgba(0, 0, 0, 0.6); color: #fff; padding: 10px; width: 40px; height: 40px; display: flex; justify-content: center; align-items: center; border-radius: 50%; font-size: 1.2rem; transition: background-color 0.2s, transform 0.2s; z-index: 10; border: 2px solid #555; box-shadow: 0 4px 10px rgba(0,0,0,0.5); } 
        .edit-icon-link:hover { background-color: var(--primary-color); border-color: var(--primary-color); transform: scale(1.1); } 
        
        .professional-footer { background: linear-gradient(to bottom, #1a1a1a, #0f0f0f); color: var(--text-dark); padding-top: 60px; margin-top: 50px; border-top: 4px solid #000; }
        .footer-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 40px; padding-bottom: 50px; }
        .footer-column-title { font-size: 1.3rem; font-weight: 600; color: var(--text-light); margin-bottom: 25px; position: relative; padding-bottom: 10px; }
        .footer-column-title::after { content: ''; position: absolute; bottom: 0; left: 0; width: 50px; height: 3px; background-color: var(--primary-color); }
        .footer-logo h2 { max-width: 160px; margin-bottom: 15px; color: var(--primary-color);}
        .footer-description { font-size: 0.95rem; line-height: 1.7; }
        .links-section ul { list-style: none; padding: 0; margin: 0; } .links-section ul li { margin-bottom: 12px; } .links-section ul li a { display: flex; align-items: center; gap: 10px; text-decoration: none; color: var(--text-dark); transition: all 0.2s ease-in-out; } .links-section ul li a:hover { color: var(--primary-color); transform: translateX(5px); }
        .telegram-buttons-container { display: flex; flex-direction: column; gap: 15px; } .telegram-button { display: flex; align-items: center; gap: 15px; padding: 12px 15px; border-radius: 8px; text-decoration: none; color: white; background-color: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); transition: all 0.2s ease; } .telegram-button:hover { background-color: rgba(255, 255, 255, 0.1); border-color: var(--primary-color); transform: translateY(-2px); } .telegram-button i { font-size: 1.8rem; width: 30px; text-align: center; } .telegram-button.notification i { color: #34B7F1; } .telegram-button.request i { color: #f5c518; } .telegram-button.backup i { color: #28a745; } .telegram-button span { display: flex; flex-direction: column; } .telegram-button small { font-size: 0.75rem; color: var(--text-dark); }
        .footer-note { font-size: 0.8rem; color: var(--text-dark); margin-top: 20px; background-color: rgba(0,0,0,0.2); padding: 10px; border-radius: 5px; } .footer-note a { color: #34B7F1; font-weight: bold; }
        .footer-bottom-bar { background-color: #000; text-align: center; padding: 20px; font-size: 0.9rem; border-top: 1px solid #222; }

        @keyframes rgb-glow-border { 0% { border-color: #ff00de; box-shadow: 0 0 8px #ff00de; } 25% { border-color: #00ffff; box-shadow: 0 0 10px #00ffff; } 50% { border-color: #00ff7f; box-shadow: 0 0 8px #00ff7f; } 75% { border-color: #f83d61; box-shadow: 0 0 10px #f83d61; } 100% { border-color: #ff00de; box-shadow: 0 0 8px #ff00de; } } 
        .gallery-content-wrapper { max-width: 90%; margin: 0 auto; margin-bottom: 30px;} 
        .gallery-item a { display: block; position: relative; padding-top: 56.25%; border-radius: 8px; overflow: hidden; border: 2px solid transparent; animation: rgb-glow-border 5s linear infinite; } 
        .gallery-item img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; transition: opacity 0.7s ease-in-out; } 
        .thumbnail-stack { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; } 
        #auto-change-item .changing-image { opacity: 0; } #auto-change-item .changing-image.active { opacity: 1; } 

        .download-hub-section { background-color: var(--card-bg); border: 1px solid #2a2a2a; border-radius: 12px; padding: 25px; margin: 40px auto; max-width: 800px; text-align: center; } 
        .hub-section-title { display: flex; align-items: center; justify-content: center; gap: 12px; font-size: 1.5rem; font-weight: 600; margin: 0 0 10px 0; } 
        .hub-section-description { color: var(--text-dark); margin: 0 0 25px 0; font-size: 1rem; line-height: 1.6; } 
        .hub-proceed-button { display: inline-flex; align-items: center; justify-content: center; gap: 12px; background-color: var(--primary-color); color: white; padding: 15px 35px; border-radius: 8px; font-size: 1.2rem; font-weight: 700; text-decoration: none; transition: all 0.2s ease; border: none; cursor: pointer; box-shadow: 0 4px 15px rgba(229, 9, 20, 0.3); } 
        .hub-proceed-button:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(229, 9, 20, 0.5); filter: brightness(1.1); }

        @media (max-width: 768px) { 
            .related-grid { gap: 10px; } .card-title { font-size: 0.8rem; } .badges-bottom { bottom: 6px; padding: 0 6px; } 
            .language-tag, .rating-tag, .type-tag { padding: 2px 7px; font-size: 0.6rem; border-radius: 4px; } 
            .new-badge { padding: 3px 10px 3px 6px; font-size: 0.6rem; } 
            .footer-grid { text-align: center; } .footer-column-title::after { left: 50%; transform: translateX(-50%); } .links-section ul li a { justify-content: center; }
        } 
        @media (min-width: 769px) { 
            .container { padding: 0 40px; } .hero-section-wrapper { margin: 0 40px 40px 40px; margin-bottom: 60px; } .overlay-poster { left: 50px; bottom: -80px; max-width: 220px; } .content-info-section { padding-left: 300px; } .detail-title { font-size: 2.5rem; } .related-grid { grid-template-columns: repeat(4, 1fr); } 
            .edit-icon-link { right: 50px; }
            .gallery-content-wrapper { display: grid; grid-template-columns: 2fr 1fr; gap: 15px; max-width: 1200px; } .hero-image-container { grid-column: 1 / 2; } .thumbnail-stack { grid-column: 2 / 3; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 0; }
        }
    </style>
    {{ ad_settings.ad_header | safe }}
</head>
<body>
    <header class="main-header">
        <div class="header-content container">
            <a href="{{ url_for('home') }}" class="logo">{{ website_name }}</a>
            <div style="display:flex; align-items:center;">
                <!-- NEW: Eye Icon for Auto Blur Toggle -->
                <button id="blur-toggle-btn" class="blur-toggle-btn" title="Toggle Anti-Copyright Blur">
                    <i class="fas fa-eye-slash" id="blur-icon"></i>
                </button>
            </div>
        </div>
    </header>

    {% macro render_movie_card(m) %}
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
      <div class="poster-wrapper">
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

    <div class="container">
        <div class="page-header"><a href="javascript:history.back()" class="go-back-btn"><i class="fas fa-arrow-left"></i> Back</a></div>
        
        <div class="hero-section-wrapper">
            {% if movie %}
                <a href="{{ url_for('edit_auth_redirect', movie_id=movie._id) }}" class="edit-icon-link" title="Edit Content" onclick="return confirm('You are about to enter the Admin Edit area. Continue?')"><i class="fas fa-pencil-alt"></i></a>
            {% endif %}
            <div class="detail-hero-backdrop">
                <img src="{{ movie.backdrop or movie.poster or 'https://via.placeholder.com/1280x720.png' }}" alt="{{ movie.title }}" class="hero-backdrop-img">
                <div class="hero-overlay"></div>
                <img src="{{ movie.poster or 'https://via.placeholder.com/400x600.png' }}" alt="{{ movie.title }}" class="overlay-poster movie-poster">
                <div class="content-type-badge">{{ movie.type | title }}</div>
            </div>
        </div>

        <div class="content-info-section">
            <h1 class="detail-title">{{ movie.title }} {% if movie.release_year %} ({{ movie.release_year }}){% elif movie.release_date %} ({{ movie.release_date.split('-')[0] }}){% endif %}</h1>
            <div class="detail-meta">
                {% if movie.vote_average and movie.vote_average > 0 %}<div class="meta-item rating"><i class="fas fa-star"></i> {{ "%.1f"|format(movie.vote_average) }} / 10</div>{% endif %}
                {% if movie.release_date or movie.release_year %}<div class="meta-item"><i class="far fa-calendar-alt"></i> {{ movie.release_date or movie.release_year }}</div>{% endif %}
                <div class="meta-item"><i class="far fa-clock"></i> {{ movie._id | time_ago }}</div>
                {% if movie.genres %}<div class="meta-item"><i class="fas fa-tags"></i> {{ movie.genres | join(', ') }}</div>{% endif %}
                {% if movie.languages %}<div class="meta-item"><i class="fas fa-language"></i> {{ movie.languages | join(', ') }}</div>{% endif %}
                <div class="meta-item"><i class="fas fa-eye"></i> {{ movie.view_count or 0 }} views</div>
            </div>
            {% if movie.overview %}<p class="detail-overview">{{ movie.overview }}</p>{% endif %}
        </div>

        <div style="text-align: center; margin: 40px 0;">
            <a href="{{ url_for('request_content', report_id=movie._id, title=movie.title) }}" class="report-button"><i class="fas fa-flag"></i> Report a Problem</a>
        </div>

        {% if movie.backdrop_images and movie.backdrop_images|length > 0 %}
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
                <div class="gallery-item thumbnail-item"><a href="{{ img_url }}" target="_blank"><img src="{{ img_url }}" loading="lazy" alt="thumbnail"></a></div>
                {% endfor %}
            </div>
            {% endif %}
        </div>
        {% endif %}

        {% if ad_settings.ad_detail_page %}<div class="ad-container">{{ ad_settings.ad_detail_page | safe }}</div>{% endif %}

        {% if movie.trailer_url %}
        <div class="trailer-section">
            <h2 class="section-title">Official Trailer</h2>
            <div class="trailer-video-wrap"><iframe src="{{ movie.trailer_url }}" allowfullscreen></iframe></div>
        </div>
        {% endif %}

        {% if movie.type == 'movie' %}
            {% set has_links = movie.streaming_links or movie.links or movie.files %}
            {% if has_links %}
                <div class="download-hub-section">
                    <h3 class="hub-section-title"><i class="fas fa-download"></i><span>Streaming & Download Options</span></h3>
                    <p class="hub-section-description">All available links (1080p, 720p, Stream, Direct Download, Telegram File etc.) are organized on the next page for your convenience 🔗👇.</p>
                    <a href="{{ url_for('wait_page', target=quote(url_for('download_hub', movie_id=movie._id))) }}" class="hub-proceed-button"><span>🍿 Proceed to Movie Link 🍿</span><i class="fas fa-arrow-right"></i></a>
                </div>
            {% else %}
                <div class="download-hub-section"><p>Oops! No links available for "{{ movie.title }}" yet.</p></div>
            {% endif %}
        {% elif movie.type == 'series' %} 
            {% if movie.episodes %}
                <div class="download-hub-section">
                    <h3 class="hub-section-title"><i class="fas fa-tv"></i><span>Watch All Episodes</span></h3>
                    <p class="hub-section-description">All available seasons and episodes are organized on the next page. Click below to see all links 🔗👇.</p>
                    <a href="{{ url_for('wait_page', target=quote(url_for('series_hub', series_id=movie._id))) }}" class="hub-proceed-button"><span>🍿 Proceed to Series Link 🍿</span><i class="fas fa-arrow-right"></i></a>
                </div>
            {% else %}
                <div class="download-hub-section"><p>Oops! All episodes of "{{ movie.title }}" are currently unavailable.</p></div>
            {% endif %}
        {% endif %}

        {% if related_content %}
        <section class="category-section">
            <div class="category-header"><h2 class="category-title">You Might Also Like</h2></div>
            <div class="related-grid">
                {% for m in related_content %}
                    {{ render_movie_card(m) }}
                {% endfor %}
            </div>
        </section>
        {% endif %}
    </div>

    <footer class="professional-footer">
        <div class="footer-grid">
            <div class="footer-column about-section">
                <h4 class="footer-column-title">About {{ website_name }}</h4>
                <div class="footer-logo">
                    <h2 style="color: var(--primary-color); margin: 0 0 10px 0;">{{ website_name }}</h2>
                </div>
                <p class="footer-description">
                    Your ultimate destination for downloading and streaming the latest movies and web series. We provide high-quality content ranging from 480p to 4K. Bookmark us for your daily entertainment dose!
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

    {{ ad_settings.ad_footer | safe }}
    
    <script>
        // === [NEW] AUTO BLUR LOGIC ===
        const blurConfig = {
            enabled: "{{ blur_settings.enabled }}" === "yes",
            timer: parseInt("{{ blur_settings.timer }}") * 1000
        };
        let isBlurred = false;
        let blurTimeout;

        function applyBlur() {
            document.body.classList.add('auto-blur');
            const icon = document.getElementById('blur-icon');
            if(icon) { icon.classList.remove('fa-eye-slash'); icon.classList.add('fa-eye'); }
            isBlurred = true;
        }

        function removeBlur() {
            document.body.classList.remove('auto-blur');
            const icon = document.getElementById('blur-icon');
            if(icon) { icon.classList.remove('fa-eye'); icon.classList.add('fa-eye-slash'); }
            isBlurred = false;
        }

        if (blurConfig.enabled) {
            if(blurConfig.timer === 0) { applyBlur(); } 
            else { blurTimeout = setTimeout(applyBlur, blurConfig.timer); }
        }

        const blurBtn = document.getElementById('blur-toggle-btn');
        if(blurBtn) {
            blurBtn.addEventListener('click', function() {
                if (isBlurred) {
                    removeBlur();
                    clearTimeout(blurTimeout);
                } else {
                    applyBlur();
                }
            });
        }
        // === END AUTO BLUR LOGIC ===
        
        document.addEventListener('DOMContentLoaded', function() {
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
    </script>
</body>
</html>
"""

wait_step1_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Please Wait - Step 1</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg-color: #000000; --card-bg: #1a1a1a; --primary-color: #e50914; --text-light: #ffffff; --text-dark: #aaaaaa; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); margin: 0; padding-bottom: 60px; text-align: center;}
        .fixed-header { position: fixed; top: 0; left: 0; width: 100%; background-color: var(--card-bg); padding: 15px 0; z-index: 1000; border-bottom: 1px solid #333; }
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
    {{ ad_settings.ad_header | safe }}
</head>
<body>
    <header class="fixed-header"><h2 style="color:var(--primary-color); margin:0;">{{ website_name }}</h2></header>
    <div id="top-content" class="page-section">
        {{ ad_settings.ad_body_top | safe }}
        <div class="wait-container">
            <h1>Please Wait</h1>
            <p>Your download link is being prepared. Please scroll down after the timer ends.</p>
            <div id="timer-text" class="timer">Please wait <span id="countdown">{{ wait_time }}</span> seconds...</div>
            <a id="continue-btn-1" href="#bottom-content" class="action-btn" disabled>Preparing Link...</a>
        </div>
        {% if ad_settings.ad_wait_page %}<div class="ad-container">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>
    <div class="ad-section" style="padding: 50px 0;">
        <h2>Advertisement</h2>
        {% if ad_settings.ad_wait_page %}<div class="ad-container" style="min-height: 200px;">{{ ad_settings.ad_wait_page | safe }}</div>{% endif %}
    </div>
    <div id="bottom-content" class="page-section">
        <div class="wait-container">
            <h1>Ready to Continue</h1>
            <p>Click the button below to proceed to the next step.</p>
            <a href="{{ next_step_url }}" class="action-btn ready">Continue</a>
        </div>
    </div>
    <script>
        (function() {
            let timeLeft = {{ wait_time }};
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
                } else { countdownElement.textContent = timeLeft; }
                timeLeft--;
            }, 1000);
        })();
    </script>
    {{ ad_settings.ad_footer | safe }}
</body>
</html>
"""

wait_step2_html = wait_step1_html.replace('Step 1', 'Step 2').replace('Please Wait', 'Almost There...').replace('Your download link is being prepared', 'Please wait while we process your request').replace('Continue', 'Continue to Final Step').replace('Ready to Continue', 'Ready for Final Step')

wait_step3_html = wait_step1_html.replace('Step 1', 'Final Step').replace('Please Wait', 'Final Step').replace('Your download link is being prepared', 'Your download link is ready').replace('Ready to Continue', 'Your Link is Ready!').replace('Continue', 'Get Link').replace('Click Here to Continue', 'Click to Scroll Down').replace('href="#bottom-content"', 'href="{{ target_url | safe }}"')

request_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Request Content - {{ website_name }}</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root { --bg-color: #000000; --card-bg: #1a1a1a; --primary-color: #e50914; --text-light: #ffffff; }
        body { font-family: 'Poppins', sans-serif; background-color: var(--bg-color); color: var(--text-light); margin: 0; padding: 20px;}
        .form-container { max-width: 600px; margin: 40px auto; background-color: var(--card-bg); padding: 30px; border-radius: 8px; border: 1px solid #333; }
        .form-container h2 { text-align: center; margin-bottom: 20px; color: var(--primary-color); }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: 500; }
        .form-group input, .form-group textarea, .form-group select { width: 100%; padding: 12px; border: 1px solid #444; border-radius: 4px; background-color: #111; color: white; font-family: inherit; box-sizing: border-box; }
        .submit-btn { width: 100%; padding: 12px; background-color: var(--primary-color); color: white; border: none; border-radius: 4px; font-size: 1.1rem; font-weight: 600; cursor: pointer; transition: background-color 0.2s; }
        .submit-btn:hover { background-color: #B20710; }
    </style>
</head>
<body>
    <div class="form-container">
        {% if message_sent %}
            <h2 style="color: #28a745;">Request Submitted Successfully!</h2>
            <p style="text-align:center;">Thank you for reaching out. Our team will look into it shortly.</p>
            <a href="{{ url_for('home') }}" class="submit-btn" style="text-decoration: none; display: block; text-align:center; margin-top:20px;">Return to Home</a>
        {% else %}
            <h2>{{ 'Report a Problem' if prefill_id else 'Request Content' }}</h2>
            <form method="post">
                {% if prefill_id %}<input type="hidden" name="reported_content_id" value="{{ prefill_id }}">{% endif %}
                <div class="form-group">
                    <label>Subject</label>
                    <select name="type">
                        <option value="Movie Request" {% if prefill_type == 'Movie Request' %}selected{% endif %}>Request a Movie</option>
                        <option value="Series Request" {% if prefill_type == 'Series Request' %}selected{% endif %}>Request a Series</option>
                        <option value="Problem Report" {% if prefill_type == 'Problem Report' %}selected{% endif %}>Report Broken Link/Problem</option>
                        <option value="Other">Other Query</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Title of Content / Subject</label>
                    <input type="text" name="content_title" value="{{ prefill_title }}" required placeholder="e.g. Inception (2010)">
                </div>
                <div class="form-group">
                    <label>Your Email (Optional)</label>
                    <input type="email" name="email" placeholder="So we can notify you">
                </div>
                <div class="form-group">
                    <label>Message Details</label>
                    <textarea name="message" rows="5" required placeholder="Tell us more details..."></textarea>
                </div>
                <button type="submit" class="submit-btn">Submit Request</button>
                <a href="{{ url_for('home') }}" style="display:block; text-align:center; margin-top:15px; color:#aaa; text-decoration:none;">Cancel & Go Back</a>
            </form>
        {% endif %}
    </div>
</body>
</html>
"""

# =========================================================================================
# === ADMIN TEMPLATES (With 4 Separate Menu Tabs inside Settings) ===
# =========================================================================================

admin_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --primary-color: #e50914; --bg-dark: #121212; --card-bg: #1e1e1e; --text-light: #f5f5f5; --text-muted: #aaaaaa; --netflix-red: #E50914; --dark-gray: #141414; --light-gray: #2F2F2F; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: var(--bg-dark); color: var(--text-light); margin: 0; padding: 20px; }
        h1, h2, h3 { color: var(--text-light); font-weight: 600; margin-top: 0; }
        .admin-container { max-width: 1200px; margin: 0 auto; background-color: var(--dark-gray); padding: 30px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--light-gray); padding-bottom: 20px; margin-bottom: 30px; }
        
        .admin-tabs { display: flex; gap: 5px; margin-bottom: 25px; border-bottom: 2px solid var(--light-gray); flex-wrap: wrap; }
        .tab-button { padding: 15px 20px; cursor: pointer; background: none; border: none; color: var(--text-muted); font-size: 1rem; font-weight: bold; border-bottom: 3px solid transparent; transition: all 0.2s; }
        .tab-button:hover { background-color: var(--light-gray); color: white; }
        .tab-button.active { color: var(--netflix-red); border-bottom-color: var(--netflix-red); }
        .tab-content { display: none; animation: fadeIn 0.4s; }
        .tab-content.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

        fieldset { border: 1px solid var(--light-gray); border-radius: 8px; padding: 20px; margin-bottom: 25px; background-color: var(--card-bg); }
        legend { background-color: var(--netflix-red); color: white; padding: 5px 15px; border-radius: 4px; font-weight: bold; font-size: 0.9rem; text-transform: uppercase; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 8px; font-weight: 500; color: #ddd; }
        input[type="text"], input[type="url"], input[type="number"], select, textarea { width: 100%; padding: 12px; background-color: var(--bg-dark); border: 1px solid var(--light-gray); color: white; border-radius: 6px; font-family: inherit; box-sizing: border-box; }
        input[type="text"]:focus, input[type="url"]:focus, select:focus, textarea:focus { outline: none; border-color: var(--netflix-red); }
        
        .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; transition: 0.2s; text-decoration: none; font-size: 0.9rem;}
        .btn-primary { background-color: var(--netflix-red); color: white; } .btn-primary:hover { background-color: #f6121d; }
        .btn-secondary { background-color: var(--light-gray); color: white; border: 1px solid #444; } .btn-secondary:hover { background-color: #444; }
        .btn-success { background-color: #28a745; color: white; } .btn-success:hover { background-color: #218838; }
        .btn-danger { background-color: #dc3545; color: white; } .btn-danger:hover { background-color: #c82333; }
        .btn-edit { background-color: #ffc107; color: #000; } .btn-edit:hover { background-color: #e0a800; }

        .dashboard-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: linear-gradient(145deg, var(--card-bg), var(--light-gray)); padding: 25px; border-radius: 10px; text-align: center; border: 1px solid #333; }
        .stat-card h3 { font-size: 1rem; color: var(--text-muted); margin-bottom: 10px; }
        .stat-card p { font-size: 2.5rem; font-weight: bold; color: var(--netflix-red); margin: 0; }

        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid var(--light-gray); }
        th { background-color: var(--card-bg); font-weight: 600; text-transform: uppercase; font-size: 0.85rem; color: var(--text-muted); }
        tr:hover { background-color: rgba(255,255,255,0.05); }
        .status-badge { padding: 5px 10px; border-radius: 50px; font-size: 0.8rem; font-weight: bold; }
        .status-pending { background-color: #ffc107; color: #000; } .status-fulfilled { background-color: #28a745; color: white; } .status-rejected { background-color: #dc3545; color: white; }
        
        .category-management { display: flex; flex-wrap: wrap; gap: 20px; }
        .checkbox-group { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
        .checkbox-group label { display: flex; align-items: center; gap: 8px; margin: 0; cursor: pointer; }
    </style>
</head>
<body>
    <div class="admin-container">
        <div class="header">
            <h1>{{ website_name }} Admin Panel</h1>
            <a href="{{ url_for('home') }}" class="btn btn-secondary" target="_blank"><i class="fas fa-external-link-alt"></i> View Site</a>
        </div>

        <div class="admin-tabs">
            <button class="tab-button active" onclick="openTab(event, 'add-content')"><i class="fas fa-plus-circle"></i> Add Content</button>
            <button class="tab-button" onclick="openTab(event, 'manage-content')"><i class="fas fa-tasks"></i> Manage Content</button>
            <button class="tab-button" onclick="openTab(event, 'category-ott')"><i class="fas fa-list"></i> Category & OTT</button>
            <button class="tab-button" onclick="openTab(event, 'ads-settings')"><i class="fas fa-bullhorn"></i> Ads Settings</button>
            <button class="tab-button" onclick="openTab(event, 'wait-settings')"><i class="fas fa-clock"></i> Wait/Download</button>
            <button class="tab-button" onclick="openTab(event, 'blur-settings')"><i class="fas fa-eye-slash"></i> Anti-Copyright</button>
        </div>

        <!-- Tab 1: Add Content -->
        <div id="add-content" class="tab-content active">
            <h2><i class="fas fa-plus-circle"></i> Add New Content</h2>
            <fieldset><legend>Automatic Method (Search TMDB)</legend>
                <div class="form-group" style="display:flex; gap:10px;">
                    <input type="text" id="tmdb_search_query" placeholder="e.g., Avengers Endgame">
                    <button type="button" class="btn btn-primary" onclick="searchTmdb()">Search</button>
                </div>
            </fieldset>
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
                    <div class="form-group"><label>Release Year:</label><input type="text" name="release_year" id="release_year"></div>
                    <div class="form-group"><label>Trailer URL (YouTube):</label><input type="url" name="trailer_url" id="trailer_url"></div>
                    <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie">Movie</option><option value="series">Series</option></select></div>
                </fieldset>
                <fieldset><legend>Backdrop Images</legend>
                    <div id="backdrop_images_container"></div>
                    <button type="button" onclick="addBackdropField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Backdrop</button>
                </fieldset>
                <fieldset><legend>Categories</legend>
                    <div class="form-group checkbox-group">{% for cat in categories_list %}<label><input type="checkbox" name="categories" value="{{ cat.name }}"> {{ cat.name }}</label>{% endfor %}</div>
                </fieldset>
                <fieldset><legend>OTT Platforms</legend>
                    <div class="form-group checkbox-group">{% for platform in ott_platforms_list %}<label><input type="checkbox" name="ott_platforms" value="{{ platform.name }}"> {{ platform.name }}</label>{% endfor %}</div>
                </fieldset>
                <div id="movie_fields">
                    <fieldset><legend>Movie Links</legend>
                        <p><b>Streaming Links</b></p>
                        <div class="form-group"><input type="url" name="streaming_link_1" placeholder="480p Stream URL"></div>
                        <div class="form-group"><input type="url" name="streaming_link_2" placeholder="720p Stream URL"></div>
                        <div class="form-group"><input type="url" name="streaming_link_3" placeholder="1080p Stream URL"></div><hr>
                        <p><b>Direct Download Links</b></p>
                        <div class="form-group"><input type="url" name="link_480p" placeholder="480p DL URL"></div>
                        <div class="form-group"><input type="url" name="link_720p" placeholder="720p DL URL"></div>
                        <div class="form-group"><input type="url" name="link_1080p" placeholder="1080p DL URL"></div><hr>
                        <p><b>Telegram Links</b></p>
                        <div class="form-group"><input type="url" name="telegram_link_480p" placeholder="480p Telegram URL"></div>
                        <div class="form-group"><input type="url" name="telegram_link_720p" placeholder="720p Telegram URL"></div>
                        <div class="form-group"><input type="url" name="telegram_link_1080p" placeholder="1080p Telegram URL"></div>
                    </fieldset>
                </div>
                <div id="episode_fields" style="display: none;">
                    <fieldset><legend>Series Episodes</legend>
                        <div id="episodes_container"></div>
                        <button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button>
                    </fieldset>
                </div>
                <button type="submit" class="btn btn-primary" style="width:100%; padding:15px; font-size:1.1rem;"><i class="fas fa-save"></i> Save Content</button>
            </form>
        </div>

        <!-- Tab 2: Manage Content -->
        <div id="manage-content" class="tab-content">
            <div class="dashboard-stats">
                <div class="stat-card"><h3>Total</h3><p>{{ stats.total_content }}</p></div>
                <div class="stat-card"><h3>Movies</h3><p>{{ stats.total_movies }}</p></div>
                <div class="stat-card"><h3>Series</h3><p>{{ stats.total_series }}</p></div>
                <div class="stat-card"><h3>Requests</h3><p>{{ stats.pending_requests }}</p></div>
            </div>
            <h2><i class="fas fa-inbox"></i> Requests</h2>
            <div style="overflow-x:auto;">
                <table>
                    <tr><th>Type</th><th>Title</th><th>Message</th><th>Status</th><th>Actions</th></tr>
                    {% for req in requests_list %}
                    <tr>
                        <td>{{ req.type }}</td><td>{{ req.name }}</td><td>{{ req.info }}</td>
                        <td><span class="status-badge status-{{ req.status|lower }}">{{ req.status }}</span></td>
                        <td>
                            <a href="{{ url_for('update_request_status', req_id=req._id, status='Fulfilled') }}" class="btn btn-success" style="padding: 5px;">&#10003;</a>
                            <a href="{{ url_for('delete_request', req_id=req._id) }}" class="btn btn-danger" style="padding: 5px;">&times;</a>
                        </td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
            <hr>
            <h2><i class="fas fa-film"></i> All Content</h2>
            <form method="post"><input type="hidden" name="form_action" value="bulk_delete">
            <table>
                <tr><th><input type="checkbox" id="select-all"></th><th>Title</th><th>Type</th><th>Views</th><th>Action</th></tr>
                {% for movie in content_list %}
                <tr>
                    <td><input type="checkbox" name="selected_ids" value="{{ movie._id }}"></td>
                    <td>{{ movie.title }}</td><td>{{ movie.type }}</td><td>{{ movie.view_count or 0 }}</td>
                    <td>
                        <a href="{{ url_for('edit_movie', movie_id=movie._id) }}" class="btn btn-edit" style="padding:5px 10px;">Edit</a>
                        <a href="{{ url_for('delete_movie', movie_id=movie._id) }}" class="btn btn-danger" style="padding:5px 10px;" onclick="return confirm('Sure?')">Del</a>
                    </td>
                </tr>
                {% endfor %}
            </table>
            <button type="submit" class="btn btn-danger" style="margin-top:15px;"><i class="fas fa-trash"></i> Delete Selected</button>
            </form>
        </div>

        <!-- Tab 3: Category & OTT -->
        <div id="category-ott" class="tab-content">
            <div class="category-management">
                <form method="post" style="flex:1;"><input type="hidden" name="form_action" value="add_category"><fieldset><legend>Add Category</legend><input type="text" name="category_name" required placeholder="New Category"><br><br><button type="submit" class="btn btn-primary">Add</button></fieldset></form>
                <div style="flex:1;"><h3>Categories</h3>{% for cat in categories_list %}<div style="display:flex; justify-content:space-between; background:var(--bg-dark); padding:10px; margin-bottom:5px;">{{ cat.name }} <a href="{{ url_for('delete_category', cat_id=cat._id) }}" class="btn btn-danger" style="padding:2px 8px;">X</a></div>{% endfor %}</div>
            </div><hr>
            <div class="category-management">
                <form method="post" style="flex:1;"><input type="hidden" name="form_action" value="add_ott_platform"><fieldset><legend>Add Platform</legend><input type="text" name="ott_platform_name" required placeholder="New Platform"><br><br><button type="submit" class="btn btn-primary">Add</button></fieldset></form>
                <div style="flex:1;"><h3>Platforms</h3>{% for p in ott_platforms_list %}<div style="display:flex; justify-content:space-between; background:var(--bg-dark); padding:10px; margin-bottom:5px;">{{ p.name }} <a href="{{ url_for('delete_ott_platform', platform_id=p._id) }}" class="btn btn-danger" style="padding:2px 8px;">X</a></div>{% endfor %}</div>
            </div>
        </div>

        <!-- Tab 4: Ads Settings -->
        <div id="ads-settings" class="tab-content">
            <form method="post"><input type="hidden" name="form_action" value="update_ads">
                <fieldset><legend>Global Ads</legend>
                    <label>Header Script:</label><textarea name="ad_header">{{ ad_settings.ad_header }}</textarea>
                    <label>Body Top:</label><textarea name="ad_body_top">{{ ad_settings.ad_body_top }}</textarea>
                    <label>Footer:</label><textarea name="ad_footer">{{ ad_settings.ad_footer }}</textarea>
                </fieldset>
                <fieldset><legend>In-Page Ads</legend>
                    <label>List Page:</label><textarea name="ad_list_page">{{ ad_settings.ad_list_page }}</textarea>
                    <label>Detail Page:</label><textarea name="ad_detail_page">{{ ad_settings.ad_detail_page }}</textarea>
                    <label>Wait Page:</label><textarea name="ad_wait_page">{{ ad_settings.ad_wait_page }}</textarea>
                </fieldset>
                <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Save Ads</button>
            </form>
        </div>

        <!-- Tab 5: Wait Settings (NEW) -->
        <div id="wait-settings" class="tab-content">
            <form method="post"><input type="hidden" name="form_action" value="update_wait_settings">
                <fieldset><legend>Download Page Steps & Timers</legend>
                    <div class="form-group">
                        <label>Total Number of Wait Steps (1, 2, or 3):</label>
                        <select name="total_steps">
                            <option value="1" {% if wait_settings.total_steps == 1 %}selected{% endif %}>1 Step (Direct to Link)</option>
                            <option value="2" {% if wait_settings.total_steps == 2 %}selected{% endif %}>2 Steps</option>
                            <option value="3" {% if wait_settings.total_steps == 3 %}selected{% endif %}>3 Steps (Default)</option>
                        </select>
                    </div>
                    <div class="form-group"><label>Step 1 Timer (Seconds):</label><input type="number" name="step1" value="{{ wait_settings.step1 }}" required></div>
                    <div class="form-group"><label>Step 2 Timer (Seconds):</label><input type="number" name="step2" value="{{ wait_settings.step2 }}" required></div>
                    <div class="form-group"><label>Step 3 Timer (Seconds):</label><input type="number" name="step3" value="{{ wait_settings.step3 }}" required></div>
                </fieldset>
                <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Save Wait Settings</button>
            </form>
        </div>

        <!-- Tab 6: Anti-Copyright (NEW) -->
        <div id="blur-settings" class="tab-content">
            <form method="post"><input type="hidden" name="form_action" value="update_blur_settings">
                <fieldset><legend>Auto-Blur Posters Configuration</legend>
                    <p style="color:var(--text-muted); font-size:0.9rem;">To avoid copyright strikes, posters will automatically blur after a few seconds. Users can toggle it manually via the eye icon in the header.</p>
                    <div class="form-group">
                        <label>Enable Auto-Blur?</label>
                        <select name="enabled">
                            <option value="yes" {% if blur_settings.enabled == 'yes' %}selected{% endif %}>Yes, Enable Auto-Blur</option>
                            <option value="no" {% if blur_settings.enabled == 'no' %}selected{% endif %}>No, Disable completely</option>
                        </select>
                    </div>
                    <div class="form-group"><label>Blur Delay Timer (Seconds) (0 = Instant Blur):</label><input type="number" name="timer" value="{{ blur_settings.timer }}" required></div>
                </fieldset>
                <button type="submit" class="btn btn-primary"><i class="fas fa-save"></i> Save Blur Settings</button>
            </form>
        </div>

    </div>

    <script>
        function openTab(evt, tabName) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab-button').forEach(el => el.classList.remove('active'));
            document.getElementById(tabName).classList.add('active');
            evt.currentTarget.classList.add('active');
        }

        document.getElementById('select-all').onclick = function() {
            var checkboxes = document.querySelectorAll('input[name="selected_ids"]');
            for (var checkbox of checkboxes) checkbox.checked = this.checked;
        }

        function toggleFields() {
            const isSeries = document.getElementById('content_type').value === 'series';
            document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block';
            document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none';
        }

        function addBackdropField() {
            const div = document.createElement('div');
            div.innerHTML = '<div style="display:flex;gap:10px;margin-bottom:10px;"><input type="url" name="backdrop_images[]" placeholder="Image URL"><button type="button" class="btn btn-danger" onclick="this.parentElement.remove()">X</button></div>';
            document.getElementById('backdrop_images_container').appendChild(div);
        }

        function addEpisodeField() {
            const div = document.createElement('div');
            div.style.border = "1px solid #444"; div.style.padding = "15px"; div.style.marginBottom = "15px";
            div.innerHTML = `
                <div style="display:flex;justify-content:space-between;margin-bottom:10px;"><b>New Episode</b><button type="button" class="btn btn-danger" onclick="this.parentElement.parentElement.remove()">Remove</button></div>
                <div class="form-group"><input type="number" name="episode_season[]" placeholder="Season Number" required></div>
                <div class="form-group"><input type="text" name="episode_number[]" placeholder="Episode Number" required></div>
                <div class="form-group"><input type="text" name="episode_title[]" placeholder="Episode Title (Optional)"></div>
                <div class="form-group"><input type="url" name="episode_stream_link[]" placeholder="Stream Link"></div>
                <div class="form-group"><input type="url" name="episode_download_link[]" placeholder="Download Link"></div>
                <div class="form-group"><input type="url" name="episode_telegram_link[]" placeholder="Telegram Link"></div>
                <div class="form-group"><textarea name="episode_links[]" placeholder="Custom Links: Button Text | URL"></textarea></div>
            `;
            document.getElementById('episodes_container').appendChild(div);
        }

        function searchTmdb() {
            const query = document.getElementById('tmdb_search_query').value;
            if(!query) return alert("Enter search query");
            fetch(`/admin/api/search?query=${encodeURIComponent(query)}`)
            .then(res => res.json())
            .then(data => {
                if(data.error) return alert("Error: " + data.error);
                let html = "<div style='display:flex;flex-wrap:wrap;gap:10px;margin-top:15px;'>";
                data.forEach(item => {
                    html += `<div style='border:1px solid #444;padding:10px;width:150px;text-align:center;cursor:pointer;background:#222;' onclick='selectTmdb("${item.id}", "${item.media_type}")'>
                        <img src="${item.poster}" style="width:100%;"><br><small>${item.title} (${item.year})</small></div>`;
                });
                html += "</div>";
                const container = document.createElement('div');
                container.innerHTML = html;
                document.getElementById('tmdb_search_query').parentElement.appendChild(container);
            });
        }

        function selectTmdb(id, type) {
            fetch(`/admin/api/details?id=${id}&type=${type}`)
            .then(res => res.json())
            .then(data => {
                document.getElementById('tmdb_id').value = data.tmdb_id;
                document.getElementById('title').value = data.title;
                document.getElementById('poster').value = data.poster || '';
                document.getElementById('backdrop').value = data.backdrop || '';
                document.getElementById('overview').value = data.overview || '';
                document.getElementById('release_year').value = data.release_date ? data.release_date.split('-')[0] : '';
                document.getElementById('content_type').value = data.type;
                if(data.trailer_url) document.getElementById('trailer_url').value = data.trailer_url;
                
                const genresInput = document.getElementById('genres');
                genresInput.value = data.genres.join(', ');
                
                document.getElementById('backdrop_images_container').innerHTML = '';
                if(data.backdrop_images) {
                    data.backdrop_images.forEach(img => {
                        const div = document.createElement('div');
                        div.innerHTML = `<div style="display:flex;gap:10px;margin-bottom:10px;"><input type="url" name="backdrop_images[]" value="${img}"><button type="button" class="btn btn-danger" onclick="this.parentElement.remove()">X</button></div>`;
                        document.getElementById('backdrop_images_container').appendChild(div);
                    });
                }
                toggleFields();
                alert("Data filled successfully!");
            });
        }
    </script>
</body>
</html>
"""

edit_html = """
<!DOCTYPE html>
<html lang="en">
<head><title>Edit Content</title><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
body { background:#121212; color:#fff; font-family:sans-serif; padding:20px; }
.container { max-width:800px; margin:auto; background:#1e1e1e; padding:30px; border-radius:10px; }
input, select, textarea { width:100%; padding:10px; margin-bottom:15px; background:#111; color:#fff; border:1px solid #444; border-radius:5px;}
.btn { padding:10px 20px; cursor:pointer; font-weight:bold; color:#fff; border:none; border-radius:5px; }
.btn-primary { background:#E50914; } .btn-secondary { background:#444; } .btn-danger { background:#dc3545; }
fieldset { border:1px solid #444; padding:20px; margin-bottom:20px; border-radius:5px;} legend { background:#E50914; padding:5px 10px; border-radius:5px;}
</style></head><body>
<div class="container"><h2>Edit: {{ movie.title }}</h2>
<form method="post">
    <input type="hidden" name="content_type" id="content_type" value="{{ movie.type }}">
    <label>Title:</label><input type="text" name="title" value="{{ movie.title }}" required>
    <label>Poster:</label><input type="url" name="poster" value="{{ movie.poster }}">
    <label>Backdrop:</label><input type="url" name="backdrop" value="{{ movie.backdrop }}">
    <label>Overview:</label><textarea name="overview">{{ movie.overview }}</textarea>
    <label>Release Year:</label><input type="text" name="release_year" value="{{ movie.release_year }}">
    <label>Languages:</label><input type="text" name="languages" value="{{ movie.languages|join(', ') }}">
    <label>Genres:</label><input type="text" name="genres" value="{{ movie.genres|join(', ') }}">
    <label>Poster Badge:</label><input type="text" name="poster_badge" value="{{ movie.poster_badge }}">
    <label>Trailer URL:</label><input type="url" name="trailer_url" value="{{ movie.trailer_url }}">

    <fieldset><legend>Backdrop Images</legend>
        <div id="backdrop_images_container">
            {% for img_url in movie.backdrop_images %}
            <div style="display:flex;gap:10px;margin-bottom:10px;"><input type="url" name="backdrop_images[]" value="{{ img_url }}"><button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button></div>
            {% endfor %}
        </div>
        <button type="button" onclick="addBackdropField()" class="btn btn-secondary">Add Backdrop Image</button>
    </fieldset>

    <fieldset><legend>Categories</legend>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
        {% for cat in categories_list %}<label><input type="checkbox" name="categories" value="{{ cat.name }}" {% if cat.name in movie.categories %}checked{% endif %}> {{ cat.name }}</label>{% endfor %}
        </div>
    </fieldset>

    <fieldset><legend>OTT Platforms</legend>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
        {% for platform in ott_platforms_list %}<label><input type="checkbox" name="ott_platforms" value="{{ platform.name }}" {% if platform.name in movie.ott_platforms %}checked{% endif %}> {{ platform.name }}</label>{% endfor %}
        </div>
    </fieldset>

    {% if movie.type == 'movie' %}
    <fieldset><legend>Movie Links</legend>
        <p>Streaming</p>
        <input type="url" name="streaming_link_1" value="{{ (movie.streaming_links|selectattr('name', 'equalto', '480p')|map(attribute='url')|first) or '' }}">
        <input type="url" name="streaming_link_2" value="{{ (movie.streaming_links|selectattr('name', 'equalto', '720p')|map(attribute='url')|first) or '' }}">
        <input type="url" name="streaming_link_3" value="{{ (movie.streaming_links|selectattr('name', 'equalto', '1080p')|map(attribute='url')|first) or '' }}">
        <p>Download</p>
        <input type="url" name="link_480p" value="{{ (movie.links|selectattr('quality', 'equalto', '480p')|map(attribute='url')|first) or '' }}">
        <input type="url" name="link_720p" value="{{ (movie.links|selectattr('quality', 'equalto', '720p')|map(attribute='url')|first) or '' }}">
        <input type="url" name="link_1080p" value="{{ (movie.links|selectattr('quality', 'equalto', '1080p')|map(attribute='url')|first) or '' }}">
        <p>Telegram</p>
        <input type="url" name="telegram_link_480p" value="{{ (movie.files|selectattr('quality', 'equalto', '480p')|map(attribute='url')|first) or '' }}">
        <input type="url" name="telegram_link_720p" value="{{ (movie.files|selectattr('quality', 'equalto', '720p')|map(attribute='url')|first) or '' }}">
        <input type="url" name="telegram_link_1080p" value="{{ (movie.files|selectattr('quality', 'equalto', '1080p')|map(attribute='url')|first) or '' }}">
    </fieldset>
    {% else %}
    <fieldset><legend>Episodes</legend>
        <div id="episodes_container">
        {% for ep in movie.episodes|sort(attribute='episode_number')|sort(attribute='season') %}
        <div style="border:1px solid #444; padding:15px; margin-bottom:15px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:10px;"><b>Episode</b><button type="button" class="btn btn-danger" onclick="this.parentElement.parentElement.remove()">X</button></div>
            <input type="number" name="episode_season[]" value="{{ ep.season }}" required>
            <input type="text" name="episode_number[]" value="{{ ep.episode_number }}" required>
            <input type="text" name="episode_title[]" value="{{ ep.title }}">
            <input type="url" name="episode_stream_link[]" value="{{ ep.stream_link }}">
            <input type="url" name="episode_download_link[]" value="{{ ep.download_link }}">
            <input type="url" name="episode_telegram_link[]" value="{{ ep.telegram_link }}">
            <textarea name="episode_links[]">{% for link in ep.links %}{{ link.text }} | {{ link.url }}&#10;{% endfor %}</textarea>
        </div>
        {% endfor %}
        </div>
        <button type="button" onclick="addEpisodeField()" class="btn btn-secondary">Add Episode</button>
    </fieldset>
    {% endif %}

    <div style="background: #111; padding: 15px; border-radius: 5px; margin-bottom:20px;">
        <label style="display: flex; align-items: center; gap: 10px; cursor: pointer; margin:0;">
            <input type="checkbox" name="notify_telegram" value="yes" style="width:20px;height:20px;margin:0;">
            <strong>Notify Telegram Channel About This Update</strong>
        </label>
    </div>

    <button type="submit" class="btn btn-primary" style="width:100%;">Update Content</button>
</form>
<a href="{{ url_for('admin') }}" style="display:block; text-align:center; margin-top:15px; color:#aaa; text-decoration:none;">Cancel & Go Back</a>
</div>
<script>
    function addBackdropField() {
        const div = document.createElement('div');
        div.innerHTML = '<div style="display:flex;gap:10px;margin-bottom:10px;"><input type="url" name="backdrop_images[]"><button type="button" class="btn btn-danger" onclick="this.parentElement.remove()">X</button></div>';
        document.getElementById('backdrop_images_container').appendChild(div);
    }
    function addEpisodeField() {
        const div = document.createElement('div');
        div.style.border = "1px solid #444"; div.style.padding = "15px"; div.style.marginBottom = "15px";
        div.innerHTML = `
            <div style="display:flex;justify-content:space-between;margin-bottom:10px;"><b>New Episode</b><button type="button" class="btn btn-danger" onclick="this.parentElement.parentElement.remove()">X</button></div>
            <input type="number" name="episode_season[]" placeholder="Season Number" required>
            <input type="text" name="episode_number[]" placeholder="Episode Number" required>
            <input type="text" name="episode_title[]" placeholder="Episode Title (Optional)">
            <input type="url" name="episode_stream_link[]" placeholder="Stream Link">
            <input type="url" name="episode_download_link[]" placeholder="Download Link">
            <input type="url" name="episode_telegram_link[]" placeholder="Telegram Link">
            <textarea name="episode_links[]" placeholder="Custom Links: Button Text | URL"></textarea>
        `;
        document.getElementById('episodes_container').appendChild(div);
    }
</script>
</body></html>
"""


# =========================================================================================
# === PYTHON FUNCTIONS AND ROUTES ===
# =========================================================================================

def get_tmdb_details(tmdb_id, media_type):
    if not TMDB_API_KEY: return None
    search_type = "tv" if media_type == "tv" else "movie"
    try:
        detail_url = f"https://api.themoviedb.org/3/{search_type}/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=videos,images"
        res = requests.get(detail_url, timeout=10)
        res.raise_for_status()
        data = res.json()

        trailer_url = None
        videos = data.get("videos", {}).get("results", [])
        for video in videos:
            if video.get("site") == "YouTube" and video.get("type") == "Trailer":
                trailer_url = f"https://www.youtube.com/embed/{video.get('key')}"
                break

        backdrop_images = []
        backdrops = data.get("images", {}).get("backdrops", [])
        for backdrop in backdrops[:10]:
            backdrop_images.append(f"https://image.tmdb.org/t/p/w1280{backdrop.get('file_path')}")

        details = {
            "tmdb_id": tmdb_id,
            "title": data.get("title") or data.get("name"),
            "poster": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None,
            "backdrop": f"https://image.tmdb.org/t/p/w1280{data.get('backdrop_path')}" if data.get('backdrop_path') else None,
            "backdrop_images": backdrop_images,
            "overview": data.get("overview"),
            "release_date": data.get("release_date") or data.get("first_air_date"),
            "genres": [g['name'] for g in data.get("genres", [])],
            "vote_average": data.get("vote_average"),
            "type": "series" if search_type == "tv" else "movie",
            "trailer_url": trailer_url
        }
        return details
    except requests.RequestException as e:
        print(f"ERROR: TMDb API request failed: {e}")
        return None

def convert_to_embed_url(url):
    if not url or not isinstance(url, str): return ""
    if "youtube.com/embed/" in url: return url
    video_id = None
    from urllib.parse import urlparse, parse_qs
    parsed_url = urlparse(url)
    if "youtu.be" in parsed_url.netloc: video_id = parsed_url.path[1:]
    if "youtube.com" in parsed_url.netloc:
        query_params = parse_qs(parsed_url.query)
        if 'v' in query_params: video_id = query_params['v'][0]
    if video_id: return f"https://www.youtube.com/embed/{video_id}"
    return ""

def send_to_telegram(movie_data, movie_id):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID: return
    title = movie_data.get('title', 'Untitled')
    year = movie_data.get('release_year')
    full_title = f"{title} ({year})" if year else title

    caption_parts = [
        f"🔥 <b>New Content Added on {WEBSITE_NAME}!</b> 🔥", "━━━━━━━━━━━━━━━━━",
        f"🎬 <b>{full_title}</b>", "━━━━━━━━━━━━━━━━━"
    ]

    overview = movie_data.get('overview', '')
    if overview:
        short_overview = overview if len(overview) < 150 else overview[:150] + '...'
        caption_parts.append(f"💬 <i>{short_overview}</i>")
        caption_parts.append("━━━━━━━━━━━━━━━━━")

    details = []
    details.append(f"✨ <b>Type:</b> {movie_data.get('type', 'N/A').title()}")
    if movie_data.get('poster_badge'): details.append(f"💌 <b>Badge:</b> {movie_data.get('poster_badge')}")
    if movie_data.get('genres'): details.append(f"🎭 <b>Genres:</b> {', '.join(movie_data.get('genres', []))}")
    if movie_data.get('languages'): details.append(f"🔊 <b>Language:</b> {', '.join(movie_data.get('languages', []))}")

    if movie_data['type'] == 'movie':
        qualities = set()
        for link in movie_data.get('links', []): qualities.add(link.get('quality'))
        for file in movie_data.get('files', []): qualities.add(file.get('quality'))
        quality_info = " | ".join(sorted([q for q in qualities if q], reverse=True))
        if quality_info: details.append(f"💿 <b>Quality:</b> {quality_info}")
    elif movie_data['type'] == 'series':
        seasons = sorted(list(set(ep.get('season') for ep in movie_data.get('episodes', []))))
        if seasons:
            season_summary = ", ".join([f"Season {s}" for s in seasons])
            details.append(f"📺 <b>Available:</b> {season_summary}")

    caption_parts.append("\n".join(details))
    caption_parts.append("━━━━━━━━━━━━━━━━━")
    caption_parts.append(f"👇 <b>Watch or Download on {WEBSITE_NAME}</b> 👇")

    caption = "\n".join(caption_parts)
    watch_url = url_for('movie_detail', movie_id=movie_id, _external=True)
    keyboard = {"inline_keyboard": [
        [{"text": "✅ Watch on Website", "url": watch_url}],
        [{"text": "🤔 How to Download?", "url": HOW_TO_DOWNLOAD_URL}],
        [{"text": "🔔 Join Our Backup Channel", "url": "https://t.me/allmoviepsz"}]
    ]}
    reply_markup = json.dumps(keyboard)

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {'chat_id': TELEGRAM_CHANNEL_ID, 'photo': movie_data.get('poster'), 'caption': caption, 'parse_mode': 'HTML', 'reply_markup': reply_markup}
    try: requests.post(api_url, data=payload, timeout=20)
    except: pass

class Pagination:
    def __init__(self, page, per_page, total_count):
        self.page = page
        self.per_page = per_page
        self.total_count = total_count
    @property
    def total_pages(self): return math.ceil(self.total_count / self.per_page)
    @property
    def has_prev(self): return self.page > 1
    @property
    def has_next(self): return self.page < self.total_pages
    @property
    def prev_num(self): return self.page - 1
    @property
    def next_num(self): return self.page + 1

def get_paginated_content(query_filter, page):
    skip = (page - 1) * ITEMS_PER_PAGE
    total_count = movies.count_documents(query_filter)
    content_list = list(movies.find(query_filter).sort('updated_at', -1).skip(skip).limit(ITEMS_PER_PAGE))
    pagination = Pagination(page, ITEMS_PER_PAGE, total_count)
    return content_list, pagination

# --- Routes ---

@app.route('/')
def home():
    query = request.args.get('q', '').strip()
    if query:
        movies_list = list(movies.find({"title": {"$regex": query, "$options": "i"}}).sort('updated_at', -1))
        total_results = movies.count_documents({"title": {"$regex": query, "$options": "i"}})
        pagination = Pagination(1, ITEMS_PER_PAGE, total_results)
        return render_template_string(index_html, movies=movies_list, query=f'Results for "{query}"', is_full_page_list=True, pagination=pagination)

    available_otts = sorted([p for p in movies.distinct("ott_platforms") if p])
    slider_content = list(movies.find({}).sort('updated_at', -1).limit(10))
    featured_content = list(movies.find({"categories": "Featured"}).sort('updated_at', -1).limit(10))
    trending_content = list(movies.find({"categories": "Trending"}).sort('updated_at', -1).limit(10))
    latest_content = list(movies.find({}).sort('updated_at', -1).limit(10))
    latest_movies = list(movies.find({"type": "movie"}).sort('updated_at', -1).limit(10))
    latest_series = list(movies.find({"type": "series"}).sort('updated_at', -1).limit(10))
    coming_soon = list(movies.find({"categories": "Coming Soon"}).sort('updated_at', -1).limit(10))

    context = {
        "slider_content": slider_content,
        "featured_content": featured_content,
        "trending_content": trending_content,
        "latest_content": latest_content,
        "latest_movies": latest_movies,
        "latest_series": latest_series,
        "coming_soon": coming_soon,
        "available_otts": available_otts,
        "is_full_page_list": False
    }
    return render_template_string(index_html, **context)

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    try:
        movie = movies.find_one({"_id": ObjectId(movie_id)})
        if not movie: return "Content not found", 404
        movies.update_one({"_id": ObjectId(movie_id)}, {"$inc": {"view_count": 1}})
        related_content = list(movies.find({"type": movie.get('type'), "_id": {"$ne": movie['_id']}}).sort('updated_at', -1).limit(12))
        return render_template_string(detail_html, movie=movie, related_content=related_content)
    except: return "Content not found", 404

@app.route('/download-hub/<movie_id>')
def download_hub(movie_id):
    try:
        movie = movies.find_one({"_id": ObjectId(movie_id)})
        if not movie: return "Content not found", 404
        qualities = {}
        for link in movie.get('streaming_links', []):
            q = link.get('name', 'Unknown').strip()
            if q not in qualities: qualities[q] = []
            qualities[q].append({**link, 'type': 'stream'})
        for link in movie.get('links', []):
            q = link.get('quality', 'Unknown').strip()
            if q not in qualities: qualities[q] = []
            qualities[q].append({**link, 'type': 'download'})
        for file in movie.get('files', []):
            q = file.get('quality', 'Unknown').strip()
            if q not in qualities: qualities[q] = []
            qualities[q].append({**file, 'type': 'telegram'})

        def sort_key(q):
            try: return -int(''.join(filter(str.isdigit, q)))
            except: return 0
        sorted_qualities = sorted(qualities.keys(), key=sort_key)
        return render_template_string(download_hub_html, movie=movie, qualities=qualities, sorted_qualities=sorted_qualities)
    except Exception as e: return "An error occurred", 500

@app.route('/series-hub/<series_id>')
def series_hub(series_id):
    try:
        series = movies.find_one({"_id": ObjectId(series_id), "type": "series"})
        if not series: return "Series not found", 404
        episodes_by_season = {}
        for ep in series.get('episodes', []):
            season_num = ep.get('season')
            if season_num not in episodes_by_season: episodes_by_season[season_num] = []
            episodes_by_season[season_num].append(ep)
        seasons_sorted = sorted(episodes_by_season.keys())
        return render_template_string(series_hub_html, series=series, episodes_by_season=episodes_by_season, seasons_sorted=seasons_sorted)
    except: return "An error occurred", 500

@app.route('/movies')
def all_movies():
    page = request.args.get('page', 1, type=int)
    all_movie_content, pagination = get_paginated_content({"type": "movie"}, page)
    return render_template_string(index_html, movies=all_movie_content, query="All Movies", is_full_page_list=True, pagination=pagination)

@app.route('/series')
def all_series():
    page = request.args.get('page', 1, type=int)
    all_series_content, pagination = get_paginated_content({"type": "series"}, page)
    return render_template_string(index_html, movies=all_series_content, query="Web Series & TV Shows", is_full_page_list=True, pagination=pagination)

@app.route('/all-content')
def all_content():
    page = request.args.get('page', 1, type=int)
    all_recent_content, pagination = get_paginated_content({}, page)
    return render_template_string(index_html, movies=all_recent_content, query="All Recently Added Content", is_full_page_list=True, pagination=pagination)

@app.route('/edit_auth_redirect/<movie_id>')
@requires_auth
def edit_auth_redirect(movie_id):
    return redirect(url_for('edit_movie', movie_id=movie_id))

@app.route('/platform/<platform_name>')
def movies_by_platform(platform_name):
    page = request.args.get('page', 1, type=int)
    decoded_name = unquote_plus(platform_name)
    platform_content, pagination = get_paginated_content({"ott_platforms": {"$in": [platform_name, decoded_name]}}, page)
    return render_template_string(index_html, movies=platform_content, query=f'Available on {decoded_name}', is_full_page_list=True, pagination=pagination, platform_info={"name": decoded_name})

@app.route('/genres')
def genres_page():
    all_genres = sorted([g for g in movies.distinct("genres") if g])
    return render_template_string(genres_html, genres=all_genres)

@app.route('/genre/<genre_name>')
def movies_by_genre_name(genre_name):
    decoded_genre_name = unquote_plus(genre_name)
    page = request.args.get('page', 1, type=int)
    genre_content, pagination = get_paginated_content({"genres": decoded_genre_name}, page)
    return render_template_string(index_html, movies=genre_content, query=f'Genres: {decoded_genre_name}', is_full_page_list=True, pagination=pagination)

@app.route('/category')
def movies_by_category():
    title = request.args.get('name')
    if not title: return redirect(url_for('home'))
    page = request.args.get('page', 1, type=int)
    if title == "Latest Movies": query_filter = {"type": "movie"}
    elif title == "Latest Series": query_filter = {"type": "series"}
    else: query_filter = {"categories": title}
    is_featured_page = (title == "Featured")
    content_list, pagination = get_paginated_content(query_filter, page)
    return render_template_string(index_html, movies=content_list, query=title, is_full_page_list=True, pagination=pagination, is_featured_page=is_featured_page)

@app.route('/request', methods=['GET', 'POST'])
def request_content():
    if request.method == 'POST':
        request_data = {
            "type": request.form.get("type"), "name": request.form.get("content_title"),
            "info": request.form.get("message"), "email": request.form.get("email", "").strip(),
            "reported_content_id": request.form.get("reported_content_id"), "status": "Pending", "created_at": datetime.utcnow()
        }
        requests_collection.insert_one(request_data)
        return render_template_string(request_html, message_sent=True)
    prefill_title = request.args.get('title', '')
    prefill_id = request.args.get('report_id', '')
    prefill_type = 'Problem Report' if prefill_id else 'Movie Request'
    return render_template_string(request_html, message_sent=False, prefill_title=prefill_title, prefill_id=prefill_id, prefill_type=prefill_type)

@app.route('/wait')
def wait_page():
    encoded_target_url = request.args.get('target')
    if not encoded_target_url: return redirect(url_for('home'))
    wait_config = settings.find_one({"_id": "wait_config"}) or {"step1": 10, "step2": 7, "step3": 5, "total_steps": 3}
    total_steps = wait_config.get('total_steps', 3)
    wait_time = wait_config.get('step1', 10)
    if total_steps == 1: next_step_url = unquote(encoded_target_url)
    elif total_steps == 2: next_step_url = url_for('wait_page_step3', target=encoded_target_url)
    else: next_step_url = url_for('wait_page_step2', target=encoded_target_url)
    return render_template_string(wait_step1_html, next_step_url=next_step_url, wait_time=wait_time)

@app.route('/wait/step2')
def wait_page_step2():
    encoded_target_url = request.args.get('target')
    if not encoded_target_url: return redirect(url_for('home'))
    wait_config = settings.find_one({"_id": "wait_config"}) or {"step1": 10, "step2": 7, "step3": 5, "total_steps": 3}
    wait_time = wait_config.get('step2', 7)
    next_step_url = url_for('wait_page_step3', target=encoded_target_url)
    return render_template_string(wait_step2_html, next_step_url=next_step_url, wait_time=wait_time)

@app.route('/wait/step3')
def wait_page_step3():
    encoded_target_url = request.args.get('target')
    if not encoded_target_url: return redirect(url_for('home'))
    wait_config = settings.find_one({"_id": "wait_config"}) or {"step1": 10, "step2": 7, "step3": 5, "total_steps": 3}
    wait_time = wait_config.get('step3', 5)
    final_target_url = unquote(encoded_target_url)
    return render_template_string(wait_step3_html, target_url=final_target_url, wait_time=wait_time)

@app.route('/disclaimer')
def disclaimer(): return render_template_string(disclaimer_html)

@app.route('/dmca')
def dmca(): return render_template_string(dmca_html)

@app.route('/create-website')
def create_website(): return render_template_string(create_website_html)

@app.route('/admin', methods=["GET", "POST"])
@requires_auth
def admin():
    if request.method == "POST":
        form_action = request.form.get("form_action")
        if form_action == "update_ads":
            ad_data = {"ad_header": request.form.get("ad_header"), "ad_body_top": request.form.get("ad_body_top"), "ad_footer": request.form.get("ad_footer"), "ad_list_page": request.form.get("ad_list_page"), "ad_detail_page": request.form.get("ad_detail_page"), "ad_wait_page": request.form.get("ad_wait_page")}
            settings.update_one({"_id": "ad_config"}, {"$set": ad_data}, upsert=True)
        elif form_action == "update_wait_settings":
            wait_data = {"step1": int(request.form.get("step1", 10)), "step2": int(request.form.get("step2", 7)), "step3": int(request.form.get("step3", 5)), "total_steps": int(request.form.get("total_steps", 3))}
            settings.update_one({"_id": "wait_config"}, {"$set": wait_data}, upsert=True)
        elif form_action == "update_blur_settings":
            blur_data = {"timer": int(request.form.get("timer", 5)), "enabled": request.form.get("enabled", "yes")}
            settings.update_one({"_id": "blur_config"}, {"$set": blur_data}, upsert=True)
        elif form_action == "add_category":
            cat_name = request.form.get("category_name", "").strip()
            if cat_name: categories_collection.update_one({"name": cat_name}, {"$set": {"name": cat_name}}, upsert=True)
        elif form_action == "add_ott_platform":
            p_name = request.form.get("ott_platform_name", "").strip()
            if p_name: ott_platforms_collection.update_one({"name": p_name}, {"$set": {"name": p_name}}, upsert=True)
        elif form_action == "bulk_delete":
            ids = request.form.getlist("selected_ids")
            if ids: movies.delete_many({"_id": {"$in": [ObjectId(i) for i in ids]}})
        elif form_action == "add_content":
            c_type = request.form.get("content_type", "movie")
            movie_data = {
                "title": request.form.get("title").strip(), "type": c_type,
                "poster": request.form.get("poster").strip() or PLACEHOLDER_POSTER,
                "view_count": 0, "backdrop": request.form.get("backdrop").strip() or None,
                "overview": request.form.get("overview").strip(),
                "languages": [l.strip() for l in request.form.get("languages", "").split(',') if l.strip()],
                "poster_badge": request.form.get("poster_badge", "").strip() or None,
                "release_year": request.form.get("release_year").strip() or None, 
                "genres": [g.strip() for g in request.form.get("genres", "").split(',') if g.strip()],
                "ott_platforms": request.form.getlist("ott_platforms"), "categories": request.form.getlist("categories"),
                "trailer_url": convert_to_embed_url(request.form.get("trailer_url", "").strip()),
                "backdrop_images": request.form.getlist("backdrop_images[]"),
                "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
                "streaming_links": [], "links": [], "files": [], "episodes": []
            }
            tmdb_id = request.form.get("tmdb_id")
            if tmdb_id:
                t_details = get_tmdb_details(tmdb_id, "tv" if c_type == "series" else "movie")
                if t_details:
                    movie_data.update({'release_date': t_details.get('release_date'), 'vote_average': t_details.get('vote_average')})
                    if not movie_data.get("trailer_url") and t_details.get("trailer_url"): movie_data["trailer_url"] = t_details.get("trailer_url")

            if c_type == "movie":
                movie_data['streaming_links'] = [{"name": n, "url": u} for n, u in [("480p", request.form.get("streaming_link_1", "")), ("720p", request.form.get("streaming_link_2", "")), ("1080p", request.form.get("streaming_link_3", ""))] if u.strip()]
                movie_data['links'] = [{"quality": q, "url": u} for q, u in [("480p", request.form.get("link_480p")), ("720p", request.form.get("link_720p")), ("1080p", request.form.get("link_1080p"))] if u and u.strip()]
                movie_data['files'] = [{"quality": q, "url": u} for q, u in [("480p", request.form.get("telegram_link_480p")), ("720p", request.form.get("telegram_link_720p")), ("1080p", request.form.get("telegram_link_1080p"))] if u and u.strip()]
            else:
                for s, e, t, stream, dl, telegram, links_text in zip(request.form.getlist('episode_season[]'), request.form.getlist('episode_number[]'), request.form.getlist('episode_title[]'), request.form.getlist('episode_stream_link[]'), request.form.getlist('episode_download_link[]'), request.form.getlist('episode_telegram_link[]'), request.form.getlist('episode_links[]')):
                    if s.strip() and e.strip():
                        c_links = [{"text": p[0].strip(), "url": p[1].strip()} for line in links_text.strip().splitlines() if '|' in line for p in [line.split('|', 1)] if len(p)==2 and p[0].strip() and p[1].strip()]
                        movie_data['episodes'].append({"season": int(s), "episode_number": e.strip(), "title": t.strip(), "stream_link": stream.strip() or None, "download_link": dl.strip() or None, "telegram_link": telegram.strip() or None, "links": c_links})
            ins_res = movies.insert_one(movie_data)
            with app.app_context(): send_to_telegram(movie_data, ins_res.inserted_id)
        return redirect(url_for('admin'))

    page = request.args.get('page', 1, type=int)
    content_list, pagination = get_paginated_content({}, page)
    stats = {"total_content": movies.count_documents({}), "total_movies": movies.count_documents({"type": "movie"}), "total_series": movies.count_documents({"type": "series"}), "pending_requests": requests_collection.count_documents({"status": "Pending"})}
    requests_list = list(requests_collection.find().sort("created_at", -1))
    categories_list = list(categories_collection.find().sort("name", 1))
    ott_platforms_list = list(ott_platforms_collection.find().sort("name", 1))
    ad_settings_data = settings.find_one({"_id": "ad_config"}) or {}
    wait_settings_data = settings.find_one({"_id": "wait_config"}) or {"step1": 10, "step2": 7, "step3": 5, "total_steps": 3}
    blur_settings_data = settings.find_one({"_id": "blur_config"}) or {"timer": 5, "enabled": "yes"}
    
    return render_template_string(admin_html, content_list=content_list, stats=stats, requests_list=requests_list, ad_settings=ad_settings_data, wait_settings=wait_settings_data, blur_settings=blur_settings_data, categories_list=categories_list, ott_platforms_list=ott_platforms_list, pagination=pagination)

@app.route('/admin/category/delete/<cat_id>')
@requires_auth
def delete_category(cat_id):
    try: categories_collection.delete_one({"_id": ObjectId(cat_id)})
    except: pass
    return redirect(url_for('admin'))

@app.route('/admin/ott_platform/delete/<platform_id>')
@requires_auth
def delete_ott_platform(platform_id):
    try: ott_platforms_collection.delete_one({"_id": ObjectId(platform_id)})
    except: pass
    return redirect(url_for('admin'))

@app.route('/admin/request/update/<req_id>/<status>')
@requires_auth
def update_request_status(req_id, status):
    if status in ['Fulfilled', 'Rejected', 'Pending']:
        try: requests_collection.update_one({"_id": ObjectId(req_id)}, {"$set": {"status": status}})
        except: pass
    return redirect(url_for('admin'))

@app.route('/admin/request/delete/<req_id>')
@requires_auth
def delete_request(req_id):
    try: requests_collection.delete_one({"_id": ObjectId(req_id)})
    except: pass
    return redirect(url_for('admin'))

@app.route('/edit_movie/<movie_id>', methods=["GET", "POST"])
@requires_auth
def edit_movie(movie_id):
    try: obj_id = ObjectId(movie_id)
    except: return "Invalid ID", 400
    movie_obj = movies.find_one({"_id": obj_id})
    if not movie_obj: return "Movie not found", 404

    if request.method == "POST":
        content_type = request.form.get("content_type")
        update_data = {
            "title": request.form.get("title").strip(), "type": content_type,
            "poster": request.form.get("poster").strip() or PLACEHOLDER_POSTER,
            "backdrop": request.form.get("backdrop").strip() or None,
            "overview": request.form.get("overview").strip(),
            "languages": [lang.strip() for lang in request.form.get("languages", "").split(',') if lang.strip()],
            "poster_badge": request.form.get("poster_badge").strip() or None,
            "release_year": request.form.get("release_year").strip() or None, 
            "genres": [g.strip() for g in request.form.get("genres").split(',') if g.strip()],
            "ott_platforms": request.form.getlist("ott_platforms"),
            "categories": request.form.getlist("categories"),
            "trailer_url": convert_to_embed_url(request.form.get("trailer_url", "").strip()),
            "backdrop_images": request.form.getlist("backdrop_images[]"),
            "updated_at": datetime.utcnow()
        }
        
        if content_type == "movie":
            update_data["streaming_links"] = [{"name": n, "url": u} for n, u in [("480p", request.form.get("streaming_link_1", "")), ("720p", request.form.get("streaming_link_2", "")), ("1080p", request.form.get("streaming_link_3", ""))] if u.strip()]
            update_data["links"] = [{"quality": q, "url": u} for q, u in [("480p", request.form.get("link_480p")), ("720p", request.form.get("link_720p")), ("1080p", request.form.get("link_1080p"))] if u and u.strip()]
            update_data["files"] = [{"quality": q, "url": u} for q, u in [("480p", request.form.get("telegram_link_480p")), ("720p", request.form.get("telegram_link_720p")), ("1080p", request.form.get("telegram_link_1080p"))] if u and u.strip()]
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"episodes": ""}})
        else:
            update_data["episodes"] = []
            for s, e, t, stream, dl, telegram, links_text in zip(request.form.getlist('episode_season[]'), request.form.getlist('episode_number[]'), request.form.getlist('episode_title[]'), request.form.getlist('episode_stream_link[]'), request.form.getlist('episode_download_link[]'), request.form.getlist('episode_telegram_link[]'), request.form.getlist('episode_links[]')):
                if s.strip() and e.strip():
                    c_links = [{"text": p[0].strip(), "url": p[1].strip()} for line in links_text.strip().splitlines() if '|' in line for p in [line.split('|', 1)] if len(p)==2 and p[0].strip() and p[1].strip()]
                    update_data["episodes"].append({"season": int(s), "episode_number": e.strip(), "title": t.strip(), "stream_link": stream.strip() or None, "download_link": dl.strip() or None, "telegram_link": telegram.strip() or None, "links": c_links})
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"links": "", "streaming_links": "", "files": ""}})
        
        if request.form.get("notify_telegram") == "yes":
            with app.app_context(): send_to_telegram(update_data, obj_id)
        return redirect(url_for('admin'))

    categories_list = list(categories_collection.find().sort("name", 1))
    ott_platforms_list = list(ott_platforms_collection.find().sort("name", 1))
    return render_template_string(edit_html, movie=movie_obj, categories_list=categories_list, ott_platforms_list=ott_platforms_list)

@app.route('/delete_movie/<movie_id>')
@requires_auth
def delete_movie(movie_id):
    try: movies.delete_one({"_id": ObjectId(movie_id)})
    except: return "Invalid ID", 400
    return redirect(url_for('admin'))

@app.route('/admin/api/live_search')
@requires_auth
def admin_api_live_search():
    query = request.args.get('q', '').strip()
    try:
        results = list(movies.find({"title": {"$regex": query, "$options": "i"}} if query else {}, {"_id": 1, "title": 1, "type": 1, "view_count": 1}).sort('updated_at', -1))
        for item in results: item['_id'] = str(item['_id'])
        return jsonify(results)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/admin/api/search')
@requires_auth
def api_search_tmdb():
    query = request.args.get('query')
    if not query: return jsonify({"error": "Query parameter is missing"}), 400
    try:
        search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={quote(query)}"
        res = requests.get(search_url, timeout=10)
        res.raise_for_status()
        data = res.json()
        results = [{"id": item.get('id'),"title": item.get('title') or item.get('name'),"year": (item.get('release_date') or item.get('first_air_date', 'N/A')).split('-')[0],"poster": f"https://image.tmdb.org/t/p/w200{item.get('poster_path')}","media_type": item.get('media_type')} for item in data.get('results', []) if item.get('media_type') in ['movie', 'tv'] and item.get('poster_path')]
        return jsonify(results)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/admin/api/details')
@requires_auth
def api_get_details():
    tmdb_id, media_type = request.args.get('id'), request.args.get('type')
    if not tmdb_id or not media_type: return jsonify({"error": "ID and type are required"}), 400
    details = get_tmdb_details(tmdb_id, media_type)
    if details: return jsonify(details)
    else: return jsonify({"error": "Details not found on TMDb"}), 404

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip()
    if not query: return jsonify([])
    try:
        results = list(movies.find({"title": {"$regex": query, "$options": "i"}}, {"_id": 1, "title": 1, "poster": 1}).limit(10))
        for item in results: item['_id'] = str(item['_id'])
        return jsonify(results)
    except Exception as e:
        print(f"API Search Error: {e}")
        return jsonify({"error": "An error occurred"}), 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 3000))
    app.run(debug=True, host='0.0.0.0', port=port)
