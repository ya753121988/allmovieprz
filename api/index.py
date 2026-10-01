import os
import sys
import requests
import threading
import time
from flask import Flask, render_template_string, request, redirect, url_for, Response, jsonify, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps
from urllib.parse import unquote, quote
from datetime import datetime, date
import math
import json

# --- Environment Variables ---
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://akash1980:akash1980@cluster0.upi2een.mongodb.net/?appName=Cluster0")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "275aff9f1c570308fa10d14c6f49f998")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "MRMOHIN198")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "MRMOHIN198")
WEBSITE_NAME = os.environ.get("WEBSITE_NAME", "All Movie Prz")
SECRET_KEY = os.environ.get("SECRET_KEY", "hdf_super_secret_key_1988")

if not all([MONGO_URI, TMDB_API_KEY, ADMIN_USERNAME, ADMIN_PASSWORD]):
    print("FATAL: One or more required environment variables are missing.")
    if os.environ.get('VERCEL') != '1':
        sys.exit(1)

PLACEHOLDER_POSTER = "https://via.placeholder.com/400x600.png?text=Poster+Not+Found"
ITEMS_PER_PAGE = 20
ADMIN_ITEMS_PER_PAGE = 10 
app = Flask(__name__)
app.secret_key = SECRET_KEY

# --- CACHE CONTROL SYSTEM ---
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# --- Authentication ---
def check_auth(username, password):
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# --- Database Connection & Speed Optimization (Indexing) ---
try:
    client = MongoClient(MONGO_URI)
    db = client["movie_db"]
    movies = db["movies"]
    settings = db["settings"]
    categories_collection = db["categories"]
    languages_collection = db["languages"]
    requests_collection = db["requests"]
    tg_posts_collection = db["tg_posts"]
    
    try:
        movies.create_index([("tmdb_id", 1)]) 
        movies.create_index([("views", -1)])
        movies.create_index([("title", 1)])
        movies.create_index([("release_date", -1), ("_id", -1)])
        movies.create_index([("type", 1)])
        movies.create_index([("categories", 1)])
        movies.create_index([("is_upcoming", 1)])
    except Exception as idx_e:
        pass

    if categories_collection.count_documents({}) == 0:
        default_categories = ["Coming Soon", "Bengali", "Hindi", "English", "18+ Adult Zone", "Trending"]
        categories_collection.insert_many([{"name": cat} for cat in default_categories])

    if languages_collection.count_documents({}) == 0:
        default_languages = ["Bengali", "Hindi", "English", "Tamil", "Telugu", "Korean", "Dual Audio", "Multi Audio"]
        languages_collection.insert_many([{"name": lang} for lang in default_languages])

except Exception as e:
    print(f"FATAL: Error connecting to MongoDB: {e}.")
    if os.environ.get('VERCEL') != '1':
        sys.exit(1)

# --- Custom Jinja Filter ---
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

# --- Helper for Download Steps & Poster Blur Configuration ---
def get_download_steps_config():
    config = settings.find_one({"_id": "download_steps_config"}) or {}
    steps = config.get("steps")
    if not isinstance(steps, list) or not steps:
        steps = [
            {"step_id": 1, "html": "<p>Ad Step 1</p>", "seconds": 5},
            {"step_id": 2, "html": "<p>Ad Step 2</p>", "seconds": 5},
            {"step_id": 3, "html": "<p>Ad Step 3</p>", "seconds": 5}
        ]
    return steps

def get_poster_blur_config():
    config = settings.find_one({"_id": "poster_blur_config"}) or {}
    return {
        "enabled": bool(config.get("enabled", True)),
        "seconds": int(config.get("seconds", 10))
    }

@app.context_processor
def inject_globals():
    ad_settings = settings.find_one({"_id": "ad_config"})
    popup_settings = settings.find_one({"_id": "popup_config"}) or {}
    noti_settings = settings.find_one({"_id": "noti_config"}) or {}
    tg_bot_config = settings.find_one({"_id": "telegram_bot_config"}) or {}
    
    site_config = settings.find_one({"_id": "site_config"})
    if not site_config:
        site_config = {
            "site_name": WEBSITE_NAME,
            "logo_url": "",
            "dmca_text": "DMCA : All Movie Prz Does Not Rip Or Host Any Files On Its Servers.",
            "privacy_text": "We respect your privacy. No personal data is collected without consent.",
            "tg_channel_url": "https://t.me/yourchannel",
            "tg_group_url": "https://t.me/yourgroup",
            "c_primary": "#E50914", "c_bg_dark": "#000000", "c_card_dark": "#1a1a1a",
            "c_text_dark": "#ffffff", "c_bg_light": "#f4f4f4", "c_card_light": "#ffffff", "c_text_light": "#111111",
            "auto_blur_timer": 1
        }

    all_categories = [cat['name'] for cat in categories_collection.find().sort("name", 1)]
    all_languages = [lang['name'] for lang in languages_collection.find().sort("name", 1)]
    return dict(
        website_name=site_config.get("site_name", WEBSITE_NAME),
        site_config=site_config,
        ad_settings=ad_settings or {},
        popup_settings=popup_settings,
        noti_settings=noti_settings,
        tg_bot_config=tg_bot_config,
        predefined_categories=all_categories,
        predefined_languages=all_languages,
        today_date=date.today().strftime("%Y-%m-%d"),
        quote=quote,
        poster_blur_config=get_poster_blur_config(),
        get_download_steps_config=get_download_steps_config
    )

# --- TMDB API Helper Function ---
def get_tmdb_details(tmdb_id, media_type):
    if not TMDB_API_KEY: return None
    search_type = "tv" if media_type == "tv" else "movie"
    try:
        detail_url = f"https://api.themoviedb.org/3/{search_type}/{tmdb_id}?api_key={TMDB_API_KEY}"
        res = requests.get(detail_url, timeout=10)
        res.raise_for_status()
        data = res.json()
        details = { 
            "tmdb_id": tmdb_id, 
            "title": data.get("title") or data.get("name"), 
            "poster": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get('poster_path') else None, 
            "backdrop": f"https://image.tmdb.org/t/p/w1280{data.get('backdrop_path')}" if data.get('backdrop_path') else None, 
            "overview": data.get("overview"), 
            "release_date": data.get("release_date") or data.get("first_air_date") or "", 
            "genres": [g['name'] for g in data.get("genres", [])], 
            "vote_average": data.get("vote_average"), 
            "type": "series" if search_type == "tv" else "movie",
            "original_language": data.get("original_language")
        }
        return details
    except requests.RequestException as e:
        print(f"ERROR: TMDb API request failed: {e}")
        return None

# --- TELEGRAM AUTO POST HELPER FUNCTION ---
def send_telegram_post(movie_data, movie_id):
    tg_config = settings.find_one({"_id": "telegram_bot_config"}) or {}
    site_config = settings.find_one({"_id": "site_config"}) or {}
    
    bot_token = tg_config.get("bot_token")
    channel_id = tg_config.get("channel_id")
    site_url = tg_config.get("site_url", "").rstrip('/')
    
    if not bot_token or not channel_id or not site_url: return
    
    title = movie_data.get("title", "Unknown Title")
    release_date = movie_data.get("release_date", "")
    year = release_date.split('-')[0] if release_date else ""
    language = movie_data.get("language", "Not Specified")
    if not language: language = "Not Specified"
    genres = ", ".join(movie_data.get("genres", []))
    overview = movie_data.get("overview", "")
    if len(overview) > 180: overview = overview[:177] + "..."
    
    image_url = movie_data.get("backdrop") or movie_data.get("poster") or PLACEHOLDER_POSTER
    movie_link = f"{site_url}/movie/{movie_id}"
    
    caption = f"🎬 <b>{title} {f'({year})' if year else ''}</b>\n\n"
    caption += f"🎭 <b>Genres:</b> {genres}\n"
    caption += f"🗣 <b>Language:</b> {language}\n"
    caption += f"🕰 <b>Quality:</b> 1080p, 720p, 480p\n\n"
    caption += f"📝 <b>Storyline:</b>\n{overview}\n\n"
    caption += f"━━━━━━━━━━━━━━━━━━━\n"
    caption += f"🌐 <b>Download & Watch Here:</b>\n"
    caption += f"👉 <a href='{movie_link}'>{site_config.get('site_name', WEBSITE_NAME)}</a>\n"
    caption += f"━━━━━━━━━━━━━━━━━━━"
    
    reply_markup = {
        "inline_keyboard": [
            [{"text": "📥 Watch & Download Now 🍿", "url": movie_link}],
            [
                {"text": "📢 Join Channel", "url": site_config.get("tg_channel_url", "https://t.me/")},
                {"text": "💬 Join Group", "url": site_config.get("tg_group_url", "https://t.me/")}
            ]
        ]
    }
    
    api_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    payload = {
        "chat_id": channel_id,
        "photo": image_url,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(reply_markup)
    }
    
    try:
        res = requests.post(api_url, data=payload, timeout=10).json()
        if res.get("ok"):
            message_id = res["result"]["message_id"]
            tg_posts_collection.insert_one({
                "message_id": message_id,
                "chat_id": channel_id,
                "posted_at": datetime.utcnow().timestamp()
            })
    except Exception as e:
        print("Telegram Auto Post Error:", e)

def check_and_release_upcoming():
    try:
        today_str = date.today().strftime("%Y-%m-%d")
        to_update = list(movies.find({
            "is_upcoming": True,
            "release_date": {"$type": "string", "$lte": today_str, "$ne": ""} 
        }).limit(3))
        for m in to_update:
            movies.update_one({"_id": m["_id"]}, {"$set": {"is_upcoming": False}})
            send_telegram_post(m, str(m["_id"]))
            settings.update_one(
                {"_id": "noti_config"},
                {"$set": {
                    "latest_release_id": str(m["_id"]),
                    "latest_release_title": m.get("title", "New Content"),
                    "latest_release_poster": m.get("poster", PLACEHOLDER_POSTER),
                    "latest_release_time": datetime.utcnow().timestamp()
                }},
                upsert=True
            )
    except Exception as e:
        pass

def tg_background_worker():
    while True:
        try:
            check_and_release_upcoming()
            tg_config = settings.find_one({"_id": "telegram_bot_config"}) or {}
            bot_token = tg_config.get("bot_token")
            channel_id = tg_config.get("channel_id")
            auto_post_min = int(tg_config.get("auto_post_interval", 0))
            auto_del_min = int(tg_config.get("auto_delete_interval", 0))
            now_ts = datetime.utcnow().timestamp()

            if bot_token and channel_id:
                if auto_del_min > 0:
                    cutoff_ts = now_ts - (auto_del_min * 60)
                    old_posts = list(tg_posts_collection.find({"posted_at": {"$lte": cutoff_ts}}))
                    for p in old_posts:
                        del_url = f"https://api.telegram.org/bot{bot_token}/deleteMessage?chat_id={p['chat_id']}&message_id={p['message_id']}"
                        requests.get(del_url, timeout=5)
                        tg_posts_collection.delete_one({"_id": p["_id"]})
                
                if auto_post_min > 0:
                    last_post_time = tg_config.get("last_auto_post_time", 0)
                    if now_ts - last_post_time >= (auto_post_min * 60):
                        total_movies = movies.count_documents({})
                        if total_movies > 0:
                            last_index = tg_config.get("last_auto_post_index", -1)
                            next_index = (last_index + 1) % total_movies
                            m_list = list(movies.find().skip(next_index).limit(1))
                            if m_list:
                                send_telegram_post(m_list[0], str(m_list[0]["_id"]))
                                settings.update_one(
                                    {"_id": "telegram_bot_config"},
                                    {"$set": {
                                        "last_auto_post_time": now_ts,
                                        "last_auto_post_index": next_index
                                    }},
                                    upsert=True
                                )
        except Exception as e:
            pass
        time.sleep(60)

if os.environ.get('VERCEL') != '1':
    threading.Thread(target=tg_background_worker, daemon=True).start()

@app.before_request
def global_background_tasks():
    check_and_release_upcoming()
    try:
        tg_config = settings.find_one({"_id": "telegram_bot_config"}) or {}
        bot_token = tg_config.get("bot_token")
        channel_id = tg_config.get("channel_id")
        auto_post_min = int(tg_config.get("auto_post_interval", 0))
        auto_del_min = int(tg_config.get("auto_delete_interval", 0))
        now_ts = datetime.utcnow().timestamp()

        if bot_token and channel_id:
            if auto_del_min > 0:
                cutoff_ts = now_ts - (auto_del_min * 60)
                old_posts = list(tg_posts_collection.find({"posted_at": {"$lte": cutoff_ts}}))
                for p in old_posts:
                    del_url = f"https://api.telegram.org/bot{bot_token}/deleteMessage?chat_id={p['chat_id']}&message_id={p['message_id']}"
                    requests.get(del_url, timeout=5)
                    tg_posts_collection.delete_one({"_id": p["_id"]})
            
            if auto_post_min > 0:
                last_post_time = tg_config.get("last_auto_post_time", 0)
                if now_ts - last_post_time >= (auto_post_min * 60):
                    total_movies = movies.count_documents({})
                    if total_movies > 0:
                        last_index = tg_config.get("last_auto_post_index", -1)
                        next_index = (last_index + 1) % total_movies
                        m_list = list(movies.find().skip(next_index).limit(1))
                        if m_list:
                            send_telegram_post(m_list[0], str(m_list[0]["_id"]))
                            settings.update_one(
                                {"_id": "telegram_bot_config"},
                                {"$set": {
                                    "last_auto_post_time": now_ts,
                                    "last_auto_post_index": next_index
                                }},
                                upsert=True
                            )
    except:
        pass

@app.route('/api/cron/trigger')
def cron_trigger():
    check_and_release_upcoming()
    global_background_tasks()
    return jsonify({"status": "Background tasks executed successfully"})

@app.route('/admin/api/bulk_fetch_page', methods=['POST'])
@requires_auth
def api_bulk_fetch_page():
    year = request.form.get('year', '2025')
    country = request.form.get('country', 'ALL')
    c_type = request.form.get('c_type', 'movie')
    page = request.form.get('page', 1, type=int)
    
    tmdb_genres = {28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance", 878: "Science Fiction", 10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western", 10759: "Action & Adventure", 10762: "Kids", 10763: "News", 10764: "Reality", 10765: "Sci-Fi & Fantasy", 10766: "Soap", 10767: "Talk", 10768: "War & Politics"}

    base_url = "https://api.themoviedb.org/3/discover/"
    endpoint = "movie" if c_type == "movie" else "tv"
    
    url = f"{base_url}{endpoint}?api_key={TMDB_API_KEY}&sort_by=popularity.desc&page={page}"
    if year:
        if c_type == "movie":
            url += f"&primary_release_year={year}"
        else:
            url += f"&first_air_date_year={year}"
    
    if country and country != "ALL":
        url += f"&with_origin_country={country}"
        
    if c_type == "drama":
        url += "&with_genres=18"
        
    try:
        res = requests.get(url, timeout=10).json()
        results = res.get("results", [])
        if not results:
            return jsonify({"items": [], "stop": True})
            
        added_items = []
        for item in results:
            t_id = str(item.get("id"))
            title = item.get("title") or item.get("name")
            
            if not movies.find_one({"tmdb_id": t_id}) and not movies.find_one({"title": title}):
                rel_date = item.get("release_date") or item.get("first_air_date") or ""
                poster_path = item.get("poster_path")
                poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else PLACEHOLDER_POSTER
                backdrop_path = item.get("backdrop_path")
                backdrop = f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else None
                
                g_ids = item.get("genre_ids", [])
                genres = [tmdb_genres.get(gid, "Unknown") for gid in g_ids if gid in tmdb_genres]
                
                movie_data = {
                    "tmdb_id": t_id,
                    "title": title,
                    "type": "movie" if c_type == "movie" else "series",
                    "poster": poster,
                    "backdrop": backdrop,
                    "overview": item.get("overview", ""),
                    "release_date": rel_date,
                    "language": item.get("original_language", "").upper(),
                    "genres": genres,
                    "categories": ["Upcoming"],
                    "is_copyright": False,
                    "is_upcoming": True,
                    "views": 0,
                    "episodes": [], "links": [], "season_packs": [], "manual_links": [], 
                    "created_at": datetime.utcnow()
                }
                movies.insert_one(movie_data)
                
                added_items.append({
                    "title": title,
                    "year": rel_date.split('-')[0] if rel_date else "N/A",
                    "poster": f"https://image.tmdb.org/t/p/w200{poster_path}" if poster_path else PLACEHOLDER_POSTER
                })
        
        return jsonify({"items": added_items, "stop": len(results) < 20})
    except Exception as e:
        return jsonify({"items": [], "stop": True, "error": str(e)})

@app.route('/download-step/<int:step_num>')
def download_step(step_num):
    target = request.args.get('target', '#')
    steps = get_download_steps_config()
    
    if step_num > len(steps):
        return redirect(target)
    
    current_step = steps[step_num - 1]
    next_step_num = step_num + 1
    next_url = url_for('download_step', step_num=next_step_num, target=target) if next_step_num <= len(steps) else target
    
    step_html_page = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Download Step {step_num} - {{ website_name }}</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Poppins', sans-serif; background: #0f172a; color: #f8fafc; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
        .box {{ background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); text-align: center; max-width: 500px; width: 90%; }}
        h2 {{ color: #38bdf8; margin-top: 0; }}
        .timer {{ font-size: 2rem; font-weight: bold; color: #facc15; margin: 20px 0; }}
        .btn {{ display: inline-block; background: #e50914; color: white; padding: 12px 30px; border-radius: 50px; text-decoration: none; font-weight: bold; font-size: 1rem; pointer-events: none; opacity: 0.6; transition: 0.3s; }}
        .btn.active {{ pointer-events: auto; opacity: 1; }}
        .ad-banner {{ margin: 20px 0; }}
    </style>
    </head>
    <body>
        <div class="box">
            <h2>Download Step {step_num} of {len(steps)}</h2>
            <p>Please wait while we process your download link...</p>
            <div class="ad-banner">{current_step.get('html', '')}</div>
            <div class="timer" id="count">{current_step.get('seconds', 5)}</div>
            <a href="{next_url}" id="proceed-btn" class="btn">Please Wait...</a>
        </div>
        <script>
            let timeLeft = {current_step.get('seconds', 5)};
            const timerEl = document.getElementById('count');
            const btnEl = document.getElementById('proceed-btn');
            
            const countdown = setInterval(() => {
                timeLeft--;
                timerEl.textContent = timeLeft;
                if(timeLeft <= 0) {
                    clearInterval(countdown);
                    timerEl.textContent = "Ready!";
                    btnEl.textContent = "Continue / Next Step";
                    btnEl.classList.add('active');
                    window.location.href = "{next_url}";
                }
            }, 1000);
        </script>
    </body>
    </html>
    """
    return render_template_string(step_html_page)

dynamic_css_and_js = """
<link rel="manifest" href="/manifest.json">
<style>
  :root {
    --primary-color: {{ site_config.c_primary }}; 
    --bg-color: {{ site_config.c_bg_dark }}; 
    --card-bg: {{ site_config.c_card_dark }};
    --text-light: {{ site_config.c_text_dark }};
  }
  body.light-mode {
    --bg-color: {{ site_config.c_bg_light }};
    --card-bg: {{ site_config.c_card_light }};
    --text-light: {{ site_config.c_text_light }};
  }
  body { background-color: var(--bg-color) !important; color: var(--text-light) !important; transition: background-color 0.3s, color 0.3s; }
  .movie-card, .search-results-dropdown, .main-footer, .request-container, .mobile-nav-menu, .card-info, .bottom-nav { background-color: var(--card-bg) !important; color: var(--text-light) !important; }
  .main-header { background-color: rgba(var(--bg-color), 0.95) !important; }
  .theme-btn { background: none; border: none; color: inherit; font-size: 1.2rem; cursor: pointer; display: flex; align-items: center; justify-content: center; }
  
  .tg-float-container { position: fixed; bottom: 85px; right: 15px; display: flex; flex-direction: column; gap: 10px; z-index: 9999; }
  .tg-btn { display: flex; align-items: center; gap: 8px; background: #0088cc; color: white !important; padding: 8px 12px; border-radius: 50px; text-decoration: none; box-shadow: 0 4px 10px rgba(0,0,0,0.5); transition: transform 0.2s; font-size: 0.85rem; font-weight: 600;}
  .tg-btn:hover { transform: scale(1.05); }
  .tg-btn i { font-size: 1.2rem; }
  @media (min-width: 769px) {
    .tg-float-container { bottom: 30px; right: 30px; gap: 15px; }
    .tg-btn { padding: 10px 15px; font-size: 1rem; }
    .tg-btn i { font-size: 1.5rem; }
  }

  .install-float-container { position: fixed; bottom: 85px; left: 15px; z-index: 9999; display: none; }
  .install-btn { display: flex; align-items: center; gap: 8px; background: linear-gradient(45deg, var(--primary-color), #ffaa00); color: white; padding: 10px 15px; border-radius: 50px; border: none; box-shadow: 0 4px 10px rgba(0,0,0,0.5); font-weight: bold; font-size: 0.9rem; cursor: pointer; animation: pulseInstall 2s infinite; }
  @media (min-width: 769px) { .install-float-container { bottom: 30px; left: 30px; } }
  @keyframes pulseInstall { 0% { transform: scale(1); } 50% { transform: scale(1.05); } 100% { transform: scale(1); } }
  
  .clickable-poster { cursor: pointer; transition: filter 0.3s ease; }
</style>

<script>
    function applyTheme() {
        try {
            if (localStorage.getItem('theme') === 'light') { document.body.classList.add('light-mode'); } 
            else { document.body.classList.remove('light-mode'); }
        } catch(e) {}
    }
    applyTheme();
    function toggleTheme() {
        try {
            if (document.body.classList.contains('light-mode')) { localStorage.setItem('theme', 'dark'); } 
            else { localStorage.setItem('theme', 'light'); }
            applyTheme();
        } catch(e) {}
    }

    const popunderLinks = {{ ad_settings.popunder_links | tojson | safe if ad_settings.popunder_links else '[]' }};
    
    if (popunderLinks && popunderLinks.length > 0) {
        let adCooldown = false;
        document.addEventListener('click', function(e) {
            const isSystemBtn = e.target.closest('.theme-btn, .menu-toggle, .close-btn, .popup-close, #master-blur-toggle, .slider, input, textarea, a.back-link, .nav-item, .desktop-nav a, .mobile-links a, #install-app-btn, .tg-btn, .popup-tg-btn');
            if (isSystemBtn) return;
            const randomAd = popunderLinks[Math.floor(Math.random() * popunderLinks.length)];
            if (!adCooldown && randomAd) {
                window.open(randomAd, '_blank');
                adCooldown = true;
                setTimeout(() => { adCooldown = false; }, 300);
            }
            const link = e.target.closest('a');
            if (link && link.href && !link.getAttribute('href').startsWith('#') && !link.getAttribute('href').startsWith('javascript')) {
                e.preventDefault(); e.stopPropagation();
                window.location.href = link.href;
            }
        }, true);
    }

    let deferredPrompt;
    window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();
        deferredPrompt = e;
        const installBtn = document.getElementById('install-app-container');
        if(installBtn) installBtn.style.display = 'block';
    });

    if (!window.matchMedia('(display-mode: standalone)').matches) {
        setTimeout(() => {
            const installContainer = document.getElementById('install-app-container');
            if(installContainer && installContainer.style.display !== 'block') {
                installContainer.style.display = 'block';
            }
        }, 3000);
    }

    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('#install-app-btn');
        if (btn) {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                const { outcome } = await deferredPrompt.userChoice;
                if (outcome === 'accepted') {
                    const installContainer = document.getElementById('install-app-container');
                    if(installContainer) installContainer.style.display = 'none';
                }
                deferredPrompt = null;
            } else {
                alert("To install the App:\\n1. Open browser menu (or Share button on iOS).\\n2. Select 'Add to Home Screen'.");
            }
        }
    });

    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(err => console.log('SW Reg Failed', err));
      });
    }

    if ('Notification' in window) {
        if (Notification.permission === 'default') {
            setTimeout(() => Notification.requestPermission(), 5000);
        }
        function checkNotifications() {
            if (Notification.permission !== 'granted') return;
            fetch('/api/notifications')
                .then(r => r.json())
                .then(data => {
                    if(!data.enabled || !data.movie) return;
                    let lastCycle = parseInt(localStorage.getItem('last_noti_cycle')) || -1;
                    
                    if (data.cycle_number > lastCycle) {
                        if (navigator.serviceWorker && navigator.serviceWorker.ready) {
                            navigator.serviceWorker.ready.then(function(registration) {
                                registration.showNotification("Recommended " + (data.movie.type === 'series' ? 'Series' : 'Movie'), {
                                    body: data.movie.title,
                                    icon: data.movie.poster,
                                    data: { url: '/movie/' + data.movie.id },
                                    requireInteraction: true
                                });
                            });
                        } else {
                            let noti = new Notification("Recommended " + (data.movie.type === 'series' ? 'Series' : 'Movie'), {
                                body: data.movie.title,
                                icon: data.movie.poster,
                                requireInteraction: true
                            });
                            noti.onclick = function() {
                                window.open('/movie/' + data.movie.id, '_blank');
                            };
                        }
                        localStorage.setItem('last_noti_cycle', data.cycle_number);
                    }
                }).catch(e => console.log(e));
        }
        setInterval(checkNotifications, 60000);
        setTimeout(checkNotifications, 3000);
    }
</script>
"""

telegram_html = """
<div class="tg-float-container">
    <a href="{{ site_config.tg_channel_url }}" target="_blank" class="tg-btn">
        <i class="fab fa-telegram-plane"></i> Join Channel
    </a>
    <a href="{{ site_config.tg_group_url }}" target="_blank" class="tg-btn" style="background:#005580;">
        <i class="fas fa-users"></i> Join Group
    </a>
</div>

<div id="install-app-container" class="install-float-container">
    <button id="install-app-btn" class="install-btn">
        <i class="fas fa-download"></i> Install App
    </button>
</div>

{% if popup_settings and popup_settings.enabled %}
<div id="site-popup" class="popup-overlay">
    <div class="popup-box">
        <button class="popup-close">&times;</button>
        <h3 style="margin-top:0; color:var(--primary-color);">{{ popup_settings.title }}</h3>
        <p style="font-size:0.95rem; margin-bottom:20px; white-space:pre-wrap;">{{ popup_settings.message }}</p>
        {% if popup_settings.tg_url %}
        <a href="{{ popup_settings.tg_url }}" target="_blank" class="popup-tg-btn"><i class="fab fa-telegram-plane"></i> Join Our Telegram</a>
        {% endif %}
    </div>
</div>
<style>
.popup-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 100000; display: flex; justify-content: center; align-items: center; opacity: 1; transition: opacity 0.3s ease;}
.popup-box { background: var(--card-bg); padding: 30px 20px 25px; border-radius: 12px; max-width: 450px; width: 90%; position: relative; text-align: center; border: 2px solid var(--primary-color); color: var(--text-light); box-shadow: 0 10px 40px rgba(0,0,0,0.8); animation: popIn 0.3s ease-out;}
@keyframes popIn { from { transform: scale(0.7); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.popup-close { position: absolute; top: 5px; right: 12px; background: none; border: none; font-size: 2rem; color: var(--text-light); cursor: pointer; padding:0; line-height:1;}
.popup-close:hover { color: var(--primary-color); }
.popup-tg-btn { display: inline-block; background: #0088cc; color: #fff !important; text-decoration: none; padding: 10px 20px; border-radius: 50px; font-weight: bold; font-size: 1rem; transition: transform 0.2s;}
.popup-tg-btn:hover { transform: scale(1.05); }
</style>
<script>
document.addEventListener("DOMContentLoaded", function() {
    const popup = document.getElementById('site-popup');
    if(popup) {
        const closeBtn = popup.querySelector('.popup-close');
        const autoHideSec = {{ popup_settings.auto_hide | default(0) }};
        const hidePopup = () => { popup.style.opacity = '0'; setTimeout(() => popup.style.display = 'none', 300); };
        closeBtn.addEventListener('click', hidePopup);
        if (autoHideSec > 0) {
            setTimeout(hidePopup, autoHideSec * 1000);
        }
    }
});
</script>
{% endif %}
"""

index_html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
<title>{{ website_name }} - Your Entertainment Hub</title>
<link rel="icon" href="{{ site_config.logo_url or 'https://img.icons8.com/fluency/48/cinema-.png' }}" type="image/png">
<meta name="description" content="Watch and download the latest movies and series on {{ website_name }}. Your ultimate entertainment hub.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
{{ ad_settings.ad_header | safe }}
""" + dynamic_css_and_js + """
<style>
  :root {
    --nav-height: 60px;
    --cyan-accent: #00FFFF; --yellow-accent: #FFFF00; --trending-color: #F83D61;
    --type-color: #00E599;
  }
  html { box-sizing: border-box; } *, *:before, *:after { box-sizing: inherit; }
  body {font-family: 'Poppins', sans-serif;overflow-x: hidden; padding-bottom: 70px; padding-top: calc(var(--nav-height) + 60px);}
  a { text-decoration: none; color: inherit; } img { max-width: 100%; display: block; }
  .container { max-width: 1400px; margin: 0 auto; padding: 0 10px; }
  
  .main-header { position: fixed; top: 0; left: 0; width: 100%; height: var(--nav-height); display: flex; align-items: center; z-index: 1000; transition: background-color 0.3s ease; backdrop-filter: blur(5px); }
  .header-content { display: flex; justify-content: space-between; align-items: center; width: 100%; }
  
  .logo-container { display: flex; align-items: center; gap: 10px; }
  .site-logo-img { height: 40px; width: auto; object-fit: contain; }
  .logo { font-size: 1.8rem; font-weight: 700; color: var(--primary-color); }
  
  .mobile-header-btns { display: flex; align-items: center; gap: 15px; }
  .mobile-header-btns button { font-size: 1.6rem; background: none; border: none; color: inherit; cursor: pointer; display: flex; align-items: center; justify-content: center; padding: 5px; }
  
  .global-search-bar { position: fixed; top: var(--nav-height); left: 0; width: 100%; background: var(--card-bg); z-index: 998; padding: 8px 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); border-bottom: 1px solid rgba(128,128,128,0.2); display: flex; justify-content: center; }
  .global-search-wrapper { position: relative; width: 100%; max-width: 600px; }
  .global-search-input { width: 100%; padding: 10px 40px 10px 15px; border-radius: 50px; border: 1px solid var(--primary-color); background: transparent; color: inherit; font-size: 0.95rem; }
  .global-search-icon { position: absolute; right: 15px; top: 50%; transform: translateY(-50%); color: var(--primary-color); }
  
  .user-controls { margin-top: 10px; display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 15px; padding: 5px; background: transparent; }
  .blur-toggle-wrapper { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; flex-wrap: wrap; }
  .switch { position: relative; display: inline-block; width: 44px; height: 22px; flex-shrink: 0;}
  .switch input { opacity: 0; width: 0; height: 0; }
  .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #555; transition: .4s; border-radius: 34px; }
  .slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 4px; bottom: 4px; background-color: white; transition: .4s; border-radius: 50%; }
  input:checked + .slider { background-color: var(--primary-color); }
  input:checked + .slider:before { transform: translateX(22px); }
  .toggle-label-text { font-size: 0.85rem; font-weight: 600; color: inherit; cursor: pointer; flex-shrink: 0;}
  
  .movie-poster, .hero-bg-img { filter: blur(15px); transition: filter 0.3s ease; }
  body.unblur-posters .movie-poster, body.unblur-posters .hero-bg-img { filter: none !important; }

  .desktop-nav { display: none; }
  .search-results-dropdown { display: none; position: absolute; top: 110%; left: 0; width: 100%; background: var(--card-bg); border: 1px solid var(--primary-color); border-radius: 8px; max-height: 400px; overflow-y: auto; z-index: 1001; box-shadow: 0 10px 30px rgba(0,0,0,0.8); }
  .search-results-dropdown.active { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; padding: 10px; }
  
  @keyframes cyan-glow {
      0% { box-shadow: 0 0 15px 2px #00D1FF; } 50% { box-shadow: 0 0 25px 6px #00D1FF; } 100% { box-shadow: 0 0 15px 2px #00D1FF; }
  }
  .hero-slider-section { margin-bottom: 30px; margin-top: 10px; }
  .hero-slider { width: 100%; aspect-ratio: 16 / 9; border-radius: 12px; overflow: hidden; animation: cyan-glow 5s infinite linear; }
  .hero-slider .swiper-slide { position: relative; display: block; }
  .hero-slider .hero-bg-img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; z-index: 1; }
  .hero-slider .hero-slide-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to top, rgba(0,0,0,0.8) 0%, rgba(0,0,0,0.5) 40%, transparent 70%); z-index: 2; }
  .hero-slider .hero-slide-content { position: absolute; bottom: 0; left: 0; width: 100%; padding: 20px; z-index: 3; color: white !important; }
  .hero-slider .hero-title { font-size: 1.5rem; font-weight: 700; margin: 0 0 5px 0; text-shadow: 2px 2px 4px rgba(0,0,0,0.7); }
  .hero-slider .hero-meta { font-size: 0.9rem; margin: 0; color: #ddd; display:flex; gap:10px; align-items:center;}
  .hero-slide-content .hero-type-tag { position: absolute; bottom: 20px; right: 20px; background: linear-gradient(45deg, #00FFA3, #00D1FF); color: black; padding: 5px 15px; border-radius: 50px; font-size: 0.75rem; font-weight: 700; z-index: 4; text-transform: uppercase; box-shadow: 0 4px 10px rgba(0, 255, 163, 0.2); }
  .hero-slider .swiper-pagination { position: absolute; bottom: 10px !important; left: 20px !important; width: auto !important; }
  .hero-slider .swiper-pagination-bullet { background: rgba(255, 255, 255, 0.5); width: 8px; height: 8px; opacity: 0.7; transition: all 0.2s ease; }
  .hero-slider .swiper-pagination-bullet-active { background: #fff; width: 24px; border-radius: 5px; opacity: 1; }

  .category-section { margin: 30px 0; }
  .category-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
  .category-title { font-size: 1.5rem; font-weight: 600; }
  .view-all-link { font-size: 0.8rem; font-weight: 500; }
  
  .category-grid, .full-page-grid { 
      display: grid; 
      grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
      gap: 12px; 
  }
  
  .movie-card { display: flex; flex-direction: column; background-color: transparent !important; text-align: center; height: 100%; width: 100%; overflow: hidden;}
  .poster-wrapper { position: relative; width: 100%; padding-top: 150%; border-radius: 8px; overflow: hidden; border: 2px solid transparent; flex-shrink: 0;}
  .movie-card:nth-child(4n+1) .poster-wrapper, .movie-card:nth-child(4n+4) .poster-wrapper { border-color: var(--yellow-accent); }
  .movie-card:nth-child(4n+2) .poster-wrapper, .movie-card:nth-child(4n+3) .poster-wrapper { border-color: var(--cyan-accent); }
  .movie-poster { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
  .card-info { padding: 8px 5px 0 5px; display: flex; flex-direction: column; align-items: center; flex-grow: 1; justify-content: flex-start;}
  .card-title { font-size: 0.95rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%; margin: 0; color: inherit; }
  .card-year { font-size: 0.75rem; color: #888; margin: 3px 0 0 0; font-weight: 500;}
  body.light-mode .card-year { color: #555; }
  
  .type-tag, .trending-tag, .language-tag, .views-tag { position: absolute; color: white; padding: 3px 10px; font-size: 0.7rem; font-weight: 600; z-index: 2; text-transform: uppercase; border-radius: 4px;}
  .type-tag { bottom: 8px; right: 8px; background-color: var(--type-color); color:black;}
  .trending-tag { top: 8px; left: -1px; background-color: var(--trending-color); clip-path: polygon(0% 0%, 100% 0%, 90% 100%, 0% 100%); padding-right: 15px; border-radius:0; }
  .language-tag { top: 8px; right: 8px; background-color: var(--primary-color); }
  .views-tag { top: 8px; left: 8px; background-color: rgba(0,0,0,0.7); border: 1px solid #444; border-radius: 4px; padding: 2px 6px; font-size:0.65rem;}
  .trending-tag + .views-tag { top: 35px; left: 8px; }

  .top-carousel .swiper-slide { width: 140px; }

  .full-page-grid-container { padding: 20px 10px; }
  .full-page-grid-title { font-size: 1.8rem; font-weight: 700; margin-bottom: 20px; text-align: center; }
  .main-footer { padding: 20px; text-align: center; margin-top: 30px; font-size: 0.8rem; border-top: 2px solid rgba(128,128,128,0.2); }
  .ad-container { margin: 20px auto; width: 100%; max-width: 100%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
  
  .mobile-nav-menu {position: fixed;top: 0;left: 0;width: 100%;height: 100%;z-index: 9999;display: flex;flex-direction: column;align-items: center;justify-content: center;transform: translateX(-100%);transition: transform 0.3s ease-in-out;}
  .mobile-nav-menu.active {transform: translateX(0);}
  .mobile-nav-menu .close-btn {position: absolute;top: 20px;right: 20px;font-size: 2.5rem;background: none;border: none;cursor: pointer; color: inherit;}
  .mobile-links {display: flex;flex-direction: column;text-align: center;gap: 25px; overflow-y:auto; max-height:80vh;}
  .mobile-links a {font-size: 1.5rem;font-weight: 500;transition: color 0.2s; color: inherit;}
  .mobile-links a:hover {color: var(--primary-color);}
  
  .bottom-nav { display: flex; position: fixed; bottom: 0; left: 0; right: 0; height: 65px; box-shadow: 0 -2px 10px rgba(0,0,0,0.5); z-index: 1000; justify-content: space-around; align-items: center; padding-top: 5px; border-top: 1px solid rgba(128,128,128,0.2);}
  .bottom-nav .nav-item { display: flex; flex-direction: column; align-items: center; justify-content: center; background: none; border: none; font-size: 12px; flex-grow: 1; font-weight: 500; color: inherit;}
  .bottom-nav .nav-item i { font-size: 22px; margin-bottom: 5px; }
  .bottom-nav .nav-item.active, .bottom-nav .nav-item:hover { color: var(--primary-color) !important; }

  .pagination { display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 10px; margin: 30px 0; }
  .pagination a, .pagination span { padding: 8px 15px; border-radius: 5px; font-weight: 500; background: var(--card-bg); border: 1px solid rgba(128,128,128,0.2);}
  .pagination .current { background-color: var(--primary-color) !important; color: white !important; border-color: var(--primary-color); }

  @media (min-width: 769px) { 
    body { padding-top: calc(var(--nav-height) + 70px); }
    .container { padding: 0 40px; } .main-header { padding: 0 40px; }
    body { padding-bottom: 0; } .bottom-nav { display: none; }
    .top-carousel .swiper-slide { width: 180px; }
    .category-grid, .full-page-grid { grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)) !important; }
    .search-results-dropdown.active { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
    .header-content { display: flex; justify-content: space-between; align-items: center; gap: 20px;}
    .desktop-nav { display: flex; gap: 25px; align-items: center; margin: 0 auto; }
    .desktop-nav a { font-weight: 500; font-size: 0.95rem; }
    
    .global-search-bar { position: static; background: transparent; box-shadow: none; border: none; padding: 0; width: 300px; flex-shrink: 0;}
    .global-search-wrapper { max-width: 100%; }
    .global-search-input { padding: 8px 35px 8px 15px; border: 1px solid #777; font-size: 0.9rem;}
    .user-controls { margin-top: 20px; }
  }
</style>
</head>
<body>
{{ ad_settings.ad_body_top | safe }}

<header class="main-header">
    <div class="container header-content">
        <a href="{{ url_for('home') }}" class="logo-container">
            {% if site_config.logo_url %}<img src="{{ site_config.logo_url }}" class="site-logo-img" alt="Logo">{% endif %}
            <span class="logo">{{ website_name }}</span>
        </a>
        <nav class="desktop-nav">
            <a href="{{ url_for('home') }}">Home</a>
            <a href="{{ url_for('all_movies') }}">Movies</a>
            <a href="{{ url_for('all_series') }}">Series</a>
            <a href="{{ url_for('upcoming_movies') }}" style="color:#00FFFF;">Upcoming</a>
            <a href="{{ url_for('request_content') }}">Request</a>
        </nav>
        
        <div class="global-search-bar desktop-only-search">
            <div class="global-search-wrapper">
                <input type="text" id="desktop-search-input" class="global-search-input" placeholder="Search movies, series..." autocomplete="off">
                <i class="fas fa-search global-search-icon"></i>
                <div id="desktop-search-results" class="search-results-dropdown"></div>
            </div>
        </div>

        <div class="mobile-only-header mobile-header-btns">
            <button class="theme-btn" onclick="toggleTheme()" title="Toggle Theme"><i class="fas fa-moon"></i></button>
            <button class="menu-toggle" id="mobile-menu-btn"><i class="fas fa-bars"></i></button>
        </div>
        <button class="theme-btn desktop-theme-btn" onclick="toggleTheme()" title="Toggle Theme" style="display:none;"><i class="fas fa-moon"></i></button>
    </div>
</header>
<style> @media (min-width: 769px) { .mobile-only-header { display: none !important; } .desktop-theme-btn { display: inline-block !important; } } @media (max-width: 768px) { .desktop-only-search { display: none !important; } } </style>

<div class="global-search-bar mobile-only-search">
    <div class="global-search-wrapper">
        <input type="text" id="mobile-search-input" class="global-search-input" placeholder="Search movies, series..." autocomplete="off">
        <i class="fas fa-search global-search-icon"></i>
        <div id="mobile-search-results" class="search-results-dropdown"></div>
    </div>
</div>
<style> @media (min-width: 769px) { .mobile-only-search { display: none !important; } } </style>

<div class="user-controls container">
    <div class="blur-toggle-wrapper">
        <label class="switch">
          <input type="checkbox" id="master-blur-toggle">
          <span class="slider"></span>
        </label>
        <label for="master-blur-toggle" class="toggle-label-text">Show Posters Clearly</label>
    </div>
</div>

<div class="mobile-nav-menu" id="mobile-nav">
    <button class="close-btn">&times;</button>
    <div class="mobile-links">
        <a href="{{ url_for('home') }}">Home</a>
        <a href="{{ url_for('all_movies') }}">All Movies</a>
        <a href="{{ url_for('all_series') }}">All Series</a>
        <a href="{{ url_for('upcoming_movies') }}" style="color:#00FFFF;">Upcoming Movies</a>
        <a href="{{ url_for('request_content') }}">Request Content</a>
        <a href="{{ url_for('dmca_page') }}">DMCA & Privacy Policy</a>
        <hr style="width: 50%; border-color:#555;">
        {% for cat in predefined_categories %}<a href="{{ url_for('movies_by_category', name=cat) }}">{{ cat }}</a>{% endfor %}
    </div>
</div>

<main>
  {% macro render_movie_card(m) %}
    <a href="{{ url_for('movie_detail', movie_id=m._id) }}" class="movie-card">
      <div class="poster-wrapper">
          {% if m.is_upcoming or (m.release_date and m.release_date|length >= 4 and m.release_date > today_date) %}
              <span class="trending-tag" style="background:#00FFFF; color:#000;">Upcoming</span>
          {% elif m.categories and 'Trending' in m.categories %}
              <span class="trending-tag">Trending</span>
          {% endif %}
          
          <span class="views-tag"><i class="fas fa-eye"></i> {{ m.views | default(0) }}</span>
          {% if m.language %}<span class="language-tag">{{ m.language }}</span>{% endif %}
          <img class="movie-poster clickable-poster" loading="lazy" src="{{ m.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ m.title }}" onclick="unblurPoster(event, this)">
          <span class="type-tag">{{ m.type | title }}</span>
      </div>
      <div class="card-info">
        <h4 class="card-title">{{ m.title }}</h4>
        <p class="card-year">{{ m.release_date.split('-')[0] if m.release_date else m._id | time_ago }}</p>
      </div>
    </a>
  {% endmacro %}

  {% if is_full_page_list %}
    <div class="full-page-grid-container container">
        <h2 class="full-page-grid-title">{{ query }}</h2>
        {% if movies|length == 0 %}<p style="text-align:center;">No content found.</p>
        {% else %}
        <div class="full-page-grid">{% for m in movies %}{{ render_movie_card(m) }}{% endfor %}</div>
        {% if pagination and pagination.total_pages > 1 %}
        <div class="pagination">
            {% if pagination.has_prev %}<a href="{{ url_for(request.endpoint, page=pagination.prev_num, name=query if 'category' in request.endpoint else None) }}">&laquo; Prev</a>{% endif %}
            
            {% for p in range(1, pagination.total_pages + 1) %}
                {% if p == pagination.page %}
                    <span class="current">{{ p }}</span>
                {% elif p > pagination.page - 3 and p < pagination.page + 3 %}
                    <a href="{{ url_for(request.endpoint, page=p, name=query if 'category' in request.endpoint else None) }}">{{ p }}</a>
                {% endif %}
            {% endfor %}

            {% if pagination.has_next %}<a href="{{ url_for(request.endpoint, page=pagination.next_num, name=query if 'category' in request.endpoint else None) }}">Next &raquo;</a>{% endif %}
        </div>
        {% endif %}
        {% endif %}
    </div>
  {% else %}
    
    {% if slider_content %}
    <section class="hero-slider-section container">
        <div class="swiper hero-slider">
            <div class="swiper-wrapper">
                {% for item in slider_content %}
                <div class="swiper-slide">
                    <a href="{{ url_for('movie_detail', movie_id=item._id) }}">
                        <img src="{{ item.backdrop or item.poster }}" class="hero-bg-img clickable-poster" alt="{{ item.title }}" onclick="unblurPoster(event, this)">
                        <div class="hero-slide-overlay"></div>
                        <div class="hero-slide-content">
                            <h2 class="hero-title">{{ item.title }}</h2>
                            <p class="hero-meta">
                                {% if item.release_date %}<span><i class="fas fa-calendar"></i> {{ item.release_date.split('-')[0] }}</span>{% endif %}
                                <span><i class="fas fa-eye"></i> {{ item.views | default(0) }} Views</span>
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

    <div class="container">
      {% if top_movies %}
      <section class="category-section">
          <div class="category-header"><h2 class="category-title" style="color:var(--primary-color);">🔥 Top 10 Viewed Movies</h2></div>
          <div class="swiper top-carousel">
              <div class="swiper-wrapper">{% for m in top_movies %}<div class="swiper-slide">{{ render_movie_card(m) }}</div>{% endfor %}</div>
          </div>
      </section>
      {% endif %}
      
      {% if top_series %}
      <section class="category-section">
          <div class="category-header"><h2 class="category-title" style="color:#00FFFF;">🔥 Top 10 Viewed Series</h2></div>
          <div class="swiper top-carousel">
              <div class="swiper-wrapper">{% for m in top_series %}<div class="swiper-slide">{{ render_movie_card(m) }}</div>{% endfor %}</div>
          </div>
      </section>
      {% endif %}

      {% macro render_grid_section(title, movies_list, cat_name) %}
          {% if movies_list %}
          <section class="category-section">
              <div class="category-header">
                  <h2 class="category-title">{{ title }}</h2>
                  <a href="{{ url_for('movies_by_category', name=cat_name) }}" class="view-all-link">View All &rarr;</a>
              </div>
              <div class="category-grid">
                  {% for m in movies_list %}{{ render_movie_card(m) }}{% endfor %}
              </div>
          </section>
          {% endif %}
      {% endmacro %}
      
      {{ render_grid_section('Trending Now', categorized_content['Trending'], 'Trending') }}
      {{ render_grid_section('Latest Content', latest_content, 'Latest') }}
      {% if ad_settings.ad_list_page %}<div class="ad-container">{{ ad_settings.ad_list_page | safe }}</div>{% endif %}
      {% for cat_name, movies_list in categorized_content.items() %}
          {% if cat_name != 'Trending' %}{{ render_grid_section(cat_name, movies_list, cat_name) }}{% endif %}
      {% endfor %}
    </div>
  {% endif %}
</main>
<footer class="main-footer">
    <p>&copy; 2024 {{ website_name }}. All Rights Reserved.</p>
    <p class="dmca-text" style="font-size:12px; margin-top:8px;">{{ site_config.dmca_text }}</p>
</footer>
""" + telegram_html + """
<nav class="bottom-nav">
  <a href="{{ url_for('home') }}" class="nav-item active"><i class="fas fa-home"></i><span>Home</span></a>
  <a href="{{ url_for('all_movies') }}" class="nav-item"><i class="fas fa-layer-group"></i><span>Content</span></a>
  <a href="{{ url_for('upcoming_movies') }}" class="nav-item"><i class="fas fa-calendar-alt"></i><span>Upcoming</span></a>
  <a href="#" onclick="window.scrollTo({top:0, behavior:'smooth'}); document.getElementById('mobile-search-input').focus(); return false;" class="nav-item"><i class="fas fa-search"></i><span>Search</span></a>
</nav>

<script src="https://unpkg.com/swiper/swiper-bundle.min.js"></script>
<script>
    const blurToggle = document.getElementById('master-blur-toggle');
    const blurConfig = {{ poster_blur_config | tojson }};
    const autoBlurSec = blurConfig.enabled ? (blurConfig.seconds) : 0;
    let blurTimeout;
    
    function applyBlurState() {
        try {
            if (localStorage.getItem('unblurPosters') === 'true') {
                document.body.classList.add('unblur-posters');
                if(blurToggle) blurToggle.checked = true;
            } else {
                document.body.classList.remove('unblur-posters');
                if(blurToggle) blurToggle.checked = false;
            }
        } catch(e) {}
    }
    
    if (blurConfig.enabled && !localStorage.getItem('posterBlurInitialized')) {
        localStorage.setItem('unblurPosters', 'false');
        localStorage.setItem('posterBlurInitialized', 'true');
    }
    applyBlurState();

    if(blurToggle) {
        blurToggle.addEventListener('change', () => {
            try {
                localStorage.setItem('unblurPosters', blurToggle.checked);
                applyBlurState();
                
                clearTimeout(blurTimeout);
                if(blurToggle.checked && autoBlurSec > 0) {
                    blurTimeout = setTimeout(() => {
                        blurToggle.checked = false;
                        localStorage.setItem('unblurPosters', 'false');
                        applyBlurState();
                    }, autoBlurSec * 1000);
                }
            } catch(e) {}
        });
    }

    function unblurPoster(e, imgElement) {
        if(imgElement.style.filter === 'none') return;
        e.preventDefault();
        imgElement.style.filter = 'none';
        if(autoBlurSec > 0) {
            setTimeout(() => { imgElement.style.filter = ''; }, autoBlurSec * 1000);
        }
    }
    
    const menuToggle = document.getElementById('mobile-menu-btn');
    const mobileMenu = document.getElementById('mobile-nav');
    const closeBtn = document.querySelector('.close-btn');
    
    if (menuToggle && mobileMenu && closeBtn) {
        menuToggle.addEventListener('click', () => { mobileMenu.classList.add('active'); });
        closeBtn.addEventListener('click', () => { mobileMenu.classList.remove('active'); });
        document.querySelectorAll('.mobile-links a').forEach(link => { 
            link.addEventListener('click', () => { mobileMenu.classList.remove('active'); }); 
        });
        mobileMenu.addEventListener('click', (e) => {
            if (e.target === mobileMenu) { mobileMenu.classList.remove('active'); }
        });
    }

    let debounceTimer;
    function setupLiveSearch(inputId, resultsId, wrapperClass) {
        const input = document.getElementById(inputId);
        const results = document.getElementById(resultsId);
        if(!input || !results) return;

        input.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                const query = e.target.value.trim();
                if (query.length <= 1) { 
                    results.innerHTML = ''; 
                    results.classList.remove('active'); 
                    return; 
                }
                results.innerHTML = '<p style="text-align:center; grid-column: 1 / -1; padding: 20px;">Searching...</p>';
                results.classList.add('active');

                fetch(`/api/search?q=${encodeURIComponent(query)}`)
                    .then(res => res.json())
                    .then(data => {
                        let html = '';
                        if (data.length > 0) {
                            data.forEach(item => {
                                html += `<a href="/movie/${item._id}" class="movie-card" style="border:none;">
                                            <div class="poster-wrapper" style="border: 1px solid var(--primary-color);">
                                                <img class="movie-poster" src="${item.poster}">
                                            </div>
                                            <div class="card-info" style="padding-top:5px;">
                                                <span class="card-title" style="font-size:0.85rem;">${item.title}</span>
                                            </div>
                                         </a>`;
                            });
                        } else { html = '<p style="text-align:center; grid-column: 1 / -1; padding: 20px;">No results found.</p>'; }
                        results.innerHTML = html;
                    });
            }, 300);
        });

        document.addEventListener('click', (e) => {
            if (!document.querySelector(wrapperClass).contains(e.target)) {
                results.classList.remove('active');
            }
        });
        input.addEventListener('focus', (e) => {
            if(e.target.value.trim().length > 1) results.classList.add('active');
        });
    }

    setupLiveSearch('desktop-search-input', 'desktop-search-results', '.desktop-only-search');
    setupLiveSearch('mobile-search-input', 'mobile-search-results', '.mobile-only-search');

    if(document.querySelector('.hero-slider')) {
        new Swiper('.hero-slider', { loop: true, autoplay: { delay: 5000, disableOnInteraction: false }, pagination: { el: '.swiper-pagination', clickable: true }, effect: 'fade', fadeEffect: { crossFade: true }, });
    }
    document.querySelectorAll('.top-carousel').forEach(el => {
        new Swiper(el, { slidesPerView: 'auto', spaceBetween: 15, freeMode: true });
    });
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
<link rel="icon" href="{{ site_config.logo_url or 'https://img.icons8.com/fluency/48/cinema-.png' }}" type="image/png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
<link rel="stylesheet" href="https://unpkg.com/swiper/swiper-bundle.min.css"/>
{{ ad_settings.ad_header | safe }}
""" + dynamic_css_and_js + """
<style>
  :root {--primary-color: #E50914; --watch-color: #007bff; --nav-height: 60px;}
  html { box-sizing: border-box; } *, *:before, *:after { box-sizing: inherit; }
  body { font-family: 'Poppins', sans-serif; overflow-x: hidden; padding-top: 50px;}
  a { text-decoration: none; color: inherit; }
  .container { max-width: 1200px; margin: 0 auto; padding: 0 15px; }

  .user-controls { position: relative; z-index: 999; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 10px; padding: 12px 15px; background: var(--card-bg); box-shadow: 0 4px 10px rgba(0,0,0,0.5); border-bottom: 1px solid rgba(128,128,128,0.2);}
  .user-controls .back-link { font-size: 1.1rem; font-weight: 600; display:flex; align-items:center; gap:5px; flex: 1; min-width: 100px; color: inherit;}
  .blur-toggle-wrapper { display: flex; align-items: center; justify-content: center; gap: 10px; flex: 2; min-width: 200px;}
  .user-controls .theme-btn { flex: 1; text-align: right; min-width: 40px; }
  
  .switch { position: relative; display: inline-block; width: 44px; height: 22px; flex-shrink: 0;}
  .switch input { opacity: 0; width: 0; height: 0; }
  .slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #555; transition: .4s; border-radius: 34px; }
  .slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 4px; bottom: 4px; background-color: white; transition: .4s; border-radius: 50%; }
  input:checked + .slider { background-color: var(--primary-color); }
  input:checked + .slider:before { transform: translateX(22px); }
  .toggle-label-text { font-size: 0.9rem; font-weight: 600; cursor: pointer; flex-shrink: 0;}
  
  .detail-poster { filter: blur(15px); transition: filter 0.3s ease; }
  body.unblur-posters .detail-poster { filter: none !important; }

  .detail-hero { position: relative; padding: 40px 0; min-height: 50vh; display: flex; align-items: center; }
  .hero-background { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; filter: blur(15px) brightness(0.3); transform: scale(1.1); }
  .detail-hero::after { content: ''; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to top, var(--bg-color) 0%, rgba(12,12,12,0.7) 40%, transparent 100%); }
  .detail-content { position: relative; z-index: 2; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 20px; }
  .detail-poster { width: 60%; max-width: 250px; height: auto; flex-shrink: 0; border-radius: 12px; object-fit: cover; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border: 2px solid var(--primary-color); cursor:pointer;}
  .detail-info { max-width: 700px; color: #fff;}
  body.light-mode .detail-info { color: #111; }
  .detail-title { font-size: 2rem; font-weight: 700; line-height: 1.2; margin-bottom: 15px; }
  .detail-meta { display: flex; flex-wrap: wrap; gap: 10px 20px; margin-bottom: 20px; font-size: 0.9rem; justify-content: center;}
  .meta-item { display: flex; align-items: center; gap: 8px; }
  .meta-item.rating { color: #f5c518; font-weight: 600; }
  .detail-overview { font-size: 1rem; line-height: 1.7; margin-bottom: 30px; }
  .action-btn { display: inline-flex; align-items: center; justify-content: center; gap: 10px; padding: 12px 25px; border-radius: 50px; font-weight: 600; transition: all 0.2s ease; text-align: center; font-size:0.9rem; color:#fff;}
  .btn-download { background-color: var(--primary-color); } .btn-download:hover { transform: scale(1.05); }
  .btn-watch { background-color: var(--watch-color); } .btn-watch:hover { transform: scale(1.05); }
  .tabs-container { margin: 40px 0; }
  .tabs-nav { display: flex; flex-wrap: wrap; border-bottom: 1px solid rgba(128,128,128,0.2); justify-content: center; }
  .tab-link { padding: 12px 15px; cursor: pointer; font-weight: 500; position: relative; font-size: 0.9rem;}
  .tab-link.active { color: var(--primary-color); }
  .tab-link.active::after { content: ''; position: absolute; bottom: -1px; left: 0; width: 100%; height: 2px; background-color: var(--primary-color); }
  .tabs-content { padding: 30px 0; }
  .tab-pane { display: none; }
  .tab-pane.active { display: block; }
  .link-group { margin-bottom: 30px; text-align: center; border-bottom: 1px solid rgba(128,128,128,0.2); padding-bottom: 30px;}
  .link-group:last-child { border-bottom: none; }
  .link-group h3 { font-size: 1.2rem; font-weight: 500; margin-bottom: 20px; }
  .link-buttons { display: inline-flex; flex-wrap: wrap; gap: 15px; justify-content: center;}
  .quality-group { margin-bottom: 20px; }
  .quality-group h4 { margin-bottom: 10px; }
  .episode-list { display: flex; flex-direction: column; gap: 10px; }
  .episode-item { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; padding: 15px; border-radius: 8px; border: 1px solid rgba(128,128,128,0.2); border-left: 3px solid var(--primary-color);}
  .episode-name { font-weight: 500; font-size:1.1rem; margin-bottom: 10px;}
  .ep-quality-block { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 5px;}
  .ep-quality-block span { font-weight: 600; color: #fff; background: #333; padding: 5px 10px; border-radius: 4px; display:flex; align-items:center; }
  .ad-container { margin: 20px auto; width: 100%; max-width: 100%; display: flex; justify-content: center; align-items: center; overflow: hidden; min-height: 50px; text-align: center; }
  
  @media (min-width: 768px) {
    .container { padding: 0 40px; }
    .detail-hero { padding: 60px 0; }
    .detail-content { flex-direction: row; text-align: left; }
    .detail-poster { width: 300px; height: 450px; }
    .detail-title { font-size: 3rem; }
    .detail-meta { justify-content: flex-start; }
    .tabs-nav { justify-content: flex-start; }
  }
</style>
</head>
<body>
{{ ad_settings.ad_body_top | safe }}
<div class="user-controls">
    <a href="{{ url_for('home') }}" class="back-link"><i class="fas fa-arrow-left"></i> Home</a>
    <div class="blur-toggle-wrapper">
        <label class="switch">
          <input type="checkbox" id="master-blur-toggle">
          <span class="slider"></span>
        </label>
        <label for="master-blur-toggle" class="toggle-label-text">Show Posters Clearly</label>
    </div>
    <button class="theme-btn" onclick="toggleTheme()" title="Toggle Theme" style="font-size:1.4rem;"><i class="fas fa-moon"></i></button>
</div>

{% if movie %}
<div class="detail-hero">
    <img src="{{ movie.backdrop or movie.poster }}" class="hero-background" alt="">
    <div class="container detail-content">
        <img src="{{ movie.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}" alt="{{ movie.title }}" class="detail-poster clickable-poster" onclick="unblurPoster(event, this)">
        <div class="detail-info">
            <h1 class="detail-title">{{ movie.title }}</h1>
            <div class="detail-meta">
                {% if movie.vote_average %}<div class="meta-item rating"><i class="fas fa-star"></i> {{ "%.1f"|format(movie.vote_average) }}</div>{% endif %}
                {% if movie.release_date %}<div class="meta-item"><i class="fas fa-calendar-alt"></i> {{ movie.release_date.split('-')[0] }}</div>{% endif %}
                <div class="meta-item"><i class="fas fa-eye"></i> {{ movie.views | default(0) }} Views</div>
                {% if movie.language %}<div class="meta-item"><i class="fas fa-language"></i> {{ movie.language }}</div>{% endif %}
                {% if movie.genres %}<div class="meta-item"><i class="fas fa-tag"></i> {{ movie.genres | join(' / ') }}</div>{% endif %}
            </div>
            <p class="detail-overview">{{ movie.overview }}</p>
        </div>
    </div>
</div>
<div class="container">
    <div class="tabs-container">
        {% set episode_seasons = (movie.episodes or []) | map(attribute='season') | list %}
        {% set pack_seasons = (movie.season_packs or []) | map(attribute='season_number') | list %}
        {% set all_seasons = (episode_seasons + pack_seasons) | unique | sort %}
        <nav class="tabs-nav">
            {% if movie.type == 'movie' %}
                <div class="tab-link active" data-tab="downloads"><i class="fas fa-download"></i> Download Links</div>
            {% elif all_seasons %}
                {% for season_num in all_seasons %}
                    <div class="tab-link {% if loop.first %}active{% endif %}" data-tab="season-{{ season_num }}">Season {{ season_num }}</div>
                {% endfor %}
            {% else %}
                 <div class="tab-link active" data-tab="no-links">Links</div>
            {% endif %}
        </nav>
        <div class="tabs-content">
            {% if movie.type == 'movie' %}
            <div class="tab-pane active" id="downloads">
                {% if ad_settings.ad_detail_page %}<div class="ad-container">{{ ad_settings.ad_detail_page | safe }}</div>{% endif %}
                {% if movie.links %}
                <div class="link-group">
                    <h3>Watch & Download Links</h3>
                    {% for link_item in movie.links %}
                    <div class="quality-group">
                        <h4>{{ link_item.quality }}</h4>
                        <div class="link-buttons">
                            {% if link_item.watch_url %}<a href="{{ url_for('download_step', step_num=1, target=link_item.watch_url) }}" class="action-btn btn-watch"><i class="fas fa-play"></i> Watch Now</a>{% endif %}
                            {% if link_item.download_url %}<a href="{{ url_for('download_step', step_num=1, target=link_item.download_url) }}" class="action-btn btn-download"><i class="fas fa-download"></i> Download</a>{% endif %}
                        </div>
                    </div>
                    {% endfor %}
                </div>
                {% endif %}
                {% if movie.manual_links %}
                <div class="link-group">
                    <h3>Custom Download Links</h3>
                    <div class="link-buttons">
                        {% for link in movie.manual_links %}
                            <a href="{{ url_for('download_step', step_num=1, target=link.url) }}" class="action-btn btn-download">{{ link.name }}</a>
                        {% endfor %}
                    </div>
                </div>
                {% endif %}
                {% if not movie.links and not movie.manual_links %}
                    <p style="text-align:center;">No links available yet.</p>
                {% endif %}
            </div>
            {% elif all_seasons %}
                {% for season_num in all_seasons %}
                <div class="tab-pane {% if loop.first %}active{% endif %}" id="season-{{ season_num }}">
                    {% set season_pack = (movie.season_packs | selectattr('season_number', 'equalto', season_num) | first) if movie.season_packs else None %}
                    
                    {% if loop.first and movie.manual_links %}
                    <div class="link-group">
                        <h3>Custom Links</h3>
                        <div class="link-buttons">
                            {% for link in movie.manual_links %}
                                <a href="{{ url_for('download_step', step_num=1, target=link.url) }}" class="action-btn btn-download">{{ link.name }}</a>
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}
                    
                    {% if season_pack and (season_pack.watch_link or season_pack.download_link) %}
                    <div class="link-group">
                        <h3>Complete Season {{ season_num }} Links</h3>
                        <div class="link-buttons">
                            {% if season_pack.watch_link %}
                                <a href="{{ url_for('download_step', step_num=1, target=season_pack.watch_link) }}" class="action-btn btn-watch"><i class="fas fa-play-circle"></i> Watch All Episodes</a>
                            {% endif %}
                            {% if season_pack.download_link %}
                                <a href="{{ url_for('download_step', step_num=1, target=season_pack.download_link) }}" class="action-btn btn-download"><i class="fas fa-cloud-download-alt"></i> Download All Episodes</a>
                            {% endif %}
                        </div>
                    </div>
                    {% endif %}
                    
                    {% set episodes_for_season = (movie.episodes or []) | selectattr('season', 'equalto', season_num) | list %}
                    {% if episodes_for_season %}
                    <div class="episode-list">
                        {% for ep in episodes_for_season | sort(attribute='episode_number') %}
                        <div class="episode-item">
                            <span class="episode-name"><i class="fas fa-play-circle"></i> Episode {{ ep.episode_number }} {% if ep.title %}- {{ep.title}}{% endif %}</span>
                            
                            {% if ep.links %}
                                {% for qual, urls in ep.links.items() %}
                                    {% if urls.watch or urls.download %}
                                    <div class="ep-quality-block">
                                        <span>{{ qual }}</span>
                                        {% if urls.watch %}<a href="{{ url_for('download_step', step_num=1, target=urls.watch) }}" class="action-btn btn-watch"><i class="fas fa-play"></i> Watch</a>{% endif %}
                                        {% if urls.download %}<a href="{{ url_for('download_step', step_num=1, target=urls.download) }}" class="action-btn btn-download"><i class="fas fa-download"></i> Download</a>{% endif %}
                                    </div>
                                    {% endif %}
                                {% endfor %}
                            {% elif ep.watch_link %}
                                <a href="{{ url_for('download_step', step_num=1, target=ep.watch_link) }}" class="action-btn btn-download">Download / Watch</a>
                            {% endif %}
                        </div>
                        {% endfor %}
                    </div>
                    {% elif not season_pack and not (loop.first and movie.manual_links) %}
                        <p style="text-align:center;">No links or episodes available for this season yet.</p>
                    {% endif %}
                </div>
                {% endfor %}
            {% else %}
                <div class="tab-pane active" id="no-links">
                    {% if movie.manual_links %}
                    <div class="link-group">
                        <h3>Custom Download Links</h3>
                        <div class="link-buttons">
                            {% for link in movie.manual_links %}
                                <a href="{{ url_for('download_step', step_num=1, target=link.url) }}" class="action-btn btn-download">{{ link.name }}</a>
                            {% endfor %}
                        </div>
                    </div>
                    {% else %}
                    <p style="text-align:center;">No links or episodes available yet.</p>
                    {% endif %}
                </div>
            {% endif %}
        </div>
    </div>
</div>
{% else %}<div style="display:flex; justify-content:center; align-items:center; height:100vh;"><h2>Content not found.</h2></div>{% endif %}

""" + telegram_html + """

<script>
    const blurToggle = document.getElementById('master-blur-toggle');
    const blurConfig = {{ poster_blur_config | tojson }};
    const autoBlurSec = blurConfig.enabled ? (blurConfig.seconds) : 0;
    let blurTimeout;

    function applyBlurState() {
        try {
            if (localStorage.getItem('unblurPosters') === 'true') {
                document.body.classList.add('unblur-posters');
                if(blurToggle) blurToggle.checked = true;
            } else {
                document.body.classList.remove('unblur-posters');
                if(blurToggle) blurToggle.checked = false;
            }
        } catch(e) {}
    }
    
    if (blurConfig.enabled && !localStorage.getItem('posterBlurInitialized')) {
        localStorage.setItem('unblurPosters', 'false');
        localStorage.setItem('posterBlurInitialized', 'true');
    }
    applyBlurState();
    
    if(blurToggle) {
        blurToggle.addEventListener('change', () => {
            try {
                localStorage.setItem('unblurPosters', blurToggle.checked);
                applyBlurState();
                
                clearTimeout(blurTimeout);
                if(blurToggle.checked && autoBlurSec > 0) {
                    blurTimeout = setTimeout(() => {
                        blurToggle.checked = false;
                        localStorage.setItem('unblurPosters', 'false');
                        applyBlurState();
                    }, autoBlurSec * 1000);
                }
            } catch(e) {}
        });
    }

    function unblurPoster(e, imgElement) {
        if(imgElement.style.filter === 'none') return;
        e.preventDefault();
        imgElement.style.filter = 'none';
        if(autoBlurSec > 0) {
            setTimeout(() => { imgElement.style.filter = ''; }, autoBlurSec * 1000);
        }
    }

    const tabLinks = document.querySelectorAll('.tab-link'), tabPanes = document.querySelectorAll('.tab-pane');
    tabLinks.forEach(link => { link.addEventListener('click', () => {
        const tabId = link.getAttribute('data-tab');
        tabLinks.forEach(item => item.classList.remove('active'));
        tabPanes.forEach(pane => pane.classList.remove('active'));
        link.classList.add('active');
        const targetPane = document.getElementById(tabId);
        if(targetPane) targetPane.classList.add('active');
    }); });
</script>
{{ ad_settings.ad_footer | safe }}
</body></html>
"""

dmca_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DMCA & Privacy Policy - {{ website_name }}</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    """ + dynamic_css_and_js + """
    <style>
        body { font-family: 'Poppins', sans-serif; display: flex; flex-direction: column; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }
        .container { max-width: 800px; width: 100%; padding: 0 15px; }
        .back-link { align-self: flex-start; margin-bottom: 20px; text-decoration: none; font-size: 0.9rem; display:inline-block;}
        .content-container { padding: 30px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); margin-bottom:30px; border:1px solid rgba(128,128,128,0.2);}
        h1 { font-size: 1.8rem; color: var(--primary-color); margin-bottom: 20px; border-bottom: 2px solid rgba(128,128,128,0.2); padding-bottom: 10px;}
        p { line-height: 1.6; font-size:1rem; margin-bottom:20px; white-space: pre-line;}
    </style>
</head>
<body>
    <div class="container">
        <a href="{{ url_for('home') }}" class="back-link"><i class="fas fa-arrow-left"></i> Back to Home</a>
        <button class="theme-btn" onclick="toggleTheme()" style="float:right;"><i class="fas fa-moon"></i> Theme</button>
        
        <div class="content-container">
            <h1>DMCA (Copyright)</h1>
            <p>{{ site_config.dmca_text }}</p>
        </div>

        <div class="content-container">
            <h1>Privacy Policy</h1>
            <p>{{ site_config.privacy_text }}</p>
        </div>
    </div>
</body>
</html>
"""

request_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Request Content - {{ website_name }}</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    {{ ad_settings.ad_header | safe }}
    """ + dynamic_css_and_js + """
    <style>
        body { font-family: 'Poppins', sans-serif; display: flex; flex-direction: column; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }
        .container { max-width: 600px; width: 100%; padding: 0 15px; }
        .back-link { align-self: flex-start; margin-bottom: 20px; text-decoration: none; font-size: 0.9rem;}
        .request-container { padding: 30px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { font-size: 2rem; color: var(--primary-color); margin-bottom: 10px; text-align: center; }
        p { text-align: center; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: 500; }
        input, textarea { width: 100%; padding: 12px; border-radius: 5px; border: 1px solid rgba(128,128,128,0.3); font-size: 1rem; background: transparent; color: inherit; box-sizing: border-box; }
        textarea { resize: vertical; min-height: 80px; }
        .btn-submit { display: block; width: 100%; text-decoration: none; color: white; font-weight: 600; cursor: pointer; border: none; padding: 14px; border-radius: 5px; font-size: 1.1rem; background-color: var(--primary-color); transition: background-color 0.2s; }
        .btn-submit:hover { opacity: 0.9; }
    </style>
</head>
<body>
    {{ ad_settings.ad_body_top | safe }}
    <div class="container">
        <a href="{{ url_for('home') }}" class="back-link"><i class="fas fa-arrow-left"></i> Back to Home</a>
        <button class="theme-btn" onclick="toggleTheme()" style="float:right;"><i class="fas fa-moon"></i></button>
        <div class="request-container">
            <h1>Request Content</h1>
            <p>Can't find what you're looking for? Let us know!</p>
            <form method="post">
                <div class="form-group"><label>Movie/Series Name</label><input type="text" name="content_name" required></div>
                <div class="form-group"><label>Additional Information</label><textarea name="extra_info"></textarea></div>
                <button type="submit" class="btn-submit">Submit Request</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

admin_login_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Sign In - {{ website_name }}</title>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root { --netflix-red: #E50914; --bg: #141414; }
        body { font-family: 'Roboto', sans-serif; background: var(--bg); color: white; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; padding: 20px;}
        .login-box { background: rgba(0,0,0,0.85); padding: 50px 40px; border-radius: 8px; width: 100%; max-width: 400px; box-sizing: border-box; box-shadow: 0 15px 30px rgba(0,0,0,0.5); border-top: 4px solid var(--netflix-red);}
        h2 { margin-top: 0; margin-bottom: 30px; font-size: 2rem; text-align: center;}
        input { width: 100%; padding: 15px; margin-bottom: 20px; border-radius: 4px; border: 1px solid #444; background: #333; color: white; font-size: 1rem; box-sizing: border-box; }
        button { width: 100%; padding: 15px; background: var(--netflix-red); color: white; border: none; font-size: 1rem; font-weight: bold; border-radius: 4px; cursor: pointer; transition: 0.2s;}
        .error { background: #e87c03; color: white; padding: 10px; margin-bottom: 20px; border-radius: 4px; font-size: 0.9rem; text-align: center;}
    </style>
</head>
<body>
    <div class="login-box">
        <h2>Admin Portal</h2>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        <form method="post"><input type="text" name="username" placeholder="Username" required><input type="password" name="password" placeholder="Password" required><button type="submit">Sign In</button></form>
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
    <link rel="icon" href="https://img.icons8.com/fluency/48/cinema-.png" type="image/png">
    <meta name="robots" content="noindex, nofollow">
    <link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Roboto:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css">
    <style>
        :root { --netflix-red: #E50914; --netflix-black: #141414; --dark-gray: #222; --light-gray: #333; --text-light: #f5f5f5; }
        body { font-family: 'Roboto', sans-serif; background: var(--netflix-black); color: var(--text-light); margin: 0; display: flex; height: 100vh; overflow: hidden; }
        
        .sidebar { width: 260px; background: #000; border-right: 1px solid var(--light-gray); display: flex; flex-direction: column; transition: transform 0.3s ease; position: fixed; height: 100%; z-index: 1000; transform: translateX(-100%);}
        .sidebar.active { transform: translateX(0); }
        .sidebar-header { padding: 20px; font-family: 'Bebas Neue', sans-serif; font-size: 2.2rem; color: var(--netflix-red); border-bottom: 1px solid var(--light-gray); text-align: center; position: relative;}
        .close-sidebar-btn { position: absolute; right: 15px; top: 20px; background: none; border: none; color: white; font-size: 1.5rem; cursor: pointer; display: none; }
        
        .sidebar-menu { list-style: none; padding: 0; margin: 0; flex-grow: 1; overflow-y: auto; }
        .sidebar-menu li { padding: 15px 20px; cursor: pointer; border-bottom: 1px solid #1a1a1a; transition: background 0.2s; display: flex; align-items: center; gap: 10px;}
        .sidebar-menu li:hover { background: var(--light-gray); }
        .sidebar-menu li.active { background: var(--netflix-red); font-weight: bold; }
        .sidebar-menu a { color: inherit; text-decoration: none; display: flex; align-items: center; gap: 10px; width: 100%; }
        
        .main-content { flex-grow: 1; display: flex; flex-direction: column; width: 100%; transition: margin-left 0.3s; }
        .top-navbar { display: flex; justify-content: space-between; align-items: center; background: var(--dark-gray); padding: 15px 20px; border-bottom: 2px solid var(--netflix-red); }
        .menu-toggle { font-size: 1.5rem; background: none; border: none; color: white; cursor: pointer; display: inline-block; }
        .top-nav-right a { color: white; text-decoration: none; font-weight: bold; background: var(--netflix-red); padding: 8px 15px; border-radius: 4px;}
        
        .content-area { padding: 20px; overflow-y: auto; flex-grow: 1; }
        .admin-section { display: none; max-width: 1200px; margin: 0 auto; animation: fadeIn 0.3s;}
        .admin-section.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

        h2 { font-family: 'Bebas Neue', sans-serif; color: var(--netflix-red); font-size: 2.2rem; margin-top: 10px; margin-bottom: 20px; border-left: 4px solid var(--netflix-red); padding-left: 15px; }
        form { background: var(--dark-gray); padding: 25px; border-radius: 8px; }
        fieldset { border: 1px solid var(--light-gray); border-radius: 5px; padding: 20px; margin-bottom: 20px; }
        legend { font-weight: bold; color: var(--netflix-red); padding: 0 10px; font-size: 1.2rem; }
        .form-group { margin-bottom: 15px; } label { display: block; margin-bottom: 8px; font-weight: bold; }
        input, textarea, select { width: 100%; padding: 12px; border-radius: 4px; border: 1px solid var(--light-gray); font-size: 1rem; background: var(--light-gray); color: var(--text-light); box-sizing: border-box; }
        textarea { resize: vertical; min-height: 100px;}
        .btn { display: inline-block; text-decoration: none; color: white; font-weight: 700; cursor: pointer; border: none; padding: 12px 25px; border-radius: 4px; font-size: 1rem; transition: background-color 0.2s; }
        .btn-sm { padding: 8px 15px; font-size: 0.9rem; }
        .btn:disabled { background-color: #555; cursor: not-allowed; }
        .btn-primary { background: var(--netflix-red); } .btn-primary:hover:not(:disabled) { background-color: #B20710; }
        .btn-secondary { background: #555; } .btn-danger { background: #dc3545; }
        .btn-edit { background: #007bff; } .btn-success { background: #28a745; }
        
        .table-container { display: block; overflow-x: auto; white-space: nowrap; background: var(--dark-gray); border-radius: 8px; padding: 15px;}
        table { width: 100%; border-collapse: collapse; } th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid var(--light-gray); }
        .action-buttons { display: flex; gap: 10px; }
        .dynamic-item { border: 1px solid #444; padding: 15px; margin-bottom: 15px; border-radius: 5px; position: relative; background: #2a2a2a; }
        .dynamic-item .btn-danger { position: absolute; top: 10px; right: 10px; padding: 4px 8px; font-size: 0.8rem; }
        
        .tmdb-fetcher { display: flex; gap: 10px; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 15px; padding: 10px 0; } .checkbox-group label { display: flex; align-items: center; gap: 8px; font-weight: normal; cursor: pointer;}
        .checkbox-group input { width: auto; }
        .link-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; align-items: end;}
        .ep-qual-row { display: grid; grid-template-columns: 100px 1fr 1fr; gap: 10px; align-items: center; margin-bottom: 5px; background: #333; padding: 10px; border-radius:5px;}
        
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 2000; display: none; justify-content: center; align-items: center; padding: 20px; }
        .modal-content { background: var(--dark-gray); padding: 30px; border-radius: 8px; width: 100%; max-width: 900px; max-height: 90vh; display: flex; flex-direction: column; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-shrink: 0; }
        .modal-body { overflow-y: auto; }
        .modal-close { background: none; border: none; color: #fff; font-size: 2rem; cursor: pointer; }
        
        #search-results { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }
        .result-item { cursor: pointer; text-align: center; display: flex; flex-direction: column; }
        .result-item .img-wrapper { position: relative; width: 100%; padding-top: 150%; margin-bottom: 8px; }
        .result-item .img-wrapper img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; border-radius: 5px; border: 2px solid transparent; transition: all 0.2s; }
        .result-item:hover .img-wrapper img { transform: scale(1.05); border-color: var(--netflix-red); }
        .result-item p { font-size: 0.9rem; flex-grow: 1; margin: 0; }
        
        .manage-content-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; }
        .search-form { display: flex; gap: 10px; flex-grow: 1; max-width: 500px; }
        .search-form input { flex-grow: 1; }
        
        .dashboard-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: var(--dark-gray); padding: 20px; border-radius: 8px; text-align: center; border-left: 5px solid var(--netflix-red); }
        .stat-card p { font-size: 2.5rem; font-weight: 700; margin: 0; color: var(--netflix-red); }

        .pagination-admin { display: flex; justify-content: center; gap: 10px; margin-top: 20px; }
        .pagination-admin a, .pagination-admin span { padding: 8px 15px; border-radius: 4px; background: #333; color: white; text-decoration: none; }
        .pagination-admin .current { background: var(--netflix-red); }

        .admin-movie-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-bottom: 20px;}
        @media (min-width: 768px) { .admin-movie-grid { grid-template-columns: repeat(4, 1fr); } }
        @media (min-width: 1024px) { .admin-movie-grid { grid-template-columns: repeat(5, 1fr); } }
        .admin-movie-card { background: #1a1a1a; border-radius: 8px; overflow: hidden; border: 1px solid var(--light-gray); display: flex; flex-direction: column; position: relative; height: 100%;}
        .admin-card-img-wrapper { position: relative; width: 100%; padding-top: 150%; flex-shrink: 0;}
        .admin-card-img-wrapper img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover; }
        .admin-card-checkbox { position: absolute; top: 10px; left: 10px; width: 22px; height: 22px; z-index: 10; cursor: pointer; box-shadow: 0 0 5px rgba(0,0,0,0.8);}
        .copy-badge { position: absolute; top: 10px; right: 10px; background: yellow; color: black; font-size: 0.75rem; padding: 3px 6px; border-radius: 4px; font-weight: bold; z-index: 10;}
        .type-badge { position: absolute; bottom: 10px; right: 10px; background: var(--netflix-red); color: white; font-size: 0.75rem; padding: 3px 6px; border-radius: 4px; font-weight: bold; z-index: 10; text-transform: uppercase;}
        .admin-card-info { padding: 12px; display: flex; flex-direction: column; flex-grow: 1; justify-content: space-between; gap: 10px;}
        .admin-card-title { font-weight: bold; font-size: 0.95rem; line-height: 1.2; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: #fff;}
        .admin-card-meta { font-size: 0.85rem; color: #bbb; }
        .admin-movie-card .action-buttons { display: flex; gap: 8px; }
        .admin-movie-card .action-buttons .btn { flex: 1; text-align: center; padding: 6px; font-size: 0.85rem; }
        
        .live-fetch-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 20px; max-height: 300px; overflow-y: auto; background: #111; padding: 10px; border-radius: 8px; border: 1px solid #333;}
        @media(max-width: 768px) { .live-fetch-grid { grid-template-columns: repeat(2, 1fr); } }
        .live-item { background: #222; text-align: center; border-radius: 5px; overflow: hidden; padding-bottom: 5px; }
        .live-item img { width: 100%; aspect-ratio: 2/3; object-fit: cover; }
        .live-item p { font-size: 0.75rem; margin: 5px 0 0; padding: 0 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #00E599;}
        .loading-spinner { display: inline-block; width: 20px; height: 20px; border: 3px solid rgba(255,255,255,.3); border-radius: 50%; border-top-color: #fff; animation: spin 1s ease-in-out infinite; margin-left: 10px;}
        @keyframes spin { to { transform: rotate(360deg); } }
        
        @media (max-width: 991px) { .close-sidebar-btn { display: inline-block; } }
        @media (min-width: 992px) {
            .sidebar { transform: translateX(0); position: relative; }
            .menu-toggle { display: none; }
        }
    </style>
</head>
<body>

<div class="sidebar" id="sidebar">
    <div class="sidebar-header">
        Admin Panel
        <button class="close-sidebar-btn" onclick="toggleSidebar()">&times;</button>
    </div>
    <ul class="sidebar-menu">
        <li class="tab-btn active" onclick="showSection('sec-dashboard', this)"><i class="fas fa-tachometer-alt"></i> Dashboard</li>
        <li class="tab-btn" onclick="showSection('sec-add', this)"><i class="fas fa-plus-circle"></i> Add Content</li>
        <li class="tab-btn" onclick="showSection('sec-upcoming-fetch', this)"><i class="fas fa-magic"></i> Auto Fetch Upcoming</li>
        <li class="tab-btn" onclick="showSection('sec-manage', this)"><i class="fas fa-tasks"></i> Manage Content</li>
        <li class="tab-btn" onclick="showSection('sec-requests', this)"><i class="fas fa-inbox"></i> Manage Requests</li>
        <li class="tab-btn" onclick="showSection('sec-categories', this)"><i class="fas fa-tags"></i> Categories</li>
        <li class="tab-btn" onclick="showSection('sec-languages', this)"><i class="fas fa-language"></i> Languages</li>
        <li class="tab-btn" onclick="showSection('sec-popup', this)"><i class="fas fa-bell"></i> Popup & Push Noti</li>
        <li class="tab-btn" onclick="showSection('sec-siteconfig', this)"><i class="fas fa-cogs"></i> Site & Blur Settings</li>
        <li class="tab-btn" onclick="showSection('sec-download-steps', this)"><i class="fas fa-list-ol"></i> Download Step Settings</li>
        <li class="tab-btn" onclick="showSection('sec-telegram-bot', this)"><i class="fab fa-telegram"></i> Telegram Auto Post</li>
        <li class="tab-btn" onclick="showSection('sec-settings', this)"><i class="fas fa-bullhorn"></i> Ad Settings</li>
        <li><a href="{{ url_for('admin_logout') }}"><i class="fas fa-sign-out-alt"></i> Logout</a></li>
    </ul>
</div>

<div class="main-content">
    <div class="top-navbar">
        <div>
            <button class="menu-toggle" onclick="toggleSidebar()"><i class="fas fa-ellipsis-v"></i></button>
            <span style="font-weight: bold; margin-left: 15px; font-size: 1.2rem;">{{ website_name }}</span>
        </div>
        <div class="top-nav-right">
            <a href="{{ url_for('home') }}" target="_blank"><i class="fas fa-external-link-alt"></i> View Site</a>
        </div>
    </div>
    
    <div class="content-area">
        
        <div id="sec-dashboard" class="admin-section active">
            <h2><i class="fas fa-tachometer-alt"></i> At a Glance</h2>
            <div class="dashboard-stats">
                <div class="stat-card"><h3>Total Content</h3><p>{{ stats.total_content }}</p></div>
                <div class="stat-card"><h3>Total Movies</h3><p>{{ stats.total_movies }}</p></div>
                <div class="stat-card"><h3>Total Series</h3><p>{{ stats.total_series }}</p></div>
                <div class="stat-card"><h3>Total Views</h3><p>{{ stats.total_views }}</p></div>
            </div>
        </div>

        <div id="sec-upcoming-fetch" class="admin-section">
            <h2><i class="fas fa-magic"></i> Live Bulk Fetch Content</h2>
            <fieldset>
                <legend>Fetch Country Wise Content Live</legend>
                <div class="form-group"><label>Select Year:</label><input type="number" id="live_fetch_year" value="2025" required></div>
                <div class="form-group">
                    <label>Select Country (Origin):</label>
                    <select id="live_fetch_country">
                        <option value="ALL">All Over The World (Global)</option>
                        <option value="BD">Bangladesh 🇧🇩</option>
                        <option value="IN">India 🇮🇳</option>
                        <option value="KR">South Korea 🇰🇷 (K-Drama)</option>
                        <option value="US">United States 🇺🇸 (Hollywood)</option>
                        <option value="CN">China 🇨🇳 (C-Drama)</option>
                        <option value="TH">Thailand 🇹🇭 (Thai-Drama)</option>
                        <option value="JP">Japan 🇯🇵 (Anime/J-Drama)</option>
                        <option value="TR">Turkey 🇹🇷 (Turkish-Drama)</option>
                        <option value="PK">Pakistan 🇵🇰</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Content Type:</label>
                    <select id="live_fetch_type">
                        <option value="movie">Movies</option>
                        <option value="series">Web Series</option>
                        <option value="drama">Dramas (TV Shows genre 18)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Number of Pages to Scan (1 page = 20 items):</label>
                    <input type="number" id="live_fetch_pages" value="5" min="1" max="100">
                </div>
                <button type="button" id="start_live_fetch_btn" class="btn btn-primary" onclick="startLiveBulkFetch()">
                    <i class="fas fa-cloud-download-alt"></i> Start Live Fetch
                </button>
                <span id="live_fetch_status" style="margin-left:15px; font-weight:bold; color:#E50914;"></span>
                <div class="live-fetch-grid" id="live_fetch_grid_container"></div>
            </fieldset>
        </div>
        
        <div id="sec-add" class="admin-section">
            <h2><i class="fas fa-plus-circle"></i> Add New Content</h2>
            <fieldset><legend>Search TMDB / IMDb</legend><div class="form-group"><div class="tmdb-fetcher"><input type="text" id="tmdb_search_query" placeholder="Name or IMDb ID (e.g. tt1234567)"><button type="button" id="tmdb_search_btn" class="btn btn-primary" onclick="searchTmdb()">Search</button></div></div></fieldset>
            <form method="post">
                <input type="hidden" name="form_action" value="add_content"><input type="hidden" name="tmdb_id" id="tmdb_id">
                <fieldset><legend>Core Details</legend>
                    <div class="form-group"><label>Title:</label><input type="text" name="title" id="title" required></div>
                    <div class="form-group"><label>Poster URL:</label><input type="url" name="poster" id="poster"></div>
                    <div class="form-group"><label>Backdrop URL:</label><input type="url" name="backdrop" id="backdrop"></div>
                    <div class="form-group"><label>Overview:</label><textarea name="overview" id="overview"></textarea></div>
                    <div class="form-group"><label>Release Date:</label><input type="date" name="release_date" id="release_date"></div>
                    <div class="form-group">
                        <label>Language:</label>
                        <select name="language" id="language">
                            <option value="">Select Language...</option>
                            {% for lang in predefined_languages %}<option value="{{ lang }}">{{ lang }}</option>{% endfor %}
                        </select>
                    </div>
                    <div class="form-group"><label>Genres (comma-separated):</label><input type="text" name="genres" id="genres"></div>
                    <div class="form-group">
                        <label>Is Copyright Content?</label>
                        <label style="font-weight:normal; display:flex; align-items:center; gap:5px;"><input type="checkbox" name="is_copyright" value="1" style="width:auto;"> Yes, mark as Copyright</label>
                    </div>
                    <div class="form-group"><label>Categories:</label><div class="checkbox-group">{% for cat in predefined_categories %}<label><input type="checkbox" name="categories" value="{{ cat }}"> {{ cat }}</label>{% endfor %}</div></div>
                    <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie">Movie</option><option value="series">Series</option></select></div>
                </fieldset>
                
                <div id="movie_fields">
                    <fieldset><legend>Movie Links</legend>
                        <div class="link-pair"><label>480p Watch Link:<input type="url" name="watch_link_480p"></label><label>480p DL Link:<input type="url" name="download_link_480p"></label></div>
                        <div class="link-pair"><label>720p Watch Link:<input type="url" name="watch_link_720p"></label><label>720p DL Link:<input type="url" name="download_link_720p"></label></div>
                        <div class="link-pair"><label>1080p Watch Link:<input type="url" name="watch_link_1080p"></label><label>1080p DL Link:<input type="url" name="download_link_1080p"></label></div>
                    </fieldset>
                </div>
                
                <div id="episode_fields" style="display: none;">
                    <fieldset><legend>Series Links</legend>
                        <label>Complete Season Packs:</label><div id="season_packs_container"></div><button type="button" onclick="addSeasonPackField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Season Pack</button><hr style="margin: 20px 0; border-color: #333;">
                        <label>Individual Episodes (Dooplay Style):</label>
                        <div id="episodes_container"></div><button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button>
                    </fieldset>
                </div>
                
                <fieldset><legend>Manual Download Buttons</legend><div id="manual_links_container"></div><button type="button" onclick="addManualLinkField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Manual Button</button></fieldset>
                
                <div class="form-group" style="background:#1a1a1a; padding:15px; border-left:4px solid #0088cc; border-radius:5px;">
                    <label style="color:#00E599; font-size:1.1rem; cursor:pointer; display:flex; align-items:center; gap:10px;">
                        <input type="checkbox" name="send_tg_post" value="1" checked style="width:20px; height:20px;"> Send Telegram Auto Post to Channel Now
                    </label>
                </div>
                
                <button type="submit" class="btn btn-primary" onclick="localStorage.setItem('activeAdminTab', 'sec-add')"><i class="fas fa-check"></i> Save Content</button>
            </form>
        </div>

        <div id="sec-manage" class="admin-section">
            <div class="manage-content-header">
                <h2><i class="fas fa-tasks"></i> Manage Content</h2>
                <form method="get" action="{{ url_for('admin') }}" class="search-form">
                    <input type="search" name="search" placeholder="Search by title..." value="{{ request.args.get('search', '') }}">
                    <button type="submit" class="btn btn-primary"><i class="fas fa-search"></i></button>
                    {% if request.args.get('search') %}<a href="{{ url_for('admin') }}" class="btn btn-secondary">Clear</a>{% endif %}
                </form>
            </div>
            
            <form method="post" id="bulk-action-form">
                <input type="hidden" name="form_action" value="bulk_delete">
                <button type="submit" class="btn btn-danger" style="margin-bottom: 15px;" onclick="return confirm('Are you sure you want to delete all selected items?')"><i class="fas fa-trash-alt"></i> Delete Selected</button>
                
                <div style="display:flex; align-items:center; gap:10px; margin-bottom:15px; background:var(--dark-gray); padding:10px; border-radius:5px;">
                    <input type="checkbox" id="select-all" title="Select All" style="width:20px; height:20px; cursor:pointer;">
                    <label for="select-all" style="margin:0; cursor:pointer; font-weight:bold;">Select All</label>
                </div>

                <div class="admin-movie-grid">
                {% for movie in content_list %}
                    <div class="admin-movie-card">
                        <div class="admin-card-img-wrapper">
                            <input type="checkbox" name="selected_ids" value="{{ movie._id }}" class="row-checkbox admin-card-checkbox">
                            <img src="{{ movie.poster or 'https://via.placeholder.com/400x600.png?text=No+Image' }}">
                            {% if movie.is_copyright %}<span class="copy-badge">Copy</span>{% endif %}
                            <span class="type-badge">{{ movie.type|title }}</span>
                        </div>
                        <div class="admin-card-info">
                            <div class="admin-card-title">{{ movie.title }}</div>
                            <div class="admin-card-meta"><i class="fas fa-eye"></i> {{ movie.views | default(0) }} Views</div>
                            <div class="action-buttons">
                                <a href="{{ url_for('edit_movie', movie_id=movie._id) }}" class="btn btn-edit btn-sm">Edit</a>
                                <a href="{{ url_for('delete_movie', movie_id=movie._id) }}" onclick="return confirm('Are you sure?')" class="btn btn-danger btn-sm">Delete</a>
                            </div>
                        </div>
                    </div>
                {% else %}
                    <p style="grid-column: 1 / -1; text-align: center; font-size:1.2rem;">No content found.</p>
                {% endfor %}
                </div>
                
                <button type="submit" class="btn btn-danger" style="margin-top: 15px;" onclick="return confirm('Are you sure you want to delete all selected items?')"><i class="fas fa-trash-alt"></i> Delete Selected</button>
            </form>
            
            {% if pagination and pagination.total_pages > 1 %}
            <div class="pagination-admin">
                {% if pagination.has_prev %}<a href="?page={{ pagination.prev_num }}&search={{ request.args.get('search','') }}">&laquo; Prev</a>{% endif %}
                {% for p in range(1, pagination.total_pages + 1) %}
                    {% if p == pagination.page %}
                        <span class="current">{{ p }}</span>
                    {% elif p > pagination.page - 3 and p < pagination.page + 3 %}
                        <a href="?page={{ p }}&search={{ request.args.get('search','') }}">{{ p }}</a>
                    {% endif %}
                {% endfor %}
                {% if pagination.has_next %}<a href="?page={{ pagination.next_num }}&search={{ request.args.get('search','') }}">Next &raquo;</a>{% endif %}
            </div>
            {% endif %}
        </div>

        <div id="sec-requests" class="admin-section">
            <h2><i class="fas fa-inbox"></i> Manage Requests</h2>
            <div class="table-container">
                <table>
                    <thead><tr><th>Content Name</th><th>Extra Info</th><th>Status</th><th>Actions</th></tr></thead>
                    <tbody>
                    {% for req in requests_list %}
                    <tr>
                        <td>{{ req.name }}</td><td style="white-space: pre-wrap; min-width: 200px;">{{ req.info }}</td><td><span class="status-badge status-{{ req.status|lower }}">{{ req.status }}</span></td>
                        <td class="action-buttons">
                            <a href="{{ url_for('update_request_status', req_id=req._id, status='Fulfilled') }}" class="btn btn-success" style="padding: 5px 10px;">Fulfilled</a>
                            <a href="{{ url_for('update_request_status', req_id=req._id, status='Rejected') }}" class="btn btn-secondary" style="padding: 5px 10px;">Rejected</a>
                            <a href="{{ url_for('delete_request', req_id=req._id) }}" class="btn btn-danger" style="padding: 5px 10px;" onclick="return confirm('Are you sure?')">Delete</a>
                        </td>
                    </tr>
                    {% else %}<tr><td colspan="4" style="text-align:center;">No pending requests.</td></tr>{% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <div id="sec-categories" class="admin-section">
            <h2><i class="fas fa-tags"></i> Category Management</h2>
            <div style="display:flex; flex-wrap:wrap; gap:30px; align-items:flex-start;">
                <form method="post" style="flex: 1; min-width: 300px;">
                    <input type="hidden" name="form_action" value="add_category">
                    <fieldset><legend>Add New Category</legend>
                        <div class="form-group"><label>Category Name:</label><input type="text" name="category_name" required></div>
                        <button type="submit" class="btn btn-primary"><i class="fas fa-plus"></i> Add Category</button>
                    </fieldset>
                </form>
                
                <div style="flex: 1; min-width: 350px;">
                    <form method="post" id="bulk-cat-form">
                        <input type="hidden" name="form_action" value="bulk_delete_categories">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                            <h3 style="margin:0;">Existing Categories</h3>
                            <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm('Delete selected categories?')">Delete Selected</button>
                        </div>
                        <table class="table-container" style="width:100%;">
                            <thead>
                                <tr>
                                    <th style="width: 40px;"><input type="checkbox" id="select-all-cats"></th>
                                    <th>Category Name</th>
                                    <th style="text-align:right;">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for cat in predefined_categories %}
                                <tr>
                                    <td><input type="checkbox" name="selected_cats" value="{{ cat }}" class="cat-checkbox"></td>
                                    <td>{{ cat }}</td>
                                    <td style="text-align:right;">
                                        <button type="button" class="btn btn-edit btn-sm" onclick="editCategory('{{ cat }}')">Edit</button>
                                        <a href="{{ url_for('delete_category', cat_name=cat) }}" class="btn btn-danger btn-sm" onclick="return confirm('Delete this category?')">Del</a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </form>
                </div>
            </div>
        </div>
        
        <div id="sec-languages" class="admin-section">
            <h2><i class="fas fa-language"></i> Language Management</h2>
            <div style="display:flex; flex-wrap:wrap; gap:30px; align-items:flex-start;">
                <form method="post" style="flex: 1; min-width: 300px;">
                    <input type="hidden" name="form_action" value="add_language">
                    <fieldset><legend>Add New Language</legend>
                        <div class="form-group"><label>Language Name:</label><input type="text" name="language_name" required></div>
                        <button type="submit" class="btn btn-primary"><i class="fas fa-plus"></i> Add Language</button>
                    </fieldset>
                </form>
                
                <div style="flex: 1; min-width: 350px;">
                    <form method="post" id="bulk-lang-form">
                        <input type="hidden" name="form_action" value="bulk_delete_languages">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                            <h3 style="margin:0;">Existing Languages</h3>
                            <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm('Delete selected languages?')">Delete Selected</button>
                        </div>
                        <table class="table-container" style="width:100%;">
                            <thead>
                                <tr>
                                    <th style="width: 40px;"><input type="checkbox" id="select-all-langs"></th>
                                    <th>Language Name</th>
                                    <th style="text-align:right;">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for lang in predefined_languages %}
                                <tr>
                                    <td><input type="checkbox" name="selected_langs" value="{{ lang }}" class="lang-checkbox"></td>
                                    <td>{{ lang }}</td>
                                    <td style="text-align:right;">
                                        <button type="button" class="btn btn-edit btn-sm" onclick="editLanguage('{{ lang }}')">Edit</button>
                                        <a href="{{ url_for('delete_language', lang_name=lang) }}" class="btn btn-danger btn-sm" onclick="return confirm('Delete this language?')">Del</a>
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </form>
                </div>
            </div>
        </div>

        <div id="sec-popup" class="admin-section">
            <h2><i class="fas fa-bell"></i> Popup & Push Notifications</h2>
            <form method="post">
                <input type="hidden" name="form_action" value="update_popup_noti_config">
                
                <fieldset><legend>Auto Push Notifications</legend>
                    <div class="form-group">
                        <label><input type="checkbox" name="noti_enabled" value="1" style="width:auto;" {% if noti_settings.enabled %}checked{% endif %}> Enable Web Push Notifications</label>
                    </div>
                    <div class="form-group">
                        <label>Notification Delay Cycle (Minutes):</label>
                        <input type="number" name="noti_delay_minutes" value="{{ noti_settings.delay_minutes | default(60) }}" min="1">
                    </div>
                </fieldset>

                <fieldset><legend>Site Popup Notice</legend>
                    <div class="form-group">
                        <label><input type="checkbox" name="popup_enabled" value="1" style="width:auto;" {% if popup_settings.enabled %}checked{% endif %}> Enable Popup Notice on Website</label>
                    </div>
                    <div class="form-group"><label>Popup Title:</label><input type="text" name="popup_title" value="{{ popup_settings.title | default('') }}"></div>
                    <div class="form-group"><label>Popup Message:</label><textarea name="popup_message" rows="4">{{ popup_settings.message | default('') }}</textarea></div>
                    <div class="form-group"><label>Telegram Link For Popup (Optional):</label><input type="url" name="popup_tg_url" value="{{ popup_settings.tg_url | default('') }}"></div>
                    <div class="form-group"><label>Auto Hide Timer (seconds):</label><input type="number" name="popup_auto_hide" value="{{ popup_settings.auto_hide | default(0) }}" min="0"></div>
                </fieldset>
                <button type="submit" class="btn btn-primary" onclick="localStorage.setItem('activeAdminTab', 'sec-popup')"><i class="fas fa-save"></i> Save All Settings</button>
            </form>
        </div>

        <div id="sec-siteconfig" class="admin-section">
            <h2><i class="fas fa-cogs"></i> Site & Blur Settings</h2>
            <form method="post">
                <input type="hidden" name="form_action" value="update_site_config">
                
                <fieldset><legend>Global Telegram Links (Floating Buttons)</legend>
                    <div class="form-group"><label>Telegram Channel Link:</label><input type="url" name="tg_channel_url" value="{{ site_config.tg_channel_url }}"></div>
                    <div class="form-group"><label>Telegram Group Link:</label><input type="url" name="tg_group_url" value="{{ site_config.tg_group_url }}"></div>
                </fieldset>
                
                <fieldset><legend>Site Details & Blur</legend>
                    <div class="form-group"><label>Site Name:</label><input type="text" name="site_name" value="{{ site_config.site_name }}"></div>
                    <div class="form-group"><label>Logo URL (Leave blank for text logo):</label><input type="url" name="logo_url" value="{{ site_config.logo_url }}"></div>
                    <div class="form-group"><label>Auto Blur Timer (Minutes):</label><input type="number" name="auto_blur_timer" value="{{ site_config.auto_blur_timer | default(1) }}" min="0">
                    <small style="color:#00E599;">পোস্টার আনব্লাং করার কত মিনিট পর অটোমেটিক আবার ব্লাং হয়ে যাবে (০ দিলে অটো ব্লাং বন্ধ থাকবে)।</small></div>
                </fieldset>
                
                <fieldset><legend>DMCA & Privacy</legend>
                    <div class="form-group"><label>DMCA Text:</label><textarea name="dmca_text" rows="4">{{ site_config.dmca_text }}</textarea></div>
                    <div class="form-group"><label>Privacy Text:</label><textarea name="privacy_text" rows="4">{{ site_config.privacy_text }}</textarea></div>
                </fieldset>
                
                <fieldset><legend>Theme Colors</legend>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:15px;">
                        <div class="form-group"><label>Primary Color:</label><input type="color" name="c_primary" value="{{ site_config.c_primary }}" style="height:40px; padding:0;"></div>
                        <div class="form-group"><label>Background (Dark):</label><input type="color" name="c_bg_dark" value="{{ site_config.c_bg_dark }}" style="height:40px; padding:0;"></div>
                        <div class="form-group"><label>Card Background (Dark):</label><input type="color" name="c_card_dark" value="{{ site_config.c_card_dark }}" style="height:40px; padding:0;"></div>
                        <div class="form-group"><label>Text Color (Dark):</label><input type="color" name="c_text_dark" value="{{ site_config.c_text_dark }}" style="height:40px; padding:0;"></div>
                        <div class="form-group"><label>Background (Light):</label><input type="color" name="c_bg_light" value="{{ site_config.c_bg_light }}" style="height:40px; padding:0;"></div>
                        <div class="form-group"><label>Card Background (Light):</label><input type="color" name="c_card_light" value="{{ site_config.c_card_light }}" style="height:40px; padding:0;"></div>
                        <div class="form-group"><label>Text Color (Light):</label><input type="color" name="c_text_light" value="{{ site_config.c_text_light }}" style="height:40px; padding:0;"></div>
                    </div>
                </fieldset>
                <button type="submit" class="btn btn-primary" onclick="localStorage.setItem('activeAdminTab', 'sec-siteconfig')">Save Configuration</button>
            </form>
        </div>

        <div id="sec-download-steps" class="admin-section">
            <h2><i class="fas fa-list-ol"></i> Download Steps & Timer Settings</h2>
            <form method="post">
                <input type="hidden" name="form_action" value="update_download_steps">
                <fieldset>
                    <legend>Manage Steps & Seconds</legend>
                    <p style="color:#aaa; font-size:0.9rem;">এখান থেকে আপনি ডাউনলোড পেজের অ্যাড স্টেপ বাড়াতে বা কমাতে পারবেন এবং প্রতি স্টেপের জন্য আলাদা আলাদা সেকেন্ড সেট করতে পারবেন।</p>
                    
                    <div id="download_steps_container">
                        {% for step in get_download_steps_config() %}
                        <div class="dynamic-item">
                            <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">Delete</button>
                            <div class="form-group">
                                <label>Step Number / ID:</label>
                                <input type="number" name="step_id[]" value="{{ step.step_id }}" readonly style="background:#111;">
                            </div>
                            <div class="form-group">
                                <label>Step Seconds:</label>
                                <input type="number" name="step_seconds[]" value="{{ step.seconds }}" min="0" required>
                            </div>
                            <div class="form-group">
                                <label>Step Ad HTML Code:</label>
                                <textarea name="step_html[]" rows="3">{{ step.html }}</textarea>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                    <button type="button" class="btn btn-secondary" onclick="addDownloadStepField()"><i class="fas fa-plus"></i> Add New Download Step</button>
                </fieldset>
                <button type="submit" class="btn btn-primary" onclick="localStorage.setItem('activeAdminTab', 'sec-download-steps')"><i class="fas fa-save"></i> Save Step Settings</button>
            </form>
        </div>
        
        <div id="sec-telegram-bot" class="admin-section">
            <h2><i class="fab fa-telegram"></i> Telegram Auto Post</h2>
            <form method="post">
                <input type="hidden" name="form_action" value="update_telegram_bot">
                <fieldset><legend>Telegram Webhook & Post Settings</legend>
                    <div class="form-group">
                        <label>Telegram Bot Token:</label>
                        <input type="text" name="bot_token" value="{{ tg_bot_config.bot_token | default('') }}" placeholder="1234567890:ABCdefGhIjkLmNoPqRsTuVwXyZ" required>
                    </div>
                    <div class="form-group">
                        <label>Telegram Channel ID:</label>
                        <input type="text" name="channel_id" value="{{ tg_bot_config.channel_id | default('') }}" placeholder="-1001234567890" required>
                    </div>
                    <div class="form-group">
                        <label>Your Website URL:</label>
                        <input type="url" name="site_url" value="{{ tg_bot_config.site_url | default('') }}" placeholder="https://yourwebsite.com" required>
                    </div>
                    <hr>
                    <div class="form-group">
                        <label>Auto Post Old Movies Every (Minutes):</label>
                        <input type="number" name="auto_post_interval" value="{{ tg_bot_config.auto_post_interval | default(0) }}" min="0">
                    </div>
                    <div class="form-group">
                        <label>Auto Delete Posts After (Minutes):</label>
                        <input type="number" name="auto_delete_interval" value="{{ tg_bot_config.auto_delete_interval | default(0) }}" min="0">
                    </div>
                </fieldset>
                <button type="submit" class="btn btn-primary" onclick="localStorage.setItem('activeAdminTab', 'sec-telegram-bot')"><i class="fas fa-save"></i> Save Telegram Settings</button>
            </form>
        </div>
        
        <div id="sec-settings" class="admin-section">
            <h2><i class="fas fa-bullhorn"></i> Advertisement & Settings</h2>
            <form method="post">
                <input type="hidden" name="form_action" value="update_ads">
                
                <fieldset><legend>Anywhere Click Ads (Unlimited Popunder)</legend>
                    <div id="popunder_links_container">
                        {% if ad_settings.popunder_links %}
                            {% for link in ad_settings.popunder_links %}
                            <div class="dynamic-item link-pair">
                                <input type="url" name="popunder_links[]" value="{{ link }}" required placeholder="https://your-ad-network.com/..." style="width:100%;">
                                <button type="button" class="btn btn-danger" onclick="this.parentElement.remove()" style="position:static; padding:12px;">Delete</button>
                            </div>
                            {% endfor %}
                        {% endif %}
                    </div>
                    <button type="button" class="btn btn-secondary" onclick="addPopunderLink()"><i class="fas fa-plus"></i> Add Ad Link</button>
                </fieldset>
                
                <fieldset><legend>HTML Ad Codes (Banners/Popunders)</legend>
                    <div class="form-group"><label>Header Script:</label><textarea name="ad_header">{{ ad_settings.ad_header or '' }}</textarea></div>
                    <div class="form-group"><label>Body Top Script:</label><textarea name="ad_body_top">{{ ad_settings.ad_body_top or '' }}</textarea></div>
                    <div class="form-group"><label>Footer Script:</label><textarea name="ad_footer">{{ ad_settings.ad_footer or '' }}</textarea></div>
                    <div class="form-group"><label>Homepage Ad:</label><textarea name="ad_list_page">{{ ad_settings.ad_list_page or '' }}</textarea></div>
                    <div class="form-group"><label>Details Page Ad:</label><textarea name="ad_detail_page">{{ ad_settings.ad_detail_page or '' }}</textarea></div>
                </fieldset>
                <button type="submit" class="btn btn-primary" onclick="localStorage.setItem('activeAdminTab', 'sec-settings')"><i class="fas fa-save"></i> Save Settings</button>
            </form>
        </div>
    </div>
</div>

<form id="edit-cat-form" method="post" style="display:none;">
    <input type="hidden" name="form_action" value="edit_category">
    <input type="hidden" name="old_name" id="edit-cat-old">
    <input type="hidden" name="new_name" id="edit-cat-new">
</form>
<form id="edit-lang-form" method="post" style="display:none;">
    <input type="hidden" name="form_action" value="edit_language">
    <input type="hidden" name="old_name" id="edit-lang-old">
    <input type="hidden" name="new_name" id="edit-lang-new">
</form>

<div class="modal-overlay" id="search-modal"><div class="modal-content"><div class="modal-header"><h2>Select Content</h2><button class="modal-close" onclick="closeModal()">&times;</button></div><div class="modal-body" id="search-results"></div></div></div>

<script>
    function toggleSidebar() { document.getElementById('sidebar').classList.toggle('active'); }
    
    document.addEventListener('click', function(event) {
        const sidebar = document.getElementById('sidebar');
        const toggleBtn = document.querySelector('.menu-toggle');
        if (window.innerWidth < 992 && sidebar.classList.contains('active')) {
            if (!sidebar.contains(event.target) && !toggleBtn.contains(event.target)) {
                sidebar.classList.remove('active');
            }
        }
    });

    function showSection(sectionId, element) {
        document.querySelectorAll('.admin-section').forEach(el => el.classList.remove('active'));
        document.getElementById(sectionId).classList.add('active');
        document.querySelectorAll('.sidebar-menu li').forEach(el => el.classList.remove('active'));
        if(element) element.classList.add('active');
        else {
            for(let tab of document.querySelectorAll('.sidebar-menu .tab-btn')) {
                if(tab.getAttribute('onclick').includes(sectionId)) { tab.classList.add('active'); break; }
            }
        }
        localStorage.setItem('activeAdminTab', sectionId);
    }

    document.addEventListener("DOMContentLoaded", function() {
        let activeTab = localStorage.getItem('activeAdminTab') || 'sec-dashboard';
        if (window.location.search.includes('page=') || window.location.search.includes('search=')) { activeTab = 'sec-manage'; }
        showSection(activeTab, null);
        toggleFields();
        
        document.getElementById('select-all')?.addEventListener('change', e => document.querySelectorAll('.row-checkbox').forEach(c => c.checked = e.target.checked));
        document.getElementById('select-all-cats')?.addEventListener('change', e => document.querySelectorAll('.cat-checkbox').forEach(c => c.checked = e.target.checked));
        document.getElementById('select-all-langs')?.addEventListener('change', e => document.querySelectorAll('.lang-checkbox').forEach(c => c.checked = e.target.checked));
    });

    function toggleFields() { const isSeries = document.getElementById('content_type').value === 'series'; document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; }
    
    function addEpisodeField() { 
        const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; 
        d.innerHTML = `
            <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button>
            <div style="display:flex; gap:10px; margin-bottom:10px;">
                <div class="form-group" style="flex:1;"><label>Season:</label><input type="number" name="episode_season[]" value="1" required></div>
                <div class="form-group" style="flex:1;"><label>Episode:</label><input type="number" name="episode_number[]" required></div>
                <div class="form-group" style="flex:2;"><label>Title (Opt):</label><input type="text" name="episode_title[]"></div>
            </div>
            <div class="ep-qual-row"><strong>480p</strong><input type="url" name="ep_480_w[]" placeholder="Watch Link"><input type="url" name="ep_480_d[]" placeholder="Download Link"></div>
            <div class="ep-qual-row"><strong>720p</strong><input type="url" name="ep_720_w[]" placeholder="Watch Link"><input type="url" name="ep_720_d[]" placeholder="Download Link"></div>
            <div class="ep-qual-row"><strong>1080p</strong><input type="url" name="ep_1080_w[]" placeholder="Watch Link"><input type="url" name="ep_1080_d[]" placeholder="Download Link"></div>
        `; 
        c.appendChild(d); 
    }
    
    function addDownloadStepField() {
        const c = document.getElementById('download_steps_container');
        const count = c.querySelectorAll('.dynamic-item').length + 1;
        const d = document.createElement('div');
        d.className = 'dynamic-item';
        d.innerHTML = `
            <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">Delete</button>
            <div class="form-group">
                <label>Step Number / ID:</label>
                <input type="number" name="step_id[]" value="${count}" readonly style="background:#111;">
            </div>
            <div class="form-group">
                <label>Step Seconds:</label>
                <input type="number" name="step_seconds[]" value="5" min="0" required>
            </div>
            <div class="form-group">
                <label>Step Ad HTML Code:</label>
                <textarea name="step_html[]" rows="3"></textarea>
            </div>
        `;
        c.appendChild(d);
    }
    
    function addSeasonPackField() { const container = document.getElementById('season_packs_container'); const newItem = document.createElement('div'); newItem.className = 'dynamic-item'; newItem.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="ep-qual-row"><div class="form-group"><label>Season No.</label><input type="number" name="season_pack_number[]" value="1" required></div><div class="form-group"><label>Watch Link</label><input type="url" name="season_pack_watch_link[]"></div><div class="form-group"><label>Download Link</label><input type="url" name="season_pack_download_link[]"></div></div>`; container.appendChild(newItem); }
    function addManualLinkField() { const container = document.getElementById('manual_links_container'); const newItem = document.createElement('div'); newItem.className = 'dynamic-item'; newItem.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="link-pair"><div class="form-group"><label>Button Name</label><input type="text" name="manual_link_name[]" placeholder="e.g., 480p G-Drive" required></div><div class="form-group"><label>Link URL</label><input type="url" name="manual_link_url[]" required></div></div>`; container.appendChild(newItem); }
    
    function addPopunderLink() {
        const c = document.getElementById('popunder_links_container');
        const d = document.createElement('div');
        d.className = 'dynamic-item link-pair';
        d.innerHTML = `<input type="url" name="popunder_links[]" placeholder="https://your-ad-network.com/..." required style="width:100%;"><button type="button" class="btn btn-danger" onclick="this.parentElement.remove()" style="position:static; padding:12px;">Delete</button>`;
        c.appendChild(d);
    }

    function editCategory(oldName) {
        let newName = prompt("Enter new category name:", oldName);
        if (newName && newName.trim() !== "" && newName !== oldName) {
            document.getElementById('edit-cat-old').value = oldName;
            document.getElementById('edit-cat-new').value = newName.trim();
            document.getElementById('edit-cat-form').submit();
        }
    }
    function editLanguage(oldName) {
        let newName = prompt("Enter new language name:", oldName);
        if (newName && newName.trim() !== "" && newName !== oldName) {
            document.getElementById('edit-lang-old').value = oldName;
            document.getElementById('edit-lang-new').value = newName.trim();
            document.getElementById('edit-lang-form').submit();
        }
    }

    function openModal() { document.getElementById('search-modal').style.display = 'flex'; }
    function closeModal() { document.getElementById('search-modal').style.display = 'none'; }
    
    async function searchTmdb() { 
        const query = document.getElementById('tmdb_search_query').value.trim(); 
        if (!query) return; 
        const searchBtn = document.getElementById('tmdb_search_btn'); 
        searchBtn.disabled = true; searchBtn.innerHTML = 'Searching...'; openModal(); 
        try { 
            const response = await fetch('/admin/api/search?query=' + encodeURIComponent(query)); 
            const results = await response.json(); 
            const container = document.getElementById('search-results'); container.innerHTML = ''; 
            if(results.length > 0) { 
                results.forEach(item => { 
                    const resultDiv = document.createElement('div'); resultDiv.className = 'result-item'; 
                    resultDiv.onclick = () => selectResult(item.id, item.media_type); 
                    resultDiv.innerHTML = `<div class="img-wrapper"><img src="${item.poster}" alt="${item.title}"></div><p><strong>${item.title}</strong><br>(${item.year})</p>`; 
                    container.appendChild(resultDiv); 
                }); 
            } else { container.innerHTML = '<p style="grid-column:1/-1;">No results found.</p>'; } 
        } catch (e) { console.error(e); } finally { searchBtn.disabled = false; searchBtn.innerHTML = 'Search'; } 
    }
    
    async function selectResult(tmdbId, mediaType) { 
        closeModal(); 
        try { 
            const response = await fetch(`/admin/api/details?id=${tmdbId}&type=${mediaType}`); 
            const data = await response.json(); 
            document.getElementById('tmdb_id').value = data.tmdb_id || ''; 
            document.getElementById('title').value = data.title || ''; 
            document.getElementById('overview').value = data.overview || ''; 
            document.getElementById('poster').value = data.poster || ''; 
            document.getElementById('backdrop').value = data.backdrop || ''; 
            document.getElementById('genres').value = data.genres ? data.genres.join(', ') : ''; 
            document.getElementById('release_date').value = data.release_date || ''; 
            document.getElementById('content_type').value = data.type === 'series' ? 'series' : 'movie'; 
            toggleFields(); 
        } catch (e) { console.error(e); } 
    }

    let isFetching = false;
    async function startLiveBulkFetch() {
        if(isFetching) return;
        
        const year = document.getElementById('live_fetch_year').value;
        const country = document.getElementById('live_fetch_country').value;
        const type = document.getElementById('live_fetch_type').value;
        const totalPages = parseInt(document.getElementById('live_fetch_pages').value) || 1;
        
        const btn = document.getElementById('start_live_fetch_btn');
        const statusText = document.getElementById('live_fetch_status');
        const grid = document.getElementById('live_fetch_grid_container');
        
        isFetching = true;
        btn.disabled = true;
        btn.innerHTML = '<span class="loading-spinner"></span> Fetching...';
        grid.innerHTML = '';
        
        let currentPage = 1;
        let addedCount = 0;
        
        while(currentPage <= totalPages) {
            statusText.innerText = `Scanning Page ${currentPage} of ${totalPages}...`;
            
            try {
                let fd = new FormData();
                fd.append('year', year);
                fd.append('country', country);
                fd.append('c_type', type);
                fd.append('page', currentPage);
                
                const res = await fetch('/admin/api/bulk_fetch_page', { method: 'POST', body: fd });
                const data = await res.json();
                
                if(data.items && data.items.length > 0) {
                    data.items.forEach(item => {
                        addedCount++;
                        let itemDiv = document.createElement('div');
                        itemDiv.className = 'live-item';
                        itemDiv.innerHTML = `
                            <img src="${item.poster}" alt="Poster">
                            <p>${item.title} (${item.year})</p>
                        `;
                        grid.insertBefore(itemDiv, grid.firstChild);
                    });
                }
                
                if(data.stop) break;
                
            } catch(err) {
                console.error(err);
                break;
            }
            
            currentPage++;
            await new Promise(r => setTimeout(r, 500)); 
        }
        
        isFetching = false;
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-cloud-download-alt"></i> Start Live Fetch';
        statusText.innerText = `Done! Successfully added ${addedCount} new items to the database.`;
        statusText.style.color = '#00E599';
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
        .dynamic-item { border: 1px solid #444; padding: 15px; margin-bottom: 15px; border-radius: 5px; position: relative; background: #2a2a2a; }
        .dynamic-item .btn-danger { position: absolute; top: 10px; right: 10px; padding: 4px 8px; font-size: 0.8rem; }
        .checkbox-group { display: flex; flex-wrap: wrap; gap: 15px; } .checkbox-group label { display: flex; align-items: center; gap: 5px; font-weight: normal; }
        .checkbox-group input { width: auto; }
        .link-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
        .ep-qual-row { display: grid; grid-template-columns: 100px 1fr 1fr; gap: 10px; align-items: center; margin-bottom: 5px; background: #333; padding: 10px; border-radius:5px;}
    </style>
</head>
<body>
<div class="admin-container">
  <a href="{{ url_for('admin') }}" class="back-link" onclick="localStorage.setItem('activeAdminTab', 'sec-manage')"><i class="fas fa-arrow-left"></i> Back to Admin Panel</a>
  <h2>Edit: {{ movie.title }}</h2>
  <form method="post">
    <fieldset><legend>Core Details</legend>
        <div class="form-group"><label>Title:</label><input type="text" name="title" value="{{ movie.title }}" required></div>
        <div class="form-group"><label>Poster URL:</label><input type="url" name="poster" value="{{ movie.poster or '' }}"></div>
        <div class="form-group"><label>Backdrop URL:</label><input type="url" name="backdrop" value="{{ movie.backdrop or '' }}"></div>
        <div class="form-group"><label>Overview:</label><textarea name="overview">{{ movie.overview or '' }}</textarea></div>
        <div class="form-group"><label>Release Date:</label><input type="date" name="release_date" id="release_date" value="{{ movie.release_date or '' }}"></div>
        <div class="form-group">
            <label>Language:</label>
            <select name="language" id="language">
                <option value="">Select Language...</option>
                {% for lang in predefined_languages %}<option value="{{ lang }}" {% if movie.language == lang %}selected{% endif %}>{{ lang }}</option>{% endfor %}
            </select>
        </div>
        <div class="form-group"><label>Genres:</label><input type="text" name="genres" value="{{ movie.genres|join(', ') if movie.genres else '' }}"></div>
        <div class="form-group">
            <label>Is Copyright Content?</label>
            <label style="font-weight:normal; display:flex; align-items:center; gap:5px;"><input type="checkbox" name="is_copyright" value="1" style="width:auto;" {% if movie.is_copyright %}checked{% endif %}> Yes, mark as Copyright</label>
        </div>
        <div class="form-group"><label>Categories:</label><div class="checkbox-group">{% for cat in predefined_categories %}<label><input type="checkbox" name="categories" value="{{ cat }}" {% if movie.categories and cat in movie.categories %}checked{% endif %}> {{ cat }}</label>{% endfor %}</div></div>
        <div class="form-group"><label>Content Type:</label><select name="content_type" id="content_type" onchange="toggleFields()"><option value="movie" {% if movie.type == 'movie' %}selected{% endif %}>Movie</option><option value="series" {% if movie.type == 'series' %}selected{% endif %}>Series</option></select></div>
    </fieldset>
    
    <div id="movie_fields">
        <fieldset><legend>Movie Links</legend>
            {% set links_480p = movie.links|selectattr('quality', 'equalto', '480p')|first if movie.links else None %}
            {% set links_720p = movie.links|selectattr('quality', 'equalto', '720p')|first if movie.links else None %}
            {% set links_1080p = movie.links|selectattr('quality', 'equalto', '1080p')|first if movie.links else None %}
            <div class="link-pair"><label>480p Watch Link:<input type="url" name="watch_link_480p" value="{{ links_480p.watch_url if links_480p else '' }}"></label><label>480p Download Link:<input type="url" name="download_link_480p" value="{{ links_480p.download_url if links_480p else '' }}"></label></div>
            <div class="link-pair"><label>720p Watch Link:<input type="url" name="watch_link_720p" value="{{ links_720p.watch_url if links_720p else '' }}"></label><label>720p Download Link:<input type="url" name="download_link_720p" value="{{ links_720p.download_url if links_720p else '' }}"></label></div>
            <div class="link-pair"><label>1080p Watch Link:<input type="url" name="watch_link_1080p" value="{{ links_1080p.watch_url if links_1080p else '' }}"></label><label>1080p Download Link:<input type="url" name="download_link_1080p" value="{{ links_1080p.download_url if links_1080p else '' }}"></label></div>
        </fieldset>
    </div>
    
    <div id="episode_fields" style="display: none;">
      <fieldset><legend>Series Links</legend>
        <label>Complete Season Packs:</label><div id="season_packs_container">
        {% if movie.type == 'series' and movie.season_packs %}{% for pack in movie.season_packs|sort(attribute='season_number') %}<div class="dynamic-item"><button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="ep-qual-row"><div class="form-group"><label>Season No.</label><input type="number" name="season_pack_number[]" value="{{ pack.season_number }}" required></div><div class="form-group"><label>Watch Link</label><input type="url" name="season_pack_watch_link[]" value="{{ pack.watch_link or '' }}"></div><div class="form-group"><label>Download Link</label><input type="url" name="season_pack_download_link[]" value="{{ pack.download_link or '' }}"></div></div></div>{% endfor %}{% endif %}
        </div><button type="button" onclick="addSeasonPackField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Season</button><hr style="margin: 20px 0;"><label>Individual Episodes:</label>
        
        <div id="episodes_container">
        {% if movie.type == 'series' and movie.episodes %}{% for ep in movie.episodes|sort(attribute='episode_number')|sort(attribute='season') %}
        <div class="dynamic-item">
            <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button>
            <div style="display:flex; gap:10px; margin-bottom:10px;">
                <div class="form-group" style="flex:1;"><label>Season:</label><input type="number" name="episode_season[]" value="{{ ep.season or 1 }}" required></div>
                <div class="form-group" style="flex:1;"><label>Episode:</label><input type="number" name="episode_number[]" value="{{ ep.episode_number }}" required></div>
                <div class="form-group" style="flex:2;"><label>Title:</label><input type="text" name="episode_title[]" value="{{ ep.title or '' }}"></div>
            </div>
            {% set l = ep.links if ep.links else {} %}
            <div class="ep-qual-row"><strong>480p</strong><input type="url" name="ep_480_w[]" value="{{ l.get('480p',{}).get('watch','') if l else (ep.watch_link if ep.watch_link else '') }}" placeholder="Watch Link"><input type="url" name="ep_480_d[]" value="{{ l.get('480p',{}).get('download','') if l else '' }}" placeholder="Download Link"></div>
            <div class="ep-qual-row"><strong>720p</strong><input type="url" name="ep_720_w[]" value="{{ l.get('720p',{}).get('watch','') if l else '' }}" placeholder="Watch Link"><input type="url" name="ep_720_d[]" value="{{ l.get('720p',{}).get('download','') if l else '' }}" placeholder="Download Link"></div>
            <div class="ep-qual-row"><strong>1080p</strong><input type="url" name="ep_1080_w[]" value="{{ l.get('1080p',{}).get('watch','') if l else '' }}" placeholder="Watch Link"><input type="url" name="ep_1080_d[]" value="{{ l.get('1080p',{}).get('download','') if l else '' }}" placeholder="Download Link"></div>
        </div>
        {% endfor %}{% endif %}
        </div><button type="button" onclick="addEpisodeField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Episode</button></fieldset>
    </div>
    
    <fieldset><legend>Manual Download Buttons</legend><div id="manual_links_container">
        {% if movie.manual_links %}{% for link in movie.manual_links %}<div class="dynamic-item"><button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="link-pair"><div class="form-group"><label>Button Name</label><input type="text" name="manual_link_name[]" value="{{ link.name }}" required></div><div class="form-group"><label>Link URL</label><input type="url" name="manual_link_url[]" value="{{ link.url }}" required></div></div></div>{% endfor %}{% endif %}
    </div><button type="button" onclick="addManualLinkField()" class="btn btn-secondary"><i class="fas fa-plus"></i> Add Manual Button</button></fieldset>
    
    <div class="form-group" style="background:#1a1a1a; padding:15px; border-left:4px solid #0088cc; border-radius:5px;">
        <label style="color:#00E599; font-size:1.1rem; cursor:pointer; display:flex; align-items:center; gap:10px;">
            <input type="checkbox" name="send_tg_post" value="1" style="width:20px; height:20px;"> Send Telegram Auto Post to Channel (Update)
        </label>
    </div>
                
    <button type="submit" class="btn btn-primary" onclick="localStorage.setItem('activeAdminTab', 'sec-manage')"><i class="fas fa-save"></i> Update Content</button>
  </form>
</div>
<script>
    function toggleFields() { var isSeries = document.getElementById('content_type').value === 'series'; document.getElementById('episode_fields').style.display = isSeries ? 'block' : 'none'; document.getElementById('movie_fields').style.display = isSeries ? 'none' : 'block'; }
    function addEpisodeField() { 
        const c = document.getElementById('episodes_container'); const d = document.createElement('div'); d.className = 'dynamic-item'; 
        d.innerHTML = `
            <button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button>
            <div style="display:flex; gap:10px; margin-bottom:10px;">
                <div class="form-group" style="flex:1;"><label>Season:</label><input type="number" name="episode_season[]" value="1" required></div>
                <div class="form-group" style="flex:1;"><label>Episode:</label><input type="number" name="episode_number[]" required></div>
                <div class="form-group" style="flex:2;"><label>Title (Opt):</label><input type="text" name="episode_title[]"></div>
            </div>
            <div class="ep-qual-row"><strong>480p</strong><input type="url" name="ep_480_w[]" placeholder="Watch Link"><input type="url" name="ep_480_d[]" placeholder="Download Link"></div>
            <div class="ep-qual-row"><strong>720p</strong><input type="url" name="ep_720_w[]" placeholder="Watch Link"><input type="url" name="ep_720_d[]" placeholder="Download Link"></div>
            <div class="ep-qual-row"><strong>1080p</strong><input type="url" name="ep_1080_w[]" placeholder="Watch Link"><input type="url" name="ep_1080_d[]" placeholder="Download Link"></div>
        `; 
        c.appendChild(d); 
    }
    function addSeasonPackField() { const container = document.getElementById('season_packs_container'); const newItem = document.createElement('div'); newItem.className = 'dynamic-item'; newItem.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="ep-qual-row"><div class="form-group"><label>Season No.</label><input type="number" name="season_pack_number[]" value="1" required></div><div class="form-group"><label>Watch Link</label><input type="url" name="season_pack_watch_link[]"></div><div class="form-group"><label>Download Link</label><input type="url" name="season_pack_download_link[]"></div></div>`; container.appendChild(newItem); }
    function addManualLinkField() { const container = document.getElementById('manual_links_container'); const newItem = document.createElement('div'); newItem.className = 'dynamic-item'; newItem.innerHTML = `<button type="button" onclick="this.parentElement.remove()" class="btn btn-danger">X</button><div class="link-pair"><div class="form-group"><label>Button Name</label><input type="text" name="manual_link_name[]" placeholder="e.g., 480p G-Drive" required></div><div class="form-group"><label>Link URL</label><input type="url" name="manual_link_url[]" required></div></div>`; container.appendChild(newItem); }
    document.addEventListener('DOMContentLoaded', toggleFields);
</script>
</body></html>
"""

class Pagination:
    def __init__(self, page, per_page, total_count):
        self.page = page
        self.per_page = per_page
        self.total_count = total_count
    @property
    def total_pages(self): return max(1, math.ceil(self.total_count / self.per_page))
    @property
    def has_prev(self): return self.page > 1
    @property
    def has_next(self): return self.page < self.total_pages
    @property
    def prev_num(self): return self.page - 1
    @property
    def next_num(self): return self.page + 1

@app.before_request
def check_upcoming_movies():
    try:
        check_and_release_upcoming()
    except:
        pass

@app.route('/manifest.json')
def manifest():
    site_config = settings.find_one({"_id": "site_config"}) or {}
    manifest_data = {
        "name": site_config.get("site_name", WEBSITE_NAME),
        "short_name": site_config.get("site_name", WEBSITE_NAME),
        "start_url": "/",
        "display": "standalone",
        "background_color": site_config.get("c_bg_dark", "#000000"),
        "theme_color": site_config.get("c_primary", "#E50914"),
        "icons": [{
            "src": site_config.get("logo_url", "https://img.icons8.com/fluency/192/cinema-.png"),
            "sizes": "192x192",
            "type": "image/png"
        }]
    }
    return jsonify(manifest_data)

@app.route('/api/notifications')
def api_notifications():
    noti_settings = settings.find_one({"_id": "noti_config"}) or {}
    if not noti_settings.get("enabled"): return jsonify({"enabled": False})
    
    latest_release_id = noti_settings.get("latest_release_id")
    if latest_release_id:
        release_time = noti_settings.get("latest_release_time", 0)
        return jsonify({
            "enabled": True,
            "cycle_number": int(release_time),
            "movie": {
                "id": latest_release_id,
                "title": noti_settings.get("latest_release_title", "New Movie Released!"),
                "poster": noti_settings.get("latest_release_poster", PLACEHOLDER_POSTER),
                "type": "movie"
            }
        })
    
    delay = noti_settings.get("delay_minutes", 60)
    if delay <= 0: delay = 60

    current_minutes = int(datetime.utcnow().timestamp() // 60)
    cycle_number = current_minutes // delay
    
    total_movies = movies.count_documents({})
    if total_movies == 0: return jsonify({"enabled": False})
        
    movie_index = cycle_number % total_movies
    m = list(movies.find().skip(movie_index).limit(1))[0]
    
    return jsonify({
        "enabled": True,
        "delay_minutes": delay,
        "cycle_number": cycle_number,
        "movie": {
            "id": str(m["_id"]),
            "title": m["title"],
            "poster": m["poster"],
            "type": m["type"]
        }
    })

@app.route('/sw.js')
def service_worker():
    sw_code = """
    self.addEventListener('install', (e) => { self.skipWaiting(); });
    self.addEventListener('activate', (e) => { e.waitUntil(clients.claim()); });
    self.addEventListener('fetch', (e) => { });
    self.addEventListener('notificationclick', function(event) {
        event.notification.close();
        if (event.notification.data && event.notification.data.url) {
            event.waitUntil(clients.openWindow(event.notification.data.url));
        }
    });
    """
    return Response(sw_code, mimetype='application/javascript')

@app.route('/')
def home():
    query = request.args.get('q', '').strip()
    if query:
        movies_list = list(movies.find({"title": {"$regex": query, "$options": "i"}}).sort([("release_date", -1), ("_id", -1)]))
        return render_template_string(index_html, movies=movies_list, query=f'Results for "{query}"', is_full_page_list=True)
    
    slider_content = list(movies.find({}).sort([("release_date", -1), ("_id", -1)]).limit(10))
    home_categories = [cat['name'] for cat in categories_collection.find().sort("name", 1)]
    categorized_content = {cat: list(movies.find({"categories": cat}).sort([("release_date", -1), ("_id", -1)]).limit(10)) for cat in home_categories}
    latest_content = list(movies.find().sort([("release_date", -1), ("_id", -1)]).limit(10))
    
    top_movies = list(movies.find({"type": "movie"}).sort("views", -1).limit(10))
    top_series = list(movies.find({"type": "series"}).sort("views", -1).limit(10))

    context = {
        "slider_content": slider_content, 
        "latest_content": latest_content, 
        "categorized_content": categorized_content, 
        "top_movies": top_movies,
        "top_series": top_series,
        "is_full_page_list": False
    }
    return render_template_string(index_html, **context)

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    try:
        movies.update_one({"_id": ObjectId(movie_id)}, {"$inc": {"views": 1}})
        movie = movies.find_one({"_id": ObjectId(movie_id)})
        if not movie: return "Content not found", 404
        return render_template_string(detail_html, movie=movie)
    except: return "Content not found", 404

def get_paginated_content(query_filter, page, limit=ITEMS_PER_PAGE):
    skip = (page - 1) * limit
    total_count = movies.count_documents(query_filter)
    content_list = list(movies.find(query_filter).sort([("release_date", -1), ("_id", -1)]).skip(skip).limit(limit))
    pagination = Pagination(page, limit, total_count)
    return content_list, pagination

@app.route('/movies')
def all_movies():
    page = request.args.get('page', 1, type=int)
    all_movie_content, pagination = get_paginated_content({"type": "movie"}, page)
    return render_template_string(index_html, movies=all_movie_content, query="All Movies", is_full_page_list=True, pagination=pagination)

@app.route('/series')
def all_series():
    page = request.args.get('page', 1, type=int)
    all_series_content, pagination = get_paginated_content({"type": "series"}, page)
    return render_template_string(index_html, movies=all_series_content, query="All Series", is_full_page_list=True, pagination=pagination)

@app.route('/upcoming')
def upcoming_movies():
    page = request.args.get('page', 1, type=int)
    skip = (page - 1) * ITEMS_PER_PAGE
    query_filter = {"is_upcoming": True}
    total_count = movies.count_documents(query_filter)
    upcoming_list = list(movies.find(query_filter).sort([("release_date", 1), ("_id", -1)]).skip(skip).limit(ITEMS_PER_PAGE))
    pagination = Pagination(page, ITEMS_PER_PAGE, total_count)
    return render_template_string(index_html, movies=upcoming_list, query="Upcoming Movies", is_full_page_list=True, pagination=pagination)

@app.route('/category')
def movies_by_category():
    title = request.args.get('name')
    if not title: return redirect(url_for('home'))
    page = request.args.get('page', 1, type=int)
    query_filter = {} if title == "Latest" else {"categories": title}
    content_list, pagination = get_paginated_content(query_filter, page)
    query_title = "Latest Content" if title == "Latest" else title
    return render_template_string(index_html, movies=content_list, query=query_title, is_full_page_list=True, pagination=pagination)

@app.route('/request', methods=['GET', 'POST'])
def request_content():
    if request.method == 'POST':
        content_name = request.form.get('content_name', '').strip()
        extra_info = request.form.get('extra_info', '').strip()
        if content_name:
            requests_collection.insert_one({"name": content_name, "info": extra_info, "status": "Pending", "created_at": datetime.utcnow()})
        return redirect(url_for('request_content'))
    return render_template_string(request_html)

@app.route('/dmca-privacy')
def dmca_page():
    return render_template_string(dmca_html)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if check_auth(request.form.get('username'), request.form.get('password')):
            session['admin_logged_in'] = True
            return redirect(url_for('admin'))
        else: return render_template_string(admin_login_html, error="Invalid Username or Password!")
    return render_template_string(admin_login_html)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('home'))

@app.route('/admin', methods=["GET", "POST"])
@requires_auth
def admin():
    if request.method == "POST":
        form_action = request.form.get("form_action")
        
        if form_action == "update_ads":
            popunder_links_raw = request.form.getlist("popunder_links[]")
            ad_settings_data = {
                "popunder_links": [l.strip() for l in popunder_links_raw if l.strip()],
                "ad_header": request.form.get("ad_header"), 
                "ad_body_top": request.form.get("ad_body_top"), 
                "ad_footer": request.form.get("ad_footer"), 
                "ad_list_page": request.form.get("ad_list_page"), 
                "ad_detail_page": request.form.get("ad_detail_page")
            }
            settings.update_one({"_id": "ad_config"}, {"$set": ad_settings_data}, upsert=True)
            
        elif form_action == "update_site_config":
            auto_blur_min = request.form.get("auto_blur_timer", 1, type=int)
            site_config_data = {
                "tg_channel_url": request.form.get("tg_channel_url"),
                "tg_group_url": request.form.get("tg_group_url"),
                "site_name": request.form.get("site_name"),
                "logo_url": request.form.get("logo_url"),
                "auto_blur_timer": auto_blur_min,
                "dmca_text": request.form.get("dmca_text"),
                "privacy_text": request.form.get("privacy_text"),
                "c_primary": request.form.get("c_primary"),
                "c_bg_dark": request.form.get("c_bg_dark"),
                "c_card_dark": request.form.get("c_card_dark"),
                "c_text_dark": request.form.get("c_text_dark"),
                "c_bg_light": request.form.get("c_bg_light"),
                "c_card_light": request.form.get("c_card_light"),
                "c_text_light": request.form.get("c_text_light")
            }
            settings.update_one({"_id": "site_config"}, {"$set": site_config_data}, upsert=True)
            settings.update_one({"_id": "poster_blur_config"}, {"$set": {"enabled": True, "seconds": auto_blur_min * 60}}, upsert=True)
            
        elif form_action == "update_download_steps":
            step_ids = request.form.getlist("step_id[]")
            step_seconds = request.form.getlist("step_seconds[]")
            step_htmls = request.form.getlist("step_html[]")
            
            new_steps = []
            for i in range(len(step_ids)):
                try:
                    s_id = int(step_ids[i])
                    sec = int(step_seconds[i])
                    html_code = step_htmls[i] if i < len(step_htmls) else ""
                    new_steps.append({"step_id": s_id, "seconds": sec, "html": html_code})
                except:
                    pass
            settings.update_one({"_id": "download_steps_config"}, {"$set": {"steps": new_steps}}, upsert=True)
            
        elif form_action == "update_popup_noti_config":
            popup_data = {
                "enabled": bool(request.form.get("popup_enabled")),
                "title": request.form.get("popup_title", "").strip(),
                "message": request.form.get("popup_message", "").strip(),
                "tg_url": request.form.get("popup_tg_url", "").strip(),
                "auto_hide": request.form.get("popup_auto_hide", 0, type=int)
            }
            settings.update_one({"_id": "popup_config"}, {"$set": popup_data}, upsert=True)

            noti_data = {
                "enabled": bool(request.form.get("noti_enabled")),
                "delay_minutes": request.form.get("noti_delay_minutes", 60, type=int)
            }
            settings.update_one({"_id": "noti_config"}, {"$set": noti_data}, upsert=True)
            
        elif form_action == "update_telegram_bot":
            tg_bot_data = {
                "bot_token": request.form.get("bot_token", "").strip(),
                "channel_id": request.form.get("channel_id", "").strip(),
                "site_url": request.form.get("site_url", "").strip(),
                "auto_post_interval": request.form.get("auto_post_interval", 0, type=int),
                "auto_delete_interval": request.form.get("auto_delete_interval", 0, type=int),
                "last_auto_post_time": 0,
                "last_auto_post_index": -1
            }
            settings.update_one({"_id": "telegram_bot_config"}, {"$set": tg_bot_data}, upsert=True)
            
        elif form_action == "add_category":
            category_name = request.form.get("category_name", "").strip()
            if category_name: categories_collection.update_one({"name": category_name}, {"$set": {"name": category_name}}, upsert=True)
            
        elif form_action == "edit_category":
            old_name = request.form.get("old_name", "").strip()
            new_name = request.form.get("new_name", "").strip()
            if old_name and new_name:
                categories_collection.update_one({"name": old_name}, {"$set": {"name": new_name}})
                movies.update_many({"categories": old_name}, {"$set": {"categories.$": new_name}})
                
        elif form_action == "bulk_delete_categories":
            cats_to_delete = request.form.getlist("selected_cats")
            if cats_to_delete: categories_collection.delete_many({"name": {"$in": cats_to_delete}})
        
        elif form_action == "add_language":
            language_name = request.form.get("language_name", "").strip()
            if language_name: languages_collection.update_one({"name": language_name}, {"$set": {"name": language_name}}, upsert=True)
            
        elif form_action == "edit_language":
            old_name = request.form.get("old_name", "").strip()
            new_name = request.form.get("new_name", "").strip()
            if old_name and new_name:
                languages_collection.update_one({"name": old_name}, {"$set": {"name": new_name}})
                movies.update_many({"language": old_name}, {"$set": {"language": new_name}})
                
        elif form_action == "bulk_delete_languages":
            langs_to_delete = request.form.getlist("selected_langs")
            if langs_to_delete: languages_collection.delete_many({"name": {"$in": langs_to_delete}})
            
        elif form_action == "bulk_delete":
            ids_to_delete = request.form.getlist("selected_ids")
            if ids_to_delete: movies.delete_many({"_id": {"$in": [ObjectId(id_str) for id_str in ids_to_delete]}})
            
        elif form_action == "add_content":
            content_type = request.form.get("content_type", "movie")
            is_copyright = bool(request.form.get("is_copyright"))
            release_date = request.form.get("release_date", "").strip()
            tmdb_id = request.form.get("tmdb_id", "").strip()
            
            is_upcoming = False
            if release_date:
                today_str = date.today().strftime("%Y-%m-%d")
                if release_date > today_str:
                    is_upcoming = True

            movie_data = { 
                "tmdb_id": tmdb_id,
                "title": request.form.get("title").strip(), 
                "type": content_type, 
                "poster": request.form.get("poster").strip() or PLACEHOLDER_POSTER, 
                "backdrop": request.form.get("backdrop").strip() or None, 
                "overview": request.form.get("overview").strip(), 
                "release_date": release_date,
                "language": request.form.get("language").strip() or None, 
                "genres": [g.strip() for g in request.form.get("genres", "").split(',') if g.strip()], 
                "categories": request.form.getlist("categories"), 
                "is_copyright": is_copyright,
                "is_upcoming": is_upcoming,
                "views": 0,
                "episodes": [], "links": [], "season_packs": [], "manual_links": [], "created_at": datetime.utcnow() 
            }
            if tmdb_id and not release_date:
                tmdb_details = get_tmdb_details(tmdb_id, "tv" if content_type == "series" else "movie")
                if tmdb_details:
                    movie_data.update({'release_date': tmdb_details.get('release_date')})
                    movie_data.update({'vote_average': tmdb_details.get('vote_average')})
            
            if content_type == "movie":
                movie_links = []
                for q in ["480p", "720p", "1080p"]:
                    w, d = request.form.get(f"watch_link_{q}"), request.form.get(f"download_link_{q}")
                    if w or d: movie_links.append({"quality": q, "watch_url": w, "download_url": d})
                movie_data["links"] = movie_links
            else:
                sp_nums, sp_w, sp_d = request.form.getlist('season_pack_number[]'), request.form.getlist('season_pack_watch_link[]'), request.form.getlist('season_pack_download_link[]')
                movie_data['season_packs'] = [{"season_number": int(sp_nums[i]), "watch_link": sp_w[i].strip() or None, "download_link": sp_d[i].strip() or None} for i in range(len(sp_nums)) if sp_nums[i]]
                
                s, n, t = request.form.getlist('episode_season[]'), request.form.getlist('episode_number[]'), request.form.getlist('episode_title[]')
                e_4w, e_4d = request.form.getlist('ep_480_w[]'), request.form.getlist('ep_480_d[]')
                e_7w, e_7d = request.form.getlist('ep_720_w[]'), request.form.getlist('ep_720_d[]')
                e_10w, e_10d = request.form.getlist('ep_1080_w[]'), request.form.getlist('ep_1080_d[]')
                
                for i in range(len(s)):
                    if s[i] and n[i]:
                        movie_data['episodes'].append({
                            "season": int(s[i]), "episode_number": int(n[i]), "title": t[i].strip() if i < len(t) else "",
                            "links": {
                                "480p": {"watch": e_4w[i].strip() if i < len(e_4w) else "", "download": e_4d[i].strip() if i < len(e_4d) else ""},
                                "720p": {"watch": e_7w[i].strip() if i < len(e_7w) else "", "download": e_7d[i].strip() if i < len(e_7d) else ""},
                                "1080p": {"watch": e_10w[i].strip() if i < len(e_10w) else "", "download": e_10d[i].strip() if i < len(e_10d) else ""}
                            }
                        })
                        
            names, urls = request.form.getlist('manual_link_name[]'), request.form.getlist('manual_link_url[]')
            movie_data["manual_links"] = [{"name": names[i].strip(), "url": urls[i].strip()} for i in range(len(names)) if names[i] and urls[i]]
            
            insert_result = movies.insert_one(movie_data)
            
            if request.form.get("send_tg_post") == "1":
                send_telegram_post(movie_data, str(insert_result.inserted_id))
                
        return redirect(url_for('admin'))
    
    search_query = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    query_filter = {"title": {"$regex": search_query, "$options": "i"}} if search_query else {}
    
    content_list, pagination = get_paginated_content(query_filter, page, limit=ADMIN_ITEMS_PER_PAGE)
    
    total_views_pipeline = list(movies.aggregate([{"$group": {"_id": None, "total": {"$sum": "$views"}}}]))
    total_views_count = total_views_pipeline[0]["total"] if total_views_pipeline else 0

    stats = {
        "total_content": movies.count_documents({}),
        "total_movies": movies.count_documents({"type": "movie"}),
        "total_series": movies.count_documents({"type": "series"}),
        "total_views": total_views_count
    }
    
    requests_list = list(requests_collection.find().sort("created_at", -1))
    
    return render_template_string(admin_html, content_list=content_list, pagination=pagination, stats=stats, requests_list=requests_list)

@app.route('/delete_movie/<movie_id>')
@requires_auth
def delete_movie(movie_id):
    try:
        movies.delete_one({"_id": ObjectId(movie_id)})
    except:
        pass
    return redirect(url_for('admin'))

@app.route('/admin/category/delete/<cat_name>')
@requires_auth
def delete_category(cat_name):
    try: categories_collection.delete_one({"name": cat_name})
    except: pass
    return redirect(url_for('admin'))

@app.route('/admin/language/delete/<lang_name>')
@requires_auth
def delete_language(lang_name):
    try: languages_collection.delete_one({"name": lang_name})
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
        is_copyright = bool(request.form.get("is_copyright"))
        release_date = request.form.get("release_date", "").strip()
        
        is_upcoming = False
        if release_date:
            today_str = date.today().strftime("%Y-%m-%d")
            if release_date > today_str:
                is_upcoming = True
                
        update_data = { 
            "title": request.form.get("title").strip(), 
            "type": content_type, 
            "poster": request.form.get("poster").strip() or PLACEHOLDER_POSTER, 
            "backdrop": request.form.get("backdrop").strip() or None, 
            "overview": request.form.get("overview").strip(),
            "release_date": release_date,
            "language": request.form.get("language").strip() or None, 
            "genres": [g.strip() for g in request.form.get("genres").split(',') if g.strip()], 
            "categories": request.form.getlist("categories"),
            "is_copyright": is_copyright,
            "is_upcoming": is_upcoming
        }
        names, urls = request.form.getlist('manual_link_name[]'), request.form.getlist('manual_link_url[]')
        update_data["manual_links"] = [{"name": names[i].strip(), "url": urls[i].strip()} for i in range(len(names)) if names[i] and urls[i]]
        
        if content_type == "movie":
            movie_links = []
            for q in ["480p", "720p", "1080p"]:
                w, d = request.form.get(f"watch_link_{q}"), request.form.get(f"download_link_{q}")
                if w or d: movie_links.append({"quality": q, "watch_url": w, "download_url": d})
            update_data["links"] = movie_links
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"episodes": "", "season_packs": ""}})
        else:
            sp_nums, sp_w, sp_d = request.form.getlist('season_pack_number[]'), request.form.getlist('season_pack_watch_link[]'), request.form.getlist('season_pack_download_link[]')
            update_data['season_packs'] = [{"season_number": int(sp_nums[i]), "watch_link": sp_w[i].strip() or None, "download_link": sp_d[i].strip() or None} for i in range(len(sp_nums)) if sp_nums[i]]
            
            s, n, t = request.form.getlist('episode_season[]'), request.form.getlist('episode_number[]'), request.form.getlist('episode_title[]')
            e_4w, e_4d = request.form.getlist('ep_480_w[]'), request.form.getlist('ep_480_d[]')
            e_7w, e_7d = request.form.getlist('ep_720_w[]'), request.form.getlist('ep_720_d[]')
            e_10w, e_10d = request.form.getlist('ep_1080_w[]'), request.form.getlist('ep_1080_d[]')
            
            update_data["episodes"] = []
            for i in range(len(s)):
                if s[i] and n[i]:
                    update_data["episodes"].append({
                        "season": int(s[i]), "episode_number": int(n[i]), "title": t[i].strip() if i < len(t) else "",
                        "links": {
                            "480p": {"watch": e_4w[i].strip() if i < len(e_4w) else "", "download": e_4d[i].strip() if i < len(e_4d) else ""},
                            "720p": {"watch": e_7w[i].strip() if i < len(e_7w) else "", "download": e_7d[i].strip() if i < len(e_7d) else ""},
                            "1080p": {"watch": e_10w[i].strip() if i < len(e_10w) else "", "download": e_10d[i].strip() if i < len(e_10d) else ""}
                        }
                    })
            movies.update_one({"_id": obj_id}, {"$set": update_data, "$unset": {"links": ""}})
            
        if request.form.get("send_tg_post") == "1":
            updated_movie = movies.find_one({"_id": obj_id})
            send_telegram_post(updated_movie, str(obj_id))
            
        return redirect(url_for('admin') + '?search=' + quote(update_data["title"]))
    
    return render_template_string(edit_html, movie=movie_obj)

@app.route('/admin/api/search')
@requires_auth
def api_search_tmdb():
    query = request.args.get('query')
    if not query: return jsonify({"error": "Query is missing"}), 400
    try:
        if query.startswith("tt"):
            search_url = f"https://api.themoviedb.org/3/find/{query}?api_key={TMDB_API_KEY}&external_source=imdb_id"
            res = requests.get(search_url, timeout=10)
            data = res.json()
            results = []
            for media_type in ['movie_results', 'tv_results']:
                for item in data.get(media_type, []):
                    mt = 'movie' if media_type == 'movie_results' else 'tv'
                    results.append({"id": item.get('id'), "title": item.get('title') or item.get('name'), "year": (item.get('release_date') or item.get('first_air_date', 'N/A')).split('-')[0], "poster": f"https://image.tmdb.org/t/p/w200{item.get('poster_path')}", "media_type": mt})
            return jsonify(results)
        else:
            search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={quote(query)}"
            res = requests.get(search_url, timeout=10)
            data = res.json()
            results = []
            for item in data.get('results', []):
                if item.get('media_type') in ['movie', 'tv'] and item.get('poster_path'):
                    results.append({"id": item.get('id'),"title": item.get('title') or item.get('name'),"year": (item.get('release_date') or item.get('first_air_date', 'N/A')).split('-')[0],"poster": f"https://image.tmdb.org/t/p/w200{item.get('poster_path')}","media_type": item.get('media_type')})
            return jsonify(results)
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/admin/api/details')
@requires_auth
def api_get_details():
    tmdb_id, media_type = request.args.get('id'), request.args.get('type')
    details = get_tmdb_details(tmdb_id, media_type)
    return jsonify(details) if details else (jsonify({"error": "Details not found"}), 404)

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip()
    if not query: return jsonify([])
    try:
        results = list(movies.find({"title": {"$regex": query, "$options": "i"}}, {"_id": 1, "title": 1, "poster": 1}).limit(20))
        for item in results: item['_id'] = str(item['_id'])
        return jsonify(results)
    except: return jsonify({"error": "An error occurred"}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 3000)))
